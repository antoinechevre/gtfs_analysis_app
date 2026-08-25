"""
Extraction d'un extrait OSM (.osm.pbf) pour le réseau de routage r5py,
sur une zone géographique quelconque (pas de dépendance à un découpage
communal français) : deux méthodes d'acquisition des données brutes,
suivies dans les deux cas d'un découpage précis au contour de la zone
avec osmium.

- osm_pbf_creator_depuis_geometrie (API Overpass, tuile par tuile) : porté
  et adapté de build_data_agglo.osm_pbf_creator du projet sœur
  Accessibility_analysis (github.com/antoinechevre/Accessibility_analysis).
- osm_pbf_creator_depuis_geofabrik (extraits pays pré-construits Geofabrik) :
  alternative à utiliser quand Overpass est indisponible (l'API publique
  est parfois bloquée au niveau réseau local — filtrage FAI/box, plus
  fréquent que pour download.geofabrik.de, une infrastructure de
  téléchargement statique distincte) ; aussi plus simple/robuste dans
  l'absolu (un seul gros fichier par pays, pas de tuilage ni de risque de
  géométrie tronquée aux frontières de tuile, cf. _ways_avec_geometrie_cassee
  ci-dessous, qui ne concerne que la voie Overpass).

Requiert osmium-tool (macOS : `brew install osmium-tool`).
"""

import json
import pathlib
import shutil
import subprocess
import time
import warnings

import geopandas as gpd
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests


