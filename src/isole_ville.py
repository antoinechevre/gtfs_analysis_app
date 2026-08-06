"""
Isole le réseau urbain d'une ville à partir d'un GTFS régional, en
combinant un filtrage par agence(s) et une emprise géographique
(bounding box). Le résultat est exporté comme un nouveau zip GTFS,
directement utilisable par l'app / le notebook du projet.

Usage en ligne de commande :
    uv run -m src.isoler_reseau_urbain \
        --gtfs data/gtfs_regional.zip \
        --agences AGENCE_BUS_VILLE AGENCE_TRAM_VILLE \
        --bbox 45.72 -1.20 45.78 -1.10 \
        --sortie output/gtfs_urbain.zip

Pour lister les agences disponibles avant de choisir :
    uv run -m src.isoler_reseau_urbain --gtfs data/gtfs_regional.zip --lister-agences
"""

import argparse
import os
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from src.utils import charger_gtfs
from src.hf_cache import envoyer_vers_hf

BASE_DIR = Path(__file__).resolve().parent.parent
DOSSIER_GTFS_REGIONAL = BASE_DIR / "data" / "GTFS_regional"
DOSSIER_GTFS = BASE_DIR / "data" / "GTFS"


def lister_agences(feed):
    """
    Affiche les agences présentes dans le feed (numéro, agency_id,
    agency_name) et le nombre de routes associées à chacune, pour aider à
    choisir quelles agences correspondent au réseau urbain recherché. Le
    numéro affiché est celui à utiliser en mode interactif (cf.
    executer_interactif) ; --agences en ligne de commande attend
    toujours des agency_id, pas des numéros.
    """
    if feed.agency is None or feed.agency.empty:
        print("⚠ Aucune agence trouvée dans ce GTFS (agency.txt absent ou vide)")
        return

    nb_routes_par_agence = feed.routes.groupby("agency_id").size()
    print("Agences disponibles :")
    for i, (_, ligne) in enumerate(feed.agency.iterrows()):
        agency_id = ligne.get("agency_id", "")
        nb_routes = nb_routes_par_agence.get(agency_id, 0)
        print(f"  [{i}] {agency_id!r} : {ligne.get('agency_name', '?')} ({nb_routes} route(s))")


def filtrer_par_agences(feed, agency_ids):
    """
    Restreint le feed aux agences données (cascade gtfs_kit native :
    routes -> trips -> stop_times -> stops -> shapes -> calendar).
    """
    agences_absentes = set(agency_ids) - set(feed.agency["agency_id"])
    if agences_absentes:
        print(f"⚠ agency_id introuvable dans le GTFS, ignoré(s) : {sorted(agences_absentes)}")

    feed_filtre = feed.restrict_to_agencies(agency_ids)
    print(f"✓ Après filtrage par agence(s) {agency_ids} : "
          f"{len(feed_filtre.routes)} route(s), {len(feed_filtre.stops)} arrêt(s)")
    return feed_filtre


def filtrer_par_bbox(feed, lat_min, lon_min, lat_max, lon_max):
    """
    Restreint le feed aux trips ayant au moins un arrêt dans la bounding
    box donnée (lat/lon, WGS84). Complète le filtrage par agence quand
    celui-ci ne suffit pas à isoler la ville (agence régionale unique,
    ou agence urbaine débordant sur des communes hors périmètre voulu).
    """
    emprise = gpd.GeoDataFrame(
        geometry=[box(lon_min, lat_min, lon_max, lat_max)],
        crs="EPSG:4326",
    )
    feed_filtre = feed.restrict_to_area(emprise)
    print(f"✓ Après filtrage géographique : "
          f"{len(feed_filtre.routes)} route(s), {len(feed_filtre.stops)} arrêt(s)")
    return feed_filtre


def isoler_reseau_urbain(zip_path, agency_ids=None, bbox=None):
    """
    Charge un GTFS régional et le restreint au réseau urbain d'une ville,
    en appliquant successivement (si fournis) un filtrage par agence(s)
    puis un filtrage par emprise géographique.

    Parameters
    ----------
    zip_path : str
        Chemin du GTFS régional (zip).
    agency_ids : list[str] | None
        agency_id à conserver.
    bbox : tuple[float, float, float, float] | None
        (lat_min, lon_min, lat_max, lon_max) en WGS84.

    Returns
    -------
    gtfs_kit.Feed
    """
    feed = charger_gtfs(zip_path)

    if agency_ids:
        feed = filtrer_par_agences(feed, agency_ids)

    if bbox:
        feed = filtrer_par_bbox(feed, *bbox)

    if feed.routes.empty:
        print("⚠ Le filtrage ne conserve aucune route : vérifiez les agency_id / la bbox")

    return feed


