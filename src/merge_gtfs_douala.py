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
import zipfile
from pathlib import Path

from src.merge_gtfs import fusionner_gtfs

BASE_DIR = Path(__file__).resolve().parent.parent

GTFS_ZIP_PATH_BUS = os.path.join(BASE_DIR, "data", "GTFS_tomerge", "Douala_bus.zip")
GTFS_ZIP_PATH_PARATRANSIT = os.path.join(BASE_DIR, "data", "GTFS_tomerge", "Douala_paratranist.zip")
GTFS_ZIP_PATH_PARATRANSIT_REPARE = os.path.join(BASE_DIR, "data", "GTFS_tomerge", "Douala_paratransit_repare.zip")
GTFS_ZIP_PATH_SORTIE = os.path.join(BASE_DIR, "data", "GTFS_Africa", "Douala_gtfs.zip")


def _reparer_frequencies_paratransit(chemin_source, chemin_repare):
    """Douala_paratranist.zip (source) a un frequencies.txt délimité par
    des points-virgules plutôt que des virgules — seul fichier concerné du
    zip, vérifié table par table. gtfs_kit/pandas le lisent alors comme
    une colonne unique, sans "trip_id" reconnu séparément, ce qui fait
    planter gtfs_kit.Feed.expand_frequencies (KeyError: 'trip_id') dès la
    préparation r5py de tout GTFS l'intégrant. Écrit une copie du zip avec
    ce seul fichier reconverti en CSV standard (virgules), le reste
    recopié tel quel."""
    with zipfile.ZipFile(chemin_source) as z_in:
        contenu_frequencies = z_in.read("frequencies.txt").decode("utf-8").replace(";", ",")
        with zipfile.ZipFile(chemin_repare, "w", zipfile.ZIP_DEFLATED) as z_out:
            for nom in z_in.namelist():
                if nom == "frequencies.txt":
                    z_out.writestr(nom, contenu_frequencies)
                else:
                    z_out.writestr(nom, z_in.read(nom))


if __name__ == "__main__":
    _reparer_frequencies_paratransit(GTFS_ZIP_PATH_PARATRANSIT, GTFS_ZIP_PATH_PARATRANSIT_REPARE)
    fusionner_gtfs([GTFS_ZIP_PATH_BUS, GTFS_ZIP_PATH_PARATRANSIT_REPARE], GTFS_ZIP_PATH_SORTIE)
