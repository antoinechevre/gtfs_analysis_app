"""
Récupère la population d'une agglomération/ville via Wikidata (propriété
P1082 "population", avec sa date de référence P585) : utilisée comme axe
des abscisses du benchmark inter-réseaux (cf. src/nuage_points_benchmark.py)
et pour l'afficher dans le résumé du réseau analysé.

Wikidata plutôt qu'un scraping direct de l'infobox Wikipedia (format
variable selon les pays/langues et régulièrement modifié) : donnée
structurée, un seul format d'API à gérer quelle que soit la ville.
"""

import re

import requests

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
POPULATION_PROPERTY = "P1082"
DATE_PROPERTY = "P585"

# Wikidata/Wikimedia exige un User-Agent descriptif (403 sans ça) :
# https://meta.wikimedia.org/wiki/User-Agent_policy
HEADERS = {
    "User-Agent": "GTFS-analysis-universal/1.0 (https://github.com/antoinechevre/gtfs_analysis_app)"
}

# Priorité de désambiguïsation entre plusieurs entités Wikidata partageant
# un même nom (ex: "Roma" = Rome capitale d'Italie, mais aussi une bourgade
# du Queensland ou un prénom) : la première entité dont la description
# (en anglais, langue de recherche la plus fiable pour les exonymes, cf.
# "Roma" ne remonte pas "Rome" en recherche fr) contient un de ces mots
# est retenue, dans cet ordre de priorité.
MOTS_CLES_VILLE = ["capital", "city", "municipality", "commune", "town"]


def _rechercher_qid(nom_ville):
    """Cherche l'entité Wikidata correspondant à nom_ville, renvoie son QID
    (ex: "Q90" pour Paris) ou None si rien trouvé/erreur réseau. Parmi les
    homonymes renvoyés, privilégie celui dont la description ressemble le
    plus à une ville (cf. MOTS_CLES_VILLE) plutôt que le premier résultat
    brut (souvent un pays, un prénom ou une localité sans rapport)."""
    try:
        r = requests.get(
            WIKIDATA_API,
            params={
                "action": "wbsearchentities",
                "search": nom_ville,
                "language": "en",
                "format": "json",
                "type": "item",
                "limit": 8,
            },
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        resultats = r.json().get("search", [])
        if not resultats:
            return None

        def rang_ville(item):
            description = (item.get("description") or "").lower()
            for rang, mot in enumerate(MOTS_CLES_VILLE):
                if mot in description:
                    return rang
            return len(MOTS_CLES_VILLE)

        return sorted(resultats, key=rang_ville)[0]["id"]
    except Exception:
        return None


def _dernier_claim_population(qid):
    """Renvoie (population, annee) depuis le claim P1082 le plus récent (par
    sa qualification P585, date du recensement/estimation), ou (None, None)
    si absent/erreur."""
    try:
        r = requests.get(
            WIKIDATA_API,
            params={
                "action": "wbgetclaims",
                "entity": qid,
                "property": POPULATION_PROPERTY,
                "format": "json",
            },
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        claims = r.json().get("claims", {}).get(POPULATION_PROPERTY, [])
        if not claims:
            return None, None

        def date_du_claim(claim):
            quals = claim.get("qualifiers", {}).get(DATE_PROPERTY)
            if not quals:
                return ""
            # Format Wikidata: "+2023-01-01T00:00:00Z"
            return quals[0]["datavalue"]["value"]["time"]

        meilleur = sorted(claims, key=date_du_claim, reverse=True)[0]
        population = int(float(meilleur["mainsnak"]["datavalue"]["value"]["amount"]))
        date_str = date_du_claim(meilleur)
        annee = date_str[1:5] if date_str else None
        return population, annee
    except Exception:
        return None, None


def population_agglomeration(nom_ville):
    """
    Renvoie (population, annee) pour nom_ville via Wikidata, ou (None,
    None) si la ville n'est pas trouvée ou n'a pas de population
    renseignée. Best-effort : ne lève jamais d'exception (réseau coupé,
    ville introuvable, ambiguïté...), seulement (None, None).
    """
    qid = _rechercher_qid(nom_ville)
    if qid is None:
        return None, None
    return _dernier_claim_population(qid)


def deviner_ville_depuis_nom_fichier(nom_fichier_gtfs):
    """
    Devine un nom de ville à partir du nom de fichier GTFS (ex:
    "Roma_gtfs.zip" -> "Roma", "Chicago_google_transit.zip" -> "Chicago"),
    utilisable comme repli pour population_agglomeration quand reseau_str
    n'est pas un nom de ville (ex: agence fusionnée automatiquement comme
    "Atac"/"Arriva", cf. fusionner_agences_en_une dans app.py — le nom de
    fichier contient souvent la ville même quand agency.txt ne le donne
    pas directement).

    Approche best-effort par regex, pas de garantie de résultat correct :
    seulement un second essai avant d'abandonner la population.
    """
    base = re.sub(r"\.zip$", "", nom_fichier_gtfs, flags=re.IGNORECASE)
    base = re.sub(r"[_-]?(gtfs|merge|google[_-]?transit).*$", "", base, flags=re.IGNORECASE)
    return base.replace("_", " ").replace("-", " ").strip()
