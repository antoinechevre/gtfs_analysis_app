"""
Recherche et télécharge des GTFS depuis l'API Transitland (transit.land) :
utile pour trouver le GTFS d'une ville qui n'est pas simple à localiser
autrement (mobilitydatabase.org nécessite une clé API différente, les
sites officiels des agences sont à chercher un par un).

Nécessite une clé API Transitland (gratuite, cf. https://www.transit.land/
documentation/home/api-keys) fournie via la variable d'environnement
TRANSITLAND_API_KEY, ou l'argument apikey de chaque fonction.
"""

import os

import requests

API_BASE = "https://transit.land/api/v2/rest"


def _headers(apikey=None):
    apikey = apikey or os.environ.get("TRANSITLAND_API_KEY")
    if not apikey:
        raise ValueError(
            "Clé API Transitland manquante : passe apikey=... ou définis "
            "la variable d'environnement TRANSITLAND_API_KEY."
        )
    return {"apikey": apikey}


def rechercher_feeds(recherche, apikey=None, limit=10, spec="gtfs"):
    """
    Cherche des feeds Transitland par nom (ville, agence...) — ex:
    rechercher_feeds("Chicago").

    Parameters:
    -----------
    recherche : str
        Terme de recherche plein texte (nom de ville, d'agence...).
    apikey : str, optional
        Clé API Transitland (sinon lue depuis TRANSITLAND_API_KEY).
    limit : int
        Nombre maximum de résultats.
    spec : str
        Type de feed ("gtfs" par défaut ; aussi "gtfs-rt", "gbfs", "mds").

    Returns:
    --------
    list[dict] : feeds trouvés, avec notamment "onestop_id" (identifiant à
        passer à telecharger_feed), "name", "spec", "license".
    """
    r = requests.get(
        f"{API_BASE}/feeds",
        params={"search": recherche, "limit": limit, "spec": spec},
        headers=_headers(apikey),
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("feeds", [])


def telecharger_feed(feed_onestop_id, destination, apikey=None):
    """
    Télécharge le GTFS (zip) le plus récent du feed feed_onestop_id
    (identifiant Transitland, ex: "f-9q9-caltrain", cf. rechercher_feeds)
    vers destination.

    Échoue (exception levée par raise_for_status) si la licence du feed
    source n'autorise pas la redistribution — Transitland refuse alors le
    téléchargement (403/404 selon les cas).

    Returns:
    --------
    str : destination (si le téléchargement a réussi)
    """
    r = requests.get(
        f"{API_BASE}/feeds/{feed_onestop_id}/download_latest_feed_version",
        headers=_headers(apikey),
        timeout=120,
        stream=True,
    )
    r.raise_for_status()

    os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
    with open(destination, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)

    print(f"✓ GTFS téléchargé : {destination}")
    return destination


DOSSIER_GTFS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "GTFS")


if __name__ == "__main__":
    # Usage : python -m src.telecharger_transitland "Chicago" (argument en
    # ligne de commande), ou sans argument pour se voir demander le nom de
    # la ville. TRANSITLAND_API_KEY doit être exportée avant de lancer.
    # Le feed choisi est téléchargé directement dans data/GTFS/.
    import sys

    recherche = sys.argv[1] if len(sys.argv) > 1 else input("Ville à rechercher : ").strip()
    print(f"Recherche de feeds GTFS pour {recherche!r}...")
    feeds = rechercher_feeds(recherche)

    if not feeds:
        print("Aucun résultat.")
    else:
        for i, feed in enumerate(feeds):
            url = (feed.get("urls") or {}).get("static_current") or "?"
            licence = (feed.get("license") or {}).get("spdx_identifier") or "?"
            print(f"  [{i}] {feed.get('onestop_id')} — licence: {licence} — {url}")

        choix = input(f"Numéro du feed à télécharger (0-{len(feeds) - 1}, vide pour annuler) : ").strip()
        if choix:
            feed_choisi = feeds[int(choix)]
            nom_fichier = f"{recherche.strip().replace(' ', '_')}_gtfs.zip"
            destination = os.path.join(DOSSIER_GTFS, nom_fichier)
            telecharger_feed(feed_choisi["onestop_id"], destination)
