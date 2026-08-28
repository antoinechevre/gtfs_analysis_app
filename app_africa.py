"""
GTFS Analysis Africa - Interface dédiée aux réseaux de transport africains

App séparée de app.py (pas un mode d'app.py) : catalogue GTFS propre
(data/GTFS_Africa, cf. data/GTFS_Africa/_provenance.json), onglets
spécifiques à ce que permet la donnée disponible hors de France (pas de
Base Permanente des Équipements ni de population Wikidata/BPE fiable) —
Équipements (OpenStreetMap pondéré, cf. extraire_amenities_osm.py),
Accessibilité (population/équipements accessibles en 60 min, cf.
index_accessibility_notebook_africa.ipynb) et Benchmark villes africaines.
Déployée séparément sur son propre Space Hugging Face
(antoinechevre/GTFS_Analysis_Africa, cf. scripts/deploy_hf_africa.sh) —
codebase dupliqué à dessein (cf. échange avec l'utilisateur) plutôt qu'un
mode conditionnel de app.py, pour rester deux apps clairement distinctes.
"""

import os
import sys
import tempfile

sys.path.append('..')

import streamlit as st

from src.utils import (
    charger_gtfs,
    obtenir_service_ids_pour_date,
    etendue_geographique_km,
    fusionner_agences_en_une,
    ville_str_depuis_fichier,
)
from src.info_reseau import charger_ou_calculer_dates_service, recuperer_logo_reseau
from src.population import population_agglomeration, deviner_ville_depuis_nom_fichier
from src.hf_cache import envoyer_vers_hf, lister_fichiers_hf, recuperer_depuis_hf
from src.worldpop import charger_ou_construire_grille_population_reseau, RESOLUTION_M_AFRIQUE
from src.i18n import t, LANGUES
from views.home import home_page
from views.arrets import arrets_page
from views.troncons import troncons_page
from views.equipements import equipements_page
from views.accessibilite import accessibilite_page
from views.isochrone_carreaux import isochrone_carreaux_page
from views.benchmark import benchmark_afrique_page


class TropAgencesError(Exception):
    """Levée quand le GTFS regroupe trop d'agences ET est géographiquement
    trop étendu (plusieurs villes distantes) pour être traité par l'app."""


SEUIL_ETENDUE_REGIONALE_KM = 300

# Préfixe HF dédié (dataset partagé antoinechevre/ww_GTFS, cf. src/hf_cache.py)
# séparé de "GTFS/" (catalogue standard, app.py) : les GTFS africains restent
# groupés à part, jamais mélangés au catalogue France/monde de l'app standard.
PREFIXE_HF = "GTFS_Africa"


# Configuration de la page
st.set_page_config(page_title="GTFS Analysis Africa", page_icon="🌍", layout="wide")

if "lang" not in st.session_state:
    st.session_state.lang = "fr"

disable_lang_switch = os.environ.get("GTFS_DISABLE_LANG_SWITCH", "0") == "1"
if disable_lang_switch:
    st.session_state.lang = "fr"
else:
    st.sidebar.selectbox(
        t("app.sidebar_langue", st.session_state.lang),
        options=list(LANGUES.keys()),
        format_func=lambda code: LANGUES[code],
        key="lang",
    )
lang = st.session_state.lang

st.title(t("africa.title", lang))

# Avertissement permanent sur la qualité/fraîcheur des données : contexte
# structurellement différent de la France (pas de recensement fiable à
# l'échelle infracommunale, couverture OSM très inégale selon les villes/
# quartiers, GTFS parfois figés depuis plusieurs années — cf. data/GTFS_Africa/
# _provenance.json, certains fichiers datent de 2018-2019). Répété (pas
# seulement ici) sur les onglets Équipements/Accessibilité/Benchmark, là où
# ces limites pèsent le plus directement sur l'interprétation des résultats.
st.warning(t("africa.avertissement_general", lang))

