"""
Page Accessibilité - version simplifiée de l'onglet Accessibilité du projet
sœur Accessibility_analysis (github.com/antoinechevre/Accessibility_analysis) :
deux seuils fixes (45 et 60 min) et une seule mesure "tout équipement
confondu" (pas de découpage par domaine d'équipement ni par décile de
niveau de vie) — équipements accessibles en <= 45/60 min depuis chaque
carreau (cumulative_cutoff, opportunity="equipements"), à partir du seul
fichier data/equipements_osm/{nom_reseau_str}_equipements.gpkg du réseau
chargé.

Les deux cartes sont affichées l'une au-dessus de l'autre avec un zoom/
centre synchronisé (BroadcastChannel, cf. src.cartographie.
script_synchroniser_zoom — même mécanisme que le projet sœur
Accessibility_analysis, views/accessibilite_urbaine_2.py) : zoomer/déplacer
l'une déplace l'autre à l'identique.

Nécessite une matrice de temps de trajet (TTM) pour ce réseau à la
résolution RESOLUTION_M_AFRIQUE (cf. src/worldpop.py — 600m,
index_accessibility_notebook_africa_600m.ipynb), mise en cache sur le
dataset Hugging Face partagé sous
memory_ttm/ttm_{nom_reseau_str}_{RESOLUTION_M_AFRIQUE}m.parquet (cf.
src.utilitaires_matrix.nom_fichier_ttm). Si absente, un bouton permet de
lancer le calcul complet directement depuis l'app (cf.
src.pipeline_accessibilite_afrique.calculer_pipeline_complet) — même
chaîne que le notebook (grille, OSM, équipements, r5py, TTM), mais lourde
(JVM) et bloquante (process Streamlit mono-thread pendant tout le calcul,
plusieurs dizaines de minutes possible) : à l'utilisateur de choisir de la
déclencher en connaissance de cause plutôt qu'un calcul automatique.

Avant même de songer à la TTM, tente de récupérer un résultat
cumulative_cutoff déjà mis en cache, par seuil (cf.
src.utilitaires_matrix.charger_cumulative_cutoff_cache,
memory_accessibilite/accessibilite_{nom_reseau_str}_{RESOLUTION_M_AFRIQUE}m_equipements_{cutoff}min.csv) :
si le notebook (ou un run précédent de cette page) l'a déjà calculé pour ce
réseau, cette page n'a jamais besoin de charger la TTM entière (parquet
potentiellement plusieurs Go, cf. charger_ttm) juste pour ce petit résultat.
Même principe pour chaque carte (fichier .html jumeau du .csv, cf.
charger_carte_accessibilite_cache) : évite même le coût du rendu .explore()
quand une carte déjà rendue existe. La TTM n'est chargée que si AU MOINS
un des deux seuils manque encore en cache.
"""

import os

import folium
import streamlit as st
import streamlit.components.v1 as components

from src.cartographie import fond_carte_kwargs, script_reajuster_si_masque, script_synchroniser_zoom
from src.equipements_osm import compter_equipements_par_carreau
from src.hf_cache import recuperer_depuis_hf
from src.i18n import t
from src.pipeline_accessibilite_afrique import calculer_pipeline_complet
from src.utilitaires_matrix import (
    charger_carte_accessibilite_cache,
    charger_cumulative_cutoff_cache,
    charger_ttm_reseau,
    cumulative_cutoff,
    envoyer_carte_accessibilite_cache,
    envoyer_cumulative_cutoff_cache,
    nom_fichier_carte_accessibilite,
)
from src.worldpop import charger_ou_construire_grille_population_reseau, RESOLUTION_M_AFRIQUE

CUTOFFS_MIN = [45, 60]


