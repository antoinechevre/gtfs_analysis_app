import gtfs_kit as gk
import pandas as pd
import numpy as np
from shapely import wkt
import geopandas as gpd
import gtfs_kit as gk
import pandas as pd
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


########################################################################
# HELPERS GTFS
########################################################################


def charger_gtfs(zip_path):
    """
    Charge le fichier GTFS à l'aide de gtfs_kit.
    Returns:
        feed: gtfs_kit Feed object
    """
    print(f"Chargement du fichier GTFS : {zip_path}")
    feed = gk.read_feed(zip_path, dist_units='km')
    print(f"✓ GTFS chargé avec succès")
    return feed





def longueur_lignes(feed):
    """
    Calcule la longueur (km) de chaque ligne (route_id).

    shapes.txt est un fichier optionnel de la spec GTFS (absent par
    exemple du jeu de données TCL) : quand il n'est pas fourni, la
    longueur est estimée à partir des arrêts desservis par chaque trip
    (distance à vol d'oiseau cumulée entre arrêts consécutifs), plutôt
    que depuis les tracés géométriques.
    """
    if feed.shapes is None or feed.shapes.empty:
        print("⚠ shapes.txt absent du GTFS : longueur des lignes estimée à partir des arrêts (distance à vol d'oiseau)")
        return _longueur_lignes_depuis_arrets(feed)

    geo_shapes = gk.geometrize_shapes(feed.shapes, use_utm=True)
    geo_shapes['longueur_km'] = geo_shapes.geometry.length / 1000
    # Associer chaque shape à sa ligne
    trips_shapes = feed.trips[['route_id', 'shape_id']].drop_duplicates()
    geo_shapes = geo_shapes.merge(trips_shapes, on='shape_id')
    longueur_par_ligne = geo_shapes.groupby('route_id')['longueur_km'].max().reset_index()
    return longueur_par_ligne


