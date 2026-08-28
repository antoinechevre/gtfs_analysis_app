---
title: GTFS Analysis Africa
emoji: 🌍
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

# GTFS Analysis Africa

Analyse de réseaux de transport africains à partir de GTFS : indicateurs arrêts/lignes (comme [GTFS Analysis Universal](https://huggingface.co/spaces/antoinechevre/GTFS_Analysis_Universal)), plus des onglets spécifiques à ce que permet la donnée disponible hors de France, regroupés sous "Analyse accessibilité urbaine" :

- **Équipements** : équipements OpenStreetMap pondérés (substitut à la BPE, INSEE, indisponible hors de France), pour le réseau chargé ;
- **Accessibilité** : équipements accessibles en 60 min (r5py, grille de population WorldPop 600m — calculé en amont par [`index_accessibility_notebook_africa_600m.ipynb`](https://github.com/antoinechevre/gtfs_analysis_app), ou directement depuis l'app si aucune matrice n'est encore en cache) ;
- **Isochrone carreaux** : depuis un arrêt donné, carreaux de la grille de population atteignables en moins de X minutes ;
- **Benchmark villes africaines** : comparaison inter-réseaux sur ces mêmes indicateurs, séparée du benchmark standard (population Wikidata/BPE peu fiables pour la plupart de ces villes).

⚠ Données et résultats à manier avec précaution : pas de recensement fiable à l'échelle infracommunale pour la plupart de ces villes, couverture OpenStreetMap très inégale, GTFS parfois anciens (2018-2020) et non maintenus. Voir l'avertissement affiché dans l'app pour le détail.

La méthodologie d'accessibilité s'inspire des travaux du livre *Introduction to urban accessibility* (Rafael H. M. Pereira et Daniel Herszenhut, Ipea - Institute for Applied Economic Research), notamment le chapitre [Calculating accessibility estimates in R](https://ipeagit.github.io/intro_access_book/3_calculando_acesso.en.html), réadaptés ici en Python — cf. le projet sœur [Accessibility_analysis](https://github.com/antoinechevre/Accessibility_analysis) (contexte France, carroyage INSEE/BPE) dont ce volet Afrique est dérivé.

Catalogue GTFS et code source : [gtfs_analysis_app](https://github.com/antoinechevre/gtfs_analysis_app) (`app_africa.py`).
