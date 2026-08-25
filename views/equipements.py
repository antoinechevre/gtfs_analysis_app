"""
Page Équipements - affiche les équipements OSM extraits via
extraire_amenities_osm.py (substitut à la BPE INSEE pour un réseau hors de
France, cf. data/equipements_osm/ et index_accessibility_notebook_africa.
ipynb) : un fichier .gpkg par ville (un point = un équipement OSM, colonne
"ponderation" par type — cf. le référentiel Abidjan_amenities.xlsx), une
couche sélectionnable par fichier sur une carte commune, points colorés par
pondération (gris = pondération nulle, pas un pôle d'équipement pertinent ;
rouge = pondération élevée).

Pas de lien automatique avec le réseau GTFS chargé (les fichiers sont
produits par le notebook, par ville) : tous les .gpkg présents dans
data/equipements_osm/ sont affichés, quel que soit le GTFS actuellement
sélectionné dans la barre latérale.
"""

import glob
import os
import tempfile

import branca.colormap as cm
import folium
import geopandas as gpd
import streamlit as st
import streamlit.components.v1 as components

from src.equipements_osm import compter_equipements_par_carreau, recuperer_equipements_hf
from src.i18n import t
from src.worldpop import charger_ou_construire_grille_population_reseau, RESOLUTION_M_AFRIQUE

DOSSIER_EQUIPEMENTS = os.path.join("data", "equipements_osm")


def _nom_lisible(chemin_gpkg):
    """"abidjan_equipements.gpkg" -> "Abidjan Equipements" (nom de couche affiché)."""
    base = os.path.splitext(os.path.basename(chemin_gpkg))[0]
    return base.replace("_", " ").replace("-", " ").title()


