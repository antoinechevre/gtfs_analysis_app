"""
Application d'analyse GTFS - Interface principale

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
)
from src.info_reseau import charger_ou_calculer_dates_service, recuperer_logo_reseau, nom_reseau
from src.population import population_agglomeration, deviner_ville_depuis_nom_fichier
from src.hf_cache import envoyer_vers_hf, lister_fichiers_hf, recuperer_depuis_hf
from src.telecharger_transitland import rechercher_feeds, telecharger_feed
from src.i18n import t, LANGUES
from views.home import home_page
from views.arrets import arrets_page
from views.troncons import troncons_page
from views.benchmark import benchmark_page


class TropAgencesError(Exception):
    """Levée quand le GTFS regroupe trop d'agences ET est géographiquement
    trop étendu (plusieurs villes distantes) pour être traité par l'app."""


# Au-delà de cette diagonale de bounding box (km), un GTFS à plus de 3
# agences est considéré régional (plusieurs villes distantes) et rejeté
# plutôt que fusionné en une seule agence. Calibré entre IDFM (~240 km,
# accepté via GTFS_NOM_RESEAU_FORCE) et VBB/Berlin (~584 km, rejeté).
SEUIL_ETENDUE_REGIONALE_KM = 300


# Exception au garde-fou "max 3 agences" (cf. TropAgencesError ci-dessous),
# par nom de fichier GTFS : IDFM-gtfs.zip regroupe des dizaines d'agences
# (RATP, SNCF, Optile...) mais reste un réseau urbain traitable — cf.
# gtfs_notebook_idf.ipynb, dont cette app reprend la séquence (RER
# distingué par agency_id, Transilien et TER exclus, cache par réseau, cf.
# views/troncons.py). Nom de réseau forcé plutôt que dérivé de agency.txt
# (nom_reseau() concaténerait des dizaines de noms d'agence en une chaîne
# de plusieurs centaines de caractères, invalide comme nom de fichier).
# Vérifiée uniquement pour un GTFS choisi dans le catalogue existant
# (uploaded_file is None dans charger_donnees_gtfs), jamais pour un upload :
# l'exception est pour CE fichier précis, pas pour n'importe quel GTFS qui
# porterait le même nom.
GTFS_NOM_RESEAU_FORCE = {
    "IDFM-gtfs.zip": "IDFM",
    # IDFM-gtfs_merge.zip : même GTFS, juste agency_name uniformisé à
    # "IDFM" (cf. src/merge_gtfs_IDFM.py) — toujours 64 agency_id d'origine.
    "IDFM-gtfs_merge.zip": "IDFM",
    # NYC_gtfs_merge.zip regroupe 6 agences (une par feed d'origine, cf.
    # src/merge_gtfs_NYC.py) mais reste un unique réseau urbain (MTA).
    "NYC_gtfs_merge.zip": "NYC",
}

# Logo forcé pour les mêmes réseaux que GTFS_NOM_RESEAU_FORCE : le fetch
# automatique (recuperer_logo_reseau, via agency_url) échoue pour IDFM,
# donc on sert un logo statique déposé à la main plutôt que de laisser
# l'app sans logo.
GTFS_LOGO_FORCE = {
    "IDFM-gtfs.zip": os.path.join("data", "logos", "Logo_IDFM.png"),
    "IDFM-gtfs_merge.zip": os.path.join("data", "logos", "Logo_IDFM.png"),
}

# Population forcée (habitants, année) pour un reseau_str donné : Wikidata
# (cf. src/population.py) ne résout que des noms de ville, pas des
# acronymes de réseau (IDFM, MTA...) — sans cette table, ces réseaux
# n'auraient jamais de population dans le résumé ni le benchmark.
POPULATION_FORCE = {
    # Île-de-France (desservie par IDFM), recensement INSEE 2021.
    "IDFM": (11_500_000, "2021"),
}


# Configuration de la page
st.set_page_config(page_title="Analyse GTFS", page_icon="🚌", layout="wide")

# Langue de l'interface : initialisée avant tout texte traduit de la page
if "lang" not in st.session_state:
    st.session_state.lang = "fr"

# Sur l'image Docker (déploiement Hugging Face), le sélecteur de langue est
# désactivé et l'interface reste en français
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

# Titre principal
st.title(t("app.title", lang))

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
col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 2])  # 5 colonnes pour équilibrer l'espace

with col1:
    if st.button(t("app.nav_accueil", lang), use_container_width=True):
        st.session_state.selected_page = "Accueil"

with col2:
    if st.button(t("app.nav_arrets", lang), use_container_width=True):
        st.session_state.selected_page = "Arrêts"