def _longueur_lignes_depuis_arrets(feed):
    """
    Longueur (km) de chaque ligne à partir des coordonnées des arrêts
    (fallback utilisé par longueur_lignes quand shapes.txt est absent).
    """
    stops = feed.stops.set_index('stop_id')[['stop_lat', 'stop_lon']]

    stop_times = feed.stop_times.merge(feed.trips[['trip_id', 'route_id']], on='trip_id')
    stop_times = stop_times.sort_values(['trip_id', 'stop_sequence'])
    stop_times = stop_times.merge(stops, on='stop_id')

    stop_times['lat_suivant'] = stop_times.groupby('trip_id')['stop_lat'].shift(-1)
    stop_times['lon_suivant'] = stop_times.groupby('trip_id')['stop_lon'].shift(-1)

    segments = stop_times.dropna(subset=['lat_suivant', 'lon_suivant'])

    R = 6371  # rayon de la Terre en km
    lat1, lon1, lat2, lon2 = map(
        np.radians,
        [segments['stop_lat'], segments['stop_lon'], segments['lat_suivant'], segments['lon_suivant']],
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    segments = segments.assign(longueur_km=R * 2 * np.arcsin(np.sqrt(a)))

    longueur_par_trip = segments.groupby(['trip_id', 'route_id'])['longueur_km'].sum().reset_index()
    longueur_par_ligne = longueur_par_trip.groupby('route_id')['longueur_km'].max().reset_index()
    return longueur_par_ligne

def km_par_ligne_jour(feed, longueur_par_ligne,date):
    """
    Calcule le total des kilomètres parcourus par ligne pour une journée donnée.

    Parameters
    ----------
    feed : gtfs_kit.Feed
        Le feed GTFS chargé.
    date : str
        Date au format YYYYMMDD.

    Returns
    -------
    DataFrame
        DataFrame avec route_id, date et le total des kilomètres parcourus.
    """
    
    active_trips = feed.get_trips(date=date)

    if active_trips.empty:
        print(f"⚠️ Aucune course pour la date {date}. Vérifiez la date ou la période de service du GTFS.")
        return pd.DataFrame(columns=['route_id', 'total_km', 'date'])

    nb_manquants = longueur_par_ligne['longueur_km'].isna().sum()
    if nb_manquants > 0:
        print(f"⚠️ {date} : {nb_manquants} routes sans longueur de shape associée")

    # Associer chaque trip actif à la longueur de son tracé
    trips_avec_longueur = active_trips.merge(longueur_par_ligne, on='route_id', how='left')

    # Sommer les km parcourus par ligne (chaque trip = un aller ou retour)
    km_par_ligne_jour = (
        trips_avec_longueur.groupby('route_id')['longueur_km']
        .sum()
        .reset_index()
        .rename(columns={'longueur_km': 'total_km'})
    )

    km_par_ligne_jour['date'] = date

    return km_par_ligne_jour

def km_par_ligne_plage(dates_service,feed):
    # Calcul jour par jour sur toute l'année
    total_vkm_per_plage = pd.DataFrame()
    longueur_par_ligne=longueur_lignes(feed)
    resultats_journaliers = []
    for date in dates_service:
        resultats_journaliers.append(km_par_ligne_jour(feed, longueur_par_ligne, date))

    total_vkm_par_jour = pd.concat(resultats_journaliers, ignore_index=True)

    # calcul somme sur une année entière

    for date in dates_service:
        total_vkm_per_plage = pd.concat([total_vkm_per_plage, km_par_ligne_jour(feed, longueur_par_ligne, date)], ignore_index=True)

    # Agrégation finale : somme des km par ligne sur l'année entière
    total_vkm_per_plage = (
        total_vkm_par_jour.groupby('route_id')['total_km']
        .sum()
        .reset_index()
        .rename(columns={'total_km': 'total_km_plage'})
    )

    # Ajout des noms de lignes et du mode de transport pour la lisibilité
    total_vkm_per_plage = total_vkm_per_plage.merge(
        feed.routes[['route_id', 'route_short_name', 'route_long_name', 'route_type']],
        on='route_id',
        how='left'
    )
    total_vkm_per_plage['mode'] = (
        total_vkm_per_plage['route_type'].map(LIBELLES_MODE).fillna(total_vkm_per_plage['route_type'].astype(str))
    )
    return total_vkm_per_plage

def obtenir_service_ids_pour_date(feed, date_str):
    """
    Identifie les service_id actifs pour une date donnée
    en tenant compte de calendar et calendar_dates
    Args:
        feed: gtfs_kit Feed object
        date_str (str): Date au format 'YYYYMMDD'
    Returns:
        list[str]: Liste des service_id actifs
    """
    date_obj = pd.to_datetime(date_str, format='%Y%m%d')
    jour_semaine = date_obj.strftime('%A').lower()  # lundi, mardi, etc.
    
    # Mapping jour de la semaine -> colonne calendar
    jour_mapping = {
        'monday': 'monday',
        'tuesday': 'tuesday', 
        'wednesday': 'wednesday',
        'thursday': 'thursday',
        'friday': 'friday',
        'saturday': 'saturday',
        'sunday': 'sunday'
    }
    
    service_ids = set()
    
    # 1. Vérifier calendar.txt
    if hasattr(feed, 'calendar') and feed.calendar is not None:
        calendar = feed.calendar.copy()
        # Convertir les dates
        calendar['start_date'] = pd.to_datetime(calendar['start_date'], format='%Y%m%d')
        calendar['end_date'] = pd.to_datetime(calendar['end_date'], format='%Y%m%d')
        
        # Filtrer les services actifs ce jour
        jour_col = jour_mapping[jour_semaine]
        services_calendar = calendar[
            (calendar['start_date'] <= date_obj) &
            (calendar['end_date'] >= date_obj) &
            (calendar[jour_col] == 1)
        ]['service_id'].tolist()
        
        service_ids.update(services_calendar)
    
    # 2. Vérifier calendar_dates.txt (exceptions)
    if hasattr(feed, 'calendar_dates') and feed.calendar_dates is not None:
        calendar_dates = feed.calendar_dates.copy()
        calendar_dates['date'] = pd.to_datetime(calendar_dates['date'], format='%Y%m%d')
        
        exceptions = calendar_dates[calendar_dates['date'] == date_obj]
        
        for _, row in exceptions.iterrows():
            if row['exception_type'] == 1:  # Service ajouté
                service_ids.add(row['service_id'])
            elif row['exception_type'] == 2:  # Service retiré
                service_ids.discard(row['service_id'])
    
    service_ids = list(service_ids)
    print(f"✓ Services actifs le {date_str} : {len(service_ids)} service(s)")
    return service_ids


########################################################################
# UTILITAIRES D'EXPORT ET DE LECTURE
########################################################################


def exporter_df_to_csv(df, chemin_fichier):
    """
    Exporte un DataFrame en CSV
    
    Parameters:
    -----------
    df : DataFrame
        DataFrame à exporter
    chemin_fichier : str
        Chemin du fichier de sortie
    """
    df.to_csv(chemin_fichier, index=False, encoding='utf-8-sig')
    print(f"✓ CSV exporté : {chemin_fichier}")
    
def exporter_gdf_to_csv(gdf, chemin_fichier):
    """
    Exporte un GeoDataFrame en CSV sans la geometry
    
    Parameters:
    -----------
    gdf : GeoDataFrame
        GeoDataFrame à exporter
    chemin_fichier : str
        Chemin du fichier de sortie
    """
    df = gdf.drop(columns=['geometry'], errors='ignore')
    df.to_csv(chemin_fichier, index=False, encoding='utf-8-sig')
    print(f"✓ CSV exporté : {chemin_fichier}")


def exporter_geojson(gdf, chemin_fichier):
    """
    Exporte un GeoDataFrame en GeoJSON.
    
    Parameters:
    -----------
    gdf : GeoDataFrame
        GeoDataFrame à exporter
    chemin_fichier : str
        Chemin du fichier de sortie
    """
    gdf.to_file(chemin_fichier, driver='GeoJSON')
    print(f"✓ GeoJSON exporté : {chemin_fichier}")


def charger_csv_avec_geometrie(chemin_fichier):
    """
    Charge un CSV contenant une colonne 'geometry' en WKT et retourne un GeoDataFrame.
    
    Parameters:
    -----------
    chemin_fichier : str
        Chemin du fichier CSV
    
    Returns:
    --------
    GeoDataFrame
    """
    df = pd.read_csv(chemin_fichier)
    
    if 'geometry' in df.columns:
        df['geometry'] = df['geometry'].apply(wkt.loads)
        gdf = gpd.GeoDataFrame(df, geometry='geometry', crs='EPSG:4326')
    else:
        gdf = gpd.GeoDataFrame(df, crs='EPSG:4326')
    
    return gdf



# Correspondance des codes route_type du GTFS vers un libellé lisible
# https://gtfs.org/schedule/reference/#routestxt
LIBELLES_MODE = {
    0: "Tram",
    1: "Métro",
    2: "Train",
    3: "Bus",
    4: "Ferry",
    5: "Tram (câble)",
    6: "Téléphérique",
    7: "Funiculaire",
    11: "Trolleybus",
    12: "Monorail",
}


def nom_reseau(feed):
    """
    Extrait le nom du réseau de transport à partir du GTFS.

    Se base sur agency_name (agency.txt), un champ obligatoire du standard
    GTFS : cette fonction fonctionne donc pour n'importe quel feed, pas
    seulement TBM. S'il y a plusieurs agences dans le feed, leurs noms sont
    concaténés.

    Parameters
    ----------
    feed : gtfs_kit.Feed
        Le feed GTFS chargé.

    Returns
    -------
    str
        Nom du réseau (ex: "TBM"), ou "Réseau" si agency.txt est vide/absent.
    """
    noms = feed.agency["agency_name"].dropna().unique()
    if len(noms) == 0:
        return "Réseau"
    return " / ".join(noms)


def recuperer_logo_reseau(feed, dossier_sortie="output"):
    """
    Va chercher le logo du réseau sur le site officiel de l'agence
    (agency_url dans agency.txt) et le télécharge localement.

    Fonctionne pour n'importe quel GTFS : agency_url est un champ
    obligatoire du standard GTFS. La fonction essaie, dans l'ordre :
    la balise <meta property="og:image">, l'icône apple-touch-icon,
    l'icône favicon <link rel="icon">, puis /favicon.ico en dernier
    recours.

    Parameters
    ----------
    feed : gtfs_kit.Feed
        Le feed GTFS chargé.
    dossier_sortie : str
        Dossier où enregistrer le logo téléchargé.

    Returns
    -------
    str or None
        Chemin local du fichier logo téléchargé, ou None si aucun
        logo n'a pu être trouvé/téléchargé.
    """
    urls_agence = feed.agency["agency_url"].dropna().unique()
    if len(urls_agence) == 0:
        print("⚠ Pas d'agency_url dans le GTFS, impossible de chercher un logo")
        return None

    url_site = urls_agence[0]
    entetes = {"User-Agent": "Mozilla/5.0 (compatible; gtfs-analysis-bot/1.0)"}

    try:
        reponse = requests.get(url_site, headers=entetes, timeout=10)
        reponse.raise_for_status()
    except requests.RequestException as e:
        print(f"⚠ Impossible de charger {url_site} : {e}")
        return None

    soup = BeautifulSoup(reponse.text, "html.parser")

    url_logo = None
    balise_og = soup.find("meta", property="og:image")
    if balise_og and balise_og.get("content"):
        url_logo = balise_og["content"]
    else:
        icone = soup.find("link", rel=lambda v: v and "apple-touch-icon" in v)
        if not icone:
            icone = soup.find("link", rel=lambda v: v and "icon" in v)
        if icone and icone.get("href"):
            url_logo = icone["href"]

    if url_logo is None:
        # Dernier recours : favicon.ico à la racine du site
        racine = f"{urlparse(url_site).scheme}://{urlparse(url_site).netloc}"
        url_logo = urljoin(racine, "/favicon.ico")
    else:
        url_logo = urljoin(url_site, url_logo)

    try:
        reponse_logo = requests.get(url_logo, headers=entetes, timeout=10)
        reponse_logo.raise_for_status()
    except requests.RequestException as e:
        print(f"⚠ Impossible de télécharger le logo ({url_logo}) : {e}")
        return None

    os.makedirs(dossier_sortie, exist_ok=True)
    extension = os.path.splitext(urlparse(url_logo).path)[1] or ".png"
    nom_fichier = f"logo_{nom_reseau(feed).replace(' ', '_')}{extension}"
    chemin_logo = os.path.join(dossier_sortie, nom_fichier)

    with open(chemin_logo, "wb") as f:
        f.write(reponse_logo.content)

    print(f"✓ Logo téléchargé : {chemin_logo}")
    return chemin_logo

