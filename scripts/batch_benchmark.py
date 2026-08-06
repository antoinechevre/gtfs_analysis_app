"""
Traite tous les GTFS présents dans data/GTFS/ (dates_service, tronçons et
indicateurs par mode, indicateurs arrêts, total_vk_plage, population),
pousse chaque résultat vers ww_GTFS et alimente le benchmark inter-réseaux
— en une seule commande, plutôt que de relancer le notebook réseau par
réseau.

Reproduit exactement la logique de app.py (fusion auto des agences si le
réseau est géographiquement compact, rejet si régional, repli population
sur le nom de fichier) pour que le cache généré soit directement
réutilisable par l'app : un GTFS traité ici, puis choisi dans l'app,
retombe sur ce cache au lieu de tout recalculer.

Usage : (depuis la racine du repo, avec le venv activé)
    export HF_TOKEN=...
    python -m scripts.batch_benchmark
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

import pandas as pd

from src.utils import (
    charger_gtfs,
    obtenir_service_ids_pour_date,
    km_par_ligne_plage,
    etendue_geographique_km,
    fusionner_agences_en_une,
)
from src.info_reseau import nom_reseau, charger_ou_calculer_dates_service
from src.arrets import calculer_indicateurs_arrets
from src.create_troncons_uniques import creer_troncons_uniques
from src.indicateurs_troncons import calculer_frequentation_troncons
from src.hf_cache import charger_ou_calculer_avec_cache_hf, envoyer_vers_hf, fusionner_et_envoyer_csv
from src.population import population_agglomeration, deviner_ville_depuis_nom_fichier, deviner_ville_principale

# Doit rester identique au seuil de app.py (SEUIL_ETENDUE_REGIONALE_KM) :
# au-delà, un GTFS à plus de 3 agences est considéré régional et ignoré
# plutôt que fusionné en une seule agence.
SEUIL_ETENDUE_REGIONALE_KM = 300

MODES_STANDARD = [(3, "Bus"), (0, "Tram"), (1, "Metro"), (11, "Trolley"), (4, "Ferry")]

GTFS_DIR = BASE_DIR / "data" / "GTFS"
NOM_FICHIER_HF_BENCHMARK = "benchmark/index_benchmark_reseaux.csv"
CHEMIN_LOCAL_BENCHMARK = BASE_DIR / "data" / "benchmark" / "index_benchmark_reseaux.csv"


def traiter_gtfs(chemin_zip):
    nom_fichier = chemin_zip.name
    print("=" * 70)
    print(f"TRAITEMENT : {nom_fichier}")
    print("=" * 70)

    feed = charger_gtfs(str(chemin_zip))

    if feed.agency is None or feed.agency.empty:
        print(f"⚠ {nom_fichier} ignoré : pas d'agency.txt exploitable (GTFS incomplet/corrompu ?)")
        return

    nb_agences = len(feed.agency)

    if nb_agences > 3:
        if feed.agency["agency_name"].nunique() == 1:
            # Déjà pré-traité par un script merge_gtfs_*.py dédié (ex:
            # IDFM : agency_name uniforme malgré 64 agency_id distincts,
            # volontairement conservés pour la distinction RER) : pas
            # besoin de refusionner, ni de vérifier l'étendue.
            print(f"  {nb_agences} agency_id mais agency_name déjà uniforme — pas de fusion nécessaire")
        else:
            etendue_km = etendue_geographique_km(feed)
            if etendue_km > SEUIL_ETENDUE_REGIONALE_KM:
                print(f"⚠ {nom_fichier} ignoré : régional ({nb_agences} agences, {etendue_km:.0f} km)")
                return
            nom_agence_fusion = str(feed.agency["agency_name"].iloc[0])
            fusionner_agences_en_une(feed, nom_agence_fusion)
            print(f"✓ {nb_agences} agences fusionnées en une seule ('{nom_agence_fusion}', {etendue_km:.0f} km)")

    reseau_str = str(nom_reseau(feed))
    print(f"Réseau : {reseau_str}")

    _, date_debut, date_fin, date_JOB = charger_ou_calculer_dates_service(feed, reseau_str)
    date_str = date_JOB
    active_service_ids = obtenir_service_ids_pour_date(feed, date_str)

    chemin_cache = os.path.join("data", "memory_troncons", reseau_str, "indicateurs_arrets.csv")
    nom_hf = f"memory_troncons/{reseau_str}/indicateurs_arrets.csv"
    indicateurs_arrets = charger_ou_calculer_avec_cache_hf(
        chemin_cache, nom_hf, lambda: calculer_indicateurs_arrets(feed, date_str)
    )

    troncons_par_mode = {}
    for route_type, nom_mode in MODES_STANDARD:
        chemin_cache = os.path.join("data", "memory_troncons", reseau_str, f"troncons_{nom_mode.lower()}.csv")
        nom_hf = f"memory_troncons/{reseau_str}/troncons_{nom_mode.lower()}.csv"
        troncons_par_mode[nom_mode] = charger_ou_calculer_avec_cache_hf(
            chemin_cache,
            nom_hf,
            lambda rt=route_type, nm=nom_mode: creer_troncons_uniques(
                feed, rt, agency_ids=None, prefixe=nm.upper()
            ),
        )

    for route_type, nom_mode in MODES_STANDARD:
        chemin_cache = os.path.join("data", "memory_troncons", reseau_str, f"indicateurs_{nom_mode.lower()}.csv")
        nom_hf = f"memory_troncons/{reseau_str}/indicateurs_{nom_mode.lower()}.csv"
        charger_ou_calculer_avec_cache_hf(
            chemin_cache,
            nom_hf,
            lambda rt=route_type, nm=nom_mode: calculer_frequentation_troncons(
                feed, troncons_par_mode[nm], active_service_ids, route_type=rt, agency_ids=None
            ),
        )

    liste_dates_service, _, _, _ = charger_ou_calculer_dates_service(feed, reseau_str)
    chemin_cache = os.path.join("data", "memory_troncons", reseau_str, "total_vk_plage.csv")
    nom_hf = f"memory_troncons/{reseau_str}/total_vk_plage.csv"
    total_vk_plage = charger_ou_calculer_avec_cache_hf(
        chemin_cache, nom_hf, lambda: km_par_ligne_plage(liste_dates_service, feed)
    )

    envoyer_vers_hf(str(chemin_zip), f"GTFS/{nom_fichier}")

    population, _annee = population_agglomeration(reseau_str)
    if population is None:
        ville_devinee = deviner_ville_depuis_nom_fichier(nom_fichier)
        if ville_devinee and ville_devinee != reseau_str:
            population, _annee = population_agglomeration(ville_devinee)

    vk_par_mode = total_vk_plage.groupby("mode")["total_km_plage"].sum()
    ligne_benchmark = pd.DataFrame(
        [
            {
                "reseau": reseau_str,
                "ville_principale": deviner_ville_principale(reseau_str, nom_fichier),
                "date_JOB": date_str,
                "population_totale": population,
                "nombre_arrets": len(indicateurs_arrets),
                "vehicules_km_total": float(total_vk_plage["total_km_plage"].sum()),
                "vehicules_km_bus": float(vk_par_mode.get("Bus", 0)),
                "vehicules_km_metro": float(vk_par_mode.get("Métro", 0)),
                "vehicules_km_tram": float(vk_par_mode.get("Tram", 0)),
            }
        ]
    )
    fusionner_et_envoyer_csv(
        ligne_benchmark,
        NOM_FICHIER_HF_BENCHMARK,
        str(CHEMIN_LOCAL_BENCHMARK),
        colonne_cle="reseau",
        valeur_cle=reseau_str,
    )
    print(f"✓ {reseau_str} enregistré dans le benchmark (population={population})")


if __name__ == "__main__":
    fichiers = sorted(GTFS_DIR.glob("*.zip"))
    print(f"{len(fichiers)} fichier(s) à traiter : {[f.name for f in fichiers]}\n")

    echecs = []
    for chemin_zip in fichiers:
        try:
            traiter_gtfs(chemin_zip)
        except Exception as e:
            print(f"❌ {chemin_zip.name} : échec — {type(e).__name__}: {e}")
            echecs.append(chemin_zip.name)
        print()

    print("=" * 70)
    print(f"✓ TERMINÉ — {len(fichiers) - len(echecs)}/{len(fichiers)} réussi(s)")
    if echecs:
        print(f"Échecs : {echecs}")
    print("=" * 70)
