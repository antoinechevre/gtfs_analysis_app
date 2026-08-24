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
# config git — passé uniquement le temps du push via un header HTTP.
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

# Fichiers à exclure du déploiement, en plus de deploy/ (sources des
# substitutions ci-dessous, sans intérêt une fois le Dockerfile/README
# substitués — cf. EXCLUDE_PATHS_EXTRA pour tout ajout futur).
EXCLUDE_PATHS=("deploy")
EXCLUDE_PATHS_EXTRA=()
EXCLUDE_PATHS+=("${EXCLUDE_PATHS_EXTRA[@]:-}")

git fetch "$REMOTE" "$BRANCH" -q || true
# --verify -q : échoue silencieusement (rien sur stdout/stderr) si la ref
# n'existe pas encore (Space tout juste créé, jamais poussé) — sans ce
# flag, `git rev-parse <ref inexistante>` réécrit la ref elle-même sur
# stdout en plus de son message d'erreur, que `2>/dev/null || echo ""`
# laisse passer tel quel : PARENT valait alors littéralement "hf-africa/main"
# (chaîne, pas un SHA), faisant échouer git commit-tree -p plus loin.
PARENT=$(git rev-parse --verify -q "$REMOTE/$BRANCH" 2>/dev/null || echo "")

INDEX_FILE=$(mktemp)
trap 'rm -f "$INDEX_FILE"' EXIT
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

git -c http.extraHeader="Authorization: Bearer ${HF_TOKEN}" push "$REMOTE" "${COMMIT}:refs/heads/${BRANCH}"
echo "✓ Poussé sur ${REMOTE}/${BRANCH} : ${COMMIT}"
