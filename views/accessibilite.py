"""
Page Accessibilité - version simplifiée de l'onglet Accessibilité du projet
sœur Accessibility_analysis (github.com/antoinechevre/Accessibility_analysis) :
un seul seuil (60 min) et deux mesures "tout confondu" (pas de découpage par
domaine d'équipement ni par décile de niveau de vie) :
- population accessible en <= 60 min depuis chaque carreau (cumulative_cutoff,
  opportunity="population") ;
- équipements accessibles en <= 60 min, à partir du seul fichier
  data/equipements_osm/{nom_reseau_str}_equipements.gpkg du réseau chargé
  (opportunity="equipements").

Nécessite une matrice de temps de trajet (TTM) pour ce réseau à la
résolution RESOLUTION_M_AFRIQUE (cf. src/worldpop.py — 600m,
index_accessibility_notebook_africa_600m.ipynb), mise en cache sur le
dataset Hugging Face partagé sous
memory_ttm/ttm_{nom_reseau_str}_{RESOLUTION_M_AFRIQUE}m.parquet (cf.
src.utilitaires_matrix.nom_fichier_ttm). Si absente, un bouton permet de
lancer le calcul complet directement depuis l'app (cf.
src.pipeline_accessibilite_afrique.calculer_pipeline_complet) — même
chaîne que le notebook (grille, OSM, équipements, r5py, TTM), mais lourde
(JVM) et bloquante (process Streamlit mono-thread pendant tout le calcul,
plusieurs dizaines de minutes possible) : à l'utilisateur de choisir de la
déclencher en connaissance de cause plutôt qu'un calcul automatique.
"""

import os

import streamlit as st
import streamlit.components.v1 as components

from src.cartographie import fond_carte_kwargs
from src.equipements_osm import compter_equipements_par_carreau
from src.hf_cache import recuperer_depuis_hf
from src.i18n import t
from src.pipeline_accessibilite_afrique import calculer_pipeline_complet
from src.utilitaires_matrix import charger_ttm_reseau, cumulative_cutoff
from src.worldpop import charger_ou_construire_grille_population_reseau, RESOLUTION_M_AFRIQUE

CUTOFF_MIN = 60


