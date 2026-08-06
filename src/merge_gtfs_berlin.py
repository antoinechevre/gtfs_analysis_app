"""
Prépare le GTFS Berlin pour l'app : uniformise le nom d'agence et
normalise les route_type.

Prend en entrée Berlin_urbain_gtfs.zip (pas le GTFS régional VBB brut) :
le VBB complet couvre tout le Brandebourg (~584 km de diagonale), rejeté
par le filtre régional de l'app (seuil 300 km, cf. SEUIL_ETENDUE_REGIONALE_KM
dans app.py). Berlin_urbain_gtfs.zip est le résultat de
src/isole_ville.py filtré aux deux agences du cœur urbain (796 = Berliner
Verkehrsbetriebe/BVG, 1 = S-Bahn Berlin), qui ramène l'étendue à ~76 km.

Comme pour merge_gtfs_IDFM.py, il n'y a ici qu'un seul GTFS en entrée : ce
n'est pas une fusion de plusieurs feeds distincts. Contrairement à IDFM
(où les agency_id d'origine sont préservés à cause de l'exception RER),
Berlin n'a pas de sous-réseau à distinguer par agency_id — ses agences
sont donc fusionnées en une seule (comme pour merge_gtfs_NYC.py /
merge_gtfs_lisboa.py).

Le GTFS Berlin publie aussi ses route_type au format étendu (centaines :
700=bus, 900=tram, 400=U-Bahn, 100=S-Bahn/rail...) plutôt qu'en codes de
base (0-12) — cf. src.utils.normaliser_route_type_etendu, la même
normalisation que charger_gtfs() applique déjà à la volée pour l'app et le
notebook. On l'applique ici aussi pour que le GTFS déposé sur ww_GTFS soit
directement exploitable même par un code qui ne passerait pas par
charger_gtfs().
"""

import os
import sys
from pathlib import Path

import gtfs_kit as gk

BASE_DIR = Path(__file__).resolve().parent.parent

# Rend "src" importable que le script soit lancé en module (python -m
# src.merge_gtfs_berlin, depuis la racine du repo) ou en fichier direct
# (bouton "Run" de l'IDE, où sys.path[0] est le dossier src/ lui-même).
sys.path.insert(0, str(BASE_DIR))
from src.hf_cache import envoyer_vers_hf
from src.utils import normaliser_route_type_etendu

GTFS_ZIP_PATH_BERLIN = os.path.join(BASE_DIR, "data", "GTFS", "Berlin_urbain_gtfs.zip")
OUTPUT_PATH_BERLIN_merge = os.path.join(BASE_DIR, "data", "GTFS", "Berlin_gtfs_merge.zip")


def preparer_gtfs_berlin(chemin_zip, chemin_sortie, nom_agence, dist_units="km"):
    """
    Charge le GTFS Berlin, normalise ses route_type étendus vers les codes
    de base GTFS, et fusionne ses agences en une seule portant nom_agence
    (agency_id conservé de la première, agency_id des autres remappés vers
    celui-ci dans routes et fare_attributes).

    Parameters:
    -----------
    chemin_zip : str
        Chemin du GTFS (zip) en entrée.
    chemin_sortie : str
        Chemin du GTFS (zip) à écrire.
    nom_agence : str
        Nom à forcer pour l'agence unique du GTFS préparé.
    dist_units : str
        Unité de distance à utiliser pour le feed (défaut: 'km').

    Returns:
    --------
    gtfs_kit Feed object
        Le feed préparé.
    """
    print("=" * 70)
    print("PRÉPARATION DU GTFS BERLIN")
    print("=" * 70)

    print(f"\nChargement de {os.path.basename(chemin_zip)}...")
    feed = gk.read_feed(chemin_zip, dist_units=dist_units)

    print("\nNormalisation des route_type étendus...")
    route_types_origine = feed.routes["route_type"]
    feed.routes["route_type"] = route_types_origine.apply(normaliser_route_type_etendu)
    nb_convertis = (feed.routes["route_type"] != route_types_origine).sum()
    print(f"  → {nb_convertis} route(s) normalisée(s) vers un code de base")

    anciens_agency_ids = feed.agency["agency_id"].tolist()
    agency_id_unique = anciens_agency_ids[0]

    print(f"\nFusion de {len(anciens_agency_ids)} agence(s) en une seule : '{nom_agence}'")
    agence_unique = feed.agency.iloc[[0]].copy()
    agence_unique["agency_name"] = nom_agence
    feed.agency = agence_unique.reset_index(drop=True)

    for table_nom in ("routes", "fare_attributes"):
        table = getattr(feed, table_nom)
        if table is not None and "agency_id" in table.columns:
            table["agency_id"] = agency_id_unique

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
    preparer_gtfs_berlin(
        GTFS_ZIP_PATH_BERLIN,
        OUTPUT_PATH_BERLIN_merge,
        nom_agence="Berlin Public Transport",
    )