st.markdown(
    """
<style>
.stButton button {
    width: 100% !important;
    margin: 0 !important;
}
/* Nav à deux niveaux (même principe que le projet sœur Accessibility_analysis,
   app.py) : niveau 1 (section) en aplat plein, niveau 2 (sous-page) en
   contour seul et légèrement en retrait, pour se lire comme un sous-menu. */
.st-key-nav_niveau1 [data-testid="stButtonGroup"] button,
.st-key-nav_niveau2 [data-testid="stButtonGroup"] button {
    padding: .65rem 1rem;
    min-height: 44px;
}
.st-key-nav_niveau1 [data-testid="stButtonGroup"] button {
    font-size: 1rem;
    font-weight: 700;
}
.st-key-nav_niveau1 [data-testid="stButtonGroup"] button[aria-checked="true"] {
    background: #0E7C7B !important;
    border-color: #0E7C7B !important;
}
.st-key-nav_niveau1 [data-testid="stButtonGroup"] button[aria-checked="true"] p {
    color: #FAFAF8 !important;
}
.st-key-nav_niveau2 {
    background: rgba(14, 124, 123, 0.07);
    border-radius: 10px;
    padding: .5rem .6rem .35rem;
    margin-top: -.3rem;
}
.st-key-nav_niveau2 [data-testid="stButtonGroup"] button {
    font-size: .85rem;
    font-weight: 500;
}
.st-key-nav_niveau2 [data-testid="stButtonGroup"] button[aria-checked="true"] {
    background: transparent !important;
    border: 1.5px solid #0E7C7B !important;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown("---")

if "selected_page" not in st.session_state:
    st.session_state.selected_page = "Accueil"

# Navigation à deux niveaux (même principe que le projet sœur
# Accessibility_analysis, app.py) : les pages dérivées de la grille de
# population/TTM (Accessibilité, Équipements, Isochrone carreaux) sont
# regroupées sous "Analyse accessibilité urbaine", à côté d'Accueil,
# Analyse réseau (Arrêts/Lignes, dérivées du seul GTFS) et Benchmark, qui
# n'ont pas de lien direct entre eux.
GROUPES_NAV = {
    "Accueil": ["Accueil"],
    "Analyse réseau": ["Arrêts", "Lignes"],
    "Analyse accessibilité urbaine": ["Accessibilité", "Équipements", "Isochrone carreaux"],
    "Benchmark": ["Benchmark Afrique"],
}
LIBELLES_GROUPE = {
    "Accueil": t("app.groupe_accueil", lang),
    "Analyse réseau": t("app.groupe_analyse_reseau", lang),
    "Analyse accessibilité urbaine": t("app.groupe_accessibilite_urbaine", lang),
    "Benchmark": t("app.groupe_benchmark", lang),
}
LIBELLES_PAGE = {
    "Arrêts": t("app.nav_arrets", lang),
    "Lignes": t("app.nav_lignes", lang),
    "Accessibilité": t("app.nav_accessibilite", lang),
    "Équipements": t("app.nav_equipements", lang),
    "Isochrone carreaux": t("app.nav_isochrone_carreaux", lang),
    "Benchmark Afrique": t("app.nav_benchmark_afrique", lang),
}
GROUPE_DE_LA_PAGE = {page: groupe for groupe, pages in GROUPES_NAV.items() for page in pages}

with st.container(key="nav_niveau1"):
    groupe_choisi = st.segmented_control(
        "Section",
        options=list(GROUPES_NAV.keys()),
        format_func=lambda g: LIBELLES_GROUPE[g],
        default=GROUPE_DE_LA_PAGE.get(st.session_state.selected_page, "Accueil"),
        required=True,
        label_visibility="collapsed",
        key="nav_groupe",
    )

pages_du_groupe = GROUPES_NAV[groupe_choisi]
if len(pages_du_groupe) == 1:
    st.session_state.selected_page = pages_du_groupe[0]
else:
    with st.container(key="nav_niveau2"):
        st.session_state.selected_page = st.segmented_control(
            "Page",
            options=pages_du_groupe,
            format_func=lambda p: LIBELLES_PAGE[p],
            default=(
                st.session_state.selected_page
                if st.session_state.selected_page in pages_du_groupe
                else pages_du_groupe[0]
            ),
            required=True,
            label_visibility="collapsed",
            key="nav_sous_page",
        )

# Barre latérale
st.sidebar.header(t("app.sidebar_header", lang))
uploaded_file = st.sidebar.file_uploader(t("app.sidebar_uploader", lang), type="zip")

AUCUN_GTFS_LOCAL = t("app.aucun_gtfs_local", lang)
GTFS_DATA_DIR = os.path.join(os.getcwd(), "data", "GTFS_Africa")
gtfs_locaux_disque = sorted(
    f for f in os.listdir(GTFS_DATA_DIR) if f.lower().endswith(".zip")
) if os.path.isdir(GTFS_DATA_DIR) else []
# Union avec le dossier dédié du dataset HF partagé (préfixe GTFS_Africa/,
# séparé de GTFS/ — cf. PREFIXE_HF) : un GTFS ajouté sur un déploiement
# précédent (upload, ou déposé à la main puis renvoyé vers HF, cf. plus bas)
# reste disponible même sans stockage persistant sur ce Space.
gtfs_locaux_hf = sorted(f for f in lister_fichiers_hf(PREFIXE_HF) if f.lower().endswith(".zip"))
gtfs_locaux = sorted(set(gtfs_locaux_disque) | set(gtfs_locaux_hf))

gtfs_options = [AUCUN_GTFS_LOCAL] + gtfs_locaux
gtfs_query_param = st.query_params.get("gtfs")
index_gtfs_defaut = gtfs_options.index(gtfs_query_param) if gtfs_query_param in gtfs_locaux else 0

disable_gtfs_catalog = os.environ.get("GTFS_DISABLE_CATALOG_SELECT", "0") == "1"
if disable_gtfs_catalog:
    gtfs_local_choisi = AUCUN_GTFS_LOCAL
else:
    gtfs_local_choisi = st.sidebar.selectbox(
        t("app.sidebar_gtfs_existant", lang),
        options=gtfs_options,
        index=index_gtfs_defaut,
    )

# Couche population (WorldPop) optionnelle sur les cartes arrêts/lignes,
# cf. app.py — calculée seulement à la demande.
afficher_couche_population = st.sidebar.checkbox(t("app.sidebar_couche_population", lang))

# Variables de session
for cle in (
    "feed", "active_service_ids", "date_str", "indicateurs_arrets", "indicateurs_par_mode",
    "total_vk_plage", "modes_disponibles", "last_date_str", "nom_reseau_str", "zip_path",
    "chemin_logo", "last_uploaded_name", "population_agglo", "annee_population",
    "grille_population", "accessibilite_population_60min", "accessibilite_equipements_60min",
):
    if cle not in st.session_state:
        st.session_state[cle] = None
if "is_reseau_africain" not in st.session_state:
    st.session_state.is_reseau_africain = True


def charger_ou_calculer_grille_population():
    """Cf. app.py — identique, dupliquée ici (app_africa.py est une app
    séparée, pas un module important app.py)."""
    if st.session_state.grille_population is not None:
        return st.session_state.grille_population

    with st.spinner(t("app.spinner_grille_population", lang)):
        try:
            grille = charger_ou_construire_grille_population_reseau(
                st.session_state.feed, st.session_state.nom_reseau_str, resolution_m=RESOLUTION_M_AFRIQUE,
            )
        except Exception as e:
            st.sidebar.error(t("app.erreur_grille_population", lang, erreur=e))
            return None

    st.session_state.grille_population = grille
    return grille


def charger_donnees_gtfs():
    if uploaded_file is not None:
        nom_gtfs = uploaded_file.name
        lire_gtfs = uploaded_file.read
    elif gtfs_local_choisi != AUCUN_GTFS_LOCAL:
        nom_gtfs = gtfs_local_choisi
        chemin_gtfs_local = os.path.join(GTFS_DATA_DIR, gtfs_local_choisi)
        if not os.path.exists(chemin_gtfs_local):
            with st.spinner(t("app.spinner_recuperation_hf", lang, nom=gtfs_local_choisi)):
                if not recuperer_depuis_hf(f"{PREFIXE_HF}/{gtfs_local_choisi}", chemin_gtfs_local):
                    st.error(t("app.erreur_recuperation_hf", lang, nom=gtfs_local_choisi))
                    return False
        lire_gtfs = lambda: open(chemin_gtfs_local, "rb").read()
    else:
        return False

    nouveau_fichier = nom_gtfs != st.session_state.last_uploaded_name
    if not nouveau_fichier and st.session_state.feed is not None:
        return True

    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
        tmp_file.write(lire_gtfs())
        zip_path = tmp_file.name

    try:
        with st.spinner(t("app.spinner_chargement", lang)):
            feed = charger_gtfs(zip_path)

        nb_agences = len(feed.agency)
        if nb_agences > 3:
            etendue_km = etendue_geographique_km(feed)
            if etendue_km > SEUIL_ETENDUE_REGIONALE_KM:
                raise TropAgencesError(nb_agences, etendue_km)
            nom_agence_fusion = str(feed.agency["agency_name"].iloc[0])
            fusionner_agences_en_une(feed, nom_agence_fusion)
            print(f"✓ {nb_agences} agences fusionnées en une seule ('{nom_agence_fusion}', étendue {etendue_km:.0f} km)")

        # Dérivé du nom de fichier (pas de nom_reseau(feed), basé sur
        # agency_name) : déterministe même pour un GTFS multi-agences (ex:
        # Abidjan/AMUGA, 8 agences), et identique à ce que calculent les
        # notebooks Afrique (cf. src.utils.ville_str_depuis_fichier) — sans
        # ça, les caches HF (grille, TTM, PBF) ne se retrouvaient jamais
        # entre l'app et un notebook exécuté sur le même GTFS.
        reseau_str = ville_str_depuis_fichier(nom_gtfs)
        _, _, _, date_JOB = charger_ou_calculer_dates_service(feed, reseau_str)
        date_str = date_JOB
        active_service_ids = obtenir_service_ids_pour_date(feed, date_str)

        try:
            chemin_logo = recuperer_logo_reseau(feed, dossier_sortie=tempfile.gettempdir())
        except Exception:
            chemin_logo = None

        # Population Wikidata : best-effort, rarement fiable pour ces villes
        # (cf. avertissement en tête de page) — None si non résolue, géré
        # normalement par le reste de l'app (résumé/benchmark sans ce chiffre).
        population_agglo, annee_population = population_agglomeration(reseau_str)
        if population_agglo is None:
            ville_devinee = deviner_ville_depuis_nom_fichier(nom_gtfs)
            if ville_devinee and ville_devinee != reseau_str:
                population_agglo, annee_population = population_agglomeration(ville_devinee)

        st.session_state.feed = feed
        st.session_state.active_service_ids = active_service_ids
        st.session_state.date_str = date_str
        st.session_state.zip_path = zip_path
        st.session_state.nom_reseau_str = reseau_str
        st.session_state.chemin_logo = chemin_logo
        st.session_state.population_agglo = population_agglo
        st.session_state.annee_population = annee_population
        st.session_state.last_uploaded_name = nom_gtfs
        st.session_state.indicateurs_arrets = None
        st.session_state.indicateurs_par_mode = None
        st.session_state.total_vk_plage = None
        st.session_state.modes_disponibles = None
        st.session_state.grille_population = None
        st.session_state.accessibilite_population_60min = None
        st.session_state.accessibilite_equipements_60min = None
        st.session_state.isochrone_carreaux_resultats = None

        # GTFS uploadé et jamais vu : renvoyé vers le dossier HF dédié
        # (PREFIXE_HF), jamais vers "GTFS/" (catalogue standard, app.py).
        if uploaded_file is not None and nom_gtfs not in gtfs_locaux:
            if envoyer_vers_hf(zip_path, f"{PREFIXE_HF}/{nom_gtfs}"):
                st.toast(t("app.toast_envoi_hf", lang, nom=nom_gtfs))

        return True

    except TropAgencesError as e:
        nb_agences_err, etendue_km_err = e.args
        st.error(t("app.erreur_trop_agences", lang, n=nb_agences_err, etendue=round(etendue_km_err)))
        os.unlink(zip_path)
        st.stop()

    except Exception as e:
        st.error(t("app.erreur_chargement", lang, erreur=e))
        os.unlink(zip_path)
        return False


charger_donnees_gtfs()

if afficher_couche_population and st.session_state.feed is not None:
    charger_ou_calculer_grille_population()

if st.session_state.selected_page == "Accueil":
    home_page(lang)
elif st.session_state.selected_page == "Arrêts":
    arrets_page(lang)
elif st.session_state.selected_page == "Lignes":
    troncons_page(lang)
elif st.session_state.selected_page == "Équipements":
    equipements_page(lang)
elif st.session_state.selected_page == "Accessibilité":
    accessibilite_page(lang)
elif st.session_state.selected_page == "Benchmark Afrique":
    benchmark_afrique_page(lang)
elif st.session_state.selected_page == "Isochrone carreaux":
    isochrone_carreaux_page(lang)
