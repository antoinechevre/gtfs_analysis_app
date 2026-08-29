"""
Recalcule l'index de benchmark villes africaines
(benchmark/index_benchmark_reseaux_afrique.csv) pour tous les GTFS de
data/GTFS_Africa/, à partir des caches déjà disponibles (memory_troncons/,
memory_accessibilite/, memory_gpkg/) — sans jamais relancer r5py ni le
notebook : juste indicateurs arrêts/lignes (rapides, calculés ici si pas
déjà en cache) et le résultat cumulative_cutoff équipements déjà calculé
par le notebook (cf. index_accessibility_notebook_africa_600m.ipynb,
src.utilitaires_matrix.charger_cumulative_cutoff_cache) pour chaque
réseau. Une seule commande plutôt que de cliquer "Enregistrer ce réseau"
réseau par réseau dans l'onglet Accessibilité de l'app.

pas de population_accessible_60min ici (mesure retirée de l'app, cf.
views/accessibilite.py — seule "équipements accessibles" y est encore
calculée) : seule equipements_accessibles_60min est renseignée.

Un réseau sans résultat cumulative_cutoff équipements en cache (TTM pas
encore calculée pour lui) est quand même enregistré, avec
equipements_accessibles_60min=None — l'app/le graphique gèrent déjà les
valeurs manquantes (cf. src/nuage_points_benchmark.py).

Usage : (depuis la racine du repo, avec le venv activé)
    export HF_TOKEN=...
    python -m scripts.batch_benchmark_afrique
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

import pandas as pd

from src.arrets import calculer_indicateurs_arrets
from src.hf_cache import charger_ou_calculer_avec_cache_hf, fusionner_et_envoyer_csv
from src.info_reseau import charger_ou_calculer_dates_service
from src.population import deviner_ville_principale
from src.utilitaires_matrix import charger_cumulative_cutoff_cache
from src.utils import charger_gtfs, km_par_ligne_plage, ville_str_depuis_fichier
from src.worldpop import RESOLUTION_M_AFRIQUE, charger_ou_construire_grille_population_reseau

GTFS_DIR = BASE_DIR / "data" / "GTFS_Africa"
NOM_FICHIER_HF_BENCHMARK = "benchmark/index_benchmark_reseaux_afrique.csv"
CHEMIN_LOCAL_BENCHMARK = BASE_DIR / "data" / "benchmark" / "index_benchmark_reseaux_afrique.csv"
CUTOFF_MIN = 60


def traiter_gtfs(chemin_zip):
    nom_fichier = chemin_zip.name
    print("=" * 70)
    print(f"TRAITEMENT : {nom_fichier}")
    print("=" * 70)

    feed = charger_gtfs(str(chemin_zip))
    if feed.agency is None or feed.agency.empty:
        print(f"⚠ {nom_fichier} ignoré : pas d'agency.txt exploitable (GTFS incomplet/corrompu ?)")
        return

    # Dérivé du nom de fichier (pas de l'agency_name) : même convention que
    # app_africa.py/le notebook, cf. src.utils.ville_str_depuis_fichier —
    # sinon ce script recalculerait sous une clé de cache différente de
    # celle utilisée par l'app pour le même réseau.
    reseau_str = ville_str_depuis_fichier(nom_fichier)
    print(f"Réseau : {reseau_str}")

    _, date_debut, date_fin, date_JOB = charger_ou_calculer_dates_service(feed, reseau_str)
    date_str = date_JOB

    chemin_cache = os.path.join("data", "memory_troncons", reseau_str, "indicateurs_arrets.csv")
    nom_hf = f"memory_troncons/{reseau_str}/indicateurs_arrets.csv"
    indicateurs_arrets = charger_ou_calculer_avec_cache_hf(
        chemin_cache, nom_hf, lambda: calculer_indicateurs_arrets(feed, date_str)
    )

    liste_dates_service, _, _, _ = charger_ou_calculer_dates_service(feed, reseau_str)
    chemin_cache = os.path.join("data", "memory_troncons", reseau_str, "total_vk_plage.csv")
    nom_hf = f"memory_troncons/{reseau_str}/total_vk_plage.csv"
    total_vk_plage = charger_ou_calculer_avec_cache_hf(
        chemin_cache, nom_hf, lambda: km_par_ligne_plage(liste_dates_service, feed)
    )
    vk_par_mode = total_vk_plage.groupby("mode")["total_km_plage"].sum()

    # Équipements accessibles en 60 min : résultat déjà calculé par le
    # notebook (memory_accessibilite/, cf. envoyer_cumulative_cutoff_cache
    # dans index_accessibility_notebook_africa_600m.ipynb) — jamais
    # recalculé ici (pas de TTM chargée, pas de JVM r5py).
    cum_equipements = charger_cumulative_cutoff_cache(
        reseau_str, "equipements", CUTOFF_MIN, resolution_m=RESOLUTION_M_AFRIQUE,
    )
    equipements_accessibles_60min = None
    population_totale = None
    if cum_equipements is not None:
        # Moyenne pondérée par la population du carreau d'origine (même
        # calcul que views/accessibilite.py) : nécessite la grille de
        # population (WorldPop), reconstruite depuis le cache
        # memory_gpkg/ si absente, sans jamais recalculer la TTM.
        grille_population = charger_ou_construire_grille_population_reseau(
            feed, reseau_str, resolution_m=RESOLUTION_M_AFRIQUE,
        )
        poids = grille_population.set_index("id")["population"]
        population_totale = float(poids.sum())
        if population_totale:
            equipements_accessibles_60min = float(
                (cum_equipements.set_index("id")["equipements"] * poids).sum() / population_totale
            )
    else:
        print(f"  (pas de TTM/résultat équipements en cache pour {reseau_str} — colonne laissée vide)")

    ligne_benchmark = pd.DataFrame(
        [
            {
                "reseau": reseau_str,
                "ville_principale": deviner_ville_principale(reseau_str, nom_fichier),
                "date_JOB": date_str,
                "population_totale": population_totale,
                "nombre_arrets": len(indicateurs_arrets),
                "vehicules_km_total": float(total_vk_plage["total_km_plage"].sum()),
                "vehicules_km_bus": float(vk_par_mode.get("Bus", 0)),
                "vehicules_km_metro": float(vk_par_mode.get("Métro", 0)),
                "vehicules_km_tram": float(vk_par_mode.get("Tram", 0)),
                "equipements_accessibles_60min": equipements_accessibles_60min,
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
    print(f"✓ {reseau_str} enregistré dans le benchmark Afrique (equipements_accessibles_60min={equipements_accessibles_60min})")


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
