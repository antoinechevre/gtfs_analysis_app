"""
Application d'analyse GTFS - Interface principale

"""

from IPython.display import IFrame

import random
from datetime import datetime

import sys

sys.path.append('..')
import bs4
import gtfs_kit as gk
import os
import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.geometry import LineString
from IPython.display import HTML
import folium
from folium import plugins
import numpy as np
import branca.colormap as cm

from src.utils import (
    charger_gtfs,
    longueur_lignes,
    km_par_ligne_jour,
    km_par_ligne_plage,
    obtenir_service_ids_pour_date,
    exporter_df_to_csv,
    exporter_geojson,
    exporter_gdf_to_csv,
)
from src.arrets import calculer_indicateurs_arrets, afficher_statistiques
from src.cartographie import creer_carte_troncons, create_carte_arrets 
from src.create_troncons_uniques import creer_troncons_uniques
from src.indicateurs_troncons import compute_indicateurs_troncons

from src.info_reseau import dates_service, recuperer_logo_reseau, nom_reseau

from src.export_html import (
    exporter_tableau_lignes_html,
    exporter_camembert_html,
    exporter_statistiques_html,
)
import streamlit as st

import tempfile
import pandas as pd
import streamlit as st

from src.utils import charger_gtfs, obtenir_service_ids_pour_date
from views.home import home_page
from views.arrets import arrets_page
from views.troncons import troncons_page




# Configuration de la page
st.set_page_config(page_title="Analyse GTFS", page_icon="🚌", layout="wide")

# Titre principal
st.title("🚌 Analyse GTFS - Indicateurs de Transport")

# Navigation horizontale en haut
st.markdown(
    """
<style>
.stButton button {
    width: 100% !important;
    margin: 0 !important;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown("---")
col1, col2, col3, col4 = st.columns([1, 1, 1, 3])  # 4 colonnes pour équilibrer l'espace

with col1:
    if st.button("🏠 Accueil", use_container_width=True):
        st.session_state.selected_page = "Accueil"

with col2:
    if st.button("📍 Arrêts", use_container_width=True):
        st.session_state.selected_page = "Arrêts"

with col3:
    if st.button("🛤️ Lignes", use_container_width=True):
        st.session_state.selected_page = "Lignes"

with col4:
    st.write("")  # Espace vide pour équilibrer


# Initialiser la page sélectionnée si pas déjà fait
if "selected_page" not in st.session_state:
    st.session_state.selected_page = "Accueil"

# Barre latérale pour les paramètres uniquement
st.sidebar.header("📁 Paramètres d'analyse")
uploaded_file = st.sidebar.file_uploader("Uploader le fichier GTFS (zip)", type="zip")

# Variables globales pour stocker les résultats
if "feed" not in st.session_state:
    st.session_state.feed = None
if "active_service_ids" not in st.session_state:
    st.session_state.active_service_ids = None
if "date_str" not in st.session_state:
    st.session_state.date_str = None
if "indicateurs_arrets" not in st.session_state:
    st.session_state.indicateurs_arrets = None
if "indicateurs_bus" not in st.session_state:
    st.session_state.indicateurs_bus = None
if "indicateurs_tram" not in st.session_state:
    st.session_state.indicateurs_tram = None
if "indicateurs_metro" not in st.session_state:
    st.session_state.indicateurs_metro = None
if "indicateurs_trolley" not in st.session_state:
    st.session_state.indicateurs_trolley = None
if "total_vk_plage" not in st.session_state:
    st.session_state.total_vk_plage = None
if "modes_disponibles" not in st.session_state:
    st.session_state.modes_disponibles = None
if "last_date_str" not in st.session_state:
    st.session_state.last_date_str = None
if "nom_reseau_str" not in st.session_state:
    st.session_state.nom_reseau_str = None
if "zip_path" not in st.session_state:
    st.session_state.zip_path = None
if "chemin_logo" not in st.session_state:
    st.session_state.chemin_logo = None
if "last_uploaded_name" not in st.session_state:
    st.session_state.last_uploaded_name = None


# Fonction pour charger les données. La date d'analyse (date_JOB) n'est
# pas choisie par l'utilisateur : elle est déterminée automatiquement à
# partir du GTFS (un mardi ou un jeudi tiré au hasard dans la plage de
# service fiable, voir src/info_reseau.dates_service).
def charger_donnees_gtfs():
    if uploaded_file is None:
        return False

    # Ne recharger le GTFS (et le logo, qui nécessite une requête réseau)
    # que si un nouveau fichier a été uploadé, pas à chaque interaction
    nouveau_fichier = uploaded_file.name != st.session_state.last_uploaded_name

    if not nouveau_fichier and st.session_state.feed is not None:
        return True

    # Sauvegarder temporairement le fichier (conservé pour toute la
    # session : create_carte_arrets recharge le feed depuis ce chemin
    # pour tracer les lignes)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
        tmp_file.write(uploaded_file.read())
        zip_path = tmp_file.name

    try:
        # Charger le GTFS
        with st.spinner("Chargement du fichier GTFS..."):
            feed = charger_gtfs(zip_path)

        # Plage de service fiable et jour ouvré de base (mardi/jeudi au hasard)
        _, _, _, date_JOB = dates_service(feed)
        date_str = date_JOB

        # Obtenir les services actifs
        active_service_ids = obtenir_service_ids_pour_date(feed, date_str)

        # Nom du réseau et logo (best-effort : le logo nécessite une
        # requête réseau vers le site de l'agence, ne doit pas bloquer
        # l'appli en cas d'échec)
        reseau_str = str(nom_reseau(feed))
        try:
            chemin_logo = recuperer_logo_reseau(feed, dossier_sortie=tempfile.gettempdir())
        except Exception:
            chemin_logo = None

        # Stocker dans session_state
        st.session_state.feed = feed
        st.session_state.active_service_ids = active_service_ids
        st.session_state.date_str = date_str
        st.session_state.zip_path = zip_path
        st.session_state.nom_reseau_str = reseau_str
        st.session_state.chemin_logo = chemin_logo
        st.session_state.last_uploaded_name = uploaded_file.name
        st.session_state.indicateurs_arrets = None  # Réinitialiser les indicateurs
        st.session_state.indicateurs_bus = None
        st.session_state.indicateurs_tram = None
        st.session_state.indicateurs_metro = None
        st.session_state.indicateurs_trolley = None
        st.session_state.total_vk_plage = None
        st.session_state.modes_disponibles = None

        return True

    except Exception as e:
        st.error(f"Erreur lors du chargement : {e}")
        os.unlink(zip_path)
        return False


# Charger les données automatiquement si nécessaire
charger_donnees_gtfs()

# Navigation entre les pages
if st.session_state.selected_page == "Accueil":
    home_page()
elif st.session_state.selected_page == "Arrêts":
    arrets_page()
elif st.session_state.selected_page == "Lignes":
    troncons_page()