def choisir_fichier_regional():
    """
    Liste les GTFS régionaux disponibles dans data/GTFS_regional/ (dossier
    de dépôt pour les GTFS pas encore isolés — distinct de data/GTFS/, le
    catalogue de GTFS déjà prêts pour l'app) et laisse en choisir un.
    Renvoie le chemin choisi, ou None si annulé/dossier vide.
    """
    fichiers = sorted(f for f in os.listdir(DOSSIER_GTFS_REGIONAL) if f.lower().endswith(".zip")) \
        if DOSSIER_GTFS_REGIONAL.is_dir() else []
    if not fichiers:
        print(f"Aucun GTFS régional trouvé dans {DOSSIER_GTFS_REGIONAL}")
        return None

    print("GTFS régionaux disponibles :")
    for i, nom in enumerate(fichiers):
        print(f"  [{i}] {nom}")
    choix = input(f"Numéro du GTFS à isoler (0-{len(fichiers) - 1}, vide pour annuler) : ").strip()
    if not choix:
        return None
    try:
        return str(DOSSIER_GTFS_REGIONAL / fichiers[int(choix)])
    except (ValueError, IndexError):
        print(f"⚠ numéro invalide : {choix!r}")
        return None


def executer_interactif():
    """
    Mode interactif complet : choisit un GTFS régional dans
    data/GTFS_regional/, liste ses agences, laisse sélectionner celles à
    garder (par numéro, cf. lister_agences), demande le nom du fichier de
    sortie, écrit le résultat dans data/GTFS/ et le renvoie vers ww_GTFS
    (best-effort, comme les autres scripts du projet).
    """
    chemin_zip = choisir_fichier_regional()
    if chemin_zip is None:
        return

    feed = charger_gtfs(chemin_zip)
    lister_agences(feed)
    if feed.agency is None or feed.agency.empty:
        return

    choix = input("\nNuméros des agences à garder, séparés par des espaces : ").strip()
    if not choix:
        print("Aucune agence sélectionnée, arrêt.")
        return

    agency_ids_disponibles = feed.agency["agency_id"].astype(str).tolist()
    agency_ids = []
    for jeton in choix.split():
        try:
            agency_ids.append(agency_ids_disponibles[int(jeton)])
        except (ValueError, IndexError):
            print(f"⚠ ignoré, numéro invalide : {jeton!r}")
    if not agency_ids:
        print("Aucune agence valide sélectionnée, arrêt.")
        return

    nom_sortie = input("Nom du fichier de sortie (ex: Stockholm_gtfs.zip) : ").strip() or "gtfs_urbain.zip"
    if not nom_sortie.lower().endswith(".zip"):
        nom_sortie += ".zip"
    chemin_sortie = str(DOSSIER_GTFS / nom_sortie)

    feed_urbain = isoler_reseau_urbain(chemin_zip, agency_ids=agency_ids)
    feed_urbain.to_file(chemin_sortie)
    print(f"✓ GTFS urbain exporté : {chemin_sortie}")

    if envoyer_vers_hf(chemin_sortie, f"GTFS/{nom_sortie}"):
        print(f"✓ Envoyé vers le dataset HF : GTFS/{nom_sortie}")
    else:
        print("⚠ Envoi vers le dataset HF échoué (ou HF_TOKEN absent)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gtfs", default=None, help="Chemin du GTFS régional (zip) ; omis = mode interactif")
    parser.add_argument("--agences", nargs="*", default=None, help="agency_id à conserver")
    parser.add_argument(
        "--bbox", nargs=4, type=float, default=None, metavar=("LAT_MIN", "LON_MIN", "LAT_MAX", "LON_MAX"),
        help="Bounding box WGS84 de la ville",
    )
    parser.add_argument("--sortie", default="output/gtfs_urbain.zip", help="Chemin du zip GTFS filtré à écrire")
    parser.add_argument("--lister-agences", action="store_true", help="Affiche les agences puis s'arrête")
    args = parser.parse_args()

    if args.gtfs is None:
        executer_interactif()
        return

    feed = charger_gtfs(args.gtfs)

    if args.lister_agences:
        lister_agences(feed)
        return

    if not args.agences and not args.bbox:
        parser.error("Fournir --agences et/ou --bbox (ou --lister-agences pour explorer le GTFS)")

    feed_urbain = isoler_reseau_urbain(args.gtfs, agency_ids=args.agences, bbox=args.bbox)
    feed_urbain.to_file(args.sortie)
    print(f"✓ GTFS urbain exporté : {args.sortie}")


if __name__ == "__main__":
    main()