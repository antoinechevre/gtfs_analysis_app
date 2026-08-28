"""
Reproduit, directement depuis l'app Streamlit (views/accessibilite.py),
la chaîne de traitement d'index_accessibility_notebook_africa_600m.ipynb :
grille de population -> extrait OSM (Geofabrik) -> équipements OSM -> réseau
de transport (r5py) -> matrice de temps de trajet (TTM). À utiliser
uniquement quand aucune TTM n'est déjà en cache pour ce réseau (cf.
src.utilitaires_matrix.charger_ttm_reseau) : ce calcul est lourd (r5py, JVM)
et bloque l'app pendant son exécution (process Streamlit mono-thread) —
prévenir l'utilisateur avant de lancer, cf. l'avertissement affiché par
accessibilite_page.

N'importe r5py/rasterio qu'à l'intérieur de calculer_pipeline_complet (pas
au niveau module) : ces imports démarrent une JVM (r5py) coûteuse à
l'exécution, inutile pour qui ne déclenche jamais ce calcul.
"""

import os
import shutil

from src.equipements_osm import DOSSIER_EQUIPEMENTS_DEFAUT
from src.hf_cache import envoyer_vers_hf, recuperer_depuis_hf
from src.info_reseau import charger_ou_calculer_dates_service
from src.osm_extract import extraire_amenities_depuis_pbf, osm_pbf_creator_depuis_geofabrik
from src.utilitaires_matrix import charger_ttm, nom_fichier_ttm
from src.worldpop import (
    RESOLUTION_M_AFRIQUE,
    charger_ou_construire_grille_population_reseau,
    pays_couverts_par_zone,
    zone_desservie_gtfs,
)

MEMORY_PBF_DIR = os.path.join("data", "memory_pbf")
MEMORY_TTM_DIR = os.path.join("data", "memory_ttm")
OSM_WORK_DIR = os.path.join("data", "osm_extract")
PONDERATION_XLSX = os.path.join(DOSSIER_EQUIPEMENTS_DEFAUT, "Abidjan_amenities.xlsx")
MARGE_KM = 5
ANNEE_GTFS = 2020


def _assurer_java_home():
    """Résout JAVA_HOME si pas déjà positionné (le Dockerfile du Space le
    fixe via ENV — cf. deploy/Dockerfile.africa — donc ce bloc ne s'exécute
    qu'en dev local, macOS). /usr/libexec/java_home n'existe pas sous
    Linux (conteneur du Space) : ne jamais l'appeler si JAVA_HOME est déjà
    en place."""
    if os.environ.get("JAVA_HOME"):
        return
    if shutil.which("/usr/libexec/java_home"):
        import subprocess

        try:
            os.environ["JAVA_HOME"] = subprocess.check_output(
                ["/usr/libexec/java_home", "-v", "21"], text=True
            ).strip()
        except subprocess.CalledProcessError:
            os.environ["JAVA_HOME"] = "/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home"


def _construire_transport_network(r5py_module, osm_pbf_path, gtfs_path_r5py):
    """Construit le TransportNetwork r5py, avec purge-et-relance du cache
    r5py (~/.cache/r5py) en cas d'échec — un run précédent interrompu peut y
    laisser un fichier à moitié écrit, qui ne se répare jamais tout seul
    (cf. index_accessibility_notebook_africa_800m.ipynb, même correctif)."""
    try:
        return r5py_module.TransportNetwork(osm_pbf=str(osm_pbf_path), gtfs=[str(gtfs_path_r5py)], allow_errors=True)
    except Exception:
        from r5py.util import Config

        cache_dir = Config().CACHE_DIR
        for entree in cache_dir.iterdir():
            if entree.suffix == ".jar":
                continue
            if entree.is_dir():
                shutil.rmtree(entree, ignore_errors=True)
            else:
                entree.unlink(missing_ok=True)
        return r5py_module.TransportNetwork(osm_pbf=str(osm_pbf_path), gtfs=[str(gtfs_path_r5py)], allow_errors=True)


