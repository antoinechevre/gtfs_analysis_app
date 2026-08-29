"""
Traductions de l'interface (fr/en) et fonction d'accès t().

Chaque texte visible par l'utilisateur (app Streamlit, cartes Folium,
exports HTML) est identifié par une clé stable ; TRANSLATIONS contient
la version française et anglaise de chaque clé. t() renvoie la traduction
demandée, avec repli sur le français si la clé manque dans la langue
demandée, et sur la clé elle-même si elle n'existe nulle part.
"""

LANGUES = {"fr": "🇫🇷 Français", "en": "🇬🇧 English"}

TRANSLATIONS = {
    "fr": {
        # --- app.py : navigation et chargement ---
        "app.title": "🚌 Analyse GTFS - Indicateurs de Transport",
        "app.nav_accueil": "🏠 Accueil",
        "app.nav_arrets": "📍 Arrêts",
        "app.nav_lignes": "🛤️ Lignes",
        "app.nav_benchmark": "📊 Benchmark",
        "app.nav_benchmark_afrique": "🌍📊 Benchmark Afrique",
        "app.nav_equipements": "🏥 Équipements",
        "app.nav_accessibilite": "🧭 Accessibilité",
        "app.groupe_accueil": "🏠 Accueil",
        "app.groupe_analyse_reseau": "🚏 Analyse réseau",
        "app.groupe_accessibilite_urbaine": "📈 Analyse accessibilité urbaine",
        "app.groupe_benchmark": "📊 Benchmark",
        "app.sidebar_header": "📁 Paramètres d'analyse",
        "app.sidebar_uploader": "Uploader le fichier GTFS (zip)",
        "app.sidebar_gtfs_existant": "...ou choisir un GTFS déjà présent",
        "app.aucun_gtfs_local": "— aucun —",
        "app.spinner_recuperation_hf": "Récupération de {nom} depuis Hugging Face...",
        "app.erreur_recuperation_hf": "Impossible de récupérer {nom} depuis Hugging Face.",
        "app.toast_envoi_hf": "✓ {nom} envoyé vers Hugging Face (réutilisable aux prochains déploiements)",
        "app.sidebar_langue": "🌐 Langue",
        "app.spinner_chargement": "Chargement du fichier GTFS...",
        "app.erreur_chargement": "Erreur lors du chargement : {erreur}",
        "app.erreur_trop_agences": "⚠ Ce GTFS regroupe {n} agences sur une zone étendue (~{etendue} km) : réseau régional, plusieurs villes distantes. Charger un GTFS urbain uniquement.",
        "app.transitland_titre": "🔎 Chercher un GTFS sur Transitland",
        "app.transitland_recherche": "Ville ou réseau à rechercher",
        "app.transitland_erreur_recherche": "Erreur lors de la recherche Transitland : {erreur}",
        "app.transitland_aucun_resultat": "Aucun résultat.",
        "app.transitland_choisir": "Feed à télécharger",
        "app.transitland_telecharger": "📥 Télécharger",
        "app.transitland_telechargement_en_cours": "Téléchargement depuis Transitland...",
        "app.transitland_succes": "✓ {nom} téléchargé — choisissez-le dans le menu déroulant ci-dessus",
        "app.transitland_erreur_telechargement": "Erreur lors du téléchargement : {erreur}",
        "app.nav_villes_africaines": "🌍 Villes africaines",
        "africa.title": "🌍 GTFS Analysis Africa",
        "africa.avertissement_general": "⚠ Données et résultats à manier avec précaution : il n'existe pas de recensement fiable à l'échelle infracommunale pour la plupart de ces villes (les données de population WorldPop sont une estimation modélisée, pas un comptage), la couverture OpenStreetMap des équipements est très inégale selon les villes et les quartiers, et plusieurs GTFS de ce catalogue datent de 2018-2020 et ne sont plus maintenus (cf. data/GTFS_Africa/_provenance.json). Les résultats (grille de population, équipements, accessibilité) sont des ordres de grandeur, pas des chiffres de référence.",

        # --- views/home_afrique.py --- (même modèle que le projet sœur
        # Accessibility_analysis, views/home.py : intro + onglets Objectifs/
        # Fonctionnalités/Liens avec expanders)
        "home_afrique.intro_md": """
Cette application analyse des réseaux de transport africains à partir de GTFS, en s'inspirant des travaux du livre *Introduction to urban accessibility* (Rafael H. M. Pereira et Daniel Herszenhut, Ipea - Institute for Applied Economic Research), notamment le chapitre [Calculating accessibility estimates in R](https://ipeagit.github.io/intro_access_book/3_calculando_acesso.en.html) — réadaptés en Python pour un contexte hors de France, où la Base Permanente des Équipements (BPE, INSEE) et le carroyage population INSEE 200x200 m n'existent pas.

**Concepteur :** Antoine Chèvre 🐐 (et claude.ai....)

Cette application regroupe deux types d'analyses se basant sur le même jeu de données GTFS : l'analyse d'accessibilité urbaine aux équipements en transport collectif / piéton, et l'analyse du réseau de transport collectif en lui-même — cf. le projet sœur [Accessibility_analysis](https://github.com/antoinechevre/Accessibility_analysis) (contexte France) dont ce volet Afrique est dérivé.
""",
        "home_afrique.titre_section_md": "## 📍 Analyse accessibilité urbaine",
        "home_afrique.onglet_objectifs": "🎯 Objectifs",
        "home_afrique.onglet_fonctionnalites": "⚙️ Fonctionnalités",
        "home_afrique.onglet_liens": "🔗 Liens & Instructions",
        "home_afrique.objectifs_md": """
- **Offrir une chaîne de traitement** pour passer d'un jeu GTFS brut à l'analyse d'accessibilité du réseau concerné, sans dépendre de données INSEE :
    - en mode piéton/transports collectifs en JOB à l'heure de pointe
    - des équipements OpenStreetMap pondérés (substitut à la BPE) à 60 min du réseau
    - selon une grille de population WorldPop 600x600 m (substitut au carroyage INSEE)
- **Proposer un calcul directement depuis l'app** si aucune matrice de temps de trajet n'est déjà en cache, sans passer par le notebook
- **Proposer un benchmark entre villes africaines** en comparant les indicateurs d'accessibilité aux équipements, séparé du benchmark standard (population Wikidata/BPE peu fiables hors de France)
""",
        "home_afrique.fonctionnalites_md": """
À partir d'un GTFS africain du catalogue (ou uploadé) :

1. Construit le réseau multimodal piéton + transport collectif (`r5py`) à partir du GTFS pour une date JOB indiquée, et le réseau viaire pour les cheminements piétons (extrait OpenStreetMap Geofabrik, découpé sur la zone desservie)
2. Récupère la grille de population WorldPop (raster mondial, résolution ~100m rééchantillonné en carreaux de 600x600 m) sur le rectangle englobant les arrêts du GTFS, et les équipements OpenStreetMap pondérés par type sur cette même zone
3. Calcule la matrice des temps de trajet (`TravelTimeMatrix`) entre tous les carreaux, à l'heure de pointe en JOB
4. Calcule l'accessibilité aux équipements à 60 min (opportunités cumulées, `cumulative_cutoff`)
5. Propose un benchmark inter-villes africaines sur ces indicateurs

#### 🗺️ Isochrone carreaux
- Carte interactive des carreaux atteignables en moins de X minutes depuis un arrêt sélectionné, directement lue depuis la matrice de temps de trajet déjà calculée — équivalent de l'onglet "Isochrone TTM" de l'app sœur, mais sur la grille WorldPop plutôt que le carroyage INSEE
""",
        "home_afrique.expander_equipements_titre": "Détail de la pondération des équipements (substitut OSM à la BPE)",
        "home_afrique.expander_equipements_md": """
Pas de Base Permanente des Équipements hors de France : tous les points OpenStreetMap taggés `amenity=*` sont extraits (osmium, extrait Geofabrik local — pas de dépendance à l'API Overpass), puis pondérés par type via un référentiel défini à la main sur Abidjan (`data/equipements_osm/Abidjan_amenities.xlsx`, feuille "resume_par_type") et réutilisé tel quel comme référentiel unique pour toutes les villes : 0 = pas un pôle d'équipement pertinent, jusqu'à 30 pour les équipements structurants (hôpital, gouvernement, bâtiment public...).

Pas de découpage par domaine (santé, enseignement, commerces...) comme la BPE : un seul score pondéré, "tout équipement confondu".
""",
        "home_afrique.expander_indicateurs_titre": "Détail des indicateurs d'accessibilité",
        "home_afrique.expander_indicateurs_md": """
- **Opportunités cumulées** : nombre d'équipements (pondérés) atteignables depuis chaque carreau en 60 min — mesure retenue pour l'onglet Accessibilité de l'app
- **Coût au plus proche, gravité, compétition (Enhanced 2SFCA)** : calculés aussi dans le notebook (`index_accessibility_notebook_africa_600m.ipynb`), non repris dans l'app pour rester simple
""",
        "home_afrique.liens_md": """
### Liens rapides

- **📓 Ouvrage de référence** : [Introduction to urban accessibility](https://ipeagit.github.io/intro_access_book/3_calculando_acesso.en.html) — chapitre adapté : [3. Calculating accessibility estimates in R](https://ipeagit.github.io/intro_access_book/s2_calculo.en.html)
- **📓 Ce projet** : [gtfs_analysis_app](https://github.com/antoinechevre/gtfs_analysis_app) (`app_africa.py`, `index_accessibility_notebook_africa_600m.ipynb`)
- **📓 Projet sœur (France)** : [Accessibility_analysis](https://github.com/antoinechevre/Accessibility_analysis)
- **🚏 App universelle (tous pays, arrêts/lignes uniquement)** : [GTFS Analysis Universal](https://huggingface.co/spaces/antoinechevre/GTFS_Analysis_Universal)

### Instructions

1. **Choisissez un GTFS** du catalogue (barre latérale) ou uploadez le vôtre
2. **Naviguez entre les pages** pour explorer les analyses
""",
        "home_afrique.credits_md": """
Antoine Chèvre [@antoinechevre](https://github.com/antoinechevre) 🐐
In we goat we trust
""",
        "home_afrique.titre_gtfs_md": "## 🚏 Analyse GTFS",
        "home_afrique.gtfs_intro_md": """
L'analyse GTFS (indépendante de l'accessibilité ci-dessus) a été développée lors du Hackathon TSNI 2025 du Cerema et reprise par Antoine Chèvre (et claude.ai...).

**Équipe Cerema :** Patrick Gendre, Hugo De Luca et Maxence Liogier
""",
        "home_afrique.gtfs_fonctionnalites_md": """
Analyse des données GTFS (General Transit Feed Specification) pour extraire des indicateurs clés sur les transports en commun — indépendamment de l'analyse d'accessibilité ci-dessus. Détermine la plage temporelle sur laquelle le GTFS est actif et identifie un JOB (jour ouvré de base, mardi ou jeudi le plus loin dans le temps sur cette plage).

#### 📍 Analyse par arrêts
- Nombre de passages par arrêt
- Carte interactive des arrêts
- Statistiques détaillées

Fonctionne avec n'importe quel GTFS, même sans `shapes.txt`.

#### 🛤️ Analyse par lignes
- Nombre de passages par ligne, par mode (bus, tram, métro, trolley, ferry...)
- Calcul des vitesses moyennes
- Carte interactive des lignes
""",
        "home_afrique.gtfs_liens_md": """
- **📓 Hackathon Cerema** : [Notebook Google Colab](https://colab.research.google.com/github/CEREMA/hackathon-gtfs/blob/main/gtfs_notebook.ipynb) — prendre en main le code, exécuter les cellules et regarder les cartographies dynamiques
- **📓 Application universelle** : [GTFS Analysis Universal](https://huggingface.co/spaces/antoinechevre/GTFS_Analysis_Universal)

Où trouver un GTFS africain :
- Catalogue de ce projet : `data/GTFS_Africa/` (cf. `data/GTFS_Africa/_provenance.json` pour la source et la date de chaque fichier)
- À l'international : [transit.land](https://www.transit.land/)
""",
        "app.dialog_afrique_titre": "🌍 Charger un réseau africain",
        "app.dialog_afrique_aucun": "Aucun GTFS trouvé dans {dossier}. Déposez-y un fichier .zip pour qu'il apparaisse ici.",
        "app.dialog_afrique_choisir": "Réseau à charger",
        "app.dialog_afrique_charger": "Charger",
        "app.sidebar_couche_population": "👥 Afficher la population (WorldPop) sur les cartes",
        "app.spinner_grille_population": "Construction de la grille de population WorldPop (zone GTFS + 5 km, peut prendre du temps au premier appel pour un nouveau pays)...",
        "app.erreur_grille_population": "Impossible de construire la grille de population WorldPop : {erreur}",

        # --- infos réseau, communes à Arrêts et Lignes ---
        "commun.reseau_info": "Le GTFS concerne le réseau {reseau}",
        "commun.reseau_population_info": "Le GTFS concerne le réseau {reseau}, avec une métropole de {population} k habitants ({annee})",
        "commun.analyse_du": "Analyse du {date}",
        "commun.periode_service": "Période de service du {debut} au {fin}",
        "commun.plage_info": "Il est valide sur la plage {plage}, le JOB (mardi/jeudi le plus tardif de cette plage) est {job}",
        "commun.veuillez_charger_gtfs": "👆 Veuillez charger un fichier GTFS.",
        "commun.calcul_en_cours": "🔄 Calcul des indicateurs en cours...",
        "commun.header_telechargement": "💾 Téléchargement",

        # --- views/home.py ---
        "home.hackathon_md": """
    ## Application analyse GTFS

    Ce projet a été développé lors du Hackathon TSNI 2025 du Cerema et repris par Antoine Chevre (et claude.ai...)

    **Équipe CEREMA :** Patrick GENDRE, Hugo DE LUCA et Maxence LIOGIER

    **Contributeur :** Antoine Chèvre 🐐 (et claude.ai....)
    """,
        "home.liens_md": """
    ## 🔗 Liens rapides

    Le projet originel
    Pour aller plus loin, vous pouvez consulter le notebook disponible sur Colab :
    - **📓 [Notebook Google Colab](https://colab.research.google.com/github/CEREMA/hackathon-gtfs/blob/main/gtfs_notebook.ipynb)** : Prendre en main le code, exécuter les cellules et regarder les cartographies dynamiques


    - Le projet amélioré https://github.com/antoinechevre/gtfs_analysis_app
    """,
        "home.objectifs_md": """
    ## Objectifs

    - **Offrir une chaîne de traitement** pour passer d'un jeu GTFS brut à des exports géolocalisés d'indicateurs à l'échelle des arrêts et des tronçons
    - **Proposer une offre d'indicateurs sur les tronçons** même en l'absence du fichier shapes.txt dans les données GTFS
    - **Proposer à la fois des scripts utilisables en local**, une interface web conviviale (via Streamlit) pour les utilisateurs non-techniques, et un notebook d'exemple pour tester / explorer les résultats
    """,
        "home.fonctionnalites_md": """
    ## Bienvenue dans l'application d'analyse GTFS

    Cette application vous permet d'analyser les données GTFS (General Transit Feed Specification)
    pour extraire des indicateurs clés sur les transports en commun.
    Elle détermine la plage temporelle sur laquelle le GTFS est actif et identifie un JOB (jour ouvrable de base : le mardi ou jeudi le plus tardif de cette plage)


    ### Fonctionnalités disponibles :

    #### 📍 **Analyse par Arrêts**
    - Nombre de passages par arrêt
    - Carte interactive des arrêts
    - Statistiques détaillées

    #### 🛤️ **Analyse par Tronçons**
    - Nombre de passages par tronçon (bus, tram, métro, trolley, etc.)
    - Calcul des vitesses moyennes
    - Carte interactive des tronçons
    - app élargie à plusieurs GTFS français à retrouver sur https://transport.data.gouv.fr/ ou à l'international https://www.transit.land/ 


    ### Instructions :
    1. **Chargez un fichier GTFS** dans la barre latérale (format ZIP)
    2. **Naviguez entre les pages** pour explorer les analyses

    >
    > L'analyse par arrêts fonctionne quant à elle avec n'importe quel GTFS.

    pour aller chercher des jeux de données GTFS https://transport.data.gouv.fr/ pi à l'international https://www.transit.land/ 
    """,
        "home.contributeurs_md": """
    ## Contributeurs originaux  :
    - Hugo De Luca ([@hugo-deluca](https://github.com/hugo-deluca))
    - Maxence Liogier ([@maxenceLIOGIER](https://github.com/maxenceLIOGIER))
    - Patrick Gendre ([@PatGendre](https://github.com/PatGendre))

    ## Contributeur amélioration
    - Antoine Chèvre https://github.com/antoinechevre 🐐


    ---

    [*Projet open-source - Cerema 2025*](https://github.com/CEREMA/hackathon-gtfs)
    """,

        # --- views/arrets.py ---
        "arrets.spinner_indicateurs": "Calcul des indicateurs d'arrêts...",
        "arrets.erreur_indicateurs": "Erreur lors du calcul des arrêts : {erreur}",
        "arrets.header_stats": "📊 Statistiques Globales",
        "arrets.metric_nb_arrets": "Nombre d'arrêts",
        "arrets.metric_arrets_actifs": "Arrêts actifs",
        "arrets.metric_total_passages": "Total passages",
        "arrets.header_top10": "🏆 Top 10 Arrêts les plus fréquentés",
        "arrets.aucun_actif": "Aucun arrêt actif trouvé.",
        "arrets.aucun_service": "Aucun service actif trouvé pour cette date : impossible de générer la fiche statistiques.",
        "arrets.header_fiche": "📄 Fiche Statistiques",
        "arrets.header_carte": "🗺️ Carte des Arrêts",
        "arrets.telecharger_csv": "📥 Télécharger les résultats CSV",

        # --- views/troncons.py ---
        "troncons.spinner_calcul_auto": "🔄 Calcul automatique des tronçons {mode} depuis le GTFS...",
        "troncons.succes_calcul_auto": "✅ {n} tronçons {mode} calculés automatiquement",
        "troncons.erreur_calcul_auto": "❌ Erreur lors du calcul automatique des tronçons {mode}: {erreur}",
        "troncons.spinner_reference": "Chargement/Calcul des tronçons de référence...",
        "troncons.erreur_reference": "Impossible de calculer les tronçons de référence.",
        "troncons.spinner_indicateurs": "Calcul des indicateurs de tronçons...",
        "troncons.erreur_indicateurs": "Erreur lors du calcul des tronçons : {erreur}",
        "troncons.header_stats": "📊 Statistiques Globales",
        "troncons.metric_actifs": "Tronçons {mode} actifs",
        "troncons.metric_total_passages": "Total passages {mode}",
        "troncons.spinner_vkm": "Calcul des véh.km par ligne sur la plage de service...",
        "troncons.header_top": "Top 10 Tronçons {mode}",
        "troncons.aucun_actif": "Aucun tronçon {mode} actif.",
        "troncons.header_carte": "🗺️ Carte Interactive des Tronçons",
        "troncons.telecharger_csv": "📥 Télécharger {mode} CSV",
        "troncons.veuillez_charger_et_date": "👆 Veuillez charger un fichier GTFS et sélectionner une date dans la barre latérale.",

        # --- views/benchmark.py ---
        "benchmark.header": "📊 Benchmark inter-réseaux",
        "benchmark.caption": "Population de la ville en abscisse, indicateur transit au choix en ordonnée — un point par réseau déjà enregistré.",
        "benchmark.aucun_gtfs": "Charge un GTFS pour pouvoir enregistrer ce réseau dans le benchmark (facultatif : le graphique ci-dessous reste consultable sans GTFS chargé).",
        "benchmark.prerequis_manquant": "Calcule d'abord les indicateurs (page Arrêts et page Lignes) pour pouvoir enregistrer ce réseau dans le benchmark.",
        "benchmark.population_inconnue": "Population de la ville introuvable (nom de réseau non reconnu par Wikidata) : ce réseau sera enregistré sans population.",
        "benchmark.bouton_enregistrer": "Enregistrer {reseau} dans le benchmark",
        "benchmark.succes_enregistrement": "✓ {reseau} enregistré dans le benchmark",
        "benchmark.index_vide": "Aucun réseau n'a encore été enregistré dans l'index de benchmark.",
        "benchmark.header_afrique": "🌍📊 Benchmark inter-réseaux — villes africaines",
        "benchmark.caption_afrique": "Index séparé du benchmark standard : population Wikidata et BPE indisponibles pour la plupart de ces réseaux — population de la ville en abscisse, équipements OSM accessibles en 60 min en ordonnée (cf. onglet Accessibilité).",
        "benchmark.avertissement_comparabilite": "⚠ Comparer deux villes ici, c'est aussi comparer deux niveaux de complétude de données OSM/GTFS très différents : un score plus bas peut venir d'un réseau réellement moins accessible, ou simplement d'une couverture de données plus pauvre pour cette ville. À interpréter avec cette réserve en tête.",
        "benchmark.accessibilite_manquante": "Indicateurs d'accessibilité (population/équipements en 60 min) pas encore calculés : visite l'onglet Accessibilité avant d'enregistrer, sinon ce réseau sera enregistré sans eux.",
        "benchmark.autre_type_reseau_afrique": "Le réseau chargé ({reseau}) n'a pas été sélectionné via la boîte de dialogue « Villes africaines » : rien à enregistrer ici. Le nuage de points ci-dessous reste consultable.",
        "benchmark.autre_type_reseau_standard": "Le réseau chargé ({reseau}) a été sélectionné via la boîte de dialogue « Villes africaines » : direction l'onglet Benchmark villes africaines pour l'enregistrer. Le nuage de points ci-dessous reste consultable.",

        # --- src/export_html.py ---
        "export.aucune_donnee_km": "Aucune donnée de kilométrage disponible.",
        "export.titre_page_camembert": "Répartition des véh.km par mode {reseau}",
        "export.titre_camembert": "Répartition des véh.km sur plage par mode {reseau}",
        "export.titre_page_tableau": "Lignes du réseau {reseau}",
        "export.titre_tableau": "Lignes du réseau {reseau}",
        "export.col_ligne": "Ligne",
        "export.col_mode": "Mode",
        "export.col_total_vkm": "Total veh.km/plage",
        "export.titre_stats_reseau": "Statistiques des arrêts {reseau}",
        "export.titre_stats": "Statistiques des arrêts",
        "export.sous_titre_job": "JOB - {date_job}, {plage}",
        "export.stat_arrets_desservis": "Arrêts desservis",
        "export.stat_passages_total": "Passages au total",
        "export.stat_moyenne": "Moyenne par arrêt",
        "export.stat_mediane": "Médiane par arrêt",
        "export.arret_vedette_label": "Arrêt le plus fréquenté :",
        "export.arret_vedette_passages": "passages",
        "export.premier_depart_global": "Premier départ global :",
        "export.dernier_depart_global": "Dernier départ global :",
        "export.top10_titre": "Top 10 des arrêts les plus fréquentés",
        "export.col_arret": "Arrêt",
        "export.col_passages_jour": "Passages / jour",
        "export.col_premier_depart": "Premier départ",
        "export.col_dernier_depart": "Dernier départ",

        # --- src/cartographie.py ---
        "carto.arret_popup": "Arrêt ID: {stop_id}\nPassages: {passages}",
        "carto.legende_passages_titre": "Nombre de passages",
        "carto.legende_passages_suffix": "passages",
        "carto.titre_reseau_job": "Réseau {reseau} en JOB",
        "carto.titre_reseau_troncons": "Réseau {reseau} - nombre de passages par tronçon et par mode en JOB",
        "carto.plein_ecran": "Plein écran",
        "carto.quitter_plein_ecran": "Quitter le plein écran",
        "carto.legende_passages_mode": "Nombre de passages {mode}",
        "carto.caption_passages_mode": "Nombre de passages {mode}",
        "carto.popup_troncon_titre": "TRONÇON {mode}",
        "carto.popup_id": "ID:",
        "carto.popup_de": "De:",
        "carto.popup_a": "À:",
        "carto.popup_passages": "Passages:",
        "carto.popup_vitesse": "Vitesse moy.:",
        "carto.popup_distance": "Distance:",
        "carto.couche_population": "👥 Population (WorldPop)",
        "carto.caption_population": "Population (WorldPop)",

        # --- views/equipements.py ---
        "equipements.aucun_fichier": "Aucun fichier d'équipements trouvé dans {dossier}.",
        "equipements.aide_extraction": "Générez-en un en lançant index_accessibility_notebook_africa_600m.ipynb pour ce réseau (section \"Équipements\"), ou le bouton de calcul complet de l'onglet Accessibilité.",
        "equipements.description": "Équipements OpenStreetMap extraits à la main (extraire_equipements_osm.py) — substitut à la Base Permanente des Équipements (BPE, INSEE, France uniquement) pour un réseau hors de France.",
        "equipements.avertissement_couverture": "⚠ La couverture OpenStreetMap des équipements varie énormément d'une ville à l'autre en Afrique subsaharienne (contributeurs locaux inégaux) : un faible nombre d'équipements peut refléter un vrai manque d'infrastructures, ou simplement des données OSM incomplètes pour cette zone — à ne pas confondre sans vérification terrain.",
        "equipements.erreur_lecture": "Impossible de lire {fichier} : {erreur}",
        "equipements.header_stats": "Nombre d'équipements",
        "equipements.header_carte": "Carte",
        "equipements.caption_carte": "Un point par équipement OSM, coloré par pondération — gris = pondération nulle (pas un pôle d'équipement pertinent), rouge = pondération élevée.",
        "equipements.caption_carte_grille": "Score pondéré d'équipements cumulé par carreau de la grille de population — pas l'accessibilité en temps de trajet (cf. onglet Accessibilité pour ça), juste la donnée d'offre brute.",
        "equipements.telecharger_geojson": "📥 {nom} (GeoJSON)",
        "equipements.score_pondere": "Score pondéré : {score}",
        "equipements.legende_ponderation": "Pondération (0 = pas un pôle d'équipement)",
        "equipements.header_carte_grille": "Carte grille — densité pondérée d'équipements",
        "equipements.pas_de_grille": "Grille de population indisponible : {erreur}",

        # --- views/accessibilite.py ---
        "accessibilite.description": "Version simplifiée de l'accessibilité : un seul seuil ({cutoff} min), équipements accessibles (tous types confondus, cf. onglet Équipements) sans distinction de domaine ni de niveau de vie.",
        "accessibilite.avertissement_donnees": "⚠ Chaîne complète construite sur des données incertaines : grille de population WorldPop (modélisée), réseau routier OSM potentiellement incomplet (affecte le calcul des temps de trajet), équipements OSM à couverture inégale, pondération par type d'équipement définie subjectivement sur Abidjan puis réutilisée telle quelle pour toutes les villes. À interpréter comme des ordres de grandeur relatifs (comparaison entre carreaux d'une même ville), pas des valeurs absolues.",
        "accessibilite.pas_de_grille": "Grille de population WorldPop indisponible pour ce réseau : {erreur}",
        "accessibilite.grille_vide": "grille vide (zone hors couverture WorldPop ?)",
        "accessibilite.pas_de_ttm": "Pas de matrice de temps de trajet calculée pour {reseau}.",
        "accessibilite.avertissement_calcul_complet": "⚠ Le calcul complet (grille, réseau OSM, équipements, r5py, matrice de temps de trajet) peut prendre plusieurs dizaines de minutes selon la taille du réseau, et bloque l'appli pendant ce temps (pour tous les utilisateurs). Ne lance que si tu es prêt·e à attendre.",
        "accessibilite.bouton_calculer": "🚀 Lancer le calcul complet",
        "accessibilite.status_calcul": "Calcul en cours...",
        "accessibilite.status_termine": "✓ Calcul terminé",
        "accessibilite.erreur_calcul": "Erreur pendant le calcul : {erreur}",
        "accessibilite.spinner_calcul": "Calcul de l'accessibilité...",
        "accessibilite.header_stats": "Accessibilité moyenne (pondérée par la population), en {cutoff} min",
        "accessibilite.metric_population": "Population accessible (≤{cutoff} min)",
        "accessibilite.metric_equipements": "% des équipements pondérés de l'agglomération accessibles (≤{cutoff} min)",
        "accessibilite.pas_equipements": "Aucun fichier dans data/equipements_osm/ : cf. onglet Équipements.",
        "accessibilite.header_carte_population": "Carte — population accessible en ≤{cutoff} min",
        "accessibilite.header_carte_equipements": "Carte — équipements accessibles en ≤{cutoff} min",
        "accessibilite.telecharger_population": "📥 Population accessible (CSV)",
        "accessibilite.telecharger_equipements": "📥 Équipements accessibles (CSV)",

        # --- isochrone_carreaux.py ---
        "app.nav_isochrone_carreaux": "🗺️ Isochrone carreaux",
        "isochrone_carreaux.intro": "Carreaux de la grille de population atteignables depuis un arrêt, selon une matrice de temps de trajet (TTM) déjà calculée pour ce réseau (départ figé à l'heure du calcul de cette TTM, cf. onglet Accessibilité pour le détail de son origine).",
        "isochrone_carreaux.erreur_arrets": "Erreur lors du calcul des indicateurs d'arrêts : {erreur}",
        "isochrone_carreaux.passages_suffix": "passages",
        "isochrone_carreaux.label_arret_depart": "Arrêt de départ",
        "isochrone_carreaux.label_budget": "Budget de trajet (minutes)",
        "isochrone_carreaux.bouton_calculer": "🚀 Calculer l'isochrone",
        "isochrone_carreaux.spinner_calcul": "Calcul des carreaux atteignables...",
        "isochrone_carreaux.attente_calcul": "Réglez les paramètres puis cliquez sur \"Calculer l'isochrone\".",
        "isochrone_carreaux.pas_de_carreau": "Ce point de départ ne correspond à aucun carreau de la grille de population (zone hors couverture WorldPop...) — impossible de le relier à la TTM.",
        "isochrone_carreaux.aucun_atteignable": "Aucun carreau atteignable avec ce budget.",
        "isochrone_carreaux.legende_duree": "Temps de trajet (min)",
        "isochrone_carreaux.metric_carreaux": "Carreaux atteints",
        "isochrone_carreaux.metric_duree_mediane": "Temps médian",
        "isochrone_carreaux.metric_population": "Population atteignable",
        "isochrone_carreaux.telecharger_csv": "📥 Carreaux atteignables (CSV)",
    },
    "en": {
        # --- app.py ---
        "app.title": "🚌 GTFS Analysis - Transit Indicators",
        "app.nav_accueil": "🏠 Home",
        "app.nav_arrets": "📍 Stops",
        "app.nav_lignes": "🛤️ Lines",
        "app.nav_benchmark": "📊 Benchmark",
        "app.nav_benchmark_afrique": "🌍📊 African Benchmark",
        "app.nav_equipements": "🏥 Facilities",
        "app.nav_accessibilite": "🧭 Accessibility",
        "app.groupe_accueil": "🏠 Home",
        "app.groupe_analyse_reseau": "🚏 Network analysis",
        "app.groupe_accessibilite_urbaine": "📈 Urban accessibility analysis",
        "app.groupe_benchmark": "📊 Benchmark",
        "app.sidebar_header": "📁 Analysis settings",
        "app.sidebar_uploader": "Upload the GTFS file (zip)",
        "app.sidebar_gtfs_existant": "...or pick an existing GTFS",
        "app.aucun_gtfs_local": "— none —",
        "app.spinner_recuperation_hf": "Fetching {nom} from Hugging Face...",
        "app.erreur_recuperation_hf": "Could not fetch {nom} from Hugging Face.",
        "app.toast_envoi_hf": "✓ {nom} sent to Hugging Face (reusable on future deployments)",
        "app.sidebar_langue": "🌐 Language",
        "app.spinner_chargement": "Loading GTFS file...",
        "app.erreur_chargement": "Error while loading: {erreur}",
        "app.erreur_trop_agences": "⚠ This GTFS covers {n} agencies over a wide area (~{etendue} km): regional network, several distant cities. Please load an urban GTFS only.",
        "app.transitland_titre": "🔎 Search for a GTFS on Transitland",
        "app.transitland_recherche": "City or network to search for",
        "app.transitland_erreur_recherche": "Error while searching Transitland: {erreur}",
        "app.transitland_aucun_resultat": "No results.",
        "app.transitland_choisir": "Feed to download",
        "app.transitland_telecharger": "📥 Download",
        "app.transitland_telechargement_en_cours": "Downloading from Transitland...",
        "app.transitland_succes": "✓ {nom} downloaded — pick it from the dropdown above",
        "app.transitland_erreur_telechargement": "Error while downloading: {erreur}",
        "app.nav_villes_africaines": "🌍 African cities",
        "africa.title": "🌍 GTFS Analysis Africa",
        "africa.avertissement_general": "⚠ Handle data and results with caution: there is no reliable sub-municipal census for most of these cities (WorldPop population data is a modeled estimate, not a headcount), OpenStreetMap facility coverage varies a lot between cities and neighborhoods, and several GTFS files in this catalog date back to 2018-2020 and are no longer maintained (cf. data/GTFS_Africa/_provenance.json). Results (population grid, facilities, accessibility) are orders of magnitude, not reference figures.",

        # --- views/home_afrique.py ---
        "home_afrique.intro_md": """
This app analyzes African transport networks from GTFS data, inspired by the book *Introduction to urban accessibility* (Rafael H. M. Pereira and Daniel Herszenhut, Ipea - Institute for Applied Economic Research), specifically the chapter [Calculating accessibility estimates in R](https://ipeagit.github.io/intro_access_book/3_calculando_acesso.en.html) — adapted to Python for a context outside France, where the French national facilities database (BPE, INSEE) and 200x200m population grid don't exist.

**Designer:** Antoine Chèvre 🐐 (with claude.ai....)

This app combines two types of analysis based on the same GTFS dataset: urban accessibility to facilities by public transit / walking, and the public transit network analysis itself — cf. the sister project [Accessibility_analysis](https://github.com/antoinechevre/Accessibility_analysis) (France) this Africa branch is derived from.
""",
        "home_afrique.titre_section_md": "## 📍 Urban accessibility analysis",
        "home_afrique.onglet_objectifs": "🎯 Goals",
        "home_afrique.onglet_fonctionnalites": "⚙️ Features",
        "home_afrique.onglet_liens": "🔗 Links & Instructions",
        "home_afrique.objectifs_md": """
- **Offer a processing chain** to go from a raw GTFS to accessibility analysis of the network, without relying on French national datasets:
    - walking/public transit mode, on a base weekday at peak hour
    - weighted OpenStreetMap facilities (substitute for the BPE) within 60 min of the network
    - on a WorldPop 600x600m population grid (substitute for the INSEE grid)
- **Offer a computation directly from the app** when no travel-time matrix is cached yet, without going through the notebook
- **Offer a benchmark across African cities**, comparing facility-accessibility indicators, separate from the standard benchmark (Wikidata/BPE population is unreliable outside France)
""",
        "home_afrique.fonctionnalites_md": """
From an African GTFS in the catalog (or uploaded):

1. Builds the multimodal walking + public transit network (`r5py`) from the GTFS for a given base weekday, and the road network for walking paths (Geofabrik OpenStreetMap extract, clipped to the service area)
2. Fetches the WorldPop population grid (global raster, ~100m resolution resampled into 600x600m cells) over the rectangle bounding the GTFS stops, and OpenStreetMap facilities weighted by type over the same area
3. Computes the travel time matrix (`TravelTimeMatrix`) between all cells, at peak hour on the base weekday
4. Computes facility accessibility within 60 min (cumulative opportunities, `cumulative_cutoff`)
5. Offers a benchmark across African cities on these indicators

#### 🗺️ Grid-cell isochrone
- Interactive map of grid cells reachable within X minutes from a selected stop, read directly from the already-computed travel time matrix — equivalent to the "Isochrone TTM" tab of the sister app, but on the WorldPop grid instead of the INSEE grid
""",
        "home_afrique.expander_equipements_titre": "Facility weighting detail (OSM substitute for the BPE)",
        "home_afrique.expander_equipements_md": """
No national facilities database outside France: every OpenStreetMap point tagged `amenity=*` is extracted (osmium, local Geofabrik extract — no dependency on the Overpass API), then weighted by type using a reference table built by hand on Abidjan (`data/equipements_osm/Abidjan_amenities.xlsx`, "resume_par_type" sheet) and reused as-is as the single reference for every city: 0 = not a relevant facility hub, up to 30 for structuring facilities (hospital, government, public building...).

No breakdown by domain (health, education, retail...) like the BPE: a single weighted score, "all facility types combined".
""",
        "home_afrique.expander_indicateurs_titre": "Accessibility indicator detail",
        "home_afrique.expander_indicateurs_md": """
- **Cumulative opportunities**: number of (weighted) facilities reachable from each cell within 60 min — the measure used on the app's Accessibility tab
- **Cost to closest, gravity, competition (Enhanced 2SFCA)**: also computed in the notebook (`index_accessibility_notebook_africa_600m.ipynb`), not carried over to the app to keep it simple
""",
        "home_afrique.liens_md": """
### Quick links

- **📓 Reference book**: [Introduction to urban accessibility](https://ipeagit.github.io/intro_access_book/3_calculando_acesso.en.html) — adapted chapter: [3. Calculating accessibility estimates in R](https://ipeagit.github.io/intro_access_book/s2_calculo.en.html)
- **📓 This project**: [gtfs_analysis_app](https://github.com/antoinechevre/gtfs_analysis_app) (`app_africa.py`, `index_accessibility_notebook_africa_600m.ipynb`)
- **📓 Sister project (France)**: [Accessibility_analysis](https://github.com/antoinechevre/Accessibility_analysis)
- **🚏 Universal app (any country, stops/lines only)**: [GTFS Analysis Universal](https://huggingface.co/spaces/antoinechevre/GTFS_Analysis_Universal)

### Instructions

1. **Pick a GTFS** from the catalog (sidebar) or upload your own
2. **Navigate between pages** to explore the analyses
""",
        "home_afrique.credits_md": """
Antoine Chèvre [@antoinechevre](https://github.com/antoinechevre) 🐐
In we goat we trust
""",
        "home_afrique.titre_gtfs_md": "## 🚏 GTFS Analysis",
        "home_afrique.gtfs_intro_md": """
The GTFS analysis (independent from the accessibility analysis above) was developed during the Cerema TSNI 2025 Hackathon and taken over by Antoine Chèvre (and claude.ai...).

**Cerema team:** Patrick Gendre, Hugo De Luca and Maxence Liogier
""",
        "home_afrique.gtfs_fonctionnalites_md": """
Analysis of GTFS (General Transit Feed Specification) data to extract key public transit indicators — independent of the accessibility analysis above. Determines the date range over which the GTFS is active and identifies a base weekday (JOB, the latest Tuesday or Thursday in that range).

#### 📍 Stops analysis
- Number of passages per stop
- Interactive stop map
- Detailed statistics

Works with any GTFS, even without `shapes.txt`.

#### 🛤️ Lines analysis
- Number of passages per line, by mode (bus, tram, metro, trolley, ferry...)
- Average speed computation
- Interactive line map
""",
        "home_afrique.gtfs_liens_md": """
- **📓 Cerema Hackathon**: [Google Colab Notebook](https://colab.research.google.com/github/CEREMA/hackathon-gtfs/blob/main/gtfs_notebook.ipynb) — get familiar with the code, run the cells and look at the dynamic maps
- **📓 Universal app**: [GTFS Analysis Universal](https://huggingface.co/spaces/antoinechevre/GTFS_Analysis_Universal)

Where to find an African GTFS:
- This project's catalog: `data/GTFS_Africa/` (cf. `data/GTFS_Africa/_provenance.json` for each file's source and date)
- Internationally: [transit.land](https://www.transit.land/)
""",
        "app.dialog_afrique_titre": "🌍 Load an African network",
        "app.dialog_afrique_aucun": "No GTFS found in {dossier}. Drop a .zip file there for it to appear here.",
        "app.dialog_afrique_choisir": "Network to load",
        "app.dialog_afrique_charger": "Load",
        "app.sidebar_couche_population": "👥 Show population (WorldPop) on maps",
        "app.spinner_grille_population": "Building the WorldPop population grid (GTFS zone + 5 km margin, may take a while on first call for a new country)...",
        "app.erreur_grille_population": "Could not build the WorldPop population grid: {erreur}",

        "commun.reseau_info": "This GTFS covers the {reseau} network",
        "commun.reseau_population_info": "This GTFS covers the {reseau} network, in a metropolitan area of {population}k inhabitants ({annee})",
        "commun.analyse_du": "Analysis of {date}",
        "commun.periode_service": "Service period from {debut} to {fin}",
        "commun.plage_info": "It is valid over the {plage} range, the Base Weekday (the latest Tuesday or Thursday in this range) is {job}",
        "commun.veuillez_charger_gtfs": "👆 Please upload a GTFS file.",
        "commun.calcul_en_cours": "🔄 Computing indicators...",
        "commun.header_telechargement": "💾 Download",

        # --- views/home.py ---
        "home.hackathon_md": """
    ## GTFS analysis application

    This project was developed during Cerema's 2025 TSNI Hackathon and later picked up by Antoine Chevre (and claude.ai...)

    **CEREMA team:** Patrick GENDRE, Hugo DE LUCA and Maxence LIOGIER

    **Contributor:** Antoine Chèvre 🐐 (and claude.ai....)
    """,
        "home.liens_md": """
    ## 🔗 Quick links

    The original project
    To go further, you can check out the notebook available on Colab:
    - **📓 [Google Colab Notebook](https://colab.research.google.com/github/CEREMA/hackathon-gtfs/blob/main/gtfs_notebook.ipynb)**: get familiar with the code, run the cells and look at the dynamic maps


    - The improved project https://github.com/antoinechevre/gtfs_analysis_app
    """,
        "home.objectifs_md": """
    ## Goals

    - **Provide a processing pipeline** to go from a raw GTFS dataset to geolocated exports of indicators at the stop and segment level
    - **Provide segment-level indicators** even when the GTFS data has no shapes.txt file
    - **Provide both locally runnable scripts**, a user-friendly web interface (via Streamlit) for non-technical users, and an example notebook to test / explore the results
    """,
        "home.fonctionnalites_md": """
    ## Welcome to the GTFS analysis application

    This application lets you analyze GTFS (General Transit Feed Specification) data
    to extract key public transit indicators.
    It determines the time range over which the GTFS is active and identifies a JOB (baseline weekday: the latest Tuesday or Thursday in that range)


    ### Available features:

    #### 📍 **Stop analysis**
    - Number of passages per stop
    - Interactive stop map
    - Detailed statistics

    #### 🛤️ **Segment analysis**
    - Number of passages per segment (bus, tram, metro, trolley, etc.)
    - Average speed calculation
    - Interactive segment map
    - App extended to several French GTFS feeds, available on https://transport.data.gouv.fr/ or https://www.transit.land/ for worldwide 


    ### Instructions:
    1. **Upload a GTFS file** in the sidebar (ZIP format)
    2. **Navigate between pages** to explore the analyses

    >
    > Stop analysis works with any GTFS.

    to find GTFS datasets: https://transport.data.gouv.fr/
    """,
        "home.contributeurs_md": """
    ## Original contributors:
    - Hugo De Luca ([@hugo-deluca](https://github.com/hugo-deluca))
    - Maxence Liogier ([@maxenceLIOGIER](https://github.com/maxenceLIOGIER))
    - Patrick Gendre ([@PatGendre](https://github.com/PatGendre))

    ## Improvement contributor
    - Antoine Chèvre https://github.com/antoinechevre 🐐


    ---

    [*Open-source project - Cerema 2025*](https://github.com/CEREMA/hackathon-gtfs)
    """,

        # --- views/arrets.py ---
        "arrets.spinner_indicateurs": "Computing stop indicators...",
        "arrets.erreur_indicateurs": "Error while computing stops: {erreur}",
        "arrets.header_stats": "📊 Overall statistics",
        "arrets.metric_nb_arrets": "Number of stops",
        "arrets.metric_arrets_actifs": "Active stops",
        "arrets.metric_total_passages": "Total passages",
        "arrets.header_top10": "🏆 Top 10 busiest stops",
        "arrets.aucun_actif": "No active stop found.",
        "arrets.aucun_service": "No active service found for this date: cannot generate the statistics sheet.",
        "arrets.header_fiche": "📄 Statistics sheet",
        "arrets.header_carte": "🗺️ Stop map",
        "arrets.telecharger_csv": "📥 Download CSV results",

        # --- views/troncons.py ---
        "troncons.spinner_calcul_auto": "🔄 Automatically computing {mode} segments from the GTFS...",
        "troncons.succes_calcul_auto": "✅ {n} {mode} segments computed automatically",
        "troncons.erreur_calcul_auto": "❌ Error while automatically computing {mode} segments: {erreur}",
        "troncons.spinner_reference": "Loading/computing reference segments...",
        "troncons.erreur_reference": "Unable to compute reference segments.",
        "troncons.spinner_indicateurs": "Computing segment indicators...",
        "troncons.erreur_indicateurs": "Error while computing segments: {erreur}",
        "troncons.header_stats": "📊 Overall statistics",
        "troncons.metric_actifs": "Active {mode} segments",
        "troncons.metric_total_passages": "Total {mode} passages",
        "troncons.spinner_vkm": "Computing vehicle-km per line over the service range...",
        "troncons.header_top": "Top 10 {mode} segments",
        "troncons.aucun_actif": "No active {mode} segment.",
        "troncons.header_carte": "🗺️ Interactive segment map",
        "troncons.telecharger_csv": "📥 Download {mode} CSV",
        "troncons.veuillez_charger_et_date": "👆 Please upload a GTFS file and select a date in the sidebar.",

        # --- views/benchmark.py ---
        "benchmark.header": "📊 Cross-network benchmark",
        "benchmark.caption": "City population on the X axis, choice of transit indicator on the Y axis — one point per already-registered network.",
        "benchmark.aucun_gtfs": "Load a GTFS to register this network in the benchmark (optional: the chart below stays available without a loaded GTFS).",
        "benchmark.prerequis_manquant": "Compute the indicators first (Stops page and Lines page) to register this network in the benchmark.",
        "benchmark.population_inconnue": "City population not found (network name not recognized by Wikidata): this network will be registered without population.",
        "benchmark.bouton_enregistrer": "Register {reseau} in the benchmark",
        "benchmark.succes_enregistrement": "✓ {reseau} registered in the benchmark",
        "benchmark.index_vide": "No network has been registered in the benchmark index yet.",
        "benchmark.header_afrique": "🌍📊 Cross-network benchmark — African cities",
        "benchmark.caption_afrique": "Separate index from the standard benchmark: Wikidata population and BPE facilities are unavailable for most of these networks — city population on the X axis, OSM facilities accessible within 60 min on the Y axis (cf. Accessibility tab).",
        "benchmark.avertissement_comparabilite": "⚠ Comparing two cities here also means comparing two very different levels of OSM/GTFS data completeness: a lower score can reflect a genuinely less accessible network, or simply poorer data coverage for that city. Read with this caveat in mind.",
        "benchmark.accessibilite_manquante": "Accessibility indicators (population/facilities within 60 min) not computed yet: visit the Accessibility tab before registering, otherwise this network will be registered without them.",
        "benchmark.autre_type_reseau_afrique": "The loaded network ({reseau}) wasn't selected via the \"African cities\" dialog: nothing to register here. The chart below stays available.",
        "benchmark.autre_type_reseau_standard": "The loaded network ({reseau}) was selected via the \"African cities\" dialog: head to the African cities Benchmark tab to register it. The chart below stays available.",

        # --- src/export_html.py ---
        "export.aucune_donnee_km": "No mileage data available.",
        "export.titre_page_camembert": "Vehicle-km breakdown by mode {reseau}",
        "export.titre_camembert": "Vehicle-km breakdown over range by mode {reseau}",
        "export.titre_page_tableau": "{reseau} network lines",
        "export.titre_tableau": "{reseau} network lines",
        "export.col_ligne": "Line",
        "export.col_mode": "Mode",
        "export.col_total_vkm": "Total veh.km/range",
        "export.titre_stats_reseau": "{reseau} stop statistics",
        "export.titre_stats": "Stop statistics",
        "export.sous_titre_job": "JOB - {date_job}, {plage}",
        "export.stat_arrets_desservis": "Stops served",
        "export.stat_passages_total": "Total passages",
        "export.stat_moyenne": "Average per stop",
        "export.stat_mediane": "Median per stop",
        "export.arret_vedette_label": "Busiest stop:",
        "export.arret_vedette_passages": "passages",
        "export.premier_depart_global": "Overall first departure:",
        "export.dernier_depart_global": "Overall last departure:",
        "export.top10_titre": "Top 10 busiest stops",
        "export.col_arret": "Stop",
        "export.col_passages_jour": "Passages / day",
        "export.col_premier_depart": "First departure",
        "export.col_dernier_depart": "Last departure",

        # --- src/cartographie.py ---
        "carto.arret_popup": "Stop ID: {stop_id}\nPassages: {passages}",
        "carto.legende_passages_titre": "Number of passages",
        "carto.legende_passages_suffix": "passages",
        "carto.titre_reseau_job": "{reseau} network on JOB",
        "carto.titre_reseau_troncons": "{reseau} network - number of passages per segment and mode on JOB",
        "carto.plein_ecran": "Fullscreen",
        "carto.quitter_plein_ecran": "Exit fullscreen",
        "carto.legende_passages_mode": "Number of {mode} passages",
        "carto.caption_passages_mode": "Number of {mode} passages",
        "carto.popup_troncon_titre": "{mode} SEGMENT",
        "carto.popup_id": "ID:",
        "carto.popup_de": "From:",
        "carto.popup_a": "To:",
        "carto.popup_passages": "Passages:",
        "carto.popup_vitesse": "Avg. speed:",
        "carto.popup_distance": "Distance:",
        "carto.couche_population": "👥 Population (WorldPop)",
        "carto.caption_population": "Population (WorldPop)",

        # --- views/equipements.py ---
        "equipements.aucun_fichier": "No facilities file found in {dossier}.",
        "equipements.aide_extraction": "Generate one by running index_accessibility_notebook_africa_600m.ipynb for this network (\"Équipements\" section), or the full-computation button on the Accessibility tab.",
        "equipements.description": "OpenStreetMap facilities extracted by hand (extraire_equipements_osm.py) — a substitute for the BPE facilities database (INSEE, France only) for a network outside France.",
        "equipements.avertissement_couverture": "⚠ OpenStreetMap facility coverage varies enormously between cities in Sub-Saharan Africa (uneven local contributor base): a low facility count may reflect a real lack of infrastructure, or simply incomplete OSM data for that area — don't conflate the two without ground-truthing.",
        "equipements.erreur_lecture": "Could not read {fichier}: {erreur}",
        "equipements.header_stats": "Number of facilities",
        "equipements.header_carte": "Map",
        "equipements.caption_carte": "One point per OSM facility, colored by weight — grey = zero weight (not a relevant facility hub), red = high weight.",
        "equipements.caption_carte_grille": "Cumulative weighted facility score per grid cell — not travel-time accessibility (see the Accessibility tab for that), just the raw supply data.",
        "equipements.telecharger_geojson": "📥 {nom} (GeoJSON)",
        "equipements.score_pondere": "Weighted score: {score}",
        "equipements.legende_ponderation": "Weight (0 = not a facility hub)",
        "equipements.header_carte_grille": "Grid map — weighted facility density",
        "equipements.pas_de_grille": "Population grid unavailable: {erreur}",

        # --- views/accessibilite.py ---
        "accessibilite.description": "Simplified accessibility view: a single threshold ({cutoff} min), accessible facilities (all types combined, cf. Facilities tab), no breakdown by facility type or income level.",
        "accessibilite.avertissement_donnees": "⚠ This whole chain rests on uncertain data: modeled WorldPop population grid, potentially incomplete OSM road network (affects travel-time computation), unevenly covered OSM facilities, and a facility-type weighting scheme defined subjectively on Abidjan and reused as-is for every city. Read these as relative orders of magnitude (comparing cells within one city), not absolute values.",
        "accessibilite.pas_de_grille": "WorldPop population grid unavailable for this network: {erreur}",
        "accessibilite.grille_vide": "empty grid (zone outside WorldPop coverage?)",
        "accessibilite.pas_de_ttm": "No travel time matrix computed for {reseau}.",
        "accessibilite.avertissement_calcul_complet": "⚠ The full computation (grid, OSM network, facilities, r5py, travel time matrix) can take several tens of minutes depending on network size, and blocks the app for everyone while it runs. Only launch if you're ready to wait.",
        "accessibilite.bouton_calculer": "🚀 Run full computation",
        "accessibilite.status_calcul": "Computing...",
        "accessibilite.status_termine": "✓ Computation complete",
        "accessibilite.erreur_calcul": "Error during computation: {erreur}",
        "accessibilite.spinner_calcul": "Computing accessibility...",
        "accessibilite.header_stats": "Average accessibility (population-weighted), at {cutoff} min",
        "accessibilite.metric_population": "Accessible population (≤{cutoff} min)",
        "accessibilite.metric_equipements": "% of the metro area's weighted facilities accessible (≤{cutoff} min)",
        "accessibilite.pas_equipements": "No file in data/equipements_osm/: cf. Facilities tab.",
        "accessibilite.header_carte_population": "Map — population accessible within ≤{cutoff} min",
        "accessibilite.header_carte_equipements": "Map — facilities accessible within ≤{cutoff} min",
        "accessibilite.telecharger_population": "📥 Accessible population (CSV)",
        "accessibilite.telecharger_equipements": "📥 Accessible facilities (CSV)",

        # --- isochrone_carreaux.py ---
        "app.nav_isochrone_carreaux": "🗺️ Grid isochrone",
        "isochrone_carreaux.intro": "Population grid cells reachable from a stop, based on a travel time matrix (TTM) already computed for this network (departure time fixed to when that TTM was computed — cf. Accessibility tab for details on its origin).",
        "isochrone_carreaux.erreur_arrets": "Error while computing stop indicators: {erreur}",
        "isochrone_carreaux.passages_suffix": "trips",
        "isochrone_carreaux.label_arret_depart": "Departure stop",
        "isochrone_carreaux.label_budget": "Travel budget (minutes)",
        "isochrone_carreaux.bouton_calculer": "🚀 Compute isochrone",
        "isochrone_carreaux.spinner_calcul": "Computing reachable grid cells...",
        "isochrone_carreaux.attente_calcul": "Set the parameters then click \"Compute isochrone\".",
        "isochrone_carreaux.pas_de_carreau": "This departure point doesn't match any cell of the population grid (outside WorldPop coverage...) — cannot link it to the TTM.",
        "isochrone_carreaux.aucun_atteignable": "No cell reachable within this budget.",
        "isochrone_carreaux.legende_duree": "Travel time (min)",
        "isochrone_carreaux.metric_carreaux": "Cells reached",
        "isochrone_carreaux.metric_duree_mediane": "Median time",
        "isochrone_carreaux.metric_population": "Reachable population",
        "isochrone_carreaux.telecharger_csv": "📥 Reachable cells (CSV)",
    },
}


def t(key, lang="fr", **kwargs):
    """
    Renvoie la traduction de `key` dans la langue `lang`.

    Repli sur le français si la clé n'existe pas dans `lang`, puis sur la
    clé elle-même si elle n'existe nulle part (pour ne jamais planter
    l'affichage sur une clé oubliée).
    """
    texte = TRANSLATIONS.get(lang, {}).get(key, TRANSLATIONS["fr"].get(key, key))
    return texte.format(**kwargs) if kwargs else texte
