"""
Page Équipements - affiche les équipements OSM extraits via
src/osm_extract.py:extraire_amenities_depuis_pbf (substitut à la BPE INSEE
pour un réseau hors de France, cf. data/equipements_osm/ et
index_accessibility_notebook_africa_600m.ipynb) : un fichier .gpkg par
ville (un point = un équipement OSM, colonne "ponderation" par type — cf.
le référentiel Abidjan_amenities.xlsx), points colorés par pondération
(gris = pondération nulle, pas un pôle d'équipement pertinent ; rouge =
pondération élevée).

Se limite au seul fichier du réseau actuellement chargé dans la barre
latérale (nom_reseau_str) — pas d'affichage de toutes les villes du cache
partagé : cohérent avec compter_equipements_par_carreau (cf. correctif sur
la collision Abidjan AMUGA / Abidjan_gtfs), et évite de télécharger/afficher
des données sans rapport avec le GTFS en cours d'analyse.
"""

import os
import tempfile

import branca.colormap as cm
import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.cartographie import fond_carte_kwargs
from src.equipements_osm import compter_equipements_par_carreau
from src.hf_cache import recuperer_depuis_hf
from src.i18n import t
from src.worldpop import charger_ou_construire_grille_population_reseau, RESOLUTION_M_AFRIQUE

DOSSIER_EQUIPEMENTS = os.path.join("data", "equipements_osm")
NOM_PONDERATION_XLSX = "Abidjan_amenities.xlsx"


def charger_table_ponderation():
    """Référentiel de pondération par type d'équipement (feuille
    "resume_par_type" de Abidjan_amenities.xlsx, cf. src.pipeline_
    accessibilite_afrique.PONDERATION_XLSX) : défini à la main sur Abidjan
    et réutilisé tel quel pour toutes les villes — un seul fichier partagé,
    pas un fichier par ville."""
    chemin_xlsx = os.path.join(DOSSIER_EQUIPEMENTS, NOM_PONDERATION_XLSX)
    if not os.path.exists(chemin_xlsx):
        recuperer_depuis_hf(f"equipements_osm/{NOM_PONDERATION_XLSX}", chemin_xlsx)
    return pd.read_excel(chemin_xlsx, sheet_name="resume_par_type")