def accessibilite_page(lang="fr"):
    st.markdown("---")
    st.warning(t("accessibilite.avertissement_donnees", lang))

    if st.session_state.feed is None:
        st.info(t("commun.veuillez_charger_gtfs", lang))
        return

    st.info(t("accessibilite.description", lang, cutoff=CUTOFF_MIN))

    # Cette page a systématiquement besoin de la grille de population,
    # contrairement à la couche optionnelle des cartes arrêts/lignes (case à
    # cocher de la barre latérale, cf. app.py) : chargée/calculée directement
    # ici si pas déjà en cache dans la session.
    if st.session_state.grille_population is None:
        with st.spinner(t("app.spinner_grille_population", lang)):
            try:
                st.session_state.grille_population = charger_ou_construire_grille_population_reseau(
                    st.session_state.feed, st.session_state.nom_reseau_str, resolution_m=RESOLUTION_M_AFRIQUE,
                )
            except Exception as e:
                st.warning(t("accessibilite.pas_de_grille", lang, erreur=e))
                return

    grille_population = st.session_state.grille_population
    if grille_population is None or grille_population.empty:
        st.warning(t("accessibilite.pas_de_grille", lang, erreur=t("accessibilite.grille_vide", lang)))
        return

    ttm = charger_ttm_reseau(st.session_state.nom_reseau_str, resolution_m=RESOLUTION_M_AFRIQUE)
    if ttm is None:
        st.warning(t("accessibilite.pas_de_ttm", lang, reseau=st.session_state.nom_reseau_str))
        st.warning(t("accessibilite.avertissement_calcul_complet", lang))

        if st.button(t("accessibilite.bouton_calculer", lang), type="primary"):
            statut = st.status(t("accessibilite.status_calcul", lang), expanded=True)
            try:
                grille_population, ttm = calculer_pipeline_complet(
                    st.session_state.feed,
                    st.session_state.nom_reseau_str,
                    st.session_state.zip_path,
                    resolution_m=RESOLUTION_M_AFRIQUE,
                    on_step=statut.write,
                )
            except Exception as e:
                statut.update(label=t("accessibilite.erreur_calcul", lang, erreur=e), state="error")
                return
            st.session_state.grille_population = grille_population
            statut.update(label=t("accessibilite.status_termine", lang), state="complete")
        else:
            return

    land_use_data = grille_population[["id", "population"]].copy()

    with st.spinner(t("accessibilite.spinner_calcul", lang)):
        cum_population = cumulative_cutoff(
            ttm, land_use_data=land_use_data, opportunity="population",
            travel_cost="travel_time", cutoff=CUTOFF_MIN,
        )

        # Best-effort : sur un Space déployé, data/equipements_osm/ est vide
        # (exclu du déploiement, cf. scripts/deploy_hf_africa.sh) — ce .gpkg
        # n'est disponible qu'en le récupérant depuis le dataset HF partagé.
        # Un seul fichier (celui du réseau chargé), pas tout le dossier : cf.
        # compter_equipements_par_carreau(nom_reseau_str=...) ci-dessous.
        recuperer_depuis_hf(
            f"equipements_osm/{st.session_state.nom_reseau_str.lower()}_equipements.gpkg",
            os.path.join("data", "equipements_osm", f"{st.session_state.nom_reseau_str.lower()}_equipements.gpkg"),
        )
        equipements_par_carreau = compter_equipements_par_carreau(
            grille_population, nom_reseau_str=st.session_state.nom_reseau_str,
        )
        cum_equipements = None
        if equipements_par_carreau is not None:
            cum_equipements = cumulative_cutoff(
                ttm, land_use_data=equipements_par_carreau, opportunity="equipements",
                travel_cost="travel_time", cutoff=CUTOFF_MIN,
            )

    # Statistiques globales : moyenne pondérée par la population du carreau
    # d'origine (même principe que calculer_index_benchmark côté notebook
    # source, simplifié à un seul cutoff/groupe "Tous").
    st.header(t("accessibilite.header_stats", lang, cutoff=CUTOFF_MIN))
    poids = grille_population.set_index("id")["population"]
    population_totale = poids.sum()

    col1, col2 = st.columns(2)
    with col1:
        moyenne_pop = (
            (cum_population.set_index("id")["population"] * poids).sum() / population_totale
            if population_totale else 0
        )
        st.metric(t("accessibilite.metric_population", lang, cutoff=CUTOFF_MIN), f"{moyenne_pop:,.0f}")

    # Mis en session pour l'onglet Benchmark (index spécifique villes
    # africaines, cf. views/benchmark.py) : ces deux indicateurs y servent
    # de substitut aux métriques BPE-par-domaine du benchmark standard,
    # indisponibles hors de France.
    st.session_state.accessibilite_population_60min = moyenne_pop

    with col2:
        if cum_equipements is not None:
            moyenne_equip = (
                (cum_equipements.set_index("id")["equipements"] * poids).sum() / population_totale
                if population_totale else 0
            )
            st.metric(t("accessibilite.metric_equipements", lang, cutoff=CUTOFF_MIN), f"{moyenne_equip:,.1f}")
            st.session_state.accessibilite_equipements_60min = moyenne_equip
        else:
            st.info(t("accessibilite.pas_equipements", lang))

    # Cartes
    st.header(t("accessibilite.header_carte_population", lang, cutoff=CUTOFF_MIN))
    carte_pop = grille_population[["id", "geometry"]].merge(cum_population, on="id")
    m_pop = carte_pop.explore(
        "population", cmap="viridis", **fond_carte_kwargs("CartoDB positron"),
        style_kwds={"style_function": lambda x: {"weight": 0, "fillOpacity": 0.7}},
    )
    components.html(m_pop.get_root().render(), height=650, width=1000)

    if cum_equipements is not None:
        st.header(t("accessibilite.header_carte_equipements", lang, cutoff=CUTOFF_MIN))
        carte_equip = grille_population[["id", "geometry"]].merge(cum_equipements, on="id")
        m_equip = carte_equip.explore(
            "equipements", cmap="magma", **fond_carte_kwargs("CartoDB positron"),
            style_kwds={"style_function": lambda x: {"weight": 0, "fillOpacity": 0.7}},
        )
        components.html(m_equip.get_root().render(), height=650, width=1000)

    # Téléchargement
    st.header(t("commun.header_telechargement", lang))
    csv = cum_population.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=t("accessibilite.telecharger_population", lang),
        data=csv,
        file_name=f"accessibilite_population_{CUTOFF_MIN}min_{st.session_state.nom_reseau_str}.csv",
        mime="text/csv",
    )
