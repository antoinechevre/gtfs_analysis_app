"""
Fusionne plusieurs GTFS (data/GTFS_tomerge/) en un seul, prêt pour le
catalogue data/GTFS_Africa/ — utilisé quand un réseau est publié en
plusieurs feeds distincts et non superposés (ex: bus + métro à Cairo, bus
+ paratransit à Douala), cf. src/merge_gtfs_cairo.py et
src/merge_gtfs_douala.py pour les scripts par ville.

Concaténation simple (pas de déduplication à la Google Transit Merge Spec,
cf. https://github.com/google/transitfeed/wiki/Merge) : chaque feed garde
toutes ses entités, avec ses identifiants (stop_id, route_id, trip_id,
service_id, shape_id...) préfixés par feed pour garantir l'absence de
collision avant concaténation table par table — adapté à des réseaux
distincts (pas de recouvrement géographique bord à bord), pas à la fusion
de deux feeds décrivant le même réseau.
"""

import os

import gtfs_kit as gk
import pandas as pd

from src.utils import charger_gtfs

# Tables GTFS gérées par gtfs_kit.Feed
TABLES_GTFS = [
    "agency",
    "stops",
    "routes",
    "trips",
    "stop_times",
    "calendar",
    "calendar_dates",
    "fare_attributes",
    "fare_rules",
    "shapes",
    "frequencies",
    "transfers",
    "feed_info",
    "attributions",
]


def _etendre_calendrier_si_disjoint(feed_reference, feed):
    """Si le calendar.txt de `feed` ne chevauche pas du tout celui de
    `feed_reference` (aucune date de validité en commun), étend ses
    start_date/end_date pour couvrir la même plage — préserve le motif
    hebdomadaire (colonnes monday..sunday), ne touche qu'aux bornes de
    validité.

    Cas rencontré sur la fusion Cairo bus (calendrier 2025) + métro
    (calendrier 2020-09 à 2021-09, obsolète dans la source
    Cairo_metro.zip) : sans ce recalage, le métro n'est jamais actif le
    jour analysé (date_JOB, choisi dans la plage du feed bus) et
    n'apparaît jamais sur les cartes Arrêts/Lignes ni dans le routage
    r5py, malgré une fusion par ailleurs correcte (les 3 lignes de métro
    sont bien présentes dans routes.txt/trips.txt du GTFS fusionné). Un
    no-op quand les calendriers se chevauchent déjà (ex: Douala bus et
    paratransit, tous deux 2018-06 à 2019-07 dans leurs sources)."""
    if feed_reference.calendar is None or feed.calendar is None:
        return feed

    ref_min = feed_reference.calendar["start_date"].min()
    ref_max = feed_reference.calendar["end_date"].max()
    feed_min = feed.calendar["start_date"].min()
    feed_max = feed.calendar["end_date"].max()

    if feed_min <= ref_max and feed_max >= ref_min:
        return feed  # chevauchement déjà présent, rien à faire

    print(
        f"  → calendrier disjoint de la référence ({feed_min}-{feed_max} vs "
        f"{ref_min}-{ref_max}) : étendu à {ref_min}-{ref_max}"
    )
    feed.calendar["start_date"] = ref_min
    feed.calendar["end_date"] = ref_max
    return feed


def fusionner_gtfs(chemins_zip, chemin_sortie, dist_units="km"):
    """
    Fusionne plusieurs GTFS (fichiers zip) en un seul GTFS.

    Chaque feed est chargé (via src.utils.charger_gtfs, pour bénéficier au
    passage de la normalisation route_type appliquée partout ailleurs dans
    l'app), puis ses identifiants sont préfixés par son rang dans
    chemins_zip pour garantir l'absence de collision entre feeds, avant
    concaténation table par table. Le calendrier de chaque feed après le
    premier est aligné sur celui du premier s'il en est complètement
    disjoint (cf. _etendre_calendrier_si_disjoint) : le premier chemin de
    chemins_zip sert donc de référence de date pour tous les autres.

    Parameters
    ----------
    chemins_zip : list[str]
        Chemins des fichiers GTFS (zip) à fusionner, au moins 2.
    chemin_sortie : str
        Chemin du fichier GTFS (zip) fusionné à écrire.
    dist_units : str
        Unité de distance à utiliser pour le feed fusionné (défaut : 'km').
        Les feeds dans une autre unité sont convertis avant fusion.

    Returns
    -------
    gtfs_kit.Feed
        Le feed fusionné.
    """
    if len(chemins_zip) < 2:
        raise ValueError("Il faut au moins 2 GTFS à fusionner")

    feeds_prefixes = []
    for i, chemin in enumerate(chemins_zip):
        print(f"Chargement de {os.path.basename(chemin)}...")
        feed = charger_gtfs(chemin)

        prefixe = f"{i}_"
        print(f"  → préfixage des identifiants avec '{prefixe}'")
        feeds_prefixes.append(gk.prefix_feed_ids(feed, prefixe))

    for i in range(1, len(feeds_prefixes)):
        feeds_prefixes[i] = _etendre_calendrier_si_disjoint(feeds_prefixes[0], feeds_prefixes[i])

    tables_fusionnees = {}
    for table in TABLES_GTFS:
        dfs = [
            getattr(feed, table)
            for feed in feeds_prefixes
            if getattr(feed, table) is not None
        ]
        if not dfs:
            continue
        if table == "feed_info":
            # feed_info décrit le feed dans son ensemble (0 ou 1 ligne selon
            # la spec GTFS) : le concaténer comme les autres tables produit
            # plusieurs lignes, rejetées par les lecteurs GTFS stricts (dont
            # celui de r5py : "FeedInfo contains more than one record",
            # qui casse alors tout le TransportNetwork malgré allow_errors=True
            # — cf. l'incident Casablanca/Cairo TTM 100% NaN sauf diagonale).
            # On ne garde que la première ligne rencontrée plutôt que de
            # fusionner plusieurs feed_info entre eux.
            tables_fusionnees[table] = dfs[0].iloc[[0]].reset_index(drop=True)
        else:
            tables_fusionnees[table] = pd.concat(dfs, ignore_index=True, sort=False)

    feed_fusionne = gk.Feed(dist_units=dist_units, **tables_fusionnees)

    os.makedirs(os.path.dirname(chemin_sortie), exist_ok=True)
    feed_fusionne.to_file(chemin_sortie)
    print(f"✓ GTFS fusionné enregistré dans : {chemin_sortie}")

    return feed_fusionne