def equipements_page(lang="fr"):
    st.markdown("---")
    st.warning(t("africa.avertissement_general", lang))
    st.warning(t("equipements.avertissement_couverture", lang))

    if st.session_state.feed is None:
        st.info(t("commun.veuillez_charger_gtfs", lang))
        return

    nom_reseau = st.session_state.nom_reseau_str
    nom_fichier = f"{nom_reseau.lower()}_equipements.gpkg"
    chemin_gpkg = os.path.join(DOSSIER_EQUIPEMENTS, nom_fichier)

    # Best-effort : sur un Space déployé, data/equipements_osm/ est vide
    # (exclu du déploiement, cf. scripts/deploy_hf_africa.sh) — ce .gpkg n'est
    # disponible qu'en le récupérant depuis le dataset HF partagé.
    if not os.path.exists(chemin_gpkg):
        recuperer_depuis_hf(f"equipements_osm/{nom_fichier}", chemin_gpkg)

    if not os.path.exists(chemin_gpkg):
        st.info(t("equipements.aucun_fichier", lang, dossier=DOSSIER_EQUIPEMENTS))
        st.caption(t("equipements.aide_extraction", lang))
        return

    try:
        gdf = gpd.read_file(chemin_gpkg)
    except Exception as e:
        st.warning(t("equipements.erreur_lecture", lang, fichier=nom_fichier, erreur=e))
        return

    if "ponderation" not in gdf.columns:
        gdf["ponderation"] = 1  # format hérité sans pondération : poids uniforme

    st.info(t("equipements.description", lang))
    st.info(t("commun.reseau_info", lang, reseau=nom_reseau))

    # Statistiques
    st.header(t("equipements.header_stats", lang))
    score_total = f"{gdf['ponderation'].sum():,.0f}"
    st.success(f"{len(gdf):,} — {t('equipements.score_pondere', lang, score=score_total)}")

    # Carte des points, colorés par pondération
    st.header(t("equipements.header_carte", lang))
    st.caption(t("equipements.caption_carte", lang))

    centre = gdf.geometry.unary_union.centroid
    ponderation_max = gdf["ponderation"].max() or 1
    colormap = cm.LinearColormap(
        colors=["#bdbdbd", "#fee08b", "#f46d43", "#a50026"],
        vmin=0, vmax=ponderation_max,
        caption=t("equipements.legende_ponderation", lang),
    )

    m = folium.Map(location=[centre.y, centre.x], zoom_start=11, **fond_carte_kwargs("CartoDB positron"))
    # Ne garde que les équipements pondérés (les autres n'apportent rien à la
    # lecture de la carte), triés par pondération croissante : chaque
    # CircleMarker est ajouté au-dessus des précédents (ordre du DOM
    # Leaflet), donc les plus pondérés sont dessinés en dernier et ressortent
    # devant les autres.
    gdf_carte = gdf[gdf["ponderation"] > 0].sort_values("ponderation")
    for _, row in gdf_carte.iterrows():
        ponderation = row["ponderation"]
        couleur = colormap(ponderation)
        libelle = row.get("name") or row.get("amenity") or nom_reseau
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=4,
            color=couleur,
            fill=True,
            fill_color=couleur,
            fill_opacity=0.85,
            tooltip=f"{libelle} — pondération {ponderation:.0f}",
        ).add_to(m)
    colormap.add_to(m)

    output_map = os.path.join(tempfile.gettempdir(), "equipements_map_streamlit.html")
    m.save(output_map)
    components.html(m.get_root().render(), height=800, width=1000)

    # Carte grille (densité pondérée) : même grille que la page Accessibilité
    # (population WorldPop, cf. charger_ou_construire_grille_population_
    # reseau), carreaux colorés en nuances de bleu selon le score pondéré
    # d'équipements qu'ils contiennent.
    st.header(t("equipements.header_carte_grille", lang))
    st.caption(t("equipements.caption_carte_grille", lang))

    if st.session_state.grille_population is None:
        with st.spinner(t("app.spinner_grille_population", lang)):
            try:
                st.session_state.grille_population = charger_ou_construire_grille_population_reseau(
                    st.session_state.feed, nom_reseau, resolution_m=RESOLUTION_M_AFRIQUE,
                )
            except Exception as e:
                st.warning(t("equipements.pas_de_grille", lang, erreur=e))

    grille_population = st.session_state.grille_population
    if grille_population is None or grille_population.empty:
        if grille_population is not None:  # vide, pas une erreur de calcul (déjà signalée ci-dessus)
            st.warning(t("equipements.pas_de_grille", lang, erreur=t("accessibilite.grille_vide", lang)))
    else:
        score_par_carreau = compter_equipements_par_carreau(
            grille_population, dossier=DOSSIER_EQUIPEMENTS, nom_reseau_str=nom_reseau,
        )
        carte_grille = grille_population[["id", "geometry"]].merge(score_par_carreau, on="id")
        m_grille = carte_grille.explore(
            "equipements",
            cmap="Blues",
            **fond_carte_kwargs("CartoDB positron"),
            style_kwds={"style_function": lambda x: {"weight": 0, "fillOpacity": 0.75}},
        )
        components.html(m_grille.get_root().render(), height=650, width=1000)

    # Téléchargement
    st.header(t("commun.header_telechargement", lang))
    geojson = gdf.to_json().encode("utf-8")
    st.download_button(
        label=t("equipements.telecharger_geojson", lang, nom=nom_reseau),
        data=geojson,
        file_name=f"{nom_reseau.lower()}.geojson",
        mime="application/geo+json",
    )

    # Référentiel de pondération (même table pour toutes les villes) :
    # affiché en fin de page, après la carte/le téléchargement propres à ce
    # réseau, comme rappel de la méthode utilisée pour calculer "ponderation".
    st.header(t("equipements.header_ponderation", lang))
    st.caption(t("equipements.caption_ponderation", lang))
    try:
        table_ponderation = charger_table_ponderation()
        ponderation_non_nulle = (
            table_ponderation[table_ponderation["Ponderation"] > 0]
            .sort_values("Ponderation", ascending=False)[["amenity", "Ponderation"]]
            .rename(columns={
                "amenity": t("equipements.colonne_type", lang),
                "Ponderation": t("equipements.colonne_ponderation", lang),
            })
        )
        st.dataframe(ponderation_non_nulle, hide_index=True, use_container_width=True)
    except Exception as e:
        st.warning(t("equipements.pas_de_ponderation", lang, erreur=e))
