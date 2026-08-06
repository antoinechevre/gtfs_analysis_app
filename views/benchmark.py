"""
Page Benchmark - nuage de points comparant tous les réseaux déjà
enregistrés dans l'index de benchmark partagé (bouton "Enregistrer ce
réseau" ci-dessous, ou la cellule équivalente du notebook), avec le
réseau actuellement chargé (s'il y en a un) surligné en rouge parmi les
autres en bleu.

Repris du même principe que l'onglet Benchmark de l'app sœur
"accessibility" (views/benchmark_reseaux.py, antoinechevre/
Accessibility_analysis), avec des métriques transit (véhicules.km,
nombre d'arrêts) à la place des métriques d'accessibilité aux équipements.
"""

import os

import streamlit as st

from src.hf_cache import lire_csv_partage, fusionner_et_envoyer_csv
from src.nuage_points_benchmark import generer_html_str
from src.population import deviner_ville_principale
from src.i18n import t

NOM_FICHIER_HF = "benchmark/index_benchmark_reseaux.csv"
CHEMIN_LOCAL = os.path.join("data", "benchmark", "index_benchmark_reseaux.csv")


def construire_ligne_benchmark():
    """
    Construit la ligne de benchmark pour le réseau actuellement chargé, à
    partir des données déjà calculées dans session_state (aucun recalcul).
    Renvoie None si un prérequis manque (feed non chargé, tronçons/vk pas
    encore calculés sur la page Lignes...).
    """
    if st.session_state.feed is None or st.session_state.nom_reseau_str is None:
        return None
    if st.session_state.total_vk_plage is None or st.session_state.indicateurs_arrets is None:
        return None

    total_vk_plage = st.session_state.total_vk_plage
    vk_par_mode = total_vk_plage.groupby("mode")["total_km_plage"].sum()

    return {
        "reseau": st.session_state.nom_reseau_str,
        "ville_principale": deviner_ville_principale(
            st.session_state.nom_reseau_str, st.session_state.last_uploaded_name or ""
        ),
        "date_JOB": st.session_state.date_str,
        "population_totale": st.session_state.population_agglo,
        "nombre_arrets": len(st.session_state.indicateurs_arrets),
        "vehicules_km_total": float(total_vk_plage["total_km_plage"].sum()),
        "vehicules_km_bus": float(vk_par_mode.get("Bus", 0)),
        "vehicules_km_metro": float(vk_par_mode.get("Métro", 0)),
        "vehicules_km_tram": float(vk_par_mode.get("Tram", 0)),
    }


def benchmark_page(lang="fr"):
    st.markdown("---")
    st.header(t("benchmark.header", lang))
    st.caption(t("benchmark.caption", lang))

    reseau_actuel = st.session_state.get("nom_reseau_str")
    ligne_benchmark = construire_ligne_benchmark()

    if ligne_benchmark is None:
        if st.session_state.feed is None:
            st.info(t("benchmark.aucun_gtfs", lang))
        else:
            st.info(t("benchmark.prerequis_manquant", lang))
    else:
        if ligne_benchmark["population_totale"] is None:
            st.warning(t("benchmark.population_inconnue", lang))
        if st.button(t("benchmark.bouton_enregistrer", lang, reseau=reseau_actuel)):
            import pandas as pd

            fusionner_et_envoyer_csv(
                pd.DataFrame([ligne_benchmark]),
                NOM_FICHIER_HF,
                CHEMIN_LOCAL,
                colonne_cle="reseau",
                valeur_cle=reseau_actuel,
            )
            st.success(t("benchmark.succes_enregistrement", lang, reseau=reseau_actuel))

    tableau_benchmark = lire_csv_partage(NOM_FICHIER_HF, CHEMIN_LOCAL)
    if tableau_benchmark is None or tableau_benchmark.empty:
        st.info(t("benchmark.index_vide", lang))
        return

    html_benchmark = generer_html_str(tableau_benchmark, reseau_actuel=reseau_actuel)
    st.components.v1.html(html_benchmark, height=760, scrolling=False)