with col3:
    if st.button(t("app.nav_lignes", lang), use_container_width=True):
        st.session_state.selected_page = "Lignes"

with col4:
    if st.button(t("app.nav_benchmark", lang), use_container_width=True):
        st.session_state.selected_page = "Benchmark"

with col5:
    st.write("")  # Espace vide pour équilibrer


# Initialiser la page sélectionnée si pas déjà fait
if "selected_page" not in st.session_state:
    st.session_state.selected_page = "Accueil"

# Barre latérale pour les paramètres uniquement
st.sidebar.header(t("app.sidebar_header", lang))
uploaded_file = st.sidebar.file_uploader(t("app.sidebar_uploader", lang), type="zip")

# Alternative à l'upload : choisir un GTFS déjà présent dans data/GTFS ou
# dans le catalogue du dataset HF antoinechevre/ww_GTFS (mêmes
# fichiers, téléversés une fois pour toutes, cf. src/hf_cache.py). Union des
# deux plutôt que l'un OU l'autre : data/GTFS n'est pas versionné par git
# donc vide sur un déploiement fraîchement démarré sans stockage persistant,
# mais peut aussi contenir un fichier déjà téléchargé à la demande lors
# d'une sélection précédente — s'arrêter au premier non-vide masquerait
# alors silencieusement tout le reste du catalogue HF.
AUCUN_GTFS_LOCAL = t("app.aucun_gtfs_local", lang)
GTFS_DATA_DIR = os.path.join(os.getcwd(), "data", "GTFS")
gtfs_locaux_disque = sorted(
    f for f in os.listdir(GTFS_DATA_DIR) if f.lower().endswith(".zip")
) if os.path.isdir(GTFS_DATA_DIR) else []
gtfs_locaux_hf = sorted(f for f in lister_fichiers_hf("GTFS") if f.lower().endswith(".zip"))
gtfs_locaux = sorted(set(gtfs_locaux_disque) | set(gtfs_locaux_hf))

gtfs_options = [AUCUN_GTFS_LOCAL] + gtfs_locaux
# Présélection depuis l'app Accessibilité (paramètre ?gtfs=<nom_fichier.zip>
# dans le lien "Pour analyser le GTFS correspondant") : ignoré silencieusement
# si le fichier ne fait pas partie du catalogue actuel (ex. lien obsolète).
gtfs_query_param = st.query_params.get("gtfs")
index_gtfs_defaut = gtfs_options.index(gtfs_query_param) if gtfs_query_param in gtfs_locaux else 0

# Sur l'image Docker (déploiement Hugging Face), ce sélecteur est masqué :
# seul l'upload manuel reste disponible pour choisir un GTFS.
disable_gtfs_catalog = os.environ.get("GTFS_DISABLE_CATALOG_SELECT", "0") == "1"

if disable_gtfs_catalog:
    gtfs_local_choisi = AUCUN_GTFS_LOCAL
else:
    gtfs_local_choisi = st.sidebar.selectbox(
        t("app.sidebar_gtfs_existant", lang),
        options=gtfs_options,
        index=index_gtfs_defaut,
    )

# Recherche d'un GTFS sur Transitland (cf. src/telecharger_transitland.py),
# pour les réseaux absents du catalogue existant. Le fichier téléchargé
# atterrit dans data/GTFS/ : il apparaît dans le menu déroulant
# ci-dessus au rerun déclenché par le bouton "Télécharger" (pas besoin de
# le rajouter explicitement à gtfs_options ici).
with st.sidebar.expander(t("app.transitland_titre", lang)):
    recherche_transitland = st.text_input(t("app.transitland_recherche", lang))
    if recherche_transitland:
        try:
            resultats_transitland = rechercher_feeds(recherche_transitland)
        except Exception as e:
            st.error(t("app.transitland_erreur_recherche", lang, erreur=e))
            resultats_transitland = []

        if not resultats_transitland:
            st.info(t("app.transitland_aucun_resultat", lang))
        else:
            options_transitland = {
                f"{f.get('onestop_id')} — licence: {(f.get('license') or {}).get('spdx_identifier') or '?'}": f
                for f in resultats_transitland
            }
            choix_transitland = st.selectbox(
                t("app.transitland_choisir", lang), options=list(options_transitland.keys())
            )
            feed_transitland_choisi = options_transitland[choix_transitland]
            url_transitland_choisi = (feed_transitland_choisi.get("urls") or {}).get("static_current")
            if url_transitland_choisi:
                st.caption(url_transitland_choisi)

            if st.button(t("app.transitland_telecharger", lang)):
                nom_fichier_transitland = f"{recherche_transitland.strip().replace(' ', '_')}_gtfs.zip"
                destination_transitland = os.path.join(GTFS_DATA_DIR, nom_fichier_transitland)
                try:
                    with st.spinner(t("app.transitland_telechargement_en_cours", lang)):
                        telecharger_feed(feed_transitland_choisi["onestop_id"], destination_transitland)
                        # Renvoyé vers ww_GTFS (best-effort, comme un upload
                        # manuel) : sinon, seul disponible localement sur ce
                        # Space, perdu au prochain redémarrage sans stockage
                        # persistant, invisible des autres visiteurs/déploiements.
                        envoyer_vers_hf(destination_transitland, f"GTFS/{nom_fichier_transitland}")
                    st.success(t("app.transitland_succes", lang, nom=nom_fichier_transitland))
                    st.rerun()
                except Exception as e:
                    st.error(t("app.transitland_erreur_telechargement", lang, erreur=e))

