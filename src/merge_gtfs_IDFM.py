"""
Uniformise le nom d'agence du GTFS IDFM en un seul nom "IDFM".

Contrairement à merge_gtfs_NYC.py / merge_gtfs_lisboa.py, il n'y a ici
qu'un seul GTFS en entrée (IDFM-gtfs.zip) : ce n'est pas une fusion de
plusieurs feeds distincts, mais un feed unique qui regroupe déjà en
interne des dizaines d'agences (RATP, SNCF, Optile...).

Important : contrairement aux scripts NYC/Lisboa, les agency_id d'origine
sont conservés tels quels (pas de fusion en une agence unique ni de
remappage des références). Le RER est distingué des autres trains
(Transilien, TER) dans l'app via son agency_id précis IDFM:71 (cf.
MODES_IDFM, views/troncons.py) : le remplacer casserait cette distinction.
Seul agency_name est réécrit, pour un affichage uniforme "IDFM" partout où
le nom d'agence est montré, sans toucher aux identifiants.
"""

import os
from pathlib import Path

import gtfs_kit as gk

from src.hf_cache import envoyer_vers_hf

BASE_DIR = Path(__file__).resolve().parent.parent

GTFS_ZIP_PATH_IDFM = os.path.join(BASE_DIR, "data", "GTFS", "IDFM-gtfs.zip")
OUTPUT_PATH_IDFM_merge = os.path.join(BASE_DIR, "data", "GTFS", "IDFM-gtfs_merge.zip")


def forcer_nom_agence(chemin_zip, chemin_sortie, nom_agence, dist_units="km"):
    """
    Réécrit agency_name à `nom_agence` pour toutes les agences du GTFS,
    en conservant leurs agency_id d'origine (donc sans impact sur les
    tables qui y font référence : routes, fare_attributes...).

    Parameters:
    -----------
    chemin_zip : str
        Chemin du GTFS (zip) en entrée.
    chemin_sortie : str
        Chemin du GTFS (zip) à écrire.
    nom_agence : str
        Nom à forcer pour toutes les lignes de agency.txt.
    dist_units : str
        Unité de distance à utiliser pour le feed (défaut: 'km').

    Returns:
    --------
    gtfs_kit Feed object
        Le feed avec agency_name uniformisé.
    """
    print("=" * 70)
    print("UNIFORMISATION DU NOM D'AGENCE")
    print("=" * 70)

    print(f"\nChargement de {os.path.basename(chemin_zip)}...")
    feed = gk.read_feed(chemin_zip, dist_units=dist_units)

    nb_agences = len(feed.agency)
    print(f"\n{nb_agences} agence(s) trouvée(s), agency_id conservés tels quels")
    print(f"Forçage d'agency_name à '{nom_agence}' pour les {nb_agences} agence(s)")
    feed.agency["agency_name"] = nom_agence

    feed.to_file(chemin_sortie)
    print(f"\n✓ GTFS enregistré dans : {chemin_sortie}")

    # Renvoyé vers le dataset HF partagé (best-effort) uniquement une fois
    # arrivé ici sans erreur : le chargement et l'écriture locale ont réussi.
    nom_fichier_hf = f"GTFS/{os.path.basename(chemin_sortie)}"
    if envoyer_vers_hf(chemin_sortie, nom_fichier_hf):
        print(f"✓ Envoyé vers le dataset HF : {nom_fichier_hf}")
    else:
        print(f"⚠ Envoi vers le dataset HF échoué (ou HF_TOKEN absent) : {nom_fichier_hf}")

    print("\n" + "=" * 70)
    print("✓ TERMINÉ")
    print("=" * 70)

    return feed


if __name__ == "__main__":
    forcer_nom_agence(
        GTFS_ZIP_PATH_IDFM,
        OUTPUT_PATH_IDFM_merge,
        nom_agence="IDFM",
    )
