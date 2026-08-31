"""
Catalogue GTFS + cache de calculs sur Hugging Face, sur deux datasets :
- antoinechevre/accessibility-data : dataset historique de l'app sœur
  "accessibility", en lecture seule ici. Contient déjà des caches
  memory_troncons/ et memory_ttm/ (matrices de temps de trajet) conséquents
  (dont IDFM en entier) — on les réutilise pour cette app plutôt que tout
  recalculer, mais on n'y écrit jamais depuis ici (pas notre dataset), et on
  n'y pioche PAS le catalogue GTFS/ : cette app ne doit proposer que les
  GTFS déposés sur son propre dataset.
- antoinechevre/ww_GTFS : dataset dédié à cette app, en lecture+écriture.
  Toute donnée nouvelle (GTFS uploadé, résultat de calcul) y est déposée,
  et c'est l'unique source du catalogue GTFS/ proposé dans l'app.

Le repli sur accessibility-data (recuperer_depuis_hf, lister_fichiers_hf)
ne s'applique donc qu'aux chemins memory_troncons/ et memory_ttm/
(résultats de calcul), jamais à GTFS/ (catalogue de fichiers zip).
Écriture (envoyer_vers_hf) : toujours vers ww_GTFS uniquement.

Les deux datasets étant privés, un token HF (variable d'environnement
HF_TOKEN, droits lecture pour les consulter, écriture pour contribuer à
ww_GTFS) doit être configuré dans les secrets du déploiement.
"""

import os
import shutil

HF_DATA_REPO_ID = "antoinechevre/ww_GTFS"
HF_DATA_REPO_ID_LEGACY = "antoinechevre/accessibility-data"

# Seuls ces sous-dossiers bénéficient du repli en lecture sur
# HF_DATA_REPO_ID_LEGACY : le catalogue GTFS/ ne doit provenir que de
# HF_DATA_REPO_ID (cf. docstring du module).
SOUS_DOSSIERS_AVEC_REPLI_LEGACY = ("memory_troncons", "memory_ttm")


def _repos_pour_chemin(chemin_hf):
    """Datasets à essayer, dans l'ordre, pour lire chemin_hf (repli sur
    HF_DATA_REPO_ID_LEGACY uniquement pour les sous-dossiers listés dans
    SOUS_DOSSIERS_AVEC_REPLI_LEGACY, ex: memory_troncons/...)."""
    sous_dossier = chemin_hf.split("/", 1)[0]
    if sous_dossier in SOUS_DOSSIERS_AVEC_REPLI_LEGACY:
        return (HF_DATA_REPO_ID_LEGACY, HF_DATA_REPO_ID)
    return (HF_DATA_REPO_ID,)


def recuperer_depuis_hf(nom_fichier_hf, destination_locale):
    """Télécharge nom_fichier_hf (chemin relatif dans le dataset HF, ex.
    "GTFS/reseau.zip") vers destination_locale s'il n'existe pas déjà en
    local — cf. _repos_pour_chemin pour l'ordre des datasets essayés.
    Retourne True si destination_locale est disponible après l'appel (déjà
    présent ou téléchargé avec succès), False sinon."""
    if os.path.exists(destination_locale):
        return True

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return False

    chemin_telecharge = None
    for repo_id in _repos_pour_chemin(nom_fichier_hf):
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


def recuperer_depuis_hf_a_jour(nom_fichier_hf, destination_locale):
    """Comme recuperer_depuis_hf, mais qui ne reste jamais figée sur une
    version périmée : recuperer_depuis_hf ne télécharge que si
    destination_locale n'existe pas encore, donc un Space déjà démarré qui
    a une première fois récupéré un fichier ne le rafraîchit plus jamais,
    même après une mise à jour sur HF (observé sur GTFS_Africa/Cairo_gtfs.zip
    : le calendrier métro corrigé et repoussé sur HF restait invisible sur
    un Space déjà en cours d'exécution, qui continuait à charger sa copie
    locale d'avant le correctif).

    Passe par hf_hub_download (cache HF natif par révision/ETag — ne
    re-télécharge que si le contenu a changé) puis copie vers
    destination_locale, qui reste le chemin stable utilisé par le reste du
    code. Coût : une vérification réseau (HEAD/ETag, pas un téléchargement
    complet si le contenu n'a pas changé) à chaque appel plutôt qu'un
    simple os.path.exists — à réserver aux fichiers pouvant réellement être
    mis à jour en cours de vie d'un Space (le catalogue GTFS), pas aux gros
    fichiers rarement modifiés (PBF, TTM) où le coût réseau répété ne se
    justifie pas.

    Retourne True si destination_locale est disponible après l'appel
    (fraîchement copiée, ou repli sur une copie locale déjà là si HF est
    injoignable), False sinon."""
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return os.path.exists(destination_locale)

    chemin_telecharge = None
    for repo_id in _repos_pour_chemin(nom_fichier_hf):
        try:
            chemin_telecharge = hf_hub_download(
                repo_id=repo_id,
                repo_type="dataset",
                filename=nom_fichier_hf,
                token=os.environ.get("HF_TOKEN"),
            )
            break
        except Exception as e:
            print(f"[hf_cache] recuperer_depuis_hf_a_jour({nom_fichier_hf!r}) absent de {repo_id} : {e!r}")

    if chemin_telecharge is None:
        return os.path.exists(destination_locale)  # HF injoignable : repli sur une éventuelle copie locale

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


