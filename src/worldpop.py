"""
Grille de population type "SIG" (carreaux + attribut population, comme le
carroyage INSEE utilisé par l'app sœur Accessibility_analysis, onglet
Cartographie INSEE) mais dérivée de WorldPop plutôt que de l'INSEE : couvre
n'importe quelle ville du monde, pas seulement la France.

WorldPop ne propose pas d'API renvoyant directement les données pour une
zone quelconque : la distribution se fait par raster GeoTIFF, un fichier
par pays (cf. https://hub.worldpop.org/rest/data/pop/wpgp?iso3=<ISO3>).
Le principe ici est donc : géocoder la ville centre -> construire un buffer
(disque géodésique) autour -> déterminer quel(s) pays il recouvre ->
télécharger le raster de chaque pays concerné (mis en cache localement,
plusieurs centaines de Mo pièce) -> découper au buffer -> vectoriser en
grille de polygones (agrégés à une résolution raisonnable pour l'affichage
carte, la résolution native ~100m étant ingérable en polygones folium sur
un rayon de 100km).

Nominatim (OpenStreetMap) est utilisé pour le géocodage et la détection des
pays traversés par le buffer : gratuit, sans clé, mais limité à 1
requête/seconde et nécessite un User-Agent descriptif (mêmes contraintes
que l'API Wikidata utilisée par src/population.py).
"""

import math
import os
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import pycountry
import rasterio
import requests
from affine import Affine
from rasterio.features import shapes as rio_shapes
from rasterio.mask import mask as rio_mask
from shapely.geometry import shape as shapely_shape
from shapely.ops import transform as shapely_transform
from shapely.geometry import Point, box
from pyproj import CRS, Transformer

from src.hf_cache import recuperer_depuis_hf, envoyer_vers_hf

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
# Politique d'usage Nominatim : max 1 requête/seconde, User-Agent descriptif
# obligatoire (https://operations.osmfoundation.org/policies/nominatim/).
NOMINATIM_HEADERS = {
    "User-Agent": "GTFS-analysis-universal/1.0 (https://github.com/antoinechevre/gtfs_analysis_app)"
}
NOMINATIM_DELAI_S = 1.1

WORLDPOP_API_URL = "https://hub.worldpop.org/rest/data/pop/wpgp"
WORLDPOP_DATA_BASE_URL = "https://data.worldpop.org/"

DOSSIER_CACHE_DEFAUT = os.path.join("data", "worldpop")


