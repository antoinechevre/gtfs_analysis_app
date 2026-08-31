"""
Page Arrêts - Analyse GTFS Indicateurs par Arrêt
"""

import os
import tempfile

import streamlit as st
import streamlit.components.v1 as components

from src.cartographie import (
    chemin_cache_carte_reseau,
    charger_carte_reseau_cache,
    create_carte_arrets,
    envoyer_carte_reseau_cache,
)
from src.info_reseau import charger_ou_calculer_dates_service, date_str, nom_reseau_str
from src.arrets import calculer_indicateurs_arrets
from src.export_html import exporter_statistiques_html
from src.hf_cache import charger_ou_calculer_avec_cache_hf
from src.i18n import t


def obtenir_indicateurs_arrets(lang="fr"):
    """Calcule les indicateurs par arrêt s'ils ne sont pas déjà en session
    (ou les recharge depuis le cache disque/Hugging Face s'ils y ont déjà
    été calculés pour ce réseau — sûr d'une exécution à l'autre car
    date_JOB est déterministe pour un GTFS donné, cf. dates_service dans
    info_reseau.py), et renvoie st.session_state.indicateurs_arrets.

    Extrait d'arrets_page pour être réutilisé par tout autre onglet ayant
    besoin de la liste des arrêts avec leur fréquentation (ex: le sélecteur
    de point de départ de l'onglet Isochrone carreaux)."""
    if st.session_state.indicateurs_arrets is None:
        with st.spinner(t("arrets.spinner_indicateurs", lang)):
            nom_fichier = "indicateurs_arrets.csv"
            nom_reseau = st.session_state.nom_reseau_str
            chemin_cache = os.path.join("data", "memory_troncons", nom_reseau, nom_fichier)
            nom_fichier_hf = f"memory_troncons/{nom_reseau}/{nom_fichier}"
            indicateurs = charger_ou_calculer_avec_cache_hf(
                chemin_cache,
                nom_fichier_hf,
                lambda: calculer_indicateurs_arrets(
                    st.session_state.feed,
                    st.session_state.date_str,
                ),
            )
            st.session_state.indicateurs_arrets = indicateurs
    return st.session_state.indicateurs_arrets


