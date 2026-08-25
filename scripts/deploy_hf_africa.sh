#!/usr/bin/env bash
# Déploie l'état actuel de main vers le Space Hugging Face dédié
# antoinechevre/GTFS_Analysis_Africa (remote "hf-africa") — app séparée de
# celle déployée par deploy_hf.sh (remote "hf") : même dépôt/historique,
# mais Dockerfile et README.md substitués à la volée (cf. deploy/
# Dockerfile.africa, deploy/README.africa.md) pour pointer l'ENTRYPOINT sur
# app_africa.py plutôt que app.py, et donner au Space son propre titre/
# descriptif. app.py reste présent dans l'arborescence poussée (inoffensif,
# non exécuté par cet ENTRYPOINT) : pas la peine de le retirer.
#
# Prérequis (une fois) :
#   git remote add hf-africa https://huggingface.co/spaces/antoinechevre/GTFS_Analysis_Africa
#
# Authentification : HF_TOKEN doit être exporté dans l'environnement (droits
# écriture sur ce Space). Jamais embarqué dans l'URL du remote ni dans la
# config git — passé uniquement le temps du fetch/push via un header HTTP.
#
# Basic, pas Bearer : le frontend git de HF (www-authenticate: Basic
# realm="git-frontend") rejette un simple "Authorization: Bearer <token>"
# en 401 sur les endpoints POST (git-upload-pack pour fetch, git-receive-pack
# pour push) — seul le GET /info/refs l'accepte, ce qui masque le problème
# tant qu'on ne pousse pas réellement. Il faut du Basic (user:token en
# base64), user = propriétaire du Space (extrait de l'URL du remote).
#
# protocol.version=0, pas v2 (défaut de ce git) : le POST git-upload-pack
# de HF renvoie un corps vide (Content-Length: 0) en v2, que git interprète
# comme "fatal: expected 'acknowledgments'" ; v0 fonctionne normalement.
#
# Usage : HF_TOKEN=hf_xxx ./scripts/deploy_hf_africa.sh

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

REMOTE="hf-africa"
BRANCH="main"
MAX_SIZE=$((10 * 1024 * 1024))  # 10 MiB, limite HF hors Xet/LFS

if [ -z "${HF_TOKEN:-}" ]; then
    echo "HF_TOKEN doit être exporté (token HF avec droits écriture sur ${REMOTE})." >&2
    exit 1
fi

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
    echo "Remote '$REMOTE' absent. Ajoute-le une fois :" >&2
    echo "  git remote add $REMOTE https://huggingface.co/spaces/antoinechevre/GTFS_Analysis_Africa" >&2
    exit 1
fi

# Propriétaire du Space, extrait de l'URL du remote (.../spaces/<user>/<space>)
# plutôt que codé en dur : sert de "username" à l'auth Basic ci-dessous (cf.
# note d'authentification en tête de fichier).
HF_USERNAME=$(git remote get-url "$REMOTE" | sed -E 's#.*/spaces/([^/]+)/.*#\1#')
AUTH_HEADER="Authorization: Basic $(printf '%s:%s' "$HF_USERNAME" "$HF_TOKEN" | base64)"

# Fichiers à exclure du déploiement, en plus de deploy/ (sources des
# substitutions ci-dessous, sans intérêt une fois le Dockerfile/README
# substitués — cf. EXCLUDE_PATHS_EXTRA pour tout ajout futur).
#
# data/equipements_osm : le backend git des Spaces HF rejette tout blob
# binaire hors stockage Xet ("Your push was rejected because it contains
# binary files"), quelle que soit sa taille (indépendant du contrôle
# TOO_BIG ci-dessous, qui ne couvre que la limite 10 Mo hors Xet/LFS) — .xlsx
# et .gpkg en font partie. L'app récupère ces fichiers depuis le dataset HF
# au runtime à la place (cf. src/equipements_osm.py, recuperer_equipements_hf),
# pas besoin qu'ils soient dans l'image Docker poussée ici.
EXCLUDE_PATHS=("deploy" "data/equipements_osm")
EXCLUDE_PATHS_EXTRA=()
EXCLUDE_PATHS+=("${EXCLUDE_PATHS_EXTRA[@]:-}")

