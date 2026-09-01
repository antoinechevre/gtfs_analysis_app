"""
Compteur de visites de l'app, très simple : un événement (horodatage +
langue) par session Streamlit, ajouté à un CSV partagé sur le dataset HF
(memory_analytics/visites_afrique.csv), affiché en barre latérale.

Ce n'est pas un suivi d'utilisateurs uniques (pas d'authentification, pas
de cookie persistant côté app) : une même personne qui revient un autre
jour, ou qui recharge la page dans un nouvel onglet, compte comme une
nouvelle visite. C'est le seul niveau de granularité possible sans mettre
en place une identité visiteur, mais suffisant pour suivre l'usage global
dans le temps (nombre de visites, tendance par jour).

Best-effort à l'écriture (comme tout le reste de src/hf_cache.py) : un
échec d'enregistrement ne doit jamais empêcher l'app de fonctionner.

Concurrence : deux sessions qui écrivent au même instant peuvent se
marcher dessus (lecture-modification-écriture non atomique sur le CSV
partagé, cf. fusionner_et_envoyer_csv) — au pire une visite occasionnelle
non comptabilisée, acceptable pour un compteur indicatif.
"""

import datetime
import os
import uuid

NOM_FICHIER_HF = "memory_analytics/visites_afrique.csv"
CHEMIN_LOCAL = os.path.join("data", "memory_analytics", "visites_afrique.csv")


def enregistrer_visite(lang):
    """Ajoute une ligne de visite (horodatage UTC, langue) au CSV partagé.
    Best-effort : ne lève jamais (échec réseau/HF silencieusement ignoré),
    ne doit jamais faire échouer le chargement de la page."""
    try:
        import pandas as pd

        from src.hf_cache import fusionner_et_envoyer_csv

        ligne = pd.DataFrame([{
            "event_id": str(uuid.uuid4()),
            "horodatage": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "lang": lang,
        }])
        fusionner_et_envoyer_csv(ligne, NOM_FICHIER_HF, CHEMIN_LOCAL, "event_id", ligne["event_id"].iloc[0])
    except Exception:
        pass


def charger_visites():
    """DataFrame des visites déjà enregistrées (colonnes event_id,
    horodatage, lang), ou None si indisponible/vide."""
    try:
        from src.hf_cache import lire_csv_partage

        return lire_csv_partage(NOM_FICHIER_HF, CHEMIN_LOCAL)
    except Exception:
        return None
