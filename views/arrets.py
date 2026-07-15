"""
Page Arrêts - Analyse GTFS Indicateurs par Arrêt
"""

import os
import tempfile

import streamlit as st
import streamlit.components.v1 as components

from src.cartographie import create_carte_arrets

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
from src.info_reseau import dates_service, formater_date_fr, date_str, longueur_par_lignes, nom_reseau_str, chemin_logo, recuperer_logo_reseau, nom_reseau 

from src.arrets import calculer_indicateurs_arrets, afficher_statistiques
#from src.create_troncons_uniques import creer_troncons_uniques
#from src.indicateurs_troncons import compute_indicateurs_troncons

from src.export_html import (
    exporter_tableau_lignes_html,
    exporter_camembert_html,
    exporter_statistiques_html,
)


def arrets_page():
    st.markdown("---")

    # Vérifier si les données sont chargées
    if (
        st.session_state.feed is not None
        and st.session_state.active_service_ids is not None
    ):
        # afficher infos réseau 
           #cherche nom réseau 
        nom_reseau_valeur = nom_reseau_str(st.session_state.feed)
        st.info(f"Le GTFS concerne le réseau {nom_reseau_valeur}")

        _, date_debut, date_fin, date_JOB = dates_service(st.session_state.feed)

        date_service_str, date_JOB_text = date_str(date_debut, date_fin, date_JOB)

        st.info(f"Il est valide sur la plage {date_service_str}, le JOB choisi au hasard est {date_JOB_text}")
        
        
        # Calculer les indicateurs automatiquement si pas déjà fait
        if st.session_state.indicateurs_arrets is None:
            with st.spinner("Calcul des indicateurs d'arrêts..."):
                try:
                    indicateurs = calculer_indicateurs_arrets(
                        st.session_state.feed,
                        st.session_state.date_str,
                    )
                    st.session_state.indicateurs_arrets = indicateurs
                except Exception as e:
                    st.error(f"Erreur lors du calcul des arrêts : {e}")
                    return

        if st.session_state.indicateurs_arrets is not None:
            indicateurs = st.session_state.indicateurs_arrets

            st.success("✅ Analyse des arrêts terminée !")

            # Statistiques globales
            st.header("📊 Statistiques Globales")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Nombre d'arrêts", len(indicateurs))
            with col2:
                st.metric(
                    "Arrêts actifs",
                    len(indicateurs[indicateurs["nombre_passages"] > 0]),
                )
            with col3:
                total_passages = int(indicateurs["nombre_passages"].sum())
                st.metric("Total passages", total_passages)

            # Top 10 arrêts
            st.header("🏆 Top 10 Arrêts les plus fréquentés")
            actifs = indicateurs[indicateurs["nombre_passages"] > 0].copy()
            if not actifs.empty:
                actifs = actifs.sort_values("nombre_passages", ascending=False)
                st.dataframe(actifs.drop(columns=["stop_lon", "stop_lat"]).head(10))
            else:
                st.info("Aucun arrêt actif trouvé.")

            # Fiche statistiques (export HTML)
            st.header("📄 Fiche Statistiques")
            output_stats = os.path.join(tempfile.gettempdir(), "statistiques_arrets_streamlit.html")
            exporter_statistiques_html(
                indicateurs,
                f"Analyse du {st.session_state.date_str}",
                st.session_state.date_str,
                output_stats,
                nom_reseau_str=st.session_state.nom_reseau_str,
            )
            with open(output_stats, "r", encoding="utf-8") as f:
                components.html(f.read(), height=600, scrolling=True)

            # Carte
            st.header("🗺️ Carte des Arrêts")
            output_map = os.path.join(tempfile.gettempdir(), "stops_map_streamlit.html")
            m = create_carte_arrets(
                indicateurs,
                st.session_state.nom_reseau_str,
                f"Analyse du {st.session_state.date_str}",
                st.session_state.date_str,
                st.session_state.zip_path,
                output_map,
                chemin_logo=st.session_state.chemin_logo,
            )
            components.html(m._repr_html_(), height=500, width=1000)

            # Télécharger les résultats
            st.header("💾 Téléchargement")
            csv = indicateurs.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Télécharger les résultats CSV",
                data=csv,
                file_name=f"indicateurs_arrets_{st.session_state.date_str}.csv",
                mime="text/csv",
            )
        else:
            st.info("🔄 Calcul des indicateurs en cours...")
    else:
        st.info(
            "👆 Veuillez charger un fichier GTFS et sélectionner une date dans la barre latérale."
        )