# Récupère (si elle existe) l'objet commit de la tête actuelle du Space, pour
# le lier comme parent ci-dessous (historique linéaire plutôt qu'un commit
# orphelin, que HF refuserait de toute façon en non-fast-forward).
#
# Un fetch direct HTTPS depuis CE dépôt échoue systématiquement ("fatal: the
# remote end hung up unexpectedly") : ce dépôt a trop de commits/refs locaux,
# tous proposés comme "have" pendant la négociation — la même requête aboutit
# sans problème depuis un clone tout neuf, sans historique à offrir. D'où le
# détour : clone superficiel (--depth=1) de la tête du Space dans un dossier
# temporaire (négociation triviale, aucun "have" à proposer), puis rapatrié
# dans ce dépôt via un fetch en LOCAL (transport filesystem, pas de
# négociation smart-HTTP, donc pas concerné par le problème ci-dessus).
PARENT_CLONE_DIR=$(mktemp -d)
PARENT=""
if git -c protocol.version=0 -c http.extraHeader="$AUTH_HEADER" \
    clone -q --bare --depth=1 --branch "$BRANCH" "$(git remote get-url "$REMOTE")" "$PARENT_CLONE_DIR" 2>/dev/null; then
    PARENT=$(git -C "$PARENT_CLONE_DIR" rev-parse -q --verify "$BRANCH" 2>/dev/null || echo "")
    # --update-shallow : sans ça, l'objet commit est bien rapatrié mais son
    # SHA n'est pas enregistré dans .git/shallow de CE dépôt ("warning:
    # rejected ... because shallow roots are not allowed to be updated") —
    # git le traite alors comme un commit normal et tente de remonter à SON
    # propre parent (absent localement, puisque le clone d'où il vient est
    # lui-même superficiel) dès qu'autre chose (ex: le push plus bas) a
    # besoin de parcourir son historique, avec "error: Could not read
    # <sha du grand-parent>". --update-shallow enregistre correctement la
    # frontière superficielle, qui bloque net la remontée à cet endroit.
    [ -n "$PARENT" ] && git fetch --update-shallow -q "$PARENT_CLONE_DIR" "$PARENT" 2>/dev/null || true
fi
# Sinon (Space tout juste créé, jamais poussé, ou clone temporaire indisponible) :
# PARENT reste vide, le commit ci-dessous est créé sans parent.

INDEX_FILE=$(mktemp)
trap 'rm -f "$INDEX_FILE"; rm -rf "$PARENT_CLONE_DIR"' EXIT
export GIT_INDEX_FILE="$INDEX_FILE"

git read-tree HEAD
for path in "${EXCLUDE_PATHS[@]:-}"; do
    [ -n "$path" ] && git rm --cached -q -r --ignore-unmatch -- "$path"
done

# Substitution Dockerfile/README.md : ENTRYPOINT app_africa.py + titre/
# descriptif dédiés, sans dupliquer tout le reste du dépôt dans une branche
# séparée.
DOCKERFILE_BLOB=$(git hash-object -w deploy/Dockerfile.africa)
README_BLOB=$(git hash-object -w deploy/README.africa.md)
git update-index --add --cacheinfo 100644,"$DOCKERFILE_BLOB",Dockerfile
git update-index --add --cacheinfo 100644,"$README_BLOB",README.md

TREE=$(git write-tree)
unset GIT_INDEX_FILE

TOO_BIG=$(git ls-tree -r -l "$TREE" | awk -v max="$MAX_SIZE" '$4 ~ /^[0-9]+$/ && $4+0 > max {print $4, $5}')
if [ -n "$TOO_BIG" ]; then
    echo "Fichier(s) trop volumineux pour ${REMOTE} (>10 Mo) — ajoute-les à EXCLUDE_PATHS_EXTRA dans ce script :" >&2
    echo "$TOO_BIG" >&2
    exit 1
fi

MESSAGE="Deploy snapshot of $(git rev-parse --short HEAD) — $(git log -1 --format=%s HEAD)

Africa Space: Dockerfile/README substituted (deploy/Dockerfile.africa, deploy/README.africa.md). See origin/main for full history."

if [ -n "$PARENT" ]; then
    COMMIT=$(git commit-tree "$TREE" -p "$PARENT" -m "$MESSAGE")
else
    COMMIT=$(git commit-tree "$TREE" -m "$MESSAGE")
fi

git -c protocol.version=0 -c http.extraHeader="$AUTH_HEADER" push "$REMOTE" "${COMMIT}:refs/heads/${BRANCH}"
echo "✓ Poussé sur ${REMOTE}/${BRANCH} : ${COMMIT}"
