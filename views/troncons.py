"""
Page Tronçons - Analyse GTFS Indicateurs par Tronçon
"""

import os
import tempfile

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.indicateurs_troncons import compute_indicateurs_troncons
from src.cartographie import creer_carte_troncons
from src.create_troncons_uniques import creer_troncons_uniques
from src.utils import km_par_ligne_plage
from src.export_html import exporter_camembert_html, exporter_tableau_lignes_html
from src.info_reseau import dates_service, formater_date_fr, date_str, longueur_par_lignes, nom_reseau_str, chemin_logo, recuperer_logo_reseau, nom_reseau 

# route_type GTFS -> (nom_mode, emoji) pour chaque mode couvert par cette page
MODES = [
    (3, "Bus", "🚌"),
    (0, "Tram", "🚊"),
    (1, "Metro", "🚇"),
    (11, "Trolley", "🚎"),
]


def charger_ou_calculer_troncons(feed, route_type, nom_mode):
    """
    Calcule automatiquement les tronçons depuis le GTFS uploadé.

    Cette fonction calcule toujours les tronçons à partir du feed GTFS fourni,
    garantissant la compatibilité avec n'importe quel réseau de transport.

    Parameters:
    -----------
    feed : gtfs_kit Feed object
        Feed GTFS chargé
    route_type : int
        Type de route GTFS (0=tram, 1=métro, 3=bus, 11=trolleybus, etc.)
    nom_mode : str
        Nom du mode pour les messages ("Bus", "Tram", "Metro" ou "Trolley")

    Returns:
    --------
    pandas.DataFrame : Tronçons avec colonnes nécessaires pour l'analyse
    """
    
    
    
    st.info(f"🔄 Calcul automatique des tronçons {nom_mode} depuis le GTFS...")

    try:
        # Calculer les tronçons uniques
        troncons_gdf = creer_troncons_uniques(feed, route_type)

        st.success(f"✅ {len(troncons_gdf)} tronçons {nom_mode} calculés automatiquement")
        return troncons_gdf

    except Exception as e:
        st.error(f"❌ Erreur lors du calcul automatique des tronçons {nom_mode}: {e}")
        return None


