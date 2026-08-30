import os
import pathlib

import gtfs_kit as gk
import pandas as pd
import numpy as np
from shapely import wkt
import geopandas as gpd


########################################################################
# HELPERS GTFS
########################################################################

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


# Vocabulaire GTFS étendu (https://developers.google.com/transit/gtfs/reference/extended-route-types)
# vers les codes de base (0-12) que le reste de l'app connaît : plusieurs
# réseaux européens (ex: VBB à Berlin) publient leurs route_type en
# centaines (700=bus, 900=tram...) plutôt qu'en codes de base, ce que
# gtfs_kit/l'app ne reconnaissent pas tel quel (aucun tronçon détecté).
# Bornes de plage -> code de base ; toute valeur déjà dans 0-12 ou hors de
# ces plages n'est pas modifiée.
PLAGES_ROUTE_TYPE_ETENDU = [
    (100, 200, 2),   # Railway Service (dont S-Bahn, RER régional...) -> Train
    (400, 405, 1),   # Urban Railway Service (U-Bahn...) -> Métro
    (700, 717, 3),   # Bus Service -> Bus
    (800, 801, 11),  # Trolleybus Service -> Trolleybus
    (900, 907, 0),   # Tram Service -> Tram
    (1000, 1001, 4),  # Water Transport Service -> Ferry
]


def normaliser_route_type_etendu(route_type):
    """Convertit un route_type GTFS étendu (centaines) vers son équivalent
    en code de base, cf. PLAGES_ROUTE_TYPE_ETENDU. Renvoie route_type
    inchangé s'il est déjà un code de base ou hors des plages connues."""
    for debut, fin, code_base in PLAGES_ROUTE_TYPE_ETENDU:
        if debut <= route_type < fin:
            return code_base
    return route_type


def etendue_geographique_km(feed):
    """
    Diagonale (km) de la zone couverte par les arrêts du feed (bounding
    box sur stops.txt), pour distinguer un réseau urbain compact (même
    regroupant plusieurs agences administratives) d'un réseau régional
    couvrant plusieurs villes distantes.
    """
    from math import radians, sin, cos, sqrt, atan2

    lat = feed.stops["stop_lat"].astype(float)
    lon = feed.stops["stop_lon"].astype(float)
    lat_min, lat_max = lat.min(), lat.max()
    lon_min, lon_max = lon.min(), lon.max()

    rayon_terre_km = 6371
    p1, p2 = radians(lat_min), radians(lat_max)
    dphi = radians(lat_max - lat_min)
    dlambda = radians(lon_max - lon_min)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return 2 * rayon_terre_km * atan2(sqrt(a), sqrt(1 - a))


def fusionner_agences_en_une(feed, nom_agence):
    """
    Fusionne toutes les lignes de feed.agency en une seule agence nommée
    nom_agence (agency_id conservé de la première, propagé aux autres
    tables qui y font référence : routes, fare_attributes). Modifie feed
    en place et le renvoie.

    Utile pour un GTFS urbain compact regroupant administrativement
    plusieurs agences (ex: Berlin/VBB, IDFM) que l'app ne saurait traiter
    telles quelles (garde-fou "max 3 agences", cf. app.py) — à ne pas
    utiliser sur un GTFS où les agency_id d'origine doivent rester
    distinguables (ex: RER pour IDFM, cf. MODES_IDFM dans views/troncons.py).
    """
    agency_id_unique = feed.agency["agency_id"].iloc[0]
    agence_unique = feed.agency.iloc[[0]].copy()
    agence_unique["agency_name"] = nom_agence
    feed.agency = agence_unique.reset_index(drop=True)

    for table_nom in ("routes", "fare_attributes"):
        table = getattr(feed, table_nom)
        if table is not None and "agency_id" in table.columns:
            table["agency_id"] = agency_id_unique

    return feed


