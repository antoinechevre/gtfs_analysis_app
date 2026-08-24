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

Analyse de réseaux de transport africains à partir de GTFS : indicateurs arrêts/tronçons (comme [GTFS Analysis Universal](https://huggingface.co/spaces/antoinechevre/GTFS_Analysis_Universal)), plus des onglets spécifiques à ce que permet la donnée disponible hors de France :

- **Équipements** : équipements OpenStreetMap pondérés (substitut à la BPE, INSEE, indisponible hors de France) ;
- **Accessibilité** : population et équipements accessibles en 60 min (r5py, calculé en amont par [`index_accessibility_notebook_africa.ipynb`](https://github.com/antoinechevre/gtfs_analysis_app)) ;
- **Benchmark villes africaines** : comparaison inter-réseaux sur ces mêmes indicateurs, séparée du benchmark standard (population Wikidata/BPE peu fiables pour la plupart de ces villes).

⚠ Données à manier avec précaution : pas de recensement fiable à l'échelle infracommunale pour la plupart de ces villes, couverture OpenStreetMap très inégale, GTFS parfois anciens (2018-2020) et non maintenus. Voir l'avertissement affiché dans l'app pour le détail.

Catalogue GTFS et code source : [gtfs_analysis_app](https://github.com/antoinechevre/gtfs_analysis_app) (`app_africa.py`).
