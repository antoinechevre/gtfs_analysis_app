"""
Catalogue partagé de GTFS sur Hugging Face, sur deux datasets :
- antoinechevre/accessibility-data : dataset historique de l'app sœur
  "accessibility", en lecture seule ici. Contient déjà un catalogue GTFS et
  un cache memory_troncons/ conséquents (dont IDFM en entier) — on les
  réutilise pour cette app plutôt que tout recalculer, mais on n'y écrit
  jamais depuis ici (pas notre dataset).
- antoinechevre/ww_GTFS : dataset dédié à cette app, en lecture+écriture.
  Toute donnée nouvelle (GTFS uploadé, résultat de calcul) y est déposée.

Lecture (recuperer_depuis_hf, lister_fichiers_hf) : accessibility-data
d'abord, ww_GTFS ensuite si absent du premier — les deux catalogues/caches
apparaissent donc réunis côté app. Écriture (envoyer_vers_hf) : toujours
vers ww_GTFS uniquement.

Les deux datasets étant privés, un token HF (variable d'environnement
HF_TOKEN, droits lecture pour les consulter, écriture pour contribuer à
ww_GTFS) doit être configuré dans les secrets du déploiement.
"""

import os
import shutil

HF_DATA_REPO_ID = "antoinechevre/ww_GTFS"
HF_DATA_REPO_ID_LEGACY = "antoinechevre/accessibility-data"


def recuperer_depuis_hf(nom_fichier_hf, destination_locale):
    """Télécharge nom_fichier_hf (chemin relatif dans le dataset HF, ex.
    "GTFS/reseau.zip") vers destination_locale s'il n'existe pas déjà en
    local — cherché d'abord dans HF_DATA_REPO_ID_LEGACY (cache existant),
    puis dans HF_DATA_REPO_ID si absent du premier. Retourne True si
    destination_locale est disponible après l'appel (déjà présent ou
    téléchargé avec succès), False sinon."""
    if os.path.exists(destination_locale):
        return True

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return False

    chemin_telecharge = None
    for repo_id in (HF_DATA_REPO_ID_LEGACY, HF_DATA_REPO_ID):
        try:
            chemin_telecharge = hf_hub_download(
                repo_id=repo_id,
                repo_type="dataset",
                filename=nom_fichier_hf,
                token=os.environ.get("HF_TOKEN"),
            )
            break
        except Exception as e:
            print(f"[hf_cache] recuperer_depuis_hf({nom_fichier_hf!r}) absent de {repo_id} : {e!r}")

    if chemin_telecharge is None:
        return False

    os.makedirs(os.path.dirname(destination_locale), exist_ok=True)
    shutil.copy(chemin_telecharge, destination_locale)
    return True


def envoyer_vers_hf(chemin_local, nom_fichier_hf):
    """Envoie chemin_local vers le dataset HF sous nom_fichier_hf (chemin
    relatif, ex: "GTFS/reseau.zip"). Best-effort : échec silencieux (retourne
    False) si HF_TOKEN absent/sans droit d'écriture, dataset inaccessible,
    etc. Ne doit jamais faire échouer le chargement du GTFS lui-même,
    seulement son enregistrement à distance — appelé après coup."""
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return False

    try:
        HfApi().upload_file(
            path_or_fileobj=chemin_local,
            path_in_repo=nom_fichier_hf,
            repo_id=HF_DATA_REPO_ID,
            repo_type="dataset",
            token=os.environ.get("HF_TOKEN"),
        )
    except Exception as e:
        print(f"[hf_cache] envoyer_vers_hf({nom_fichier_hf!r}) a échoué : {e!r}")
        return False
    return True


def lister_fichiers_hf(sous_dossier):
    """Liste les fichiers sous sous_dossier/ (ex: "GTFS") réunis des deux
    datasets (HF_DATA_REPO_ID_LEGACY et HF_DATA_REPO_ID), noms de fichiers
    (basename, sans le préfixe de dossier) triés, sans doublons.

    Un dataset inaccessible (token absent, hors ligne, huggingface_hub non
    installé...) est ignoré plutôt que de faire planter l'appelant ; liste
    vide si aucun des deux n'est accessible."""
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return []

    prefixe = f"{sous_dossier}/"
    api = HfApi()
    noms = set()
    for repo_id in (HF_DATA_REPO_ID_LEGACY, HF_DATA_REPO_ID):
        try:
            fichiers = api.list_repo_files(
                repo_id=repo_id,
                repo_type="dataset",
                token=os.environ.get("HF_TOKEN"),
            )
        except Exception as e:
            print(f"[hf_cache] lister_fichiers_hf({sous_dossier!r}) a échoué sur {repo_id} : {e!r}")
            continue
        noms.update(f[len(prefixe):] for f in fichiers if f.startswith(prefixe) and f != prefixe)

    return sorted(noms)


def charger_ou_calculer_avec_cache_hf(chemin_cache_local, nom_fichier_hf, fonction_calcul):
    """
    Cache à deux niveaux pour une étape de calcul coûteuse (tronçons
    uniques, indicateurs de fréquentation par tronçon...), sous
    memory_troncons/<réseau>/ dans le dataset HF :
    1. cache disque local (chemin_cache_local) si déjà présent ;
    2. sinon, tente de le récupérer depuis le dataset HF (nom_fichier_hf) —
       utile sur un déploiement Spaces fraîchement démarré, sans stockage
       persistant, mais où un run précédent (le sien ou celui d'un autre
       visiteur) a déjà calculé et renvoyé ce résultat ;
    3. sinon, calcule via fonction_calcul(), sauvegarde en local et renvoie
       vers HF (best-effort) pour que les prochains runs en profitent.

    Parameters:
    -----------
    chemin_cache_local : str
        Chemin du fichier CSV de cache local (créé si absent).
    nom_fichier_hf : str
        Chemin relatif dans le dataset HF (ex: "memory_troncons/IDFM/troncons_bus.csv").
    fonction_calcul : callable
        Fonction sans argument à appeler si aucun cache n'est disponible ;
        doit renvoyer un DataFrame ou GeoDataFrame.

    Returns:
    --------
    DataFrame ou GeoDataFrame
    """
    from src.utils import charger_csv_avec_geometrie

    if os.path.exists(chemin_cache_local):
        print(f"✓ Chargé depuis le cache local : {chemin_cache_local}")
        return charger_csv_avec_geometrie(chemin_cache_local)

    if recuperer_depuis_hf(nom_fichier_hf, chemin_cache_local):
        print(f"✓ Chargé depuis le cache Hugging Face : {nom_fichier_hf}")
        return charger_csv_avec_geometrie(chemin_cache_local)

    resultat = fonction_calcul()
    os.makedirs(os.path.dirname(chemin_cache_local), exist_ok=True)
    resultat.to_csv(chemin_cache_local, index=False)
    print(f"✓ Calculé et mis en cache localement : {chemin_cache_local}")
    envoyer_vers_hf(chemin_cache_local, nom_fichier_hf)
    return resultat