def geocoder_ville(nom_ville):
    """
    Géocode nom_ville via Nominatim. Renvoie (lat, lon, code_pays_alpha2)
    où code_pays_alpha2 est le code ISO 3166-1 alpha-2 en minuscules (ex:
    "fr"), ou None si Nominatim ne le fournit pas.

    Lève ValueError si la ville n'est pas trouvée.
    """
    r = requests.get(
        NOMINATIM_SEARCH_URL,
        params={"q": nom_ville, "format": "json", "limit": 1, "addressdetails": 1},
        headers=NOMINATIM_HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    resultats = r.json()
    if not resultats:
        raise ValueError(f"Ville introuvable via Nominatim : {nom_ville!r}")

    resultat = resultats[0]
    lat, lon = float(resultat["lat"]), float(resultat["lon"])
    code_pays = resultat.get("address", {}).get("country_code")
    return lat, lon, code_pays


def ville_centre_depuis_gtfs(feed):
    """
    Devine automatiquement la ville centre et le pays du réseau à partir
    des arrêts du feed GTFS, par reverse-geocoding Nominatim du centroïde
    de feed.stops : évite d'avoir à saisir "Ville, Pays" à la main pour
    construire_grille_population quand on dispose déjà du GTFS.

    Renvoie (nom_ville, lat_centre, lon_centre) où nom_ville est au format
    "Ville, Pays" (utilisable tel quel comme VILLE_CENTRE). Lève
    ValueError si Nominatim ne renvoie pas d'adresse exploitable pour ce
    point (ex: centroïde tombé en zone non peuplée).
    """
    lat = feed.stops["stop_lat"].astype(float)
    lon = feed.stops["stop_lon"].astype(float)
    lat_centre, lon_centre = lat.mean(), lon.mean()

    r = requests.get(
        NOMINATIM_REVERSE_URL,
        params={"lat": lat_centre, "lon": lon_centre, "format": "json", "addressdetails": 1, "zoom": 10},
        headers=NOMINATIM_HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    adresse = r.json().get("address", {})

    # Nominatim ne renvoie pas toujours "city" (ex: commune sans statut de
    # ville) : repli sur les champs suivants par ordre de préférence.
    # "state" en tout dernier recours seulement : dans la plupart des pays
    # c'est une région administrative (ex: "Île-de-France", pas une
    # ville), mais dans certains (ex: Abidjan en Côte d'Ivoire, "district
    # autonome" classé "state" par Nominatim) c'est le seul champ qui
    # correspond à la ville elle-même — n'est donc utilisé que si rien de
    # plus précis n'est disponible.
    nom_ville = (
        adresse.get("city")
        or adresse.get("town")
        or adresse.get("municipality")
        or adresse.get("village")
        or adresse.get("county")
        or adresse.get("state")
    )
    nom_pays = adresse.get("country")
    if not nom_ville or not nom_pays:
        raise ValueError(
            f"Reverse-geocoding Nominatim incomplet pour le centroïde des arrêts "
            f"({lat_centre:.4f}, {lon_centre:.4f}) : {adresse!r}"
        )

    return f"{nom_ville}, {nom_pays}", lat_centre, lon_centre


def buffer_geodesique(lat, lon, rayon_km):
    """
    Construit un disque de rayon_km autour de (lat, lon), en WGS84
    (EPSG:4326). Passe par une projection azimutale équidistante centrée
    sur le point (buffer exact en mètres, valable à n'importe quelle
    latitude) plutôt qu'un buffer naïf en degrés (qui déformerait le
    disque selon la latitude).
    """
    aeqd = CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs")
    wgs84 = CRS.from_epsg(4326)
    vers_aeqd = Transformer.from_crs(wgs84, aeqd, always_xy=True).transform
    vers_wgs84 = Transformer.from_crs(aeqd, wgs84, always_xy=True).transform

    centre_aeqd = shapely_transform(vers_aeqd, Point(lon, lat))
    buffer_aeqd = centre_aeqd.buffer(rayon_km * 1000, quad_segs=64)
    return shapely_transform(vers_wgs84, buffer_aeqd)


def alpha2_vers_alpha3(code_alpha2):
    """Convertit un code pays ISO 3166-1 alpha-2 en alpha-3 (ex: "fr" ->
    "FRA", le format attendu par l'API WorldPop). None si non reconnu."""
    if not code_alpha2:
        return None
    pays = pycountry.countries.get(alpha_2=code_alpha2.upper())
    return pays.alpha_3 if pays else None


def pays_couverts_par_zone(zone_geom, code_pays_centre=None, nb_points=12):
    """
    Détermine les pays (codes alpha-2) recouverts par zone_geom (Polygon
    quelconque : disque géodésique via buffer_geodesique, ou rectangle
    englobant via zone_desservie_gtfs), en interrogeant Nominatim en
    reverse-geocoding sur nb_points points répartis sur son contour.
    Approche par échantillonnage (pas de jeu de frontières téléchargé) :
    suffisant pour une zone de l'ordre de 100km, mais peut manquer un
    petit pays traversé entre deux points échantillonnés, ou entièrement
    enclavé dans la zone sans toucher son contour.
    """
    codes = set()
    if code_pays_centre:
        codes.add(code_pays_centre)

    coords_contour = list(zone_geom.exterior.coords)
    pas = max(1, len(coords_contour) // nb_points)
    points_a_tester = coords_contour[::pas]

    for pt_lon, pt_lat in points_a_tester:
        time.sleep(NOMINATIM_DELAI_S)
        try:
            r = requests.get(
                NOMINATIM_REVERSE_URL,
                params={"lat": pt_lat, "lon": pt_lon, "format": "json", "zoom": 3},
                headers=NOMINATIM_HEADERS,
                timeout=15,
            )
            r.raise_for_status()
            code = r.json().get("address", {}).get("country_code")
            if code:
                codes.add(code)
        except Exception:
            # Point en pleine mer ou sans réponse exploitable : ignoré.
            continue

    return codes


def zone_desservie_gtfs(feed, marge_km=0):
    """
    Construit la zone desservie par feed comme le rectangle (bounding box)
    englobant tous les arrêts de feed.stops, plutôt qu'un disque autour
    d'une ville centre : colle à l'étendue réelle du réseau GTFS (utile
    quand le réseau ne correspond pas à un simple rayon autour d'un point,
    ex: réseau régional allongé le long d'un axe).

    marge_km ajoute une marge (en km, approximative) sur chaque côté du
    rectangle, ex: pour inclure la population juste au-delà des arrêts
    extrêmes.

    Renvoie (geom, lat_centre, lon_centre), geom en WGS84 (EPSG:4326).
    """
    lat = feed.stops["stop_lat"].astype(float)
    lon = feed.stops["stop_lon"].astype(float)
    lat_min, lat_max = lat.min(), lat.max()
    lon_min, lon_max = lon.min(), lon.max()
    lat_centre = (lat_min + lat_max) / 2
    lon_centre = (lon_min + lon_max) / 2

    if marge_km:
        marge_lat = marge_km / 111.32
        marge_lon = marge_km / (111.32 * math.cos(math.radians(lat_centre)))
        lat_min, lat_max = lat_min - marge_lat, lat_max + marge_lat
        lon_min, lon_max = lon_min - marge_lon, lon_max + marge_lon

    return box(lon_min, lat_min, lon_max, lat_max), lat_centre, lon_centre


def url_raster_worldpop(iso3, annee):
    """Interroge l'API WorldPop pour iso3 et renvoie l'URL de téléchargement
    du GeoTIFF de population pour annee. Lève ValueError si aucun dataset
    ne correspond (avec la liste des années disponibles, pour ajuster)."""
    r = requests.get(WORLDPOP_API_URL, params={"iso3": iso3}, timeout=30)
    r.raise_for_status()
    datasets = r.json().get("data", [])

    candidats = [d for d in datasets if d.get("popyear") == str(annee)]
    if not candidats:
        annees_dispo = sorted({d.get("popyear") for d in datasets})
        raise ValueError(
            f"Pas de dataset WorldPop pour {iso3} en {annee}. "
            f"Années disponibles : {annees_dispo}"
        )
    return WORLDPOP_DATA_BASE_URL + candidats[0]["data_file"]


def telecharger_raster_worldpop(iso3, annee, dossier_cache=DOSSIER_CACHE_DEFAUT):
    """Télécharge (en streaming) le raster WorldPop de iso3/annee vers
    dossier_cache, sauf s'il y est déjà en local OU déjà sur le dataset HF
    partagé (memory_worldpop/{iso3}_ppp_{annee}.tif — plusieurs centaines
    de Mo par pays : sans ce cache, chaque nouveau conteneur/redéploiement
    du Space le retéléchargerait depuis les serveurs WorldPop à chaque
    fois, jamais partagé entre déploiements ni avec le notebook). Renvoie
    le chemin local."""
    os.makedirs(dossier_cache, exist_ok=True)
    chemin_local = os.path.join(dossier_cache, f"{iso3}_ppp_{annee}.tif")
    nom_fichier_hf = f"memory_worldpop/{iso3}_ppp_{annee}.tif"

    if os.path.exists(chemin_local):
        print(f"✓ Raster déjà en cache local : {chemin_local}")
        return chemin_local

    if recuperer_depuis_hf(nom_fichier_hf, chemin_local):
        print(f"✓ Raster repris du cache HF : {chemin_local}")
        return chemin_local

    url = url_raster_worldpop(iso3, annee)
    print(f"Téléchargement {iso3} {annee} depuis {url} ...")
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(chemin_local, "wb") as f:
            for bloc in r.iter_content(chunk_size=1024 * 1024):
                f.write(bloc)
    print(f"✓ Téléchargé : {chemin_local}")
    envoyer_vers_hf(chemin_local, nom_fichier_hf)
    return chemin_local


def decouper_et_vectoriser(chemin_tif, buffer_geom, resolution_m=1000):
    """
    Découpe le raster (chemin_tif) au buffer_geom (EPSG:4326, cf.
    buffer_geodesique) puis agrège les pixels par blocs pour atteindre
    resolution_m : la résolution native WorldPop (~100m) donnerait des
    millions de polygones sur un rayon de 100km, ingérable pour une carte
    folium. La population d'un bloc est la SOMME des pixels qui le
    composent (un dénombrement d'habitants, pas une densité à moyenner).

    Renvoie un GeoDataFrame [population, geometry] (CRS du raster source,
    WGS84 pour WorldPop), vide si le buffer ne recouvre aucun pixel
    peuplé de ce raster (ex: pays dont seule une zone inhabitée est dans
    le buffer).
    """
    with rasterio.open(chemin_tif) as src:
        lat_centre = buffer_geom.centroid.y
        # Taille approx d'un pixel en mètres à cette latitude (pixels
        # WorldPop en degrés, ~3 arc-secondes) : sert seulement à choisir
        # un facteur d'agrégation entier, pas besoin de précision fine.
        taille_pixel_m = abs(src.transform.a) * 111_320 * math.cos(math.radians(lat_centre))

        tableau, transform_decoupe = rio_mask(src, [buffer_geom], crop=True, nodata=np.nan, filled=True)
        crs = src.crs

    tableau = tableau[0]
    tableau = np.where(np.isnan(tableau) | (tableau < 0), 0, tableau)

    facteur = max(1, round(resolution_m / taille_pixel_m))
    if facteur > 1:
        nb_lignes, nb_col = tableau.shape
        nb_lignes_r = nb_lignes - nb_lignes % facteur
        nb_col_r = nb_col - nb_col % facteur
        tableau = tableau[:nb_lignes_r, :nb_col_r]
        tableau = tableau.reshape(nb_lignes_r // facteur, facteur, nb_col_r // facteur, facteur).sum(axis=(1, 3))
        transform_agrege = transform_decoupe * Affine.scale(facteur, facteur)
    else:
        transform_agrege = transform_decoupe

    if tableau.size == 0:
        return gpd.GeoDataFrame(columns=["population", "geometry"], geometry="geometry", crs=crs)

    formes = [
        {"population": valeur, "geometry": shapely_shape(geom)}
        for geom, valeur in rio_shapes(tableau.astype(np.float32), mask=tableau > 0, transform=transform_agrege)
    ]

    if not formes:
        return gpd.GeoDataFrame(columns=["population", "geometry"], geometry="geometry", crs=crs)

    return gpd.GeoDataFrame(formes, geometry="geometry", crs=crs)


def _grille_depuis_zone(zone_geom, codes_alpha3, annee, resolution_m, dossier_cache):
    """
    Partie commune aux pipelines construire_grille_population et
    construire_grille_population_gtfs : télécharge (ou réutilise le
    cache) le raster de chaque pays de codes_alpha3, le découpe/vectorise
    au zone_geom et concatène le tout en une grille de polygones
    population. Renvoie un GeoDataFrame [id, population, geometry].
    """
    if not codes_alpha3:
        raise ValueError("Aucun pays détecté sur la zone : vérifiez le nom de ville / le rayon")

    grilles = []
    for iso3 in codes_alpha3:
        chemin_tif = telecharger_raster_worldpop(iso3, annee, dossier_cache)
        grille_pays = decouper_et_vectoriser(chemin_tif, zone_geom, resolution_m)
        print(f"✓ {iso3} : {len(grille_pays)} carreaux dans la zone")
        if not grille_pays.empty:
            grilles.append(grille_pays)

    if not grilles:
        raise ValueError("Aucune donnée de population trouvée sur la zone")

    grille = gpd.GeoDataFrame(pd.concat(grilles, ignore_index=True), crs=grilles[0].crs)
    grille["id"] = range(len(grille))
    return grille


def construire_grille_population(nom_ville, rayon_km=100, annee=2020, resolution_m=1000, dossier_cache=DOSSIER_CACHE_DEFAUT):
    """
    Pipeline complet : géocode nom_ville, construit le buffer de rayon_km,
    détermine les pays traversés, télécharge (ou réutilise le cache) leurs
    rasters WorldPop annee, découpe/vectorise chacun au buffer et
    concatène le tout en une grille de polygones population.

    Renvoie (grille, lat, lon) où grille est un GeoDataFrame
    [id, population, geometry] (CRS EPSG:4326).
    """
    lat, lon, code_pays_centre = geocoder_ville(nom_ville)
    print(f"✓ {nom_ville!r} géocodée : {lat:.4f}, {lon:.4f} (pays : {code_pays_centre})")

    buffer_geom = buffer_geodesique(lat, lon, rayon_km)

    codes_alpha2 = pays_couverts_par_zone(buffer_geom, code_pays_centre=code_pays_centre)
    codes_alpha3 = sorted({c for c in (alpha2_vers_alpha3(code) for code in codes_alpha2) if c})
    print(f"✓ Pays couverts par le rayon de {rayon_km} km : {codes_alpha3}")

    grille = _grille_depuis_zone(buffer_geom, codes_alpha3, annee, resolution_m, dossier_cache)
    return grille, lat, lon


def construire_grille_population_gtfs(feed, marge_km=0, annee=2020, resolution_m=1000, dossier_cache=DOSSIER_CACHE_DEFAUT):
    """
    Variante de construire_grille_population dont la zone n'est pas un
    disque autour d'une ville centre mais le rectangle englobant tous les
    arrêts de feed (cf. zone_desservie_gtfs) : colle à l'étendue réelle du
    réseau GTFS plutôt qu'à un rayon arbitraire autour d'un point.

    marge_km : marge (km) ajoutée sur chaque côté du rectangle, cf.
    zone_desservie_gtfs.

    Renvoie (grille, lat_centre, lon_centre) comme construire_grille_population.
    """
    zone_geom, lat_centre, lon_centre = zone_desservie_gtfs(feed, marge_km=marge_km)
    print(f"✓ Zone GTFS : {len(feed.stops)} arrêts, rectangle centré sur {lat_centre:.4f}, {lon_centre:.4f}")

    codes_alpha2 = pays_couverts_par_zone(zone_geom)
    codes_alpha3 = sorted({c for c in (alpha2_vers_alpha3(code) for code in codes_alpha2) if c})
    print(f"✓ Pays couverts par la zone GTFS : {codes_alpha3}")

    grille = _grille_depuis_zone(zone_geom, codes_alpha3, annee, resolution_m, dossier_cache)
    return grille, lat_centre, lon_centre


# Résolution de grille utilisée par app_africa.py et tous ses onglets
# (Équipements, Accessibilité, Isochrone carreaux) — 800m plutôt que le
# défaut générique 400m de charger_ou_construire_grille_population_reseau
# ci-dessous (repris tel quel par l'app universelle, app.py, pour sa couche
# population optionnelle) : la TTM d'un réseau dense comme Abidjan (grille
# 400m, ~59 273 carreaux) fait ~87 Go en mémoire au rechargement
# (charger_ttm) — OOM constaté sur une machine à 16 Go de RAM. 800m
# (~14 800 carreaux, TTM ~16x plus légère, cf.
# index_accessibility_notebook_africa_800m.ipynb) est le compromis retenu.
# Tous les appels Afrique doivent utiliser CETTE résolution pour que la
# grille (partagée en session, st.session_state.grille_population) reste
# cohérente d'un onglet à l'autre, et que ses "id" correspondent à ceux de
# la TTM 800m.
RESOLUTION_M_AFRIQUE = 800


def charger_ou_construire_grille_population_reseau(
    feed, nom_reseau_str, marge_km=5, resolution_m=400, annee=2020,
    dossier_cache_worldpop=DOSSIER_CACHE_DEFAUT, dossier_cache_local=None,
):
    """
    Charge la grille de population WorldPop d'un réseau GTFS depuis le
    cache (local, puis dataset Hugging Face partagé — memory_gpkg/
    grille_population_{nom_reseau_str}.gpkg, cf. src/hf_cache.py), ou la
    construit (construire_grille_population_gtfs) si absente des deux, en
    la sauvegardant dans les deux caches pour la suite.

    Fonction pure (pas de dépendance à streamlit) : utilisée à l'identique
    depuis l'app Streamlit (app.py, views/accessibilite.py) et
    potentiellement un notebook — à chaque appelant d'entourer l'appel de
    son propre spinner/gestion d'erreur si besoin.

    marge_km/resolution_m doivent rester identiques partout où cette grille
    est utilisée conjointement à une matrice de temps de trajet (TTM) déjà
    calculée pour ce réseau (cf. views/accessibilite.py) : l'"id" de
    chaque carreau doit correspondre à celui utilisé pour construire la
    TTM (cf. index_accessibility_notebook_abidjan.ipynb, mêmes valeurs
    par défaut ici).

    Nom de cache suffixé par résolution seulement si resolution_m diffère
    du défaut historique (400m, sans suffixe — grilles déjà en cache sous
    ce nom pour les réseaux existants) : les notebooks Afrique
    600m/800m/1km (cf. index_accessibility_notebook_africa_800m.ipynb)
    utilisent une résolution différente pour la même grille — sans ce
    suffixe, deux résolutions du même réseau se marcheraient dessus (même
    nom de fichier, mauvaise grille rechargée silencieusement, comme pour
    la TTM, cf. src.utilitaires_matrix.nom_fichier_ttm).
    """
    suffixe_resolution = "" if resolution_m == 400 else f"_{resolution_m}m"
    dossier_cache_local = dossier_cache_local or os.path.join("data", "memory_gpkg")
    os.makedirs(dossier_cache_local, exist_ok=True)
    chemin_cache = os.path.join(dossier_cache_local, f"grille_population_{nom_reseau_str}{suffixe_resolution}.gpkg")
    nom_fichier_hf = f"memory_gpkg/grille_population_{nom_reseau_str}{suffixe_resolution}.gpkg"

    recuperer_depuis_hf(nom_fichier_hf, chemin_cache)
    if os.path.exists(chemin_cache):
        print(f"✓ Grille de population déjà en cache pour ce réseau, réutilisée : {chemin_cache}")
        return gpd.read_file(chemin_cache)

    grille, _, _ = construire_grille_population_gtfs(
        feed, marge_km=marge_km, annee=annee, resolution_m=resolution_m, dossier_cache=dossier_cache_worldpop,
    )
    grille.to_file(chemin_cache, driver="GPKG")
    envoyer_vers_hf(chemin_cache, nom_fichier_hf)
    return grille


def carte_population_worldpop(grille, nom_ville, annee, tiles="CartoDB positron"):
    """
    Carte HTML interactive de la grille de population WorldPop, même style
    que carte_population_infracommunale (carroyage INSEE) de l'app sœur
    Accessibility_analysis : dégradé de rouge par population, carreaux
    vides transparents. Renvoie None si grille est vide.
    """
    import folium

    from src.cartographie import fond_carte_kwargs

    if grille.empty:
        return None

    carte = grille.explore(
        "population",
        cmap="Reds",
        **fond_carte_kwargs(tiles),
        style_kwds={
            "style_function": lambda x: {
                "fillOpacity": 0 if x["properties"]["population"] == 0 else 0.7,
                "weight": 0,
                "opacity": 0,
            }
        },
        prefer_canvas=True,
    )

    titre_html = f"""
    <div style="position: fixed; top: 10px; left: 60px; z-index: 9999;
                background-color: white; padding: 6px 12px; border-radius: 4px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-size: 14px;">
        <b>Population — WorldPop {annee}</b><br>{nom_ville}
    </div>
    """
    carte.get_root().html.add_child(folium.Element(titre_html))
    return carte
