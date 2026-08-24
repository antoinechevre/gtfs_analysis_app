"""
Extrait des équipements (points d'intérêt) OpenStreetMap sur une ville/zone
donnée, filtrés par un ou plusieurs tags OSM, vers un GeoPackage — substitut
possible à la Base Permanente des Équipements (BPE, INSEE, France
uniquement) pour un réseau hors de France (ex : Abidjan), en entrée des
mesures d'accessibilité de src/utilitaires_matrix.py (cost_to_closest,
gravity, cumulative_cutoff...).

Usage (zone = contour/disque autour de la ville géocodée) :
    python3 extraire_equipements_osm.py "Abidjan" amenity=hospital healthcare=hospital -o abidjan_hopitaux.gpkg

Usage (zone = même rectangle GTFS+marge que le notebook d'accessibilité,
cf. zone_desservie_gtfs dans src/worldpop.py — pour une couverture cohérente
avec la grille de population et le réseau routier utilisés par ailleurs) :
    python3 extraire_equipements_osm.py "Abidjan" amenity=hospital healthcare=hospital -o abidjan_hopitaux.gpkg \\
        --gtfs data/GTFS/Abidjan_AMUGA_GTFS_2025_mapping_v2.zip --marge-km 5

Plusieurs tags = union (OR) : un élément OSM matchant au moins un des tags
donnés est inclus (utile car un même type d'équipement est parfois taggé
différemment selon les contributeurs, ex: amenity=hospital vs
healthcare=hospital).

Sans --gtfs, la zone interrogée est, par ordre de préférence :
1. Le contour administratif OSM de `ville` (le résultat Nominatim est une
   relation/way avec limite), interrogé via `area()` Overpass — précis, pas
   de sur- ni sous-couverture.
2. À défaut (résultat Nominatim ponctuel, sans contour — le cas pour
   "Abidjan", dont le meilleur résultat Nominatim est un simple point), un
   disque géodésique de secours de `--rayon-km` autour du point géocodé
   (mêmes principes que src/worldpop.py : buffer_geodesique).
"""

import argparse
import json

import geopandas as gpd
import requests
from shapely.geometry import Point

from src.worldpop import NOMINATIM_SEARCH_URL, NOMINATIM_HEADERS, buffer_geodesique, zone_desservie_gtfs
from src.osm_extract import session_avec_retries
from src.utils import charger_gtfs

OVERPASS_URL_DEFAUT = "https://overpass-api.de/api/interpreter"

# Ajoutés à l'osm_id Nominatim pour former l'id de "area" Overpass :
# convention Overpass (cf. https://wiki.openstreetmap.org/wiki/Overpass_API/Areas).
DECALAGE_AREA_ID = {"relation": 3600000000, "way": 2400000000}


