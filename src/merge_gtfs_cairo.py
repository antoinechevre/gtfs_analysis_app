"""
Fusionne les deux GTFS Caire de data/GTFS_tomerge/ (bus + métro, deux
feeds distincts non superposés) en un seul GTFS, prêt pour le catalogue
data/GTFS_Africa/ — cf. src/merge_gtfs.py pour la logique de fusion
générique (réutilisée aussi par src/merge_gtfs_douala.py).

Usage :
    python3 -m src.merge_gtfs_cairo
"""

import os
from pathlib import Path

from src.merge_gtfs import fusionner_gtfs

BASE_DIR = Path(__file__).resolve().parent.parent

GTFS_ZIP_PATH_BUS = os.path.join(BASE_DIR, "data", "GTFS_tomerge", "Cairo_bus.zip")
GTFS_ZIP_PATH_TRAM = os.path.join(BASE_DIR, "data", "GTFS_tomerge", "Cairo_metro.zip")
GTFS_ZIP_PATH_SORTIE = os.path.join(BASE_DIR, "data", "GTFS_Africa", "Cairo_gtfs.zip")


if __name__ == "__main__":
    fusionner_gtfs([GTFS_ZIP_PATH_BUS, GTFS_ZIP_PATH_TRAM], GTFS_ZIP_PATH_SORTIE)
