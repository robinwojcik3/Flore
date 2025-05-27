# app.py

import streamlit as st
import pandas as pd
import webbrowser
# Potentiellement Selenium pour la navigation automatisée et le scrapping dynamique
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.common.keys import Keys
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# Potentiellement Requests et BeautifulSoup pour le scrapping statique
# import requests
# from bs4 import BeautifulSoup

# Configuration de la page Streamlit
st.set_page_config(layout="wide", page_title="Agrégateur d'Informations Floristiques")

st.title("Application d'Automatisation de Recherche Floristique")

# --- 1. Interface Utilisateur et Saisie des Espèces ---
st.header("Saisie des Espèces")

# Initialisation d'un DataFrame pour la saisie des espèces si non existant
if 'species_df' not in st.session_state:
    st.session_state.species_df = pd.DataFrame(columns=["Nom de l'espèce"])

# Affichage et édition du DataFrame des espèces
edited_df = st.data_editor(st.session_state.species_df, num_rows="dynamic", key="species_editor")
st.session_state.species_df = edited_df

# --- Fonctions Utilitaires ---

def build_tela_botanica_url(species_name):
    """
    Construit l'URL de la fiche espèce sur Tela Botanica.
    À adapter selon la structure exacte de l'URL.
    """
    # Exemple (à vérifier et adapter) :
    # query_name = species_name.replace(" ", "+")
    # return f"https://www.tela-botanica.org/eflore/?search={query_name}"
    # OU si l'ID est connu ou peut être trouvé via une API/recherche préliminaire
    # return f"https://www.tela-botanica.org/bdtfx-nn-{ID_ESPECE}-synthese"
    st.warning(f"[Tela Botanica] Logique de construction d'URL pour '{species_name}' à implémenter.")
    return None

def build_infoflora_url(species_name):
    """
    Construit l'URL de la fiche espèce sur InfoFlora.
    À adapter selon la structure exacte de l'URL.
    """
    # Exemple (à vérifier et adapter) :
    # query_name = species_name.replace(" ", "-").lower()
    # return f"https://www.infoflora.ch/fr/flore/{query_name}.html"
    st.warning(f"[InfoFlora] Logique de construction d'URL pour '{species_name}' à implémenter.")
    return None

def search_and_scrape_floralp(species_name):
    """
    Automatise la recherche sur Floralp et scrape les images.
    Nécessite Selenium.
    """
    st.subheader(f"Floralp : {species_name}")
    # --- Début du Code pour Floralp (Selenium) ---
    # Initialiser le driver Selenium (ex: ChromeDriver)
    # driver = webdriver.Chrome(service=webdriver.chrome.service.Service(ChromeDriverManager().install())) # Nécessite webdriver_manager
    # driver.get("URL_DE_FLORALP")

    # Localiser la barre de recherche, entrer le nom de l'espèce, soumettre
    # search_bar = driver.find_element(By.ID, "ID_BARRE_RECHERCHE_FLORALP") # Ou autre sélecteur
    # search_bar.send_keys(species_name)
    # search_bar.send_keys(Keys.RETURN) # Ou cliquer sur un bouton de recherche

    # Attendre que la page de résultats se charge et naviguer vers la page espèce si nécessaire
    # WebDriverWait(driver, 10).until(...)

    # Une fois sur la page espèce, scraper les images
    # image_elements = driver.find_elements(By.XPATH, "//XPATH_VERS_IMAGES_FLORALP")
    # image_urls = [img.get_attribute('src') for img in image_elements]

    # for url in image_urls:
    #     st.image(url, caption=f"Image de {species_name} depuis Floralp")

    # driver.quit()
    # --- Fin du Code pour Floralp ---
    st.warning(f"[Floralp] Logique de recherche et de scrapping pour '{species_name}' à implémenter avec Selenium.")
    # Retourner les URLs des images ou les afficher directement
    return [] # Liste des URLs d'images

def display_openobs_distribution(species_name):
    """
    Affiche la répartition de l'espèce depuis OpenObs.
    Peut être un iframe ou une image générée/scrapée.
    """
    st.subheader(f"OpenObs - Répartition : {species_name}")
    # --- Début du Code pour OpenObs ---
    # Exemple avec un iframe si OpenObs le permet et a une URL constructible
    # openobs_url = f"URL_OPENOBS_POUR_ESPECE_{species_name.replace(' ', '_')}"
    # st.components.v1.iframe(openobs_url, height=400)
    # OU
    # Scrapper les informations/images nécessaires si pas d'iframe possible.
    # --- Fin du Code pour OpenObs ---
    st.warning(f"[OpenObs] Logique d'affichage de la répartition pour '{species_name}' à implémenter.")

