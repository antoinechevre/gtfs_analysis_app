"""
Page d'accueil - Application d'analyse GTFS
"""

import streamlit as st

from src.i18n import t


def home_page(lang="fr"):
    st.markdown("---")

    # Section Hackathon
    st.markdown(t("home.hackathon_md", lang))

    st.markdown("---")

    # Liens rapides
    st.markdown(t("home.liens_md", lang))

    st.markdown("---")

    # Objectifs
    st.markdown(t("home.objectifs_md", lang))

    st.markdown("---")

    # Fonctionnalités disponibles
    st.markdown(t("home.fonctionnalites_md", lang))

    st.markdown("---")

    # Section Auteurs
    st.markdown(t("home.contributeurs_md", lang))
