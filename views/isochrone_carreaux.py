"""
Page Isochrone carreaux - carreaux de la grille de population atteignables
depuis un arrêt en un budget de temps donné, d'après une matrice de temps
de trajet (TTM) déjà calculée (cf. src/isochrone_carreaux.py). Équivalent
de l'onglet Isochrone (ttm) de l'app sœur Accessibility_analysis.
"""

import streamlit as st
import streamlit.components.v1 as components

from src.i18n import t
from src.isochrone_carreaux import build_map_isochrone_carreaux, carreaux_atteignables, trouver_carreau_origine
from src.utilitaires_matrix import chemin_ttm_reseau, charger_ttm_pour_origine
from src.worldpop import charger_ou_construire_grille_population_reseau, RESOLUTION_M_AFRIQUE
from views.arrets import obtenir_indicateurs_arrets

BUDGET_MIN_DEFAUT = 30


def isochrone_carreaux_page(lang="fr"):
    st.markdown("---")
    st.info(t("isochrone_carreaux.intro", lang))

    if st.session_state.feed is None:
        st.info(t("commun.veuillez_charger_gtfs", lang))
        return

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

    # Simple vérification d'existence (pas de lecture du contenu) : la TTM
    # entière n'est jamais chargée sur cette page — cf. charger_ttm_pour_origine
    # plus bas, qui ne lit que les lignes de l'origine choisie une fois le
    # calcul lancé. Charger la TTM entière (charger_ttm_reseau) ici, rejouée
    # à chaque interaction Streamlit (slider, sélection d'arrêt...), a fait
    # dépasser la limite mémoire du Space en usage réel sur un réseau
    # volumineux (Abidjan, 706M lignes).
    if chemin_ttm_reseau(st.session_state.nom_reseau_str, resolution_m=RESOLUTION_M_AFRIQUE) is None:
        st.warning(t("accessibilite.pas_de_ttm", lang, reseau=st.session_state.nom_reseau_str))
        return

    if st.session_state.indicateurs_arrets is None:
        with st.spinner(t("arrets.spinner_indicateurs", lang)):
            try:
                obtenir_indicateurs_arrets(lang)
            except Exception as e:
                st.error(t("isochrone_carreaux.erreur_arrets", lang, erreur=e))
                return

    indicateurs = st.session_state.indicateurs_arrets
    if indicateurs is None or indicateurs.empty:
        st.info(t("commun.calcul_en_cours", lang))
        return

    # Trié par nombre de passages décroissant : l'arrêt le plus fréquenté
    # (index 0) est présélectionné par défaut.
    arrets_tries = indicateurs.sort_values("nombre_passages", ascending=False).reset_index(drop=True)
    options_labels = [
        f"{row.stop_name} — {int(row.nombre_passages)} {t('isochrone_carreaux.passages_suffix', lang)}"
        for row in arrets_tries.itertuples()
    ]

    col_choix, col_budget = st.columns([2, 1])
    with col_choix:
        index_choisi = st.selectbox(
            t("isochrone_carreaux.label_arret_depart", lang),
            options=range(len(options_labels)),
            format_func=lambda i: options_labels[i],
            index=0,
            key="isochrone_carreaux_arret",
        )
    with col_budget:
        budget_min = st.slider(
            t("isochrone_carreaux.label_budget", lang), 5, 90, BUDGET_MIN_DEFAUT, step=5,
            key="isochrone_carreaux_budget",
        )

    origine = arrets_tries.iloc[index_choisi]

    if st.button(t("isochrone_carreaux.bouton_calculer", lang), type="primary"):
        with st.spinner(t("isochrone_carreaux.spinner_calcul", lang)):
            origin_id = trouver_carreau_origine(grille_population, origine["stop_lat"], origine["stop_lon"])
            if origin_id is None:
                gdf = None
            else:
                ttm_origine = charger_ttm_pour_origine(
                    st.session_state.nom_reseau_str, origin_id, resolution_m=RESOLUTION_M_AFRIQUE,
                )
                gdf = carreaux_atteignables(grille_population, ttm_origine, origin_id, budget_min)
        st.session_state["isochrone_carreaux_resultats"] = (origine["stop_id"], origin_id, gdf, budget_min)

    resultats = st.session_state.get("isochrone_carreaux_resultats")
    if resultats is None or resultats[0] != origine["stop_id"]:
        st.info(t("isochrone_carreaux.attente_calcul", lang))
        return

    _, origin_id, gdf, budget_min_affiche = resultats

    if origin_id is None:
        st.warning(t("isochrone_carreaux.pas_de_carreau", lang))
        return

    col_map, col_stats = st.columns([3, 1])
    with col_map:
        m = build_map_isochrone_carreaux(
            origine, gdf, budget_min_affiche, legende_duree=t("isochrone_carreaux.legende_duree", lang)
        )
        components.html(m.get_root().render(), height=650)
    with col_stats:
        st.subheader(origine["stop_name"])
        if gdf.empty:
            st.warning(t("isochrone_carreaux.aucun_atteignable", lang))
        else:
            st.metric(t("isochrone_carreaux.metric_carreaux", lang), f"{len(gdf):,}".replace(",", " "))
            st.metric(t("isochrone_carreaux.metric_duree_mediane", lang), f"{gdf['travel_time'].median():.0f} min")
            st.metric(
                t("isochrone_carreaux.metric_population", lang),
                f"{gdf['population'].sum():,.0f}".replace(",", " "),
            )

    st.header(t("commun.header_telechargement", lang))
    csv = gdf.drop(columns="geometry").to_csv(index=False).encode("utf-8")
    st.download_button(
        label=t("isochrone_carreaux.telecharger_csv", lang),
        data=csv,
        file_name=f"isochrone_carreaux_{budget_min_affiche}min_{st.session_state.nom_reseau_str}.csv",
        mime="text/csv",
    )