def accessibilite_page(lang="fr"):
    st.markdown("---")
    st.warning(t("accessibilite.avertissement_donnees", lang))

    if st.session_state.feed is None:
        st.info(t("commun.veuillez_charger_gtfs", lang))
        return

    st.info(t("accessibilite.description", lang))

    # Cette page a systématiquement besoin de la grille de population,
    # contrairement à la couche optionnelle des cartes arrêts/lignes (case à
    # cocher de la barre latérale, cf. app.py) : chargée/calculée directement
    # ici si pas déjà en cache dans la session.
    if st.session_state.grille_population is None:
        with st.spinner(t("app.spinner_grille_population", lang)):
            try:
                st.session_state.grille_population = charger_ou_construire_grille_population_reseau(
                    st.session_state.feed, st.session_state.nom_reseau_str, resolution_m=RESOLUTION_M_AFRIQUE,
                )
            except Exception as e:
                st.warning(t("accessibilite.pas_de_grille", lang, erreur=e))
                return

    grille_population = st.session_state.grille_population
    if grille_population is None or grille_population.empty:
        st.warning(t("accessibilite.pas_de_grille", lang, erreur=t("accessibilite.grille_vide", lang)))
        return

    nom_reseau_str = st.session_state.nom_reseau_str

    # Résultat cumulative_cutoff déjà mis en cache, par seuil (par un run
    # précédent de ce notebook ou de cette app, cf.
    # envoyer_cumulative_cutoff_cache ci-dessous) : évite de charger la TTM
    # entière (potentiellement plusieurs Go, cf. charger_ttm) juste pour ce
    # petit résultat déjà connu.
    cum_par_cutoff = {
        cutoff: charger_cumulative_cutoff_cache(nom_reseau_str, "equipements", cutoff, resolution_m=RESOLUTION_M_AFRIQUE)
        for cutoff in CUTOFFS_MIN
    }

    if any(cum is None for cum in cum_par_cutoff.values()):
        ttm = charger_ttm_reseau(nom_reseau_str, resolution_m=RESOLUTION_M_AFRIQUE)
        if ttm is None:
            st.warning(t("accessibilite.pas_de_ttm", lang, reseau=nom_reseau_str))
            st.warning(t("accessibilite.avertissement_calcul_complet", lang))

            if st.button(t("accessibilite.bouton_calculer", lang), type="primary"):
                statut = st.status(t("accessibilite.status_calcul", lang), expanded=True)
                try:
                    grille_population, ttm = calculer_pipeline_complet(
                        st.session_state.feed,
                        nom_reseau_str,
                        st.session_state.zip_path,
                        resolution_m=RESOLUTION_M_AFRIQUE,
                        on_step=statut.write,
                    )
                except Exception as e:
                    statut.update(label=t("accessibilite.erreur_calcul", lang, erreur=e), state="error")
                    return
                st.session_state.grille_population = grille_population
                statut.update(label=t("accessibilite.status_termine", lang), state="complete")
            else:
                return

        with st.spinner(t("accessibilite.spinner_calcul", lang)):
            # Best-effort : sur un Space déployé, data/equipements_osm/ est
            # vide (exclu du déploiement, cf. scripts/deploy_hf_africa.sh) —
            # ce .gpkg n'est disponible qu'en le récupérant depuis le
            # dataset HF partagé. Un seul fichier (celui du réseau chargé),
            # pas tout le dossier : cf.
            # compter_equipements_par_carreau(nom_reseau_str=...) ci-dessous.
            recuperer_depuis_hf(
                f"equipements_osm/{nom_reseau_str.lower()}_equipements.gpkg",
                os.path.join("data", "equipements_osm", f"{nom_reseau_str.lower()}_equipements.gpkg"),
            )
            equipements_par_carreau = compter_equipements_par_carreau(
                grille_population, nom_reseau_str=nom_reseau_str,
            )
            if equipements_par_carreau is not None:
                # Exprimé en % du score pondéré total de l'agglomération (pas
                # en score brut, difficile à interpréter seul) : par carreau,
                # part du stock total d'équipements pondérés de la ville
                # atteignable en <= cutoff min depuis ce carreau.
                score_total_agglo = equipements_par_carreau["equipements"].sum()
                for cutoff in CUTOFFS_MIN:
                    if cum_par_cutoff[cutoff] is not None:
                        continue
                    cum = cumulative_cutoff(
                        ttm, land_use_data=equipements_par_carreau, opportunity="equipements",
                        travel_cost="travel_time", cutoff=cutoff,
                    )
                    if score_total_agglo:
                        cum["equipements"] = cum["equipements"] / score_total_agglo * 100
                    envoyer_cumulative_cutoff_cache(
                        cum, nom_reseau_str, "equipements", cutoff, resolution_m=RESOLUTION_M_AFRIQUE,
                    )
                    cum_par_cutoff[cutoff] = cum

    if all(cum is None for cum in cum_par_cutoff.values()):
        st.info(t("accessibilite.pas_equipements", lang))
        return

    # Statistiques globales : moyenne pondérée par la population du carreau
    # d'origine (même principe que calculer_index_benchmark côté notebook
    # source, simplifié à un seul cutoff/groupe "Tous"), une par seuil.
    st.header(t("accessibilite.header_stats", lang))
    poids = grille_population.set_index("id")["population"]
    population_totale = poids.sum()

    colonnes_stats = st.columns(len(CUTOFFS_MIN))
    for cutoff, colonne in zip(CUTOFFS_MIN, colonnes_stats):
        cum = cum_par_cutoff[cutoff]
        if cum is None:
            continue
        moyenne_equip = (
            (cum.set_index("id")["equipements"] * poids).sum() / population_totale
            if population_totale else 0
        )
        with colonne:
            st.metric(t("accessibilite.metric_equipements", lang, cutoff=cutoff), f"{moyenne_equip:,.1f} %")
        # Mis en session pour l'onglet Benchmark (index spécifique villes
        # africaines, cf. views/benchmark.py) : substitut aux métriques
        # BPE-par-domaine du benchmark standard, indisponibles hors de France.
        st.session_state[f"accessibilite_equipements_{cutoff}min"] = moyenne_equip

    # Cartes : une par seuil, empilées (l'une au-dessus de l'autre), avec un
    # zoom/centre synchronisé entre les deux (même canal BroadcastChannel,
    # cf. script_synchroniser_zoom) — zoomer/déplacer l'une déplace l'autre à
    # l'identique. Chacune tente d'abord une carte déjà rendue en cache (par
    # le notebook ou un run précédent de cette page, cf.
    # envoyer_carte_accessibilite_cache ci-dessous) — évite même le coût du
    # rendu .explore() (jointure + génération du HTML Folium), pas seulement
    # le chargement de la TTM.
    canal_sync = f"zoom_accessibilite_{nom_reseau_str}"
    for cutoff in CUTOFFS_MIN:
        cum = cum_par_cutoff[cutoff]
        if cum is None:
            continue

        st.header(t("accessibilite.header_carte_equipements", lang, cutoff=cutoff))
        chemin_carte_cache = charger_carte_accessibilite_cache(
            nom_reseau_str, "equipements", cutoff, resolution_m=RESOLUTION_M_AFRIQUE,
        )
        if chemin_carte_cache is not None:
            with open(chemin_carte_cache, "r", encoding="utf-8") as f:
                components.html(f.read(), height=650, width=1000)
        else:
            carte_equip_df = grille_population[["id", "geometry"]].merge(cum, on="id")
            m_equip = carte_equip_df.explore(
                "equipements", cmap="magma", **fond_carte_kwargs("CartoDB positron"),
                style_kwds={"style_function": lambda x: {
                    "weight": 0, "fillOpacity": 0 if x["properties"]["equipements"] == 0 else 0.7,
                }},
            )
            minx, miny, maxx, maxy = carte_equip_df.to_crs(epsg=4326).total_bounds
            bounds = [[miny, minx], [maxy, maxx]]
            m_equip.get_root().html.add_child(folium.Element(script_reajuster_si_masque(m_equip, bounds)))
            m_equip.get_root().html.add_child(folium.Element(script_synchroniser_zoom(m_equip, canal_sync)))

            html_carte = m_equip.get_root().render()
            components.html(html_carte, height=650, width=1000)

            nom_fichier_carte = nom_fichier_carte_accessibilite(
                nom_reseau_str, "equipements", cutoff, resolution_m=RESOLUTION_M_AFRIQUE,
            )
            chemin_carte = os.path.join("data", "memory_accessibilite", nom_fichier_carte)
            os.makedirs(os.path.dirname(chemin_carte), exist_ok=True)
            with open(chemin_carte, "w", encoding="utf-8") as f:
                f.write(html_carte)
            envoyer_carte_accessibilite_cache(
                chemin_carte, nom_reseau_str, "equipements", cutoff, resolution_m=RESOLUTION_M_AFRIQUE,
            )

    # Téléchargement
    st.header(t("commun.header_telechargement", lang))
    colonnes_dl = st.columns(len(CUTOFFS_MIN))
    for cutoff, colonne in zip(CUTOFFS_MIN, colonnes_dl):
        cum = cum_par_cutoff[cutoff]
        if cum is None:
            continue
        with colonne:
            csv = cum.to_csv(index=False).encode("utf-8")
            st.download_button(
                label=t("accessibilite.telecharger_equipements", lang, cutoff=cutoff),
                data=csv,
                file_name=f"accessibilite_equipements_{cutoff}min_{nom_reseau_str}.csv",
                mime="text/csv",
                key=f"telechargement_equipements_{cutoff}",
            )
