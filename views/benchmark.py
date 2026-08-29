"""
Page Benchmark - nuage de points comparant tous les réseaux déjà
enregistrés dans l'index de benchmark partagé (bouton "Enregistrer ce
réseau" ci-dessous, ou la cellule équivalente du notebook), avec le
réseau actuellement chargé (s'il y en a un) surligné en rouge parmi les
autres en bleu.

Repris du même principe que l'onglet Benchmark de l'app sœur
"accessibility" (views/benchmark_reseaux.py, antoinechevre/
Accessibility_analysis) : sur l'onglet standard, métriques transit
(véhicules.km, nombre d'arrêts) — l'app sœur a un deuxième graphique
identique. Sur l'onglet Afrique, un seul graphique (équivalent du premier
et seul retenu de l'app sœur, "Accessibilité aux équipements") : colonnes
véhicules.km/arrêts masquées pour ce tableau, cf. _afficher_benchmark.
"""

import os

import streamlit as st

from src.hf_cache import lire_csv_partage, fusionner_et_envoyer_csv
from src.nuage_points_benchmark import generer_html_str
from src.population import deviner_ville_principale
from src.i18n import t

NOM_FICHIER_HF = "benchmark/index_benchmark_reseaux.csv"
CHEMIN_LOCAL = os.path.join("data", "benchmark", "index_benchmark_reseaux.csv")

# Index séparé pour les réseaux africains (cf. app.py, boîte de dialogue
# "Villes africaines" / data/GTFS_Africa) : pas de population Wikidata
# fiable ni de BPE pour la plupart de ces villes (cf. construire_ligne_benchmark
# ci-dessous, qui y substitue les indicateurs de la page Accessibilité —
# population/équipements accessibles en 60 min, cf. views/accessibilite.py)
# — mélanger les deux fausserait le nuage de points standard (échelles/
# indicateurs différents) et l'index France, déjà partagé avec l'app sœur.
NOM_FICHIER_HF_AFRIQUE = "benchmark/index_benchmark_reseaux_afrique.csv"
CHEMIN_LOCAL_AFRIQUE = os.path.join("data", "benchmark", "index_benchmark_reseaux_afrique.csv")


def construire_ligne_benchmark():
    """
    Construit la ligne de benchmark pour le réseau actuellement chargé, à
    partir des données déjà calculées dans session_state (aucun recalcul).
    Renvoie None si un prérequis manque (feed non chargé, tronçons/vk pas
    encore calculés sur la page Lignes...).

    Pour un réseau africain (st.session_state.is_reseau_africain), ajoute
    les indicateurs de la page Accessibilité (population_accessible_60min /
    equipements_accessibles_60min, cf. views/accessibilite.py) — None s'ils
    n'y ont pas encore été calculés (page pas visitée, ou TTM pas encore
    disponible pour ce réseau) : à l'appelant/au lecteur du CSV de gérer les
    valeurs manquantes, pas de blocage ici.
    """
    if st.session_state.feed is None or st.session_state.nom_reseau_str is None:
        return None
    if st.session_state.total_vk_plage is None or st.session_state.indicateurs_arrets is None:
        return None

    total_vk_plage = st.session_state.total_vk_plage
    vk_par_mode = total_vk_plage.groupby("mode")["total_km_plage"].sum()

    ligne = {
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

    if st.session_state.get("is_reseau_africain"):
        ligne["population_accessible_60min"] = st.session_state.get("accessibilite_population_60min")
        ligne["equipements_accessibles_60min"] = st.session_state.get("accessibilite_equipements_60min")

    return ligne


def _afficher_benchmark(lang, africain):
    """
    Corps commun aux deux onglets Benchmark (standard / Afrique, cf.
    benchmark_page et benchmark_afrique_page ci-dessous) : chacun est
    toujours consultable (nuage de points de son propre index), que le
    réseau actuellement chargé corresponde ou non à son type — seul le
    bouton "Enregistrer" n'apparaît que sur l'onglet correspondant au type
    du réseau chargé (un réseau standard n'a pas les indicateurs
    d'accessibilité attendus par l'index Afrique, et réciproquement pas de
    population Wikidata/BPE fiable pour un réseau africain).
    """
    nom_fichier_hf = NOM_FICHIER_HF_AFRIQUE if africain else NOM_FICHIER_HF
    chemin_local = CHEMIN_LOCAL_AFRIQUE if africain else CHEMIN_LOCAL

    reseau_actuel = st.session_state.get("nom_reseau_str")
    reseau_correspond = st.session_state.get("is_reseau_africain", False) == africain

    if st.session_state.feed is None:
        st.info(t("benchmark.aucun_gtfs", lang))
    elif not reseau_correspond:
        cle_message = "benchmark.autre_type_reseau_afrique" if africain else "benchmark.autre_type_reseau_standard"
        st.info(t(cle_message, lang, reseau=reseau_actuel))
    else:
        ligne_benchmark = construire_ligne_benchmark()
        if ligne_benchmark is None:
            st.info(t("benchmark.prerequis_manquant", lang))
        else:
            if ligne_benchmark["population_totale"] is None:
                st.warning(t("benchmark.population_inconnue", lang))
            if africain and ligne_benchmark.get("population_accessible_60min") is None:
                st.info(t("benchmark.accessibilite_manquante", lang))
            if st.button(t("benchmark.bouton_enregistrer", lang, reseau=reseau_actuel)):
                import pandas as pd

                fusionner_et_envoyer_csv(
                    pd.DataFrame([ligne_benchmark]),
                    nom_fichier_hf,
                    chemin_local,
                    colonne_cle="reseau",
                    valeur_cle=reseau_actuel,
                )
                st.success(t("benchmark.succes_enregistrement", lang, reseau=reseau_actuel))

    tableau_benchmark = lire_csv_partage(nom_fichier_hf, chemin_local)
    if tableau_benchmark is None or tableau_benchmark.empty:
        st.info(t("benchmark.index_vide", lang))
        return

    if africain:
        # Un seul graphique, indicateurs d'accessibilité uniquement (comme
        # le premier des deux graphiques de l'app sœur, "Accessibilité aux
        # équipements") : masque les colonnes véhicules.km/arrêts plutôt que
        # de les mélanger dans le même menu Y que population_accessible_60min/
        # equipements_accessibles_60min — generer_html_str (options_y) ne
        # propose de toute façon que les colonnes présentes dans le tableau.
        colonnes_a_garder = [
            c for c in tableau_benchmark.columns
            if c in ("reseau", "ville_principale", "population_totale",
                      "population_accessible_60min", "equipements_accessibles_60min")
        ]
        tableau_benchmark = tableau_benchmark[colonnes_a_garder]

    html_benchmark = generer_html_str(
        tableau_benchmark, reseau_actuel=reseau_actuel if reseau_correspond else None
    )
    st.components.v1.html(html_benchmark, height=760, scrolling=False)


def benchmark_page(lang="fr"):
    st.markdown("---")
    st.header(t("benchmark.header", lang))
    st.caption(t("benchmark.caption", lang))
    _afficher_benchmark(lang, africain=False)


def benchmark_afrique_page(lang="fr"):
    st.markdown("---")
    st.header(t("benchmark.header_afrique", lang))
    st.caption(t("benchmark.caption_afrique", lang))
    st.warning(t("benchmark.avertissement_comparabilite", lang))
    _afficher_benchmark(lang, africain=True)