def equipements_page(lang="fr"):
    st.markdown("---")
    st.warning(t("equipements.avertissement_couverture", lang))

    # Best-effort : sur un Space déployé, data/equipements_osm/ est vide
    # (exclu du déploiement, cf. scripts/deploy_hf_africa.sh) — ces .gpkg ne
    # sont disponibles qu'en les récupérant depuis le dataset HF partagé.
    recuperer_equipements_hf(DOSSIER_EQUIPEMENTS)
    fichiers_gpkg = sorted(glob.glob(os.path.join(DOSSIER_EQUIPEMENTS, "*.gpkg")))

    if not fichiers_gpkg:
        st.info(t("equipements.aucun_fichier", lang, dossier=DOSSIER_EQUIPEMENTS))
        st.caption(t("equipements.aide_extraction", lang))
        return

    st.info(t("equipements.description", lang))

    couches = {}
    for chemin in fichiers_gpkg:
        try:
            gdf = gpd.read_file(chemin)
            if "ponderation" not in gdf.columns:
                gdf["ponderation"] = 1  # format hérité sans pondération : poids uniforme
            couches[_nom_lisible(chemin)] = gdf
        except Exception as e:
            st.warning(t("equipements.erreur_lecture", lang, fichier=os.path.basename(chemin), erreur=e))

    if not couches:
        return

    # Statistiques globales : nombre d'équipements et score pondéré total
    st.header(t("equipements.header_stats", lang))
    colonnes = st.columns(len(couches))
    for (nom, gdf), colonne in zip(couches.items(), colonnes):
        with colonne:
            st.metric(nom, len(gdf))
            st.caption(t("equipements.score_pondere", lang, score=f"{gdf['ponderation'].sum():,.0f}"))

    # Carte commune, une couche (sélectionnable) par fichier, points colorés
    # par pondération (échelle commune à toutes les couches, pour rester
    # comparable d'une ville à l'autre).
    st.header(t("equipements.header_carte", lang))

    toutes_geometries = gpd.GeoDataFrame(
        gpd.pd.concat([gdf.geometry for gdf in couches.values()], ignore_index=True), columns=["geometry"], crs="EPSG:4326"
    )
    centre = toutes_geometries.geometry.unary_union.centroid

    ponderation_max = max(gdf["ponderation"].max() for gdf in couches.values()) or 1
    colormap = cm.LinearColormap(
        colors=["#bdbdbd", "#fee08b", "#f46d43", "#a50026"],
        vmin=0, vmax=ponderation_max,
        caption=t("equipements.legende_ponderation", lang),
    )

    m = folium.Map(location=[centre.y, centre.x], zoom_start=11, tiles="cartodbpositron")

    for nom, gdf in couches.items():
        feature_group = folium.FeatureGroup(name=f"{nom} ({len(gdf)})", show=True)
        for _, row in gdf.iterrows():
            ponderation = row["ponderation"]
            couleur = colormap(ponderation)
            libelle = row.get("name") or row.get("amenity") or nom
            folium.CircleMarker(
                location=[row.geometry.y, row.geometry.x],
                radius=4 if ponderation > 0 else 2,
                color=couleur,
                fill=True,
                fill_color=couleur,
                fill_opacity=0.85 if ponderation > 0 else 0.4,
                tooltip=f"{libelle} — pondération {ponderation:.0f}",
            ).add_to(feature_group)
        feature_group.add_to(m)

    colormap.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    output_map = os.path.join(tempfile.gettempdir(), "equipements_map_streamlit.html")
    m.save(output_map)
    components.html(m.get_root().render(), height=800, width=1000)

    # Carte grille (densité pondérée) : même grille 400x400 que la page
    # Accessibilité (population WorldPop, cf. charger_ou_construire_grille_
    # population_reseau), carreaux colorés en nuances de bleu selon le score
    # pondéré d'équipements qu'ils contiennent — contrairement à la carte
    # "toutes couches" ci-dessus (qui affiche volontairement chaque ville en
    # calque séparé, cf. docstring du module), celle-ci se limite au seul
    # .gpkg du réseau chargé (nom_reseau_str) pour rester correcte même si
    # deux réseaux différents ont des zones qui se recouvrent.
    st.header(t("equipements.header_carte_grille", lang))

    if st.session_state.feed is None:
        st.info(t("commun.veuillez_charger_gtfs", lang))
    else:
        if st.session_state.grille_population is None:
            with st.spinner(t("app.spinner_grille_population", lang)):
                try:
                    st.session_state.grille_population = charger_ou_construire_grille_population_reseau(
                        st.session_state.feed, st.session_state.nom_reseau_str, resolution_m=RESOLUTION_M_AFRIQUE,
                    )
                except Exception as e:
                    st.warning(t("equipements.pas_de_grille", lang, erreur=e))

        grille_population = st.session_state.grille_population
        if grille_population is None or grille_population.empty:
            if grille_population is not None:  # vide, pas une erreur de calcul (déjà signalée ci-dessus)
                st.warning(t("equipements.pas_de_grille", lang, erreur=t("accessibilite.grille_vide", lang)))
        else:
            score_par_carreau = compter_equipements_par_carreau(
                grille_population, dossier=DOSSIER_EQUIPEMENTS, nom_reseau_str=st.session_state.nom_reseau_str,
            )
            carte_grille = grille_population[["id", "geometry"]].merge(score_par_carreau, on="id")
            m_grille = carte_grille.explore(
                "equipements",
                cmap="Blues",
                tiles="cartodbpositron",
                style_kwds={"style_function": lambda x: {"weight": 0, "fillOpacity": 0.75}},
            )
            components.html(m_grille.get_root().render(), height=650, width=1000)

    # Téléchargement
    st.header(t("commun.header_telechargement", lang))
    colonnes_dl = st.columns(len(couches))
    for (nom, gdf), colonne in zip(couches.items(), colonnes_dl):
        with colonne:
            geojson = gdf.to_json().encode("utf-8")
            st.download_button(
                label=t("equipements.telecharger_geojson", lang, nom=nom),
                data=geojson,
                file_name=f"{nom.lower().replace(' ', '_')}.geojson",
                mime="application/geo+json",
                key=f"telechargement_equipement_{nom}",
            )
