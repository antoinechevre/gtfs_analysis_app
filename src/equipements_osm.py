"""
Dispatch des équipements OSM (data/equipements_osm/*.gpkg, cf.
extraire_amenities_osm.py et index_accessibility_notebook_africa.ipynb) sur
une grille de carreaux (population WorldPop, cf. src/worldpop.py) : jointure
spatiale point-dans-polygone, sommée par carreau (colonne "ponderation").

Fonction partagée entre views/accessibilite.py (score utilisé comme
"opportunité" pour cumulative_cutoff) et views/equipements.py (carte grille
de densité pondérée) — un seul endroit pour cette logique.
"""

import glob
import os

import geopandas as gpd
import pandas as pd

DOSSIER_EQUIPEMENTS_DEFAUT = os.path.join("data", "equipements_osm")


def recuperer_equipements_hf(dossier=DOSSIER_EQUIPEMENTS_DEFAUT):
    """Télécharge (best-effort, ceux pas déjà en local) tous les .gpkg
    disponibles sous equipements_osm/ sur le dataset HF partagé, vers
    `dossier`. À appeler avant compter_equipements_par_carreau sur un
    déploiement qui n'a pas ces fichiers dans son image (contrairement au
    poste de dev, où ils sont commités dans le dépôt) : le backend git des
    Spaces HF rejette tout blob binaire hors stockage Xet (.xlsx, .gpkg),
    donc data/equipements_osm est exclu du déploiement (cf.
    scripts/deploy_hf_africa.sh, EXCLUDE_PATHS) — cette fonction est l'unique
    façon dont ces fichiers atteignent un Space déployé."""
    from src.hf_cache import lister_fichiers_hf, recuperer_depuis_hf

    for nom_fichier in lister_fichiers_hf("equipements_osm"):
        if not nom_fichier.endswith(".gpkg"):
            continue
        recuperer_depuis_hf(f"equipements_osm/{nom_fichier}", os.path.join(dossier, nom_fichier))


def compter_equipements_par_carreau(grille_population, dossier=DOSSIER_EQUIPEMENTS_DEFAUT):
    """
    Union de tous les .gpkg de `dossier` (un point par équipement OSM,
    colonne "ponderation" par type), jointure spatiale dans les carreaux de
    grille_population, sommés par carreau (colonne "equipements" = score
    pondéré, pas un simple comptage). Un fichier sans colonne "ponderation"
    (format hérité) retombe sur un poids de 1 par équipement.

    Renvoie un DataFrame [id, equipements], ou None si `dossier` ne contient
    aucun .gpkg.
    """
    fichiers = sorted(glob.glob(os.path.join(dossier, "*.gpkg")))
    if not fichiers:
        return None

    couches = []
    for f in fichiers:
        gdf = gpd.read_file(f)
        if "ponderation" not in gdf.columns:
            gdf["ponderation"] = 1
        couches.append(gdf[["ponderation", "geometry"]])

    points = gpd.GeoDataFrame(pd.concat(couches, ignore_index=True), crs="EPSG:4326")
    jointure = gpd.sjoin(points, grille_population[["id", "geometry"]], how="inner", predicate="within")
    scores = jointure.groupby("id")["ponderation"].sum().rename("equipements")

    resultat = grille_population[["id"]].merge(scores, on="id", how="left")
    resultat["equipements"] = resultat["equipements"].fillna(0)
    return resultat