def troncons_page():
    st.markdown("---")

    # Avertissement sur les limitations
    st.warning(
        """
    ⚠️ Cette analyse a été debuggée sur plusieurs GTFS en mentionnant les modes bus / tram / metro / trolley
    """
    )
     # afficher infos réseau 
           #cherche nom réseau 
    nom_reseau_valeur = nom_reseau_str(st.session_state.feed)
    st.info(f"Le GTFS concerne le réseau {nom_reseau_valeur}")

    date_debut, date_fin, date_JOB = dates_service(st.session_state.feed)

    date_service_str, date_JOB_text = date_str(date_debut, date_fin, date_JOB)

    st.info(f"Il est valide sur la plage {date_service_str}, le JOB choisi au hasard est {date_JOB_text}")
        
    st.markdown("---")

    # Vérifier si les données sont chargées
    if (
        st.session_state.feed is not None
        and st.session_state.active_service_ids is not None
    ):

        # Calculer les indicateurs automatiquement si pas déjà fait
        if (
            st.session_state.indicateurs_bus is None
            or st.session_state.indicateurs_tram is None
            or st.session_state.indicateurs_metro is None
            or st.session_state.indicateurs_trolley is None
        ):

            with st.spinner("Chargement/Calcul des tronçons de référence..."):
                troncons_par_mode = {
                    nom_mode: charger_ou_calculer_troncons(
                        st.session_state.feed, route_type=route_type, nom_mode=nom_mode
                    )
                    for route_type, nom_mode, _ in MODES
                }

                if any(t is None for t in troncons_par_mode.values()):
                    st.error("Impossible de calculer les tronçons de référence.")
                    return

            with st.spinner("Calcul des indicateurs de tronçons..."):
                try:
                    (
                        indicateurs_bus,
                        indicateurs_tram,
                        indicateurs_metro,
                        indicateurs_trolley,
                    ) = compute_indicateurs_troncons(
                        st.session_state.feed,
                        st.session_state.active_service_ids,
                        troncons_par_mode["Bus"],
                        troncons_par_mode["Tram"],
                        troncons_par_mode["Metro"],
                        troncons_par_mode["Trolley"],
                    )
                    st.session_state.indicateurs_bus = indicateurs_bus
                    st.session_state.indicateurs_tram = indicateurs_tram
                    st.session_state.indicateurs_metro = indicateurs_metro
                    st.session_state.indicateurs_trolley = indicateurs_trolley
                except Exception as e:
                    st.error(f"Erreur lors du calcul des tronçons : {e}")
                    return

        if (
            st.session_state.indicateurs_bus is not None
            and st.session_state.indicateurs_tram is not None
            and st.session_state.indicateurs_metro is not None
            and st.session_state.indicateurs_trolley is not None
        ):

            indicateurs_bus = st.session_state.indicateurs_bus
            indicateurs_tram = st.session_state.indicateurs_tram
            indicateurs_metro = st.session_state.indicateurs_metro
            indicateurs_trolley = st.session_state.indicateurs_trolley
            indicateurs_par_mode = {
                "Bus": indicateurs_bus,
                "Tram": indicateurs_tram,
                "Metro": indicateurs_metro,
                "Trolley": indicateurs_trolley,
            }

            st.success("✅ Analyse des tronçons terminée !")

            # Statistiques globales
            st.header("📊 Statistiques Globales")
            colonnes_stats = st.columns(len(MODES))
            for (_, nom_mode, emoji), colonne in zip(MODES, colonnes_stats):
                indicateurs_mode = indicateurs_par_mode[nom_mode]
                with colonne:
                    st.metric(
                        f"{emoji} Tronçons {nom_mode} actifs",
                        len(indicateurs_mode[indicateurs_mode["nombre_passages"] > 0]),
                    )
                    st.metric(
                        f"Total passages {nom_mode}",
                        int(indicateurs_mode["nombre_passages"].sum()),
                    )

            # Répartition des véh.km par mode et tableau des lignes
            if st.session_state.total_vk_plage is None:
                with st.spinner("Calcul des véh.km par ligne sur la plage de service..."):
                    liste_dates_service, _, _, _ = dates_service(st.session_state.feed)
                    st.session_state.total_vk_plage = km_par_ligne_plage(
                        liste_dates_service, st.session_state.feed
                    )
            total_vk_plage = st.session_state.total_vk_plage

            date_service_str = f"Analyse du {st.session_state.date_str}"

            output_camembert = os.path.join(tempfile.gettempdir(), "camembert_troncons_streamlit.html")
            exporter_camembert_html(
                st.session_state.nom_reseau_str,
                date_service_str,
                total_vk_plage,
                output_camembert,
            )
            with open(output_camembert, "r", encoding="utf-8") as f:
                components.html(f.read(), height=450, scrolling=True)

            output_tableau = os.path.join(tempfile.gettempdir(), "tableau_lignes_streamlit.html")
            exporter_tableau_lignes_html(
                st.session_state.nom_reseau_str,
                date_service_str,
                st.session_state.feed,
                output_tableau,
                total_vk_plage=total_vk_plage,
            )
            with open(output_tableau, "r", encoding="utf-8") as f:
                components.html(f.read(), height=600, scrolling=True)

            # Top tronçons (uniquement les modes présents dans le GTFS)
            cols_to_show = [
                "stop_depart_name",
                "stop_arrivee_name",
                "nombre_passages",
                "vitesse_moyenne_kmh",
            ]
            modes_presents = [
                mode for mode in MODES if len(indicateurs_par_mode[mode[1]]) > 0
            ]
            colonnes_top = st.columns(len(modes_presents))
            for (_, nom_mode, emoji), colonne in zip(modes_presents, colonnes_top):
                indicateurs_mode = indicateurs_par_mode[nom_mode]
                with colonne:
                    st.header(f"{emoji} Top 10 Tronçons {nom_mode}")
                    actifs = indicateurs_mode[indicateurs_mode["nombre_passages"] > 0].copy()
                    if not actifs.empty:
                        actifs = actifs.sort_values("nombre_passages", ascending=False)
                        actifs["vitesse_moyenne_kmh"] = actifs["vitesse_moyenne_kmh"].round(1)
                        st.dataframe(actifs[cols_to_show].head(10))
                    else:
                        st.info(f"Aucun tronçon {nom_mode.lower()} actif.")

            # Carte interactive
            st.header("🗺️ Carte Interactive des Tronçons")
            output_map = os.path.join(tempfile.gettempdir(), "troncons_map_streamlit.html")
            m = creer_carte_troncons(
                indicateurs_bus,
                indicateurs_tram,
                indicateurs_metro,
                indicateurs_trolley,
                output_map,
                date_service_str,
                nom_reseau_str=st.session_state.nom_reseau_str,
                chemin_logo=st.session_state.chemin_logo,
            )
            components.html(m._repr_html_(), height=1000, width=1000)

            # Télécharger les résultats
            st.header("💾 Téléchargement")
            colonnes_telechargement = st.columns(len(MODES))
            for (_, nom_mode, emoji), colonne in zip(MODES, colonnes_telechargement):
                indicateurs_mode = indicateurs_par_mode[nom_mode]
                with colonne:
                    csv = indicateurs_mode.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label=f"📥 Télécharger {nom_mode} CSV",
                        data=csv,
                        file_name=f"indicateurs_troncons_{nom_mode.lower()}_{st.session_state.date_str}.csv",
                        mime="text/csv",
                        key=f"telechargement_{nom_mode.lower()}",
                    )
        else:
            st.info("🔄 Calcul des indicateurs en cours...")
    else:
        st.info(
            "👆 Veuillez charger un fichier GTFS et sélectionner une date dans la barre latérale."
        )