def ville_str_depuis_fichier(nom_fichier_gtfs):
    """Nom de ville/réseau dérivé du nom de fichier GTFS (ex:
    "Abidjan_AMUGA_GTFS_2025_mapping_v2.zip" -> "Abidjan",
    "Accra_gtfs.zip" -> "Accra") : premier segment avant "_", en convention
    dans le catalogue data/GTFS_Africa/ (cf. _provenance.json).

    À utiliser comme clé de cache (grille, TTM, extrait OSM, équipements)
    pour app_africa.py ET index_accessibility_notebook_africa*.ipynb à la
    place de nom_reseau_str(feed) (dérivé d'agency_name) : ce dernier n'est
    pas stable pour un GTFS multi-agences (ex: Abidjan/AMUGA, 8 agences) —
    fusionner_agences_en_une donne un nom différent selon l'ordre/le
    contexte d'exécution, et un notebook qui ne fusionne pas du tout donne
    encore un autre nom (concaténation des 8 agences) — les caches HF ne se
    retrouvaient alors jamais entre l'app et le notebook. Un nom dérivé du
    fichier, lui, est trivialement déterministe et identique partout."""
    return os.path.splitext(os.path.basename(nom_fichier_gtfs))[0].split("_")[0]


def charger_gtfs(zip_path):
    """
    Charge le fichier GTFS à l'aide de gtfs_kit.
    Returns:
        feed: gtfs_kit Feed object
    """
    print(f"Chargement du fichier GTFS : {zip_path}")
    feed = gk.read_feed(zip_path, dist_units='km')

    if feed.routes is not None and not feed.routes.empty:
        route_types_origine = feed.routes["route_type"]
        feed.routes["route_type"] = route_types_origine.apply(normaliser_route_type_etendu)
        nb_convertis = (feed.routes["route_type"] != route_types_origine).sum()
        if nb_convertis:
            print(f"  → {nb_convertis} route(s) avec un route_type étendu normalisé vers un code de base")

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
    # Calcul jour par jour sur toute la plage
    longueur_par_ligne=longueur_lignes(feed)
    resultats_journaliers = []
    for date in dates_service:
        resultats_journaliers.append(km_par_ligne_jour(feed, longueur_par_ligne, date))

    total_vkm_par_jour = pd.concat(resultats_journaliers, ignore_index=True)

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
    Charge un CSV et le retourne en GeoDataFrame s'il contient une colonne
    'geometry' (en WKT), ou en DataFrame classique sinon — les indicateurs
    par arrêt (cf. calculer_indicateurs_arrets, arrets.py) n'ont pas de
    géométrie (juste stop_lat/stop_lon), donc mis en cache sans colonne
    'geometry' : geopandas interdit d'assigner un crs à un GeoDataFrame
    sans géométrie.

    Parameters:
    -----------
    chemin_fichier : str
        Chemin du fichier CSV

    Returns:
    --------
    GeoDataFrame ou DataFrame
    """
    df = pd.read_csv(chemin_fichier)

    if 'geometry' in df.columns:
        df['geometry'] = df['geometry'].apply(wkt.loads)
        return gpd.GeoDataFrame(df, geometry='geometry', crs='EPSG:4326')

    return df


def charger_ou_calculer_gdf(chemin_cache, fonction_calcul):
    """
    Cache disque pour une étape de calcul coûteuse (tronçons uniques,
    indicateurs de fréquentation par tronçon...) : charge chemin_cache s'il
    existe déjà, sinon appelle fonction_calcul() et sauvegarde le résultat
    pour que les prochaines exécutions (notebook relancé, app redémarrée,
    même réseau resélectionné) n'aient pas à tout recalculer.

    Sûr à réutiliser d'une exécution à l'autre car date_JOB est désormais
    déterministe pour un GTFS donné (cf. dates_service dans info_reseau.py) :
    les indicateurs par tronçon ne varient donc pas d'un run à l'autre tant
    que le GTFS ne change pas.

    Parameters:
    -----------
    chemin_cache : str
        Chemin du fichier CSV de cache (créé si absent).
    fonction_calcul : callable
        Fonction sans argument à appeler si le cache est absent ; doit
        renvoyer un DataFrame ou GeoDataFrame.

    Returns:
    --------
    DataFrame ou GeoDataFrame
    """
    if os.path.exists(chemin_cache):
        print(f"✓ Chargé depuis le cache : {chemin_cache}")
        return charger_csv_avec_geometrie(chemin_cache)

    resultat = fonction_calcul()
    os.makedirs(os.path.dirname(chemin_cache), exist_ok=True)
    resultat.to_csv(chemin_cache, index=False)
    print(f"✓ Calculé et mis en cache : {chemin_cache}")
    return resultat


def dir_tree(path, prefix=""):
    """Équivalent de fs::dir_tree(data_path) : affiche l'arborescence d'un dossier."""
    path = pathlib.Path(path)
    entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
    for i, entry in enumerate(entries):
        connector = "└── " if i == len(entries) - 1 else "├── "
        print(prefix + connector + entry.name)
        if entry.is_dir():
            extension = "    " if i == len(entries) - 1 else "│   "
            dir_tree(entry, prefix + extension)


def preparer_gtfs_pour_r5py(zip_path, output_path=None):
    """
    Prépare un GTFS pour r5py.TransportNetwork :
    1. Étale (expand_frequencies) un frequencies.txt non vide en trips/
       stop_times explicites. R5 (com.conveyal.r5.analyst.TravelTimeComputer)
       plante par endroits sur certains GTFS à fréquences denses avec une
       java.lang.ArrayIndexOutOfBoundsException (observé sur Freetown et
       Harare, tous deux avec de nombreuses entrées frequencies.txt) —
       expand_frequencies fait disparaître le plantage ET donne une
       couverture de service plus fidèle qu'un simple retrait de
       frequencies.txt (366/400 vs 161/400 sur un échantillon de test
       Freetown), retrait qui viderait purement et simplement le service
       fréquentiel plutôt que le représenter.
    2. Retire (passage à None avant écriture — gtfs_kit Feed.to_file omet
       les tables None, cf. gtfs_kit.feed.Feed.to_file) les tables
       optionnelles présentes mais vides (calendar, transfers, frequencies,
       fare_rules, shapes) : r5py (contrairement à gtfs_kit) distingue
       "fichier absent" de "fichier présent mais vide" et rejette le second
       cas avec une EmptyTableError au lieu de l'ignorer.

    Passe par le Feed gtfs_kit déjà chargé (pas une inspection du zip brut) :
    certains GTFS réels (ex. Freetown_gtfs.zip) empaquettent leurs tables
    dans un sous-dossier du zip plutôt qu'à la racine — gtfs_kit/R5 lisent
    ce cas sans broncher, mais une inspection zipfile au nom de fichier
    littéral ("frequencies.txt" à la racine) le manquerait silencieusement.

    Si aucune des deux étapes n'a rien à faire, le zip d'origine est
    renvoyé tel quel (aucune copie créée).

    zip_path: chemin vers le GTFS à préparer.
    output_path: chemin du GTFS nettoyé (par défaut : data/gtfs_r5py_prepared/
        "<zip_path stem>_r5py.zip" — jamais à côté de zip_path lui-même :
        zip_path vit typiquement dans data/GTFS_Africa/, le dossier catalogue
        dont l'app liste tout .zip présent (cf. app_africa.py) pour son menu
        déroulant de réseaux ; y écrire ce dérivé le ferait apparaître comme
        un réseau sélectionnable à part entière).
    Returns: chemin du GTFS à utiliser avec r5py.TransportNetwork(gtfs=...).
    """
    zip_path = pathlib.Path(zip_path)
    if output_path is None:
        dossier_prepares = pathlib.Path("data") / "gtfs_r5py_prepared"
        dossier_prepares.mkdir(parents=True, exist_ok=True)
        output_path = dossier_prepares / f"{zip_path.stem}_r5py.zip"

    feed = charger_gtfs(zip_path)
    a_modifier = False

    if feed.frequencies is not None and not feed.frequencies.empty:
        print(f"frequencies.txt non vide dans {zip_path.name} : étalement (expand_frequencies) avant chargement r5py")
        feed = feed.expand_frequencies()
        a_modifier = True

    noms_fichiers = {
        "calendar": "calendar.txt", "transfers": "transfers.txt", "frequencies": "frequencies.txt",
        "fare_rules": "fare_rules.txt", "shapes": "shapes.txt",
    }
    for attr, nom_fichier in noms_fichiers.items():
        table = getattr(feed, attr)
        if table is not None and table.empty:
            setattr(feed, attr, None)
            a_modifier = True
            print(f"{nom_fichier} vide dans {zip_path.name} : retrait avant chargement r5py")

    if not a_modifier:
        return zip_path

    feed.to_file(output_path)
    print(f"✓ GTFS nettoyé écrit dans {output_path}")
    return output_path





