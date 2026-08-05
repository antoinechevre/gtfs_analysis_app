"""
Récupère la population d'une agglomération/ville via Wikidata (propriété
P1082 "population", avec sa date de référence P585) : utilisée comme axe
des abscisses du benchmark inter-réseaux (cf. src/nuage_points_benchmark.py)
et pour l'afficher dans le résumé du réseau analysé.

Wikidata plutôt qu'un scraping direct de l'infobox Wikipedia (format
variable selon les pays/langues et régulièrement modifié) : donnée
structurée, un seul format d'API à gérer quelle que soit la ville.
"""

import requests

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
POPULATION_PROPERTY = "P1082"
DATE_PROPERTY = "P585"

# Wikidata/Wikimedia exige un User-Agent descriptif (403 sans ça) :
# https://meta.wikimedia.org/wiki/User-Agent_policy
HEADERS = {
    "User-Agent": "GTFS-analysis-universal/1.0 (https://github.com/antoinechevre/gtfs_analysis_app)"
}


def _rechercher_qid(nom_ville):
    """Cherche l'entité Wikidata correspondant à nom_ville, renvoie son QID
    (ex: "Q90" pour Paris) ou None si rien trouvé/erreur réseau."""
    try:
        r = requests.get(
            WIKIDATA_API,
            params={
                "action": "wbsearchentities",
                "search": nom_ville,
                "language": "fr",
                "format": "json",
                "type": "item",
                "limit": 1,
            },
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        resultats = r.json().get("search", [])
        return resultats[0]["id"] if resultats else None
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