def _telecharger_dernier_csv(nom_fichier_hf, chemin_local):
    """Lit un CSV partagé entre plusieurs machines/déploiements via les
    datasets HF (ex: index de benchmark inter-réseaux) : contrairement à
    recuperer_depuis_hf (qui garde la copie locale si déjà présente), on
    retélécharge ici TOUJOURS la version la plus récente — ce fichier est
    modifié depuis plusieurs sources, la copie locale peut être en retard
    sur des lignes ajoutées ailleurs. Retombe sur la copie locale si HF est
    inaccessible, puis sur None si aucune des deux n'existe."""
    import pandas as pd

    try:
        from huggingface_hub import hf_hub_download

        for repo_id in _repos_pour_chemin(nom_fichier_hf):
            try:
                chemin_distant = hf_hub_download(
                    repo_id=repo_id,
                    repo_type="dataset",
                    filename=nom_fichier_hf,
                    token=os.environ.get("HF_TOKEN"),
                    force_download=True,
                )
                return pd.read_csv(chemin_distant)
            except Exception:
                continue
    except ImportError:
        pass

    if os.path.exists(chemin_local):
        return pd.read_csv(chemin_local)
    return None


def lire_csv_partage(nom_fichier_hf, chemin_local):
    """Version lecture seule de _telecharger_dernier_csv, pour un affichage
    sans vouloir y fusionner de nouvelles lignes. Retourne None si
    introuvable sur HF et en local."""
    return _telecharger_dernier_csv(nom_fichier_hf, chemin_local)


def fusionner_et_envoyer_csv(nouvelles_lignes, nom_fichier_hf, chemin_local, colonne_cle, valeur_cle):
    """Fusionne nouvelles_lignes (DataFrame) dans un CSV partagé entre
    plusieurs machines/déploiements via les datasets HF (cf.
    _telecharger_dernier_csv).

    Les lignes existantes où colonne_cle == valeur_cle sont retirées avant
    d'ajouter nouvelles_lignes (une relance remplace plutôt que duplique).
    Sauvegarde en local puis renvoie vers HF_DATA_REPO_ID (best-effort, cf.
    envoyer_vers_hf — un échec d'envoi n'empêche pas la sauvegarde locale).

    Retourne le DataFrame fusionné (celui effectivement écrit en local)."""
    import pandas as pd

    index_existant = _telecharger_dernier_csv(nom_fichier_hf, chemin_local)
    if index_existant is not None:
        index_existant = index_existant[index_existant[colonne_cle] != valeur_cle]
        tableau_final = pd.concat([index_existant, nouvelles_lignes], ignore_index=True)
    else:
        tableau_final = nouvelles_lignes

    os.makedirs(os.path.dirname(chemin_local), exist_ok=True)
    tableau_final.to_csv(chemin_local, index=False)
    envoyer_vers_hf(chemin_local, nom_fichier_hf)
    return tableau_final


def lister_fichiers_hf(sous_dossier):
    """Liste les fichiers sous sous_dossier/ (ex: "GTFS"), noms de fichiers
    (basename, sans le préfixe de dossier) triés — cf. _repos_pour_chemin
    pour l'ordre/l'ensemble des datasets consultés (GTFS/ : uniquement
    HF_DATA_REPO_ID ; memory_troncons/ : les deux, réunis).

    Un dataset inaccessible (token absent, hors ligne, huggingface_hub non
    installé...) est ignoré plutôt que de faire planter l'appelant ; liste
    vide si aucun des datasets consultés n'est accessible."""
    try:
        from huggingface_hub import HfApi
    except ImportError:
        return []

    prefixe = f"{sous_dossier}/"
    api = HfApi()
    noms = set()
    for repo_id in _repos_pour_chemin(prefixe):
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