def session_avec_retries(methods=("GET",), total=5, backoff_factor=1):
    """Session HTTP tolérante aux lenteurs/coupures ponctuelles d'une API distante."""
    session = requests.Session()
    retries = Retry(
        total=total,
        backoff_factor=backoff_factor,  # 1s, 2s, 4s, 8s, 16s... entre les tentatives
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=list(methods),
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def _tuiles_bbox(min_lon, min_lat, max_lon, max_lat, taille_deg):
    """Découpe une bbox en tuiles carrées d'au plus `taille_deg` degrés de côté.

    Pour les grandes zones, interroger Overpass sur toute l'emprise en une
    seule requête dépasse vite les limites de taille/temps du service public.
    On découpe donc en tuiles plus petites, récupérées séparément puis
    fusionnées.
    """
    tuiles = []
    lat = min_lat
    while lat < max_lat:
        haut = min(lat + taille_deg, max_lat)
        lon = min_lon
        while lon < max_lon:
            droite = min(lon + taille_deg, max_lon)
            tuiles.append((lon, lat, droite, haut))
            lon = droite
        lat = haut
    return tuiles


def _telecharger_tuile_overpass(bbox, output_path, session, overpass_url, timeout, max_essais_tuile=3):
    """Télécharge les données OSM d'une tuile (bbox) via Overpass, au format XML."""
    min_lon, min_lat, max_lon, max_lat = bbox
    query = (
        f"[out:xml][timeout:{timeout}];"
        f"(node({min_lat},{min_lon},{max_lat},{max_lon});"
        f"way({min_lat},{min_lon},{max_lat},{max_lon});"
        f"relation({min_lat},{min_lon},{max_lat},{max_lon}););"
        # (._;>;) : récupère aussi tous les nœuds référencés par les ways/relations
        # ci-dessus, même hors de la bbox interrogée. Sans ça, un way qui ne fait que
        # longer/traverser le bord de la bbox (route, rivière...) est renvoyé avec sa
        # liste de nœuds, mais seuls les nœuds tombant dans la bbox sont eux-mêmes
        # présents dans la réponse — les autres sont des références "dans le vide".
        # osmium (merge/extract) ne valide pas cette cohérence et laisse passer un
        # .osm.pbf avec des ways à la géométrie trouée, mais r5py, plus strict,
        # échoue dessus ("Writer thread failed" / "Error occurred while parsing OSM
        # file").
        "(._;>;);"
        "out body;"  # tags + géométrie seulement (pas d'historique d'édition)
    )
    headers = {"User-Agent": "GTFS-analysis-universal/1.0 (src/osm_extract.py)"}

    # Retry manuel en plus de celui de `session` (session_avec_retries) : ce
    # dernier ne couvre que l'établissement de la connexion / les codes HTTP
    # de status_forcelist, pas un timeout de LECTURE survenant en cours de
    # flux une fois la réponse déjà entamée (ReadTimeoutError, observé sur une
    # grosse tuile dense — ex. zone GTFS+marge d'Abidjan, ~150x65km) : sans
    # cette boucle, une telle erreur remonte immédiatement sans nouvelle
    # tentative.
    derniere_erreur = None
    for essai in range(1, max_essais_tuile + 1):
        try:
            response = session.post(
                overpass_url, data={"data": query}, headers=headers, timeout=timeout + 30
            )
            response.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(response.content)
            return
        except requests.exceptions.RequestException as e:
            derniere_erreur = e
            if essai < max_essais_tuile:
                print(f"  ⚠ tuile {bbox} : {e} — nouvelle tentative ({essai}/{max_essais_tuile})")
                time.sleep(5 * essai)
    raise derniere_erreur


def _ways_avec_geometrie_cassee(pbf_path):
    """Vérifie l'intégrité référentielle du .osm.pbf produit par osmium
    extract : repère les ways taggés highway=* auxquels il ne reste, une
    fois les nœuds manquants exclus, plus qu'au maximum 1 nœud résolvable —
    donc plus aucune géométrie exploitable (une ligne a besoin d'au moins 2
    points). Ce genre de way à la géométrie dégénérée (troncature Overpass
    sur une tuile) est rejeté par le lecteur OSM de r5py avec "Writer
    thread failed" / "Error occurred while parsing OSM file".

    Retourne la liste des identifiants de way (str) concernés, vide si le
    fichier est utilisable tel quel.
    """
    verif = subprocess.run(
        ["osmium", "check-refs", "-i", str(pbf_path)],
        capture_output=True, text=True,
    )
    manquants_par_way = {}
    for ligne in verif.stdout.splitlines():
        if " in w" not in ligne:
            continue
        way_id = ligne.split(" in w", 1)[1].strip()
        manquants_par_way[way_id] = manquants_par_way.get(way_id, 0) + 1

    ways_casses = []
    for way_id, nb_manquants in manquants_par_way.items():
        opl = subprocess.run(
            ["osmium", "getid", str(pbf_path), f"w{way_id}", "-f", "opl"],
            capture_output=True, text=True,
        ).stdout.strip()
        if "highway=" not in opl or " N" not in opl:
            continue
        nb_total = len(opl.split(" N", 1)[1].strip().split(","))
        if nb_total - nb_manquants < 2:
            ways_casses.append(way_id)
    return ways_casses


def osm_pbf_creator_depuis_geometrie(
    zone_geom,
    output_dir,
    output_pbf_path=None,
    tile_size_deg=0.3,
    overpass_url="https://overpass-api.de/api/interpreter",
    timeout=180,
    pause=1.0,
    max_essais=3,
):
    """Construit un .osm.pbf couvrant zone_geom (n'importe quelle géométrie
    shapely en WGS84, ex : le rectangle de zone_desservie_gtfs) : les
    données OSM sont téléchargées directement sur son emprise via l'API
    Overpass, puis découpées précisément sur son contour réel avec osmium.
    Fonctionne pour n'importe quelle géographie dans le monde (pas de
    dépendance à un découpage administratif préexistant).

    Pour les grandes zones, l'emprise est découpée en tuiles d'au plus
    `tile_size_deg` degrés de côté (0.3° ≈ 30 km) afin de rester sous les
    limites de taille/temps de l'API Overpass publique ; les tuiles sont
    téléchargées une par une (avec retries automatiques et une pause de
    `pause` secondes entre chacune, pour ne pas surcharger le service
    public) puis fusionnées avant le découpage final.

    output_dir: dossier de travail (fichiers intermédiaires + .osm.pbf par défaut).
    output_pbf_path: chemin du .osm.pbf en sortie (par défaut : "agglo.osm.pbf"
        dans output_dir).
    max_essais: nombre de tentatives si l'extrait produit s'avère corrompu
        (cf. _ways_avec_geometrie_cassee) — chaque nouvel essai retélécharge
        avec des tuiles deux fois plus petites.

    Renvoie le chemin du .osm.pbf produit.
    """
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_pbf_path is None:
        output_pbf_path = output_dir / "agglo.osm.pbf"
    output_pbf_path = pathlib.Path(output_pbf_path)
    BOUNDARY_GEOJSON = output_dir / "agglo_boundary.geojson"

    if shutil.which("osmium") is None:
        raise SystemExit(
            "osmium-tool is required but not found. Install it with: brew install osmium-tool"
        )

    boundary = gpd.GeoDataFrame(geometry=[zone_geom], crs="EPSG:4326")
    boundary.to_file(BOUNDARY_GEOJSON, driver="GeoJSON")
    print(f"wrote {BOUNDARY_GEOJSON}, bounds: {boundary.total_bounds}")

    ways_casses = []
    for essai in range(1, max_essais + 1):
        min_lon, min_lat, max_lon, max_lat = boundary.total_bounds
        tuiles = _tuiles_bbox(min_lon, min_lat, max_lon, max_lat, tile_size_deg)
        print(
            f"emprise découpée en {len(tuiles)} tuile(s) de {tile_size_deg}° "
            f"pour Overpass (essai {essai}/{max_essais})"
        )

        fichiers_tuiles = []
        with session_avec_retries(methods=("GET", "POST"), total=8, backoff_factor=2) as session:
            for i, bbox in enumerate(tuiles, start=1):
                tuile_path = output_dir / f"agglo_tuile_{i}.osm"
                print(f"téléchargement tuile {i}/{len(tuiles)} (bbox {bbox}) ...")
                _telecharger_tuile_overpass(bbox, tuile_path, session, overpass_url, timeout)
                fichiers_tuiles.append(tuile_path)
                time.sleep(pause)

        if len(fichiers_tuiles) > 1:
            fusion_path = output_dir / "agglo_fusion.osm.pbf"
            subprocess.run(
                ["osmium", "merge", *fichiers_tuiles, "-o", fusion_path, "--overwrite"],
                check=True,
            )
            print(f"wrote {fusion_path} (fusion de {len(fichiers_tuiles)} tuiles)")
        else:
            fusion_path = fichiers_tuiles[0]

        subprocess.run(
            ["osmium", "extract", "-p", BOUNDARY_GEOJSON, "-o", output_pbf_path, "--overwrite", fusion_path],
            check=True,
        )
        print(f"wrote {output_pbf_path}")

        for f in fichiers_tuiles:
            pathlib.Path(f).unlink()
        if len(fichiers_tuiles) > 1:
            pathlib.Path(fusion_path).unlink()

        ways_casses = _ways_avec_geometrie_cassee(output_pbf_path)
        if not ways_casses:
            break
        print(
            f"⚠ extrait OSM avec {len(ways_casses)} way(s) routier(s) à la géométrie "
            f"dégénérée (id : {', '.join(ways_casses[:10])}"
            f"{', ...' if len(ways_casses) > 10 else ''}) — probable troncature "
            f"Overpass sur une tuile, nouvel essai avec des tuiles plus petites"
        )
        tile_size_deg = tile_size_deg / 2
    else:
        raise RuntimeError(
            f"Extrait OSM toujours corrompu après {max_essais} essai(s) : "
            f"{len(ways_casses)} way(s) routier(s) à la géométrie dégénérée "
            f"(id : {', '.join(ways_casses)}) — probablement une troncature "
            f"systématique d'Overpass sur cette zone plutôt qu'un aléa ponctuel."
        )

    return output_pbf_path


GEOFABRIK_INDEX_URL = "https://download.geofabrik.de/index-v1-nogeom.json"
GEOFABRIK_CACHE_DEFAUT = pathlib.Path("data") / "osm_pbf_pays"


def _charger_index_geofabrik(dossier_cache=GEOFABRIK_CACHE_DEFAUT, session=None):
    """Télécharge (une fois, mis en cache localement — l'index évolue peu :
    un nouveau pays de temps en temps) l'index Geofabrik "nogeom" (sans les
    géométries de contour, seulement id/nom/codes pays/URLs — largement
    suffisant ici puisqu'on sélectionne un extrait par code pays, pas par
    intersection géométrique fine) et le renvoie parsé (dict)."""
    dossier_cache = pathlib.Path(dossier_cache)
    dossier_cache.mkdir(parents=True, exist_ok=True)
    chemin_cache = dossier_cache / "index-v1-nogeom.json"

    if not chemin_cache.exists():
        session = session or session_avec_retries()
        reponse = session.get(GEOFABRIK_INDEX_URL, timeout=60)
        reponse.raise_for_status()
        chemin_cache.write_bytes(reponse.content)

    return json.loads(chemin_cache.read_text())


def url_pbf_geofabrik(code_alpha2, dossier_cache=GEOFABRIK_CACHE_DEFAUT, session=None):
    """URL de téléchargement (dernier extrait .osm.pbf) du pays
    code_alpha2 (ISO 3166-1 alpha-2, ex: "ci" pour Côte d'Ivoire) dans le
    catalogue Geofabrik, ou None si aucune entrée pays exacte ne correspond
    (micro-territoires absents du catalogue, code invalide...).

    Ne retient que les entrées où "iso3166-1:alpha2" vaut EXACTEMENT
    [code_alpha2] (une entrée à un seul pays) : les entrées continent/région
    du même index listent plusieurs codes et seraient hors de propos ici
    (on veut le plus petit extrait qui couvre le pays entier, pas tout un
    continent)."""
    index = _charger_index_geofabrik(dossier_cache, session=session)
    code_alpha2 = code_alpha2.upper()
    for feature in index["features"]:
        proprietes = feature["properties"]
        if proprietes.get("iso3166-1:alpha2") == [code_alpha2]:
            return proprietes["urls"]["pbf"]
    return None


def telecharger_pbf_pays_geofabrik(code_alpha2, dossier_cache=GEOFABRIK_CACHE_DEFAUT):
    """Télécharge (si pas déjà en cache local) l'extrait pays Geofabrik de
    code_alpha2, et renvoie son chemin local. None si code_alpha2 n'a pas
    d'entrée dans le catalogue Geofabrik (cf. url_pbf_geofabrik)."""
    dossier_cache = pathlib.Path(dossier_cache)
    dossier_cache.mkdir(parents=True, exist_ok=True)
    chemin_local = dossier_cache / f"{code_alpha2.lower()}-latest.osm.pbf"
    if chemin_local.exists():
        return chemin_local

    session = session_avec_retries()
    url = url_pbf_geofabrik(code_alpha2, dossier_cache, session=session)
    if url is None:
        return None

    print(f"téléchargement de l'extrait Geofabrik {code_alpha2} ({url}) ...")
    with session.get(url, stream=True, timeout=300) as reponse:
        reponse.raise_for_status()
        with open(chemin_local, "wb") as f:
            for bloc in reponse.iter_content(chunk_size=1024 * 1024):
                f.write(bloc)
    print(f"✓ téléchargé : {chemin_local} ({chemin_local.stat().st_size / 1e6:.0f} Mo)")
    return chemin_local


def osm_pbf_creator_depuis_geofabrik(
    zone_geom, output_dir, codes_pays_alpha2, output_pbf_path=None,
    dossier_cache_pbf=GEOFABRIK_CACHE_DEFAUT,
):
    """Construit un .osm.pbf couvrant zone_geom, comme
    osm_pbf_creator_depuis_geometrie, mais à partir d'extraits pays
    pré-construits Geofabrik (téléchargement direct, un fichier par pays de
    codes_pays_alpha2 — cf. src/worldpop.pays_couverts_par_zone pour les
    obtenir) plutôt que d'interroger l'API Overpass tuile par tuile :
    alternative à utiliser quand Overpass est indisponible (cf. docstring
    du module), ou simplement plus rapide/robuste pour un pays déjà mis en
    cache localement lors d'un run précédent.

    zone_geom au sein d'un seul pays : téléchargement d'un unique fichier,
    fusionné avec les autres via `osmium merge` si codes_pays_alpha2 en
    contient plusieurs (zone à cheval sur une frontière).

    Lève ValueError si un des codes pays n'a pas d'extrait Geofabrik
    disponible (cf. url_pbf_geofabrik).

    Renvoie le chemin du .osm.pbf produit (comme
    osm_pbf_creator_depuis_geometrie).
    """
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_pbf_path is None:
        output_pbf_path = output_dir / "agglo.osm.pbf"
    output_pbf_path = pathlib.Path(output_pbf_path)
    BOUNDARY_GEOJSON = output_dir / "agglo_boundary.geojson"

    if shutil.which("osmium") is None:
        raise SystemExit(
            "osmium-tool is required but not found. Install it with: brew install osmium-tool"
        )

    boundary = gpd.GeoDataFrame(geometry=[zone_geom], crs="EPSG:4326")
    boundary.to_file(BOUNDARY_GEOJSON, driver="GeoJSON")
    print(f"wrote {BOUNDARY_GEOJSON}, bounds: {boundary.total_bounds}")

    fichiers_pays = []
    for code in codes_pays_alpha2:
        chemin = telecharger_pbf_pays_geofabrik(code, dossier_cache_pbf)
        if chemin is None:
            raise ValueError(f"aucun extrait Geofabrik disponible pour le pays {code!r}")
        fichiers_pays.append(chemin)

    if len(fichiers_pays) > 1:
        fusion_path = output_dir / "agglo_fusion.osm.pbf"
        subprocess.run(
            ["osmium", "merge", *[str(f) for f in fichiers_pays], "-o", fusion_path, "--overwrite"],
            check=True,
        )
        print(f"wrote {fusion_path} (fusion de {len(fichiers_pays)} pays)")
    else:
        fusion_path = fichiers_pays[0]

    subprocess.run(
        ["osmium", "extract", "-p", BOUNDARY_GEOJSON, "-o", output_pbf_path, "--overwrite", fusion_path],
        check=True,
    )
    print(f"wrote {output_pbf_path}")

    if len(fichiers_pays) > 1:
        pathlib.Path(fusion_path).unlink()

    return output_pbf_path


def extraire_amenities_depuis_pbf(pbf_path, dossier_travail):
    """Extrait tous les éléments amenity=* (n'importe quelle valeur) d'un
    .osm.pbf déjà présent localement — typiquement AGGLO_PBF_PATH, le
    résultat déjà découpé sur la zone voulue par
    osm_pbf_creator_depuis_geofabrik/_depuis_geometrie — via osmium
    (tags-filter puis export), sans aucune requête réseau. Alternative
    locale à extraire_amenities_osm.extraire_amenities_osm (Overpass) quand
    Overpass est indisponible (cf. docstring du module) : réutilise le pbf
    déjà téléchargé pour le réseau de routage plutôt que d'interroger une
    deuxième source pour la même zone.

    Renvoie un DataFrame [osm_type, osm_id, amenity, name, lat, lon,
    tous_les_tags] — même format que extraire_amenities_osm.
    extraire_amenities_osm, pour rester un remplacement direct dans le
    reste du pipeline (pondération, dispatch sur la grille...). lat/lon :
    le point lui-même pour un node, le centroïde (planaire, en degrés —
    approximation, comme le "out center" d'Overpass) de la géométrie pour
    un way/relation.
    """
    dossier_travail = pathlib.Path(dossier_travail)
    dossier_travail.mkdir(parents=True, exist_ok=True)

    # tags-filter garde aussi, par défaut, les objets référencés nécessaires
    # à la géométrie (ex: les nodes d'un way sans amenity eux-mêmes) — filtrés
    # ci-dessous via gdf["amenity"].notna(), pas via --omit-referenced (qui
    # casserait la reconstruction géométrique des ways/relations matchés).
    filtre_path = dossier_travail / "amenities_filtre.osm.pbf"
    subprocess.run(
        ["osmium", "tags-filter", str(pbf_path), "n/amenity", "w/amenity", "r/amenity",
         "-o", str(filtre_path), "--overwrite"],
        check=True,
    )

    geojson_path = dossier_travail / "amenities.geojson"
    subprocess.run(
        ["osmium", "export", str(filtre_path), "-o", str(geojson_path), "--overwrite", "-a", "type,id"],
        check=True,
    )

    gdf = gpd.read_file(geojson_path)
    gdf = gdf[gdf["amenity"].notna()].copy()
    # allow_override : le GeoJSON exporté par osmium n'embarque pas de CRS
    # explicite (WGS84 implicite, comme tout GeoJSON) — fiona/geopandas le
    # lit alors sans CRS renseigné, d'où l'avertissement "Geometry is in a
    # geographic CRS" au .centroid ci-dessous sans ce set_crs.
    gdf = gdf.set_crs(4326, allow_override=True)
    with warnings.catch_warnings():
        # Avertissement geopandas attendu et sans conséquence ici : centroïde
        # planaire en degrés, approximation assumée (cf. docstring), pas une
        # erreur à corriger via une reprojection.
        warnings.filterwarnings("ignore", message="Geometry is in a geographic CRS")
        centroides = gdf.geometry.centroid  # no-op pour un Point, centroïde planaire sinon

    colonnes_tags = [c for c in gdf.columns if c not in ("@type", "@id", "geometry")]
    lignes = []
    for (_, row), point in zip(gdf.iterrows(), centroides):
        # str(...) : un tag OSM est toujours une chaîne dans les faits, mais
        # le lecteur GeoJSON de fiona/geopandas infère parfois un dtype plus
        # spécifique par colonne (ex: colonne "check_date" entière en
        # Timestamp) — non sérialisable tel quel par json.dumps ci-dessous.
        tags = {c: str(row[c]) for c in colonnes_tags if pd.notna(row[c])}
        lignes.append({
            "osm_type": row["@type"],
            "osm_id": row["@id"],
            "amenity": row["amenity"],
            "name": tags.get("name"),
            "lat": point.y,
            "lon": point.x,
            "tous_les_tags": json.dumps(tags, ensure_ascii=False),
        })

    filtre_path.unlink()
    geojson_path.unlink()

    return pd.DataFrame(lignes)
