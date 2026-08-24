"""
Extrait TOUS les points d'intérêt taggés amenity=* (n'importe quelle
valeur) d'OpenStreetMap sur une ville, avec l'ensemble de leurs tags, vers
un classeur Excel — usage exploratoire (voir quelle nature de données OSM
est disponible sur une ville donnée), contrairement à
extraire_equipements_osm.py qui cible des tags précis pour nourrir le
pipeline d'accessibilité.

Usage (zone = contour/disque autour de la ville géocodée, sortie par défaut
dans data/equipements_osm/) :
    python3 extraire_amenities_osm.py "Abidjan"

Usage (zone = même rectangle GTFS+marge que le notebook d'accessibilité) :
    python3 extraire_amenities_osm.py "Abidjan" \\
        --gtfs data/GTFS_Africa/Abidjan_AMUGA_GTFS_2025_mapping_v2.zip --marge-km 5

Même logique de zone que extraire_equipements_osm.py (contour administratif
OSM si disponible, sinon disque de secours de --rayon-km ; ou rectangle
GTFS+marge avec --gtfs) — cf. ce module pour le détail.
"""

import argparse
import json
import os

import pandas as pd

from extraire_equipements_osm import DECALAGE_AREA_ID, geocoder_zone
from src.osm_extract import session_avec_retries
from src.utils import charger_gtfs
from src.worldpop import zone_desservie_gtfs

OVERPASS_URL_DEFAUT = "https://overpass-api.de/api/interpreter"


def _construire_requete_amenities(timeout, area_id=None, cercle=None, bbox=None):
    """Même principe que _construire_requete_overpass dans
    extraire_equipements_osm.py, mais sans filtre de valeur : n'importe
    quel élément portant la clé "amenity" (peu importe sa valeur)."""
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

    return f'[out:json][timeout:{timeout}];\n{prefixe}(\n  nwr["amenity"]{filtre_zone};\n);\nout center tags;'


def _point_de(element):
    if element["type"] == "node":
        return element["lon"], element["lat"]
    centre = element["center"]
    return centre["lon"], centre["lat"]


def extraire_amenities_osm(
    ville,
    zone_geom=None,
    rayon_km_secours=15,
    overpass_url=OVERPASS_URL_DEFAUT,
    timeout=180,
):
    """
    Interroge Overpass pour tous les éléments amenity=* (n'importe quelle
    valeur) sur la zone de `ville` (ou zone_geom si fourni, cf.
    extraire_equipements_osm.extraire_equipements_osm), et renvoie un
    DataFrame [osm_type, osm_id, amenity, name, lat, lon, tous_les_tags]
    — un usage exploratoire, donc tous les tags d'origine sont conservés
    (colonne tous_les_tags, JSON) plutôt que réduits aux quelques champs
    utiles au pipeline d'accessibilité.
    """
    if zone_geom is not None:
        west, south, east, north = zone_geom.bounds
        print(f"✓ Zone fournie directement (rectangle, bounds : {zone_geom.bounds}) — pas de géocodage")
        requete = _construire_requete_amenities(timeout, bbox=(south, west, north, east))
    else:
        lat, lon, osm_type, osm_id = geocoder_zone(ville)
        print(f"✓ {ville!r} géocodée : {lat:.4f}, {lon:.4f} (osm_type={osm_type}, osm_id={osm_id})")

        if osm_type in DECALAGE_AREA_ID:
            area_id = DECALAGE_AREA_ID[osm_type] + osm_id
            requete = _construire_requete_amenities(timeout, area_id=area_id)
            print(f"✓ Contour administratif OSM trouvé, recherche restreinte à cette zone (area {area_id})")
        else:
            print(
                f"⚠ Pas de contour administratif pour {ville!r} (osm_type={osm_type}) : "
                f"repli sur un disque de {rayon_km_secours} km autour du point géocodé"
            )
            requete = _construire_requete_amenities(timeout, cercle=(lat, lon, rayon_km_secours * 1000))

    with session_avec_retries(methods=("GET", "POST"), total=5, backoff_factor=2) as session:
        headers = {"User-Agent": "GTFS-analysis-universal/1.0 (extraire_amenities_osm.py)"}
        reponse = session.post(overpass_url, data={"data": requete}, headers=headers, timeout=timeout + 30)
        reponse.raise_for_status()

    elements = reponse.json().get("elements", [])
    print(f"✓ {len(elements)} élément(s) amenity=* trouvé(s)")

    lignes = []
    for element in elements:
        lon_e, lat_e = _point_de(element)
        tags = element.get("tags", {})
        lignes.append({
            "osm_type": element["type"],
            "osm_id": element["id"],
            "amenity": tags.get("amenity"),
            "name": tags.get("name"),
            "lat": lat_e,
            "lon": lon_e,
            "tous_les_tags": json.dumps(tags, ensure_ascii=False),
        })

    return pd.DataFrame(lignes)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ville", help='Ville à interroger (ex: "Abidjan"), idéalement "Ville, Pays"')
    parser.add_argument("-o", "--output", default=None, help="Chemin du fichier Excel de sortie (défaut : data/equipements_osm/<Ville>_amenities.xlsx)")
    parser.add_argument("--gtfs", default=None, help="Chemin d'un GTFS (zip) : zone = son rectangle englobant les arrêts + --marge-km, au lieu de géocoder `ville`")
    parser.add_argument("--marge-km", type=float, default=5, help="Marge (km) ajoutée au rectangle GTFS si --gtfs est fourni (défaut : 5)")
    parser.add_argument("--rayon-km", type=float, default=15, help="Rayon (km) du disque de secours si --gtfs absent et aucun contour administratif trouvé (défaut : 15)")
    parser.add_argument("--overpass-url", default=OVERPASS_URL_DEFAUT)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    zone_geom = None
    if args.gtfs:
        feed = charger_gtfs(args.gtfs)
        zone_geom, _, _ = zone_desservie_gtfs(feed, marge_km=args.marge_km)

    df = extraire_amenities_osm(
        args.ville, zone_geom=zone_geom, rayon_km_secours=args.rayon_km,
        overpass_url=args.overpass_url, timeout=args.timeout,
    )

    if args.output:
        sortie = args.output
    else:
        dossier_defaut = os.path.join("data", "equipements_osm")
        os.makedirs(dossier_defaut, exist_ok=True)
        nom_ville = args.ville.split(",")[0].strip().replace(" ", "_")
        sortie = os.path.join(dossier_defaut, f"{nom_ville}_amenities.xlsx")

    resume = df["amenity"].value_counts().rename_axis("amenity").reset_index(name="nombre")

    with pd.ExcelWriter(sortie, engine="openpyxl") as writer:
        resume.to_excel(writer, sheet_name="resume_par_type", index=False)
        df.to_excel(writer, sheet_name="donnees", index=False)

    print(f"✓ {len(df)} amenity(s) exporté(s) : {sortie}")
    print(resume.to_string(index=False))


if __name__ == "__main__":
    main()
