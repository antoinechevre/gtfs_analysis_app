"""
Fusionne les deux GTFS Caire de data/GTFS_tomerge/ (bus + métro, deux
feeds distincts non superposés) en un seul GTFS, prêt pour le catalogue
data/GTFS_Africa/.

Concaténation simple (pas de déduplication à la Google Transit Merge Spec,
cf. https://github.com/google/transitfeed/wiki/Merge) : chaque feed garde
toutes ses entités, avec ses identifiants (stop_id, route_id, trip_id,
service_id, shape_id...) préfixés par feed pour garantir l'absence de
collision avant concaténation table par table — adapté à deux réseaux
distincts (bus/métro, pas de recouvrement géographique bord à bord), pas à
la fusion de deux feeds décrivant le même réseau.

Usage :
    python3 -m src.merge_gtfs_cairo
"""

import os
from pathlib import Path

import gtfs_kit as gk
import pandas as pd

from src.utils import charger_gtfs

BASE_DIR = Path(__file__).resolve().parent.parent

GTFS_ZIP_PATH_BUS = os.path.join(BASE_DIR, "data", "GTFS_tomerge", "Cairo_bus.zip")
GTFS_ZIP_PATH_TRAM = os.path.join(BASE_DIR, "data", "GTFS_tomerge", "Cairo_metro.zip")
GTFS_ZIP_PATH_SORTIE = os.path.join(BASE_DIR, "data", "GTFS_Africa", "Cairo_gtfs.zip")

# Tables GTFS gérées par gtfs_kit.Feed
TABLES_GTFS = [
    "agency",
    "stops",
    "routes",
    "trips",
    "stop_times",
    "calendar",
    "calendar_dates",
    "fare_attributes",
    "fare_rules",
    "shapes",
    "frequencies",
    "transfers",
    "feed_info",
    "attributions",
]


def fusionner_gtfs(chemins_zip, chemin_sortie, dist_units="km"):
    """
    Fusionne plusieurs GTFS (fichiers zip) en un seul GTFS.

    Chaque feed est chargé (via src.utils.charger_gtfs, pour bénéficier au
    passage de la normalisation route_type appliquée partout ailleurs dans
    l'app), puis ses identifiants sont préfixés par son rang dans
    chemins_zip pour garantir l'absence de collision entre feeds, avant
    concaténation table par table.

    Parameters
    ----------
    chemins_zip : list[str]
        Chemins des fichiers GTFS (zip) à fusionner, au moins 2.
    chemin_sortie : str
        Chemin du fichier GTFS (zip) fusionné à écrire.
    dist_units : str
        Unité de distance à utiliser pour le feed fusionné (défaut : 'km').
        Les feeds dans une autre unité sont convertis avant fusion.

    Returns
    -------
    gtfs_kit.Feed
        Le feed fusionné.
    """
    if len(chemins_zip) < 2:
        raise ValueError("Il faut au moins 2 GTFS à fusionner")

    feeds_prefixes = []
    for i, chemin in enumerate(chemins_zip):
        print(f"Chargement de {os.path.basename(chemin)}...")
        feed = charger_gtfs(chemin)

        prefixe = f"{i}_"
        print(f"  → préfixage des identifiants avec '{prefixe}'")
        feeds_prefixes.append(gk.prefix_feed_ids(feed, prefixe))

    tables_fusionnees = {}
    for table in TABLES_GTFS:
        dfs = [
            getattr(feed, table)
            for feed in feeds_prefixes
            if getattr(feed, table) is not None
        ]
        if not dfs:
            continue
        if table == "feed_info":
            # feed_info décrit le feed dans son ensemble (0 ou 1 ligne selon
            # la spec GTFS) : le concaténer comme les autres tables produit
            # plusieurs lignes, rejetées par les lecteurs GTFS stricts (dont
            # celui de r5py : "FeedInfo contains more than one record",
            # qui casse alors tout le TransportNetwork malgré allow_errors=True
            # — cf. l'incident Casablanca/Cairo TTM 100% NaN sauf diagonale).
            # On ne garde que la première ligne rencontrée plutôt que de
            # fusionner plusieurs feed_info entre eux.
            tables_fusionnees[table] = dfs[0].iloc[[0]].reset_index(drop=True)
        else:
            tables_fusionnees[table] = pd.concat(dfs, ignore_index=True, sort=False)

    feed_fusionne = gk.Feed(dist_units=dist_units, **tables_fusionnees)

    os.makedirs(os.path.dirname(chemin_sortie), exist_ok=True)
    feed_fusionne.to_file(chemin_sortie)
    print(f"✓ GTFS fusionné enregistré dans : {chemin_sortie}")

    return feed_fusionne


if __name__ == "__main__":
    fusionner_gtfs([GTFS_ZIP_PATH_BUS, GTFS_ZIP_PATH_TRAM], GTFS_ZIP_PATH_SORTIE)
