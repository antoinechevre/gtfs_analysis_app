"""
Page d'accueil dédiée à app_africa.py — même modèle que views/home.py du
projet sœur Accessibility_analysis (github.com/antoinechevre/
Accessibility_analysis) : intro, onglets Objectifs/Fonctionnalités/Liens
avec expanders pour le détail, plutôt que le home.py générique partagé
avec app.py (qui ne mentionne aucune des spécificités Afrique :
équipements OSM, accessibilité r5py, isochrone carreaux, benchmark
villes africaines).
"""

import streamlit as st

from src.i18n import t


def home_page_afrique(lang="fr"):
    st.markdown(t("home_afrique.intro_md", lang))

    st.markdown("---")
    st.markdown(t("home_afrique.titre_section_md", lang))

    onglet_objectifs, onglet_fonctionnalites, onglet_liens = st.tabs(
        [t("home_afrique.onglet_objectifs", lang), t("home_afrique.onglet_fonctionnalites", lang), t("home_afrique.onglet_liens", lang)]
    )

    with onglet_objectifs:
        st.markdown(t("home_afrique.objectifs_md", lang))

    with onglet_fonctionnalites:
        st.markdown(t("home_afrique.fonctionnalites_md", lang))
        with st.expander(t("home_afrique.expander_equipements_titre", lang)):
            st.markdown(t("home_afrique.expander_equipements_md", lang))
        with st.expander(t("home_afrique.expander_indicateurs_titre", lang)):
            st.markdown(t("home_afrique.expander_indicateurs_md", lang))

    with onglet_liens:
        st.markdown(t("home_afrique.liens_md", lang))
        st.warning(t("africa.avertissement_general", lang))

    st.markdown("---")
    _explications_analyse_gtfs_afrique(lang)

    st.markdown("---")
    st.markdown(t("home_afrique.credits_md", lang))


def _explications_analyse_gtfs_afrique(lang="fr"):
    """Présentation de l'analyse réseau GTFS (arrêts/lignes) — même principe
    que explications_analyse_gtfs() côté projet sœur Accessibility_analysis
    (views/home.py), mais reprend seulement Arrêts/Lignes (pas d'isochrone
    arrêt à arrêt séparée côté app_africa.py, cf. GROUPES_NAV["Analyse
    réseau"] dans app_africa.py)."""
    st.markdown(t("home_afrique.titre_gtfs_md", lang))
    st.markdown(t("home_afrique.gtfs_intro_md", lang))

    onglet_fonctionnalites_gtfs, onglet_liens_gtfs = st.tabs(
        [t("home_afrique.onglet_fonctionnalites", lang), t("home_afrique.onglet_liens", lang)]
    )

    with onglet_fonctionnalites_gtfs:
        st.markdown(t("home_afrique.gtfs_fonctionnalites_md", lang))

    with onglet_liens_gtfs:
        st.markdown(t("home_afrique.gtfs_liens_md", lang))