def display_biodivaura_ecology(species_name):
    """
    Affiche les informations écologiques depuis Biodiv'Aura.
    Peut être un iframe ou du texte scrapé.
    """
    st.subheader(f"Biodiv'Aura - Écologie : {species_name}")
    # --- Début du Code pour Biodiv'Aura ---
    # Exemple avec un iframe si Biodiv'Aura le permet et a une URL constructible
    # biodivaura_url = f"URL_BIODIVAURA_POUR_ESPECE_{species_name.replace(' ', '_')}"
    # st.components.v1.iframe(biodivaura_url, height=300)
    # OU
    # Scrapper les informations textuelles pertinentes.
    # --- Fin du Code pour Biodiv'Aura ---
    st.warning(f"[Biodiv'Aura] Logique d'affichage de l'écologie pour '{species_name}' à implémenter.")


# --- 2. Bouton de Lancement et Traitement ---
if st.button("Lancer la recherche", type="primary"):
    species_list = st.session_state.species_df["Nom de l'espèce"].dropna().unique().tolist()

    if not species_list:
        st.warning("Veuillez entrer au moins un nom d'espèce.")
    else:
        st.info(f"Lancement de la recherche pour : {', '.join(species_list)}")

        # Création de colonnes pour une disposition côte à côte (optionnel)
        # Adapter le nombre de colonnes au besoin
        # cols = st.columns(len(species_list))

        for i, species_name in enumerate(species_list):
            # col = cols[i % len(cols)] # Utiliser la colonne correspondante
            # with col: # Afficher les résultats d'une espèce dans sa colonne
            st.markdown(f"--- \n ## Résultats pour : *{species_name}*")

            # 2.a. Ouvrir Tela Botanica
            tela_url = build_tela_botanica_url(species_name)
            if tela_url:
                # Pour ouvrir dans un nouvel onglet automatiquement :
                # webbrowser.open_new_tab(tela_url)
                # Pour l'instant, affichons le lien :
                st.markdown(f"- [Tela Botanica : {species_name}]({tela_url}) (Ouverture automatique à implémenter si souhaité via `webbrowser`)")


            # 2.b. Ouvrir InfoFlora
            infoflora_url = build_infoflora_url(species_name)
            if infoflora_url:
                # webbrowser.open_new_tab(infoflora_url)
                st.markdown(f"- [InfoFlora : {species_name}]({infoflora_url}) (Ouverture automatique à implémenter si souhaité via `webbrowser`)")

            # 2.c. Traitement Floralp (Recherche automatisée + Scrapping images)
            # Note : l'exécution de Selenium peut être longue et bloquante.
            # Envisager des indicateurs de chargement (st.spinner) ou des exécutions asynchrones si possible.
            with st.spinner(f"Recherche des images sur Floralp pour {species_name}..."):
                floralp_image_urls = search_and_scrape_floralp(species_name)
                if floralp_image_urls:
                    # st.image(floralp_image_urls, caption=[f"Image Floralp {j+1}" for j in range(len(floralp_image_urls))])
                    st.success(f"Images de Floralp pour {species_name} récupérées (logique d'affichage à finaliser).")
                else:
                    st.info(f"Aucune image trouvée ou erreur lors du scrapping Floralp pour {species_name}.")


            # 2.d. Afficher répartition OpenObs
            with st.spinner(f"Chargement de la répartition OpenObs pour {species_name}..."):
                display_openobs_distribution(species_name)

            # 2.e. Afficher écologie Biodiv'Aura
            with st.spinner(f"Chargement de l'écologie Biodiv'Aura pour {species_name}..."):
                display_biodivaura_ecology(species_name)

            st.markdown("---") # Séparateur entre espèces

        st.success("Recherche terminée pour toutes les espèces.")

# Pied de page ou informations supplémentaires
st.sidebar.header("À propos")
st.sidebar.info(
    "Cette application automatise la recherche d'informations sur les espèces végétales "
    "à partir de diverses plateformes."
)
st.sidebar.markdown("---")
# st.sidebar.write(f"Utilisateur : Robin Wojcik") # Information personnelle
# st.sidebar.write(f"Organisation : Améten, Grenoble") # Information personnelle
