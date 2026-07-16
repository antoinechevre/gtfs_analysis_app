"""
Page d'accueil - Application d'analyse GTFS
"""

import streamlit as st
import pandas as pd


def home_page():
    st.markdown("---")

    # Section Hackathon
    st.markdown(
        """
    ## Application analyse GTFS 

    Ce projet a été développé lors du Hackathon TSNI 2025 du Cerema et reprise par Antoine Chevre (et claude.ai...)
    
    **Équipe CEREMA :** Patrick GENDRE, Hugo DE LUCA et Maxence LIOGIER

    **Contributeur :** Antoine Chèvre 🐐 (et claude.ai....)
    """
    )

    st.markdown("---")

    # Liens rapides
    st.markdown(
        """
    ## 🔗 Liens rapides

    Le projet originel 
    Pour aller plus loin, vous pouvez consulter le notebook disponible sur Colab :
    - **📓 [Notebook Google Colab](https://colab.research.google.com/github/CEREMA/hackathon-gtfs/blob/main/gtfs_notebook.ipynb)** : Prendre en main le code, exécuter les cellules et regarder les cartographies dynamiques
    
    
    - Le projet amélioré https://github.com/antoinechevre/gtfs_analysis_app 
    """
    )

    st.markdown("---")

    # Objectifs
    st.markdown(
        """
    ## Objectifs

    - **Offrir une chaîne de traitement** pour passer d'un jeu GTFS brut à des exports géolocalisés d'indicateurs à l'échelle des arrêts et des tronçons
    - **Proposer une offre d'indicateurs sur les tronçons** même en l'absence du fichier shapes.txt dans les données GTFS
    - **Proposer à la fois des scripts utilisables en local**, une interface web conviviale (via Streamlit) pour les utilisateurs non-techniques, et un notebook d'exemple pour tester / explorer les résultats
    """
    )

    st.markdown("---")

    # Fonctionnalités disponibles
    st.markdown(
        """
    ## Bienvenue dans l'application d'analyse GTFS

    Cette application vous permet d'analyser les données GTFS (General Transit Feed Specification)
    pour extraire des indicateurs clés sur les transports en commun. 
    Elle détermine la plage temporelle sur laquelle le GTFS est actif et identifie un JOB (jour ouvrable de base mardi ou jeudi de manière aléatoire)

       
    ### Fonctionnalités disponibles :

    #### 📍 **Analyse par Arrêts**
    - Nombre de passages par arrêt
    - Carte interactive des arrêts
    - Statistiques détaillées

    #### 🛤️ **Analyse par Tronçons**
    - Nombre de passages par tronçon (bus, tram, métro, trolley; etc.)
    - Calcul des vitesses moyennes
    - Carte interactive des tronçons
    - app élargie à plusieurs GTFS français à retrouver sur https://transport.data.gouv.fr/


    ### Instructions :
    1. **Chargez un fichier GTFS** dans la barre latérale (format ZIP)
    2. **Naviguez entre les pages** pour explorer les analyses

    >
    > L'analyse par arrêts fonctionne quant à elle avec n'importe quel GTFS.
    
    pour aller chercher des jeu de données GTFS https://transport.data.gouv.fr/
    """
    )

    st.markdown("---")

    # Section Auteurs
    st.markdown(
        """
    ## Contributeurs originaux  :
    - Hugo De Luca ([@hugo-deluca](https://github.com/hugo-deluca))
    - Maxence Liogier ([@maxenceLIOGIER](https://github.com/maxenceLIOGIER))
    - Patrick Gendre ([@PatGendre](https://github.com/PatGendre))

    ## Contributeur amélioration 
    - Antoine Chèvre https://github.com/antoinechevre 🐐


    ---

    [*Projet open-source - Cerema 2025*](https://github.com/CEREMA/hackathon-gtfs)
    """
    )
