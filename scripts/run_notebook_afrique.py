"""
Enchaîne index_accessibility_notebook_africa.ipynb sur tous les GTFS de
data/GTFS_Africa/ (ou un sous-ensemble filtré), un kernel Jupyter neuf par
réseau — plutôt que de relancer le notebook à la main ville par ville.

GTFS_ZIP_PATH est paramétrable via variable d'environnement (cf. la cellule
"#chemins fixes" du notebook) : ce script se contente de la positionner
avant chaque exécution, sans dupliquer la logique du notebook lui-même
(source unique de vérité pour le pipeline).

Chaque run est très long (calcul r5py par lots, cf. calculer_ttm_par_lots :
dizaines de minutes à plusieurs heures selon la taille du réseau) — prévoir
de lancer ce script en arrière-plan sur une longue session :
    nohup ./env/bin/python -m scripts.run_notebook_afrique > run_afrique.log 2>&1 &

Reprise après interruption : le notebook met déjà en cache ses résultats
lourds (extrait OSM, TTM — localement et sur Hugging Face), avec une TTM
considérée fraîche <10 jours. Relancer ce script après une interruption
(Ctrl+C, crash) refait donc vite les réseaux déjà traités (juste rechargés
depuis le cache) et ne recalcule que les réseaux restants — pas besoin
d'une logique de reprise dédiée ici.

Usage (depuis la racine du repo) :
    ./env/bin/python -m scripts.run_notebook_afrique                # tous les GTFS
    ./env/bin/python -m scripts.run_notebook_afrique Abidjan Accra   # sous-ensemble (sous-chaîne du nom de fichier)
    ./env/bin/python -m scripts.run_notebook_afrique --liste         # liste les GTFS détectés, sans rien exécuter

Prérequis (une fois) :
    ./env/bin/pip install nbclient
    ./env/bin/python -m ipykernel install --user --name gtfs-app-env \\
        --display-name "gtfs_analysis_app (env/)"
"""

import argparse
import os
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

BASE_DIR = Path(__file__).resolve().parent.parent
GTFS_DIR = BASE_DIR / "data" / "GTFS_Africa"
NOTEBOOK_PATH = BASE_DIR / "index_accessibility_notebook_africa.ipynb"
RUNS_DIR = BASE_DIR / "output" / "notebook_runs"
KERNEL_NAME = "gtfs-app-env"


def gtfs_disponibles(filtres=None):
    """Fichiers .zip de GTFS_DIR, triés par nom, filtrés (sous-chaîne,
    insensible à la casse) si `filtres` est fourni."""
    fichiers = sorted(p for p in GTFS_DIR.glob("*.zip"))
    if not filtres:
        return fichiers
    filtres_bas = [f.lower() for f in filtres]
    return [p for p in fichiers if any(f in p.name.lower() for f in filtres_bas)]


def executer_pour_gtfs(gtfs_path):
    """Exécute une copie de NOTEBOOK_PATH avec GTFS_ZIP_PATH=gtfs_path,
    sauvegarde le notebook exécuté (résultats + éventuelle erreur) dans
    RUNS_DIR, et renvoie True si l'exécution s'est terminée sans erreur."""
    os.environ["GTFS_ZIP_PATH"] = str(gtfs_path)

    nb = nbformat.read(NOTEBOOK_PATH, as_version=4)
    # timeout=None : plusieurs cellules (TTM notamment) tournent légitimement
    # pendant des dizaines de minutes à plusieurs heures — un timeout par
    # cellule interromprait le calcul en cours pour rien.
    client = NotebookClient(
        nb, kernel_name=KERNEL_NAME, timeout=None, resources={"metadata": {"path": str(BASE_DIR)}},
    )

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    sortie_path = RUNS_DIR / f"{gtfs_path.stem}.ipynb"

    erreur = None
    try:
        client.execute()
    except CellExecutionError as e:
        erreur = str(e).splitlines()[-1] if str(e).splitlines() else str(e)
    except Exception as e:
        erreur = f"{type(e).__name__}: {e}"
    finally:
        # Sauvegardé même en cas d'erreur : le notebook exécuté contient la
        # trace complète jusqu'à la cellule qui a échoué, utile pour
        # diagnostiquer sans tout relancer.
        nbformat.write(nb, sortie_path)

    return erreur, sortie_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "filtres", nargs="*",
        help="Sous-chaînes (insensibles à la casse) des noms de fichiers GTFS à traiter — tous si omis.",
    )
    parser.add_argument(
        "--liste", action="store_true",
        help="Liste les GTFS qui seraient traités, sans rien exécuter.",
    )
    args = parser.parse_args()

    fichiers = gtfs_disponibles(args.filtres)
    if not fichiers:
        print(f"Aucun GTFS trouvé dans {GTFS_DIR} avec les filtres {args.filtres!r}.", file=sys.stderr)
        sys.exit(1)

    print(f"{len(fichiers)} GTFS à traiter :")
    for f in fichiers:
        print(f"  - {f.name}")

    if args.liste:
        return

    resultats = []  # (nom, ok, duree_s, erreur_ou_None)
    for i, gtfs_path in enumerate(fichiers, start=1):
        print("\n" + "=" * 70)
        print(f"[{i}/{len(fichiers)}] {gtfs_path.name}")
        print("=" * 70)

        t0 = time.time()
        try:
            erreur, sortie_path = executer_pour_gtfs(gtfs_path)
        except KeyboardInterrupt:
            print("\nInterrompu (Ctrl+C) — arrêt propre, résumé de ce qui a été traité :")
            break
        duree_s = time.time() - t0

        if erreur is None:
            print(f"✓ {gtfs_path.name} terminé en {duree_s / 60:.1f} min -> {sortie_path}")
        else:
            print(f"✗ {gtfs_path.name} en échec après {duree_s / 60:.1f} min : {erreur}")
            print(f"  détail complet (traceback de la cellule fautive) dans {sortie_path}")

        resultats.append((gtfs_path.name, erreur is None, duree_s, erreur))

    print("\n" + "=" * 70)
    print("RÉSUMÉ")
    print("=" * 70)
    for nom, ok, duree_s, erreur in resultats:
        statut = "✓ OK" if ok else f"✗ ÉCHEC ({erreur})"
        print(f"  {nom:60s} {duree_s / 60:6.1f} min  {statut}")

    nb_echecs = sum(1 for _, ok, _, _ in resultats if not ok)
    if nb_echecs:
        print(f"\n{nb_echecs}/{len(resultats)} réseau(x) en échec.")
        sys.exit(1)


if __name__ == "__main__":
    main()
