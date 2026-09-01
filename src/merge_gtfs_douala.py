"""
Fusionne les deux GTFS Douala de data/GTFS_tomerge/ (bus + paratransit
"Yellow Taxi", deux feeds distincts non superposés, tous deux publiés par
WhereIsMyTransport) en un seul GTFS, prêt pour le catalogue
data/GTFS_Africa/ — cf. src/merge_gtfs.py pour la logique de fusion
générique (réutilisée aussi par src/merge_gtfs_cairo.py).

Les deux calendriers sources couvrent déjà la même plage (2018-06-06 à
2019-07-06) : _etendre_calendrier_si_disjoint (cf. src/merge_gtfs.py)
n'a donc rien à faire ici, mais reste appliqué par sécurité — si l'une des
deux sources était mise à jour séparément avec une plage différente, la
fusion resterait correcte sans y repenser.

Usage :
    python3 -m src.merge_gtfs_douala
"""

import os
from pathlib import Path

from src.merge_gtfs import fusionner_gtfs

BASE_DIR = Path(__file__).resolve().parent.parent

GTFS_ZIP_PATH_BUS = os.path.join(BASE_DIR, "data", "GTFS_tomerge", "Douala_bus.zip")
GTFS_ZIP_PATH_PARATRANSIT = os.path.join(BASE_DIR, "data", "GTFS_tomerge", "Douala_paratranist.zip")
GTFS_ZIP_PATH_SORTIE = os.path.join(BASE_DIR, "data", "GTFS_Africa", "Douala_gtfs.zip")


if __name__ == "__main__":
    fusionner_gtfs([GTFS_ZIP_PATH_BUS, GTFS_ZIP_PATH_PARATRANSIT], GTFS_ZIP_PATH_SORTIE)