def calculer_pipeline_complet(feed, nom_reseau_str, gtfs_zip_path, resolution_m=RESOLUTION_M_AFRIQUE, on_step=None):
    """Grille -> OSM -> équipements -> r5py -> TTM, chacune reprise depuis
    son cache HF si déjà calculée pour ce réseau (mêmes conventions de nom
    que le notebook), sinon calculée puis uploadée pour la suite. Renvoie
    (grille_population, ttm).

    on_step(message): callback optionnel appelé avant chaque étape (ex.
    st.write côté Streamlit, pour donner une idée de la progression pendant
    un calcul qui peut durer plusieurs dizaines de minutes).
    """
    def etape(message):
        if on_step is not None:
            on_step(message)

    etape("Construction de la grille de population (WorldPop)...")
    grille_population = charger_ou_construire_grille_population_reseau(
        feed, nom_reseau_str, marge_km=MARGE_KM, resolution_m=resolution_m, annee=ANNEE_GTFS,
    )

    etape("Extraction du réseau routier OSM (Geofabrik)...")
    zone_geom, _, _ = zone_desservie_gtfs(feed, marge_km=MARGE_KM)
    os.makedirs(MEMORY_PBF_DIR, exist_ok=True)
    pbf_path_saved = os.path.join(MEMORY_PBF_DIR, f"agglo_osm_pbf_{nom_reseau_str}.osm.pbf")
    recuperer_depuis_hf(f"memory_pbf/agglo_osm_pbf_{nom_reseau_str}.osm.pbf", pbf_path_saved)

    os.makedirs(OSM_WORK_DIR, exist_ok=True)
    agglo_pbf_path = os.path.join(OSM_WORK_DIR, "agglo.osm.pbf")
    if os.path.exists(pbf_path_saved):
        shutil.copyfile(pbf_path_saved, agglo_pbf_path)
    else:
        codes_pays = pays_couverts_par_zone(zone_geom)
        agglo_pbf_path = osm_pbf_creator_depuis_geofabrik(zone_geom, OSM_WORK_DIR, codes_pays)
        shutil.copyfile(agglo_pbf_path, pbf_path_saved)
        envoyer_vers_hf(pbf_path_saved, f"memory_pbf/agglo_osm_pbf_{nom_reseau_str}.osm.pbf")

    etape("Extraction et pondération des équipements OSM...")
    # nom_reseau_str, pas ville_str_depuis_fichier(gtfs_zip_path) : ce
    # dernier vaut déjà nom_reseau_str côté appelant (app_africa.py) quand
    # gtfs_zip_path pointe vers le fichier original, mais ici gtfs_zip_path
    # est st.session_state.zip_path — le fichier temporaire créé par
    # tempfile.NamedTemporaryFile à l'upload (ex. "/tmp/tmpxxxxxx.zip"), pas
    # le nom original. Le recalculer dessus produisait un nom d'équipements
    # complètement déconnecté de nom_reseau_str (ex. "tmptz2sfh7g"),
    # introuvable ensuite par compter_equipements_par_carreau.
    os.makedirs(DOSSIER_EQUIPEMENTS_DEFAUT, exist_ok=True)
    chemin_equipements_gpkg = os.path.join(DOSSIER_EQUIPEMENTS_DEFAUT, f"{nom_reseau_str.lower()}_equipements.gpkg")
    nom_fichier_hf_equipements = f"equipements_osm/{nom_reseau_str.lower()}_equipements.gpkg"
    if not recuperer_depuis_hf(nom_fichier_hf_equipements, chemin_equipements_gpkg):
        import geopandas as gpd
        import pandas as pd

        amenities = extraire_amenities_depuis_pbf(agglo_pbf_path, OSM_WORK_DIR)
        if os.path.exists(PONDERATION_XLSX):
            ponderation_par_amenity = (
                pd.read_excel(PONDERATION_XLSX, sheet_name="resume_par_type").set_index("amenity")["Ponderation"]
            )
            amenities["ponderation"] = amenities["amenity"].map(ponderation_par_amenity).fillna(0)
        else:
            # Référentiel absent (déployé hors data/equipements_osm/, cf.
            # scripts/deploy_hf_africa.sh) : poids uniforme plutôt qu'un échec —
            # dégradé mais fonctionnel, cf. compter_equipements_par_carreau.
            amenities["ponderation"] = 1
        amenities_geo = gpd.GeoDataFrame(
            amenities, geometry=gpd.points_from_xy(amenities["lon"], amenities["lat"]), crs="EPSG:4326",
        )
        amenities_geo.to_file(chemin_equipements_gpkg, driver="GPKG")
        envoyer_vers_hf(chemin_equipements_gpkg, nom_fichier_hf_equipements)

    etape("Construction du réseau de transport multimodal (r5py, JVM)...")
    _assurer_java_home()
    import rasterio  # noqa: F401 -- avant r5py : initialise PROJ/GDAL avant que la JVM r5py n'écrase PROJ_LIB

    import r5py
    import r5py.util.jvm

    r5py.util.jvm.MAX_JVM_MEMORY = 2 * 1024**3

    from src.utils import preparer_gtfs_pour_r5py

    gtfs_path_r5py = preparer_gtfs_pour_r5py(gtfs_zip_path)
    transport_network = _construire_transport_network(r5py, agglo_pbf_path, gtfs_path_r5py)

    etape("Calcul de la matrice de temps de trajet (TTM, peut prendre du temps)...")
    import datetime

    from src.utilitaires_matrix import calculer_ttm_par_lots

    _, _, _, date_job = charger_ou_calculer_dates_service(feed, nom_reseau_str)
    departure_datetime = datetime.datetime.strptime(date_job, "%Y%m%d").replace(hour=14, minute=0, second=0)

    points = grille_population[["id", "geometry"]].copy()
    points["geometry"] = points.geometry.centroid

    os.makedirs(MEMORY_TTM_DIR, exist_ok=True)
    nom_fichier = nom_fichier_ttm(nom_reseau_str, resolution_m)
    ttm_path = os.path.join(MEMORY_TTM_DIR, nom_fichier)

    calculer_ttm_par_lots(
        r5py,
        transport_network,
        points,
        departure=departure_datetime,
        transport_modes=[r5py.TransportMode.WALK, r5py.TransportMode.TRANSIT],
        max_time_walking=datetime.timedelta(minutes=30),
        max_time=datetime.timedelta(minutes=120),
        ttm_path=ttm_path,
        on_step=etape,
    )
    ttm = charger_ttm(ttm_path)
    envoyer_vers_hf(ttm_path, f"memory_ttm/{nom_fichier}")

    return grille_population, ttm