def arrets_page(lang="fr"):
    st.markdown("---")
    st.warning(t("africa.avertissement_general", lang))

    # Vérifier si les données sont chargées
    if (
        st.session_state.feed is not None
        and st.session_state.active_service_ids is not None
    ):
        # afficher infos réseau
           #cherche nom réseau
        nom_reseau_valeur = nom_reseau_str(st.session_state.feed)
        if st.session_state.population_agglo:
            st.info(t(
                "commun.reseau_population_info", lang,
                reseau=nom_reseau_valeur,
                population=round(st.session_state.population_agglo / 1000),
                annee=st.session_state.annee_population,
            ))
        else:
            st.info(t("commun.reseau_info", lang, reseau=nom_reseau_valeur))

        _, date_debut, date_fin, date_JOB = charger_ou_calculer_dates_service(
            st.session_state.feed, st.session_state.nom_reseau_str
        )

        date_service_str, date_JOB_text = date_str(date_debut, date_fin, date_JOB, lang=lang)

        st.info(t("commun.plage_info", lang, plage=date_service_str, job=date_JOB_text))


        # Calculer les indicateurs automatiquement si pas déjà fait, ou les
        # recharger depuis le cache (disque local puis dataset Hugging
        # Face) s'ils y ont déjà été calculés pour ce réseau — sûr d'une
        # exécution à l'autre car date_JOB est déterministe pour un GTFS
        # donné (cf. dates_service, info_reseau.py).
        if st.session_state.indicateurs_arrets is None:
            try:
                obtenir_indicateurs_arrets(lang)
            except Exception as e:
                st.error(t("arrets.erreur_indicateurs", lang, erreur=e))
                return

        if st.session_state.indicateurs_arrets is not None:
            indicateurs = st.session_state.indicateurs_arrets

            # Statistiques globales
            st.header(t("arrets.header_stats", lang))
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(t("arrets.metric_nb_arrets", lang), len(indicateurs))
            with col2:
                st.metric(
                    t("arrets.metric_arrets_actifs", lang),
                    len(indicateurs[indicateurs["nombre_passages"] > 0]),
                )
            with col3:
                total_passages = int(indicateurs["nombre_passages"].sum())
                st.metric(t("arrets.metric_total_passages", lang), total_passages)

            # Top 10 arrêts
            st.header(t("arrets.header_top10", lang))
            actifs = indicateurs[indicateurs["nombre_passages"] > 0].copy()
            if not actifs.empty:
                actifs = actifs.sort_values("nombre_passages", ascending=False)
                st.dataframe(actifs.drop(columns=["stop_lon", "stop_lat"]).head(10))
            else:
                st.info(t("arrets.aucun_actif", lang))

            # Fiche statistiques (export HTML)
            st.header(t("arrets.header_fiche", lang))
            if indicateurs.empty:
                # indicateurs vide (pas seulement "aucun arrêt actif" ci-dessus,
                # cf. actifs) : calculer_indicateurs_arrets n'a trouvé aucun
                # trip pour date_JOB, typiquement un date_JOB mis en cache
                # pour un autre GTFS ayant partagé le même nom de réseau (cf.
                # collision Abidjan AMUGA / Abidjan_gtfs) — sans ce garde,
                # exporter_statistiques_html plante sur df.iloc[0].
                st.info(t("arrets.aucun_service", lang))
            else:
                output_stats = os.path.join(tempfile.gettempdir(), "statistiques_arrets_streamlit.html")
                exporter_statistiques_html(
                    indicateurs,
                    t("commun.analyse_du", lang, date=st.session_state.date_str),
                    st.session_state.date_str,
                    output_stats,
                    nom_reseau_str=st.session_state.nom_reseau_str,
                    lang=lang,
                )
                with open(output_stats, "r", encoding="utf-8") as f:
                    components.html(f.read(), height=600, scrolling=True)

            # Carte : tente d'abord une carte déjà rendue en cache (par le
            # notebook, qui la pousse vers HF après son propre calcul, ou un
            # run précédent de cette page) — évite le coût du rendu Folium
            # (jointure population + tracé des lignes depuis le GTFS).
            st.header(t("arrets.header_carte", lang))
            chemin_carte_cache = charger_carte_reseau_cache(st.session_state.nom_reseau_str, "arrets")
            if chemin_carte_cache is not None:
                with open(chemin_carte_cache, "r", encoding="utf-8") as f:
                    components.html(f.read(), height=1000, width=1000)
            else:
                output_map = os.path.join(tempfile.gettempdir(), "stops_map_streamlit.html")
                m = create_carte_arrets(
                    indicateurs,
                    st.session_state.nom_reseau_str,
                    t("commun.analyse_du", lang, date=st.session_state.date_str),
                    st.session_state.date_str,
                    st.session_state.zip_path,
                    output_map,
                    chemin_logo=st.session_state.chemin_logo,
                    lang=lang,
                    grille_population=st.session_state.grille_population,
                )
                # get_root().render() (le HTML complet, celui écrit par
                # .save()) plutôt que _repr_html_() : cette dernière
                # enveloppe la carte dans un wrapper "responsive"
                # (padding-bottom en %) pensé pour Jupyter, qui impose son
                # propre ratio hauteur/largeur et ignore le height/width
                # demandés ici.
                html_carte = m.get_root().render()
                components.html(html_carte, height=1000, width=1000)

                chemin_carte = chemin_cache_carte_reseau(st.session_state.nom_reseau_str, "arrets")
                os.makedirs(os.path.dirname(chemin_carte), exist_ok=True)
                with open(chemin_carte, "w", encoding="utf-8") as f:
                    f.write(html_carte)
                envoyer_carte_reseau_cache(chemin_carte, st.session_state.nom_reseau_str, "arrets")

            # Télécharger les résultats
            st.header(t("commun.header_telechargement", lang))
            csv = indicateurs.to_csv(index=False).encode("utf-8")
            st.download_button(
                label=t("arrets.telecharger_csv", lang),
                data=csv,
                file_name=f"indicateurs_arrets_{st.session_state.date_str}.csv",
                mime="text/csv",
            )
        else:
            st.info(t("commun.calcul_en_cours", lang))
    else:
        st.info(t("commun.veuillez_charger_gtfs", lang))