def geocoder_zone(ville):
    """
    Géocode `ville` via Nominatim (comme geocoder_ville dans src/worldpop.py,
    mais renvoie aussi osm_type/osm_id, nécessaires pour interroger Overpass
    sur le contour administratif exact plutôt qu'un simple point).

    Renvoie (lat, lon, osm_type, osm_id). Lève ValueError si introuvable.
    """
    r = requests.get(
        NOMINATIM_SEARCH_URL,
        params={"q": ville, "format": "json", "limit": 1},
        headers=NOMINATIM_HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    resultats = r.json()
    if not resultats:
        raise ValueError(f"Zone introuvable via Nominatim : {ville!r}")

    resultat = resultats[0]
    return (
        float(resultat["lat"]),
        float(resultat["lon"]),
        resultat.get("osm_type"),
        resultat.get("osm_id"),
    )


def parser_tag(chaine_tag):
    """Convertit "amenity=hospital" en ("amenity", "hospital"). Lève
    ValueError si le format ne contient pas de "="."""
    if "=" not in chaine_tag:
        raise ValueError(f"Tag invalide (attendu clé=valeur) : {chaine_tag!r}")
    cle, valeur = chaine_tag.split("=", 1)
    return cle.strip(), valeur.strip()


def _construire_requete_overpass(tags, timeout, area_id=None, cercle=None, bbox=None):
    """Construit la requête Overpass QL : union (OR) des filtres `tags`,
    restreinte à l'une des trois zones suivantes (une seule fournie) :
    - area_id : "area" Overpass (contour administratif) ;
    - cercle = (lat, lon, rayon_m) : disque géodésique de secours ;
    - bbox = (south, west, north, east) : rectangle exact (ex: zone_geom
      d'un zone_desservie_gtfs, déjà un rectangle — pas d'approximation)."""
    if area_id is not None:
        prefixe = f"area({area_id})->.zone;\n"
        filtre_zone = "(area.zone)"
    elif bbox is not None:
        south, west, north, east = bbox
        prefixe = ""
        filtre_zone = f"({south},{west},{north},{east})"
    else:
        lat, lon, rayon_m = cercle
        prefixe = ""
        filtre_zone = f"(around:{rayon_m},{lat},{lon})"

    clauses = "".join(f'  nwr["{cle}"="{valeur}"]{filtre_zone};\n' for cle, valeur in tags)
    return f"[out:json][timeout:{timeout}];\n{prefixe}(\n{clauses});\nout center tags;"


def _point_de(element):
    """Coordonnées (lon, lat) d'un élément Overpass : directement lat/lon
    pour un node, "center" (centroïde pré-calculé par Overpass via `out
    center`) pour un way/relation."""
    if element["type"] == "node":
        return element["lon"], element["lat"]
    centre = element["center"]
    return centre["lon"], centre["lat"]


def extraire_equipements_osm(
    ville,
    tags,
    zone_geom=None,
    rayon_km_secours=15,
    overpass_url=OVERPASS_URL_DEFAUT,
    timeout=180,
):
    """
    Interroge Overpass pour les équipements matchant `tags` (liste de
    (clé, valeur), union/OR), et renvoie un GeoDataFrame de points
    (EPSG:4326), colonnes : osm_type, osm_id, name (si taggé), tags_osm
    (dict complet des tags), geometry.

    zone_geom : géométrie (rectangle) définissant directement la zone de
    recherche (ex: zone_desservie_gtfs), sans passer par le géocodage de
    `ville` — pour une couverture cohérente avec un pipeline (population,
    routage) déjà construit sur cette zone. Si None (par défaut), la zone
    est déterminée en géocodant `ville` (cf. docstring du module).

    rayon_km_secours : rayon (km) du disque de secours utilisé seulement si
    zone_geom n'est pas fourni ET que Nominatim ne renvoie pas de contour
    administratif pour `ville` (résultat ponctuel, ex: un lieu-dit).
    """
    if zone_geom is not None:
        west, south, east, north = zone_geom.bounds
        print(f"✓ Zone fournie directement (rectangle, bounds : {zone_geom.bounds}) — pas de géocodage")
        requete = _construire_requete_overpass(tags, timeout, bbox=(south, west, north, east))
    else:
        lat, lon, osm_type, osm_id = geocoder_zone(ville)
        print(f"✓ {ville!r} géocodée : {lat:.4f}, {lon:.4f} (osm_type={osm_type}, osm_id={osm_id})")

        if osm_type in DECALAGE_AREA_ID:
            area_id = DECALAGE_AREA_ID[osm_type] + osm_id
            requete = _construire_requete_overpass(tags, timeout, area_id=area_id)
            print(f"✓ Contour administratif OSM trouvé, recherche restreinte à cette zone (area {area_id})")
        else:
            print(
                f"⚠ Pas de contour administratif pour {ville!r} (osm_type={osm_type}) : "
                f"repli sur un disque de {rayon_km_secours} km autour du point géocodé"
            )
            requete = _construire_requete_overpass(tags, timeout, cercle=(lat, lon, rayon_km_secours * 1000))

    with session_avec_retries(methods=("GET", "POST"), total=5, backoff_factor=2) as session:
        headers = {"User-Agent": "GTFS-analysis-universal/1.0 (extraire_equipements_osm.py)"}
        reponse = session.post(overpass_url, data={"data": requete}, headers=headers, timeout=timeout + 30)
        reponse.raise_for_status()

    elements = reponse.json().get("elements", [])

    lignes = []
    for element in elements:
        lon_e, lat_e = _point_de(element)
        tags_osm = element.get("tags", {})
        lignes.append({
            "osm_type": element["type"],
            "osm_id": element["id"],
            "name": tags_osm.get("name"),
            "tags_osm": json.dumps(tags_osm, ensure_ascii=False),
            "geometry": Point(lon_e, lat_e),
        })

    gdf = gpd.GeoDataFrame(lignes, geometry="geometry", crs="EPSG:4326")
    print(f"✓ {len(gdf)} équipement(s) trouvé(s) pour {['='.join(t) for t in tags]}")
    return gdf


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ville", help='Ville/zone à interroger (ex: "Abidjan"), idéalement "Ville, Pays" pour lever l\'ambiguïté du géocodage')
    parser.add_argument("tags", nargs="+", help="Filtres OSM clé=valeur (ex: amenity=hospital healthcare=hospital), combinés en union (OR)")
    parser.add_argument("-o", "--output", required=True, help="Chemin du GeoPackage de sortie")
    parser.add_argument("--gtfs", default=None, help="Chemin d'un GTFS (zip) : zone = son rectangle englobant les arrêts + --marge-km (cf. zone_desservie_gtfs), au lieu de géocoder `ville`")
    parser.add_argument("--marge-km", type=float, default=5, help="Marge (km) ajoutée au rectangle GTFS si --gtfs est fourni (défaut : 5, comme le notebook d'accessibilité)")
    parser.add_argument("--rayon-km", type=float, default=15, help="Rayon (km) du disque de secours si aucun contour administratif trouvé et --gtfs absent (défaut : 15)")
    parser.add_argument("--overpass-url", default=OVERPASS_URL_DEFAUT, help="Instance Overpass à utiliser")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout Overpass en secondes")
    args = parser.parse_args()

    tags = [parser_tag(t) for t in args.tags]

    zone_geom = None
    if args.gtfs:
        feed = charger_gtfs(args.gtfs)
        zone_geom, _, _ = zone_desservie_gtfs(feed, marge_km=args.marge_km)

    gdf = extraire_equipements_osm(
        args.ville,
        tags,
        zone_geom=zone_geom,
        rayon_km_secours=args.rayon_km,
        overpass_url=args.overpass_url,
        timeout=args.timeout,
    )

    if gdf.empty:
        print("⚠ Aucun équipement trouvé : fichier non écrit. Vérifiez les tags / le nom de zone.")
        return

    gdf.to_file(args.output, driver="GPKG")
    print(f"✓ Équipements exportés : {args.output}")


if __name__ == "__main__":
    main()
