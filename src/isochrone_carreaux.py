"""
Isochrone "carreaux" : à partir d'un arrêt de départ, carreaux de la
grille de population WorldPop (cf. src/worldpop.py) atteignables en moins
de X minutes, d'après une matrice de temps de trajet (TTM) carreau à
carreau déjà calculée (cf. src/utilitaires_matrix.charger_ttm_reseau).

Adapté de l'onglet équivalent de l'app sœur Accessibility_analysis
(github.com/antoinechevre/Accessibility_analysis, views/isochrone_ttm_test.py
+ src/isochrone_ttm.py), avec une simplification : là-bas la géométrie des
carreaux (grille INSEE 200m, France uniquement) est retéléchargée à part
depuis un fichier dédié, ici la grille WorldPop est universelle (tout
pays) et déjà chargée en session (st.session_state.grille_population) —
donc pas de second jeu de données à récupérer, on cherche directement le
carreau d'origine et les géométries atteignables dans cette même grille.

Horaire de départ figé à celui du calcul de la TTM (r5py, cf. notebook
d'accessibilité utilisé pour produire la TTM), pas choisi ici.
"""

import branca.colormap as cm
import folium
from shapely.geometry import Point

# Mêmes seuils/couleurs que l'app sœur (src/isochrone.py côté
# Accessibility_analysis) : dégradé vert (rapide) -> rouge (lent).
DUREE_COLOR_SEUILS = [0, 15, 30, 45, 60, 90]
DUREE_COLOR_BANDES = ["#1a9850", "#91cf60", "#fee08b", "#fc8d59", "#d73027"]


def trouver_carreau_origine(grille_population, lat, lon):
    """Id (colonne "id" de grille_population) du carreau contenant (lat,
    lon), ou le plus proche si aucun carreau ne le contient (carreaux
    WorldPop non peuplés retirés de la grille, cf. decouper_et_vectoriser :
    un arrêt peut tomber dans un de ces "trous"). None si grille_population
    est vide."""
    if grille_population is None or grille_population.empty:
        return None

    point = Point(lon, lat)
    contenant = grille_population[grille_population.geometry.contains(point)]
    if not contenant.empty:
        return contenant["id"].iloc[0]

    plus_proche = grille_population.geometry.distance(point).idxmin()
    return grille_population.loc[plus_proche, "id"]


def carreaux_atteignables(grille_population, ttm, origin_id, budget_min):
    """GeoDataFrame [id, population, geometry, travel_time] des carreaux de
    grille_population atteignables depuis origin_id en <= budget_min
    minutes d'après ttm."""
    sous_ensemble = ttm[
        (ttm["from_id"] == origin_id) & ttm["travel_time"].notna() & (ttm["travel_time"] <= budget_min)
    ][["to_id", "travel_time"]].rename(columns={"to_id": "id"})

    return grille_population.merge(sous_ensemble, on="id", how="inner")


def build_map_isochrone_carreaux(origine, gdf_carreaux, budget_min, legende_duree="Temps de trajet (min)"):
    """Carte folium : point de départ (l'arrêt) + carreaux atteignables
    colorés par temps de trajet."""
    center = [origine["stop_lat"], origine["stop_lon"]]
    m = folium.Map(location=center, zoom_start=12, tiles=None, prefer_canvas=True, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", cross_origin=True).add_to(m)
    folium.TileLayer("CartoDB dark_matter", name="CartoDB Dark Matter", cross_origin=True).add_to(m)
    folium.TileLayer("CartoDB positron", name="CartoDB Positron", cross_origin=True).add_to(m)

    if not gdf_carreaux.empty:
        colormap = cm.StepColormap(
            colors=DUREE_COLOR_BANDES, index=DUREE_COLOR_SEUILS,
            vmin=0, vmax=max(budget_min, DUREE_COLOR_SEUILS[-1]), caption=legende_duree,
        )
        colormap.add_to(m)

        def style_carreau(feature):
            return {
                "fillColor": colormap(feature["properties"]["travel_time"]),
                "color": "#334",
                "weight": 0,
                "fillOpacity": 0.75,
            }

        folium.GeoJson(
            gdf_carreaux[["geometry", "travel_time"]],
            name="Carreaux atteignables",
            style_function=style_carreau,
            tooltip=folium.GeoJsonTooltip(fields=["travel_time"], aliases=[legende_duree], localize=True),
        ).add_to(m)

    folium.Marker(
        center,
        tooltip=f"Départ : {origine['stop_name']}",
        icon=folium.Icon(color="darkred", icon="play", prefix="fa"),
    ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m