# Variables globales pour stocker les résultats
if "feed" not in st.session_state:
    st.session_state.feed = None
if "active_service_ids" not in st.session_state:
    st.session_state.active_service_ids = None
if "date_str" not in st.session_state:
    st.session_state.date_str = None
if "indicateurs_arrets" not in st.session_state:
    st.session_state.indicateurs_arrets = None
if "indicateurs_par_mode" not in st.session_state:
    st.session_state.indicateurs_par_mode = None
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
if "population_agglo" not in st.session_state:
    st.session_state.population_agglo = None
if "annee_population" not in st.session_state:
    st.session_state.annee_population = None


# Fonction pour charger les données. La date d'analyse (date_JOB) n'est
# pas choisie par l'utilisateur : elle est déterminée automatiquement à
# partir du GTFS (un mardi ou un jeudi tiré au hasard dans la plage de
# service fiable, voir src/info_reseau.dates_service).
def charger_donnees_gtfs():
    if uploaded_file is not None:
        nom_gtfs = uploaded_file.name
        lire_gtfs = uploaded_file.read
    elif gtfs_local_choisi != AUCUN_GTFS_LOCAL:
        nom_gtfs = gtfs_local_choisi
        chemin_gtfs_local = os.path.join(GTFS_DATA_DIR, gtfs_local_choisi)
        # recuperer_depuis_hf() ne fait rien si déjà présent en local (cas
        # gtfs_locaux_disque) : pas besoin de distinguer les deux sources ici.
        if not os.path.exists(chemin_gtfs_local):
            with st.spinner(t("app.spinner_recuperation_hf", lang, nom=gtfs_local_choisi)):
                if not recuperer_depuis_hf(f"GTFS/{gtfs_local_choisi}", chemin_gtfs_local):
                    st.error(t("app.erreur_recuperation_hf", lang, nom=gtfs_local_choisi))
                    return False
        lire_gtfs = lambda: open(chemin_gtfs_local, "rb").read()
    else:
        return False

    # Ne recharger le GTFS (et le logo, qui nécessite une requête réseau)
    # que si un nouveau fichier a été sélectionné, pas à chaque interaction
    nouveau_fichier = nom_gtfs != st.session_state.last_uploaded_name

    if not nouveau_fichier and st.session_state.feed is not None:
        return True

    # Copie dans un fichier temporaire (conservé pour toute la session :
    # create_carte_arrets recharge le feed depuis ce chemin pour tracer les
    # lignes) plutôt que d'opérer directement sur data/GTFS/<fichier> : entre
    # autres, charger_gtfs() peut réécrire le zip en place si calendar_dates.txt
    # est vide — sur le fichier original de data/GTFS, ça modifierait
    # silencieusement la source versionnée sur le dataset HF.
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
        tmp_file.write(lire_gtfs())
        zip_path = tmp_file.name

    try:
        # Charger le GTFS
        with st.spinner(t("app.spinner_chargement", lang)):
            feed = charger_gtfs(zip_path)

        # L'app ne sait traiter que des GTFS urbains (un GTFS régional
        # regroupant plusieurs villes distantes ferait exploser les temps de
        # calcul et n'a pas de sens pour les indicateurs arrêts/tronçons
        # proposés ici) — sauf exception nommée explicitement (cf.
        # GTFS_NOM_RESEAU_FORCE). Un GTFS avec plus de 3 agences mais
        # géographiquement compact (plusieurs opérateurs administratifs
        # d'une même zone urbaine, ex: Berlin/VBB) est fusionné en une seule
        # agence plutôt que rejeté ; seul un GTFS réellement étendu
        # (plusieurs villes distantes) est refusé.
        nb_agences = len(feed.agency)
        exception_valide = uploaded_file is None and nom_gtfs in GTFS_NOM_RESEAU_FORCE

        if nb_agences > 3 and not exception_valide:
            etendue_km = etendue_geographique_km(feed)
            if etendue_km > SEUIL_ETENDUE_REGIONALE_KM:
                raise TropAgencesError(nb_agences, etendue_km)

            nom_agence_fusion = str(feed.agency["agency_name"].iloc[0])
            fusionner_agences_en_une(feed, nom_agence_fusion)
            print(
                f"✓ {nb_agences} agences fusionnées en une seule "
                f"('{nom_agence_fusion}', étendue {etendue_km:.0f} km)"
            )

        # Nom du réseau, calculé avant dates_service() : sert de clé de
        # cache disque+HF pour son résultat (cf.
        # charger_ou_calculer_dates_service, info_reseau.py).
        reseau_str = GTFS_NOM_RESEAU_FORCE[nom_gtfs] if exception_valide else str(nom_reseau(feed))

        # Plage de service fiable et jour ouvré de base (le plus tardif)
        _, _, _, date_JOB = charger_ou_calculer_dates_service(feed, reseau_str)
        date_str = date_JOB

        # Obtenir les services actifs
        active_service_ids = obtenir_service_ids_pour_date(feed, date_str)

        # Logo (best-effort : nécessite une requête réseau vers le site de
        # l'agence, ne doit pas bloquer l'appli en cas d'échec)
        if exception_valide and nom_gtfs in GTFS_LOGO_FORCE:
            chemin_logo = GTFS_LOGO_FORCE[nom_gtfs]
        else:
            try:
                chemin_logo = recuperer_logo_reseau(feed, dossier_sortie=tempfile.gettempdir())
            except Exception:
                chemin_logo = None

        # Population de la ville (best-effort, via Wikidata cf.
        # src/population.py). Population de la ville-centre, pas de
        # l'agglomération complète (rarement une entité Wikidata fiable
        # selon les pays) — approximation à affiner si besoin.
        # POPULATION_FORCE prime sur Wikidata pour les réseaux dont le nom
        # n'est pas une ville (ex: IDFM). Sinon, reseau_str est essayé en
        # premier ; s'il ne résout rien (cas d'un réseau auto-fusionné,
        # cf. fusionner_agences_en_une ci-dessus, où reseau_str devient un
        # nom d'agence comme "Atac"/"Arriva", pas une ville), le nom du
        # fichier GTFS est essayé en repli (contient souvent la ville,
        # ex: "Roma_gtfs.zip").
        if reseau_str in POPULATION_FORCE:
            population_agglo, annee_population = POPULATION_FORCE[reseau_str]
        else:
            population_agglo, annee_population = population_agglomeration(reseau_str)
            if population_agglo is None:
                ville_devinee = deviner_ville_depuis_nom_fichier(nom_gtfs)
                if ville_devinee and ville_devinee != reseau_str:
                    population_agglo, annee_population = population_agglomeration(ville_devinee)

        # Stocker dans session_state
        st.session_state.feed = feed
        st.session_state.active_service_ids = active_service_ids
        st.session_state.date_str = date_str
        st.session_state.zip_path = zip_path
        st.session_state.nom_reseau_str = reseau_str
        st.session_state.chemin_logo = chemin_logo
        st.session_state.population_agglo = population_agglo
        st.session_state.annee_population = annee_population
        st.session_state.last_uploaded_name = nom_gtfs
        st.session_state.indicateurs_arrets = None  # Réinitialiser les indicateurs
        st.session_state.indicateurs_par_mode = None
        st.session_state.total_vk_plage = None
        st.session_state.modes_disponibles = None

        # GTFS uploadé (pas choisi dans le catalogue existant) et jamais vu :
        # renvoyé vers le dataset HF pour que les prochains déploiements /
        # visiteurs le retrouvent dans "...ou choisir un GTFS déjà présent"
        # sans avoir à le réuploader. Best-effort : n'empêche jamais le
        # chargement en cours de réussir.
        if uploaded_file is not None and nom_gtfs not in gtfs_locaux:
            if envoyer_vers_hf(zip_path, f"GTFS/{nom_gtfs}"):
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


# Charger les données automatiquement si nécessaire
charger_donnees_gtfs()

# Navigation entre les pages
if st.session_state.selected_page == "Accueil":
    home_page(lang)
elif st.session_state.selected_page == "Arrêts":
    arrets_page(lang)
elif st.session_state.selected_page == "Lignes":
    troncons_page(lang)
elif st.session_state.selected_page == "Benchmark":
    benchmark_page(lang)
