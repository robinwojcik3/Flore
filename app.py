# app.py

import streamlit as st
import pandas as pd
import webbrowser
import requests
from bs4 import BeautifulSoup
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import urllib.parse
import streamlit.components.v1 as components

# Configuration de la page Streamlit
st.set_page_config(layout="wide", page_title="Agrégateur d'Informations Floristiques")

st.title("🌿 Application d'Automatisation de Recherche Floristique")

# --- 1. Interface Utilisateur et Saisie des Espèces ---
st.header("📝 Saisie des Espèces")

# Initialisation d'un DataFrame pour la saisie des espèces si non existant
if 'species_df' not in st.session_state:
    # Pré-remplir avec un exemple
    st.session_state.species_df = pd.DataFrame({
        "Nom de l'espèce": ["Lamium purpureum", ""]
    })

# Affichage et édition du DataFrame des espèces
edited_df = st.data_editor(
    st.session_state.species_df, 
    num_rows="dynamic", 
    key="species_editor",
    use_container_width=True
)
st.session_state.species_df = edited_df

# --- Fonctions Utilitaires ---

def normalize_species_name(species_name):
    """Normalise le nom de l'espèce pour les URLs."""
    return species_name.lower().strip().replace(" ", "-")

def get_selenium_driver():
    """Initialise et retourne un driver Selenium Chrome en mode headless."""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    return webdriver.Chrome(options=options)

def build_tela_botanica_url(species_name):
    """
    Construit l'URL de la fiche espèce sur Tela Botanica.
    Nécessite de trouver l'ID de l'espèce - pour l'instant, retourne une URL de recherche.
    """
    # Pour une recherche directe
    query = urllib.parse.quote(species_name)
    search_url = f"https://www.tela-botanica.org/eflore/?module=recherche&action=rechercheSimple&type_nom=nom_scientifique&nom={query}"
    
    # Dans un cas réel, on pourrait faire une recherche pour obtenir l'ID exact
    # et construire l'URL comme : https://www.tela-botanica.org/bdtfx-nn-{ID}-synthese
    return search_url

def build_infoflora_url(species_name):
    """Construit l'URL de la fiche espèce sur InfoFlora."""
    normalized_name = normalize_species_name(species_name)
    return f"https://www.infoflora.ch/fr/flore/{normalized_name}.html"

def build_florealpes_url(species_name):
    """
    Construit l'URL de FloraAlpes basée sur le nom de l'espèce.
    Nécessite une logique de mapping des noms.
    """
    # Mapping simplifié - dans la réalité, il faudrait une base de données complète
    species_mapping = {
        "lamium purpureum": "lamierpourpre",
        # Ajouter d'autres mappings ici
    }
    
    normalized = species_name.lower().strip()
    if normalized in species_mapping:
        return f"https://www.florealpes.com/fiche_{species_mapping[normalized]}.php"
    else:
        # Retourner une URL de recherche par défaut
        query = urllib.parse.quote(species_name)
        return f"https://www.florealpes.com/recherche.php?rech_mot={query}"

def search_and_scrape_florealpes(species_name):
    """
    Scrape les images depuis FloraAlpes.
    """
    image_urls = []
    
    try:
        url = build_florealpes_url(species_name)
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Recherche des images dans la galerie FloraAlpes
            # Sélecteurs à adapter selon la structure exacte du site
            image_elements = soup.find_all('img', class_='img_fiche')
            if not image_elements:
                # Alternative : chercher toutes les images dans le conteneur principal
                main_content = soup.find('div', id='fiche') or soup.find('div', class_='content')
                if main_content:
                    image_elements = main_content.find_all('img')
            
            for img in image_elements:
                src = img.get('src')
                if src:
                    # Construire l'URL complète si nécessaire
                    if src.startswith('/'):
                        src = f"https://www.florealpes.com{src}"
                    elif not src.startswith('http'):
                        src = f"https://www.florealpes.com/{src}"
                    
                    # Filtrer les images pertinentes (éviter logos, icônes, etc.)
                    if 'photos' in src or 'images' in src:
                        image_urls.append(src)
            
            # Afficher le lien vers la page
            st.markdown(f"🌸 [FloraAlpes - {species_name}]({url})")
            
    except Exception as e:
        st.error(f"Erreur lors du scraping FloraAlpes pour {species_name}: {str(e)}")
    
    return image_urls

def search_and_scrape_florealpes_selenium(species_name):
    """
    Version alternative avec Selenium pour FloraAlpes si nécessaire.
    """
    st.info("Recherche sur FloraAlpes avec Selenium...")
    image_urls = []
    
    try:
        driver = get_selenium_driver()
        driver.get("https://www.florealpes.com/")
        
        # Trouver et remplir le champ de recherche
        search_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "rech_mot"))
        )
        search_input.clear()
        search_input.send_keys(species_name)
        search_input.send_keys(Keys.RETURN)
        
        # Attendre les résultats
        time.sleep(2)
        
        # Cliquer sur le premier résultat si disponible
        try:
            first_result = driver.find_element(By.CSS_SELECTOR, "div.resultat a")
            first_result.click()
            time.sleep(2)
            
            # Récupérer les images
            images = driver.find_elements(By.CSS_SELECTOR, "img.img_fiche, div.galerie img")
            for img in images:
                src = img.get_attribute('src')
                if src and ('photos' in src or 'images' in src):
                    image_urls.append(src)
                    
        except:
            st.warning(f"Aucun résultat trouvé pour {species_name} sur FloraAlpes")
        
        driver.quit()
        
    except Exception as e:
        st.error(f"Erreur Selenium FloraAlpes: {str(e)}")
        if 'driver' in locals():
            driver.quit()
    
    return image_urls

def get_biodiv_aura_info(species_name):
    """
    Récupère les informations depuis Biodiv'Aura Atlas.
    """
    # Pour l'exemple avec Lamium purpureum, l'ID est 10
    # Dans la réalité, il faudrait faire une recherche pour obtenir l'ID
    
    # URL de recherche
    search_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/recherche?q={urllib.parse.quote(species_name)}"
    
    return {
        'search_url': search_url,
        'atlas_url': None,  # À compléter avec l'ID réel
        'ecology_info': None
    }

def display_openobs_distribution(species_name):
    """
    Affiche la répartition de l'espèce depuis OpenObs/Biodiv'Aura.
    """
    info = get_biodiv_aura_info(species_name)
    
    if info['search_url']:
        st.markdown(f"🗺️ [Rechercher la répartition sur Biodiv'Aura Atlas]({info['search_url']})")
        
        # Option : intégrer une carte via iframe si l'URL directe est connue
        # if info['atlas_url']:
        #     components.iframe(info['atlas_url'], height=500)

def display_biodivaura_ecology(species_name):
    """
    Affiche les informations écologiques depuis Biodiv'Aura.
    """
    st.markdown("🌱 **Informations écologiques**")
    
    # Ici, on pourrait scraper les infos écologiques
    # Pour l'instant, on affiche un placeholder
    st.info("Les informations écologiques seront récupérées depuis Biodiv'Aura Atlas")

# --- 2. Bouton de Lancement et Traitement ---
if st.button("🔍 Lancer la recherche", type="primary", use_container_width=True):
    species_list = st.session_state.species_df["Nom de l'espèce"].dropna().unique().tolist()
    species_list = [s for s in species_list if s.strip()]  # Retirer les chaînes vides

    if not species_list:
        st.warning("⚠️ Veuillez entrer au moins un nom d'espèce.")
    else:
        st.success(f"🚀 Lancement de la recherche pour : {', '.join(species_list)}")

        # Barre de progression
        progress_bar = st.progress(0)
        
        for i, species_name in enumerate(species_list):
            progress_bar.progress((i + 1) / len(species_list))
            
            # Création d'un conteneur pour cette espèce
            with st.container():
                st.markdown(f"---")
                st.markdown(f"## 🌿 *{species_name}*")
                
                # Créer des colonnes pour organiser l'affichage
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### 📚 Fiches descriptives")
                    
                    # Tela Botanica
                    tela_url = build_tela_botanica_url(species_name)
                    st.markdown(f"📖 [Tela Botanica]({tela_url})")
                    
                    # InfoFlora
                    infoflora_url = build_infoflora_url(species_name)
                    st.markdown(f"🌼 [InfoFlora]({infoflora_url})")
                    
                    # Option pour ouvrir automatiquement dans de nouveaux onglets
                    if st.checkbox(f"Ouvrir automatiquement les liens pour {species_name}", key=f"auto_open_{i}"):
                        webbrowser.open_new_tab(tela_url)
                        webbrowser.open_new_tab(infoflora_url)
                        st.info("✅ Liens ouverts dans de nouveaux onglets")
                
                with col2:
                    st.markdown("### 🌍 Répartition géographique")
                    display_openobs_distribution(species_name)
                
                # Section images FloraAlpes
                st.markdown("### 📸 Galerie d'images (FloraAlpes)")
                
                with st.spinner(f"Recherche des images pour {species_name}..."):
                    # Utiliser la version avec requests/BeautifulSoup par défaut
                    image_urls = search_and_scrape_florealpes(species_name)
                    
                    # Si pas d'images trouvées, essayer avec Selenium
                    if not image_urls and st.checkbox(f"Utiliser la recherche avancée pour {species_name}", key=f"selenium_{i}"):
                        image_urls = search_and_scrape_florealpes_selenium(species_name)
                    
                    if image_urls:
                        # Afficher les images dans une grille
                        img_cols = st.columns(min(len(image_urls), 4))
                        for idx, img_url in enumerate(image_urls[:8]):  # Limiter à 8 images
                            with img_cols[idx % 4]:
                                st.image(img_url, caption=f"{species_name} - Photo {idx+1}", use_column_width=True)
                    else:
                        st.info(f"Aucune image trouvée pour {species_name}")
                
                # Section écologie
                st.markdown("### 🌿 Écologie")
                display_biodivaura_ecology(species_name)
        
        progress_bar.progress(1.0)
        st.balloons()
        st.success("✅ Recherche terminée pour toutes les espèces!")

# Sidebar avec informations et options
with st.sidebar:
    st.header("ℹ️ À propos")
    st.info(
        "Cette application automatise la recherche d'informations sur les espèces végétales "
        "à partir de diverses plateformes botaniques."
    )
    
    st.markdown("---")
    
    st.header("⚙️ Options")
    
    # Option pour utiliser Selenium
    use_selenium = st.checkbox("Utiliser Selenium pour le scraping avancé", 
                              help="Active la recherche automatisée avec simulation de navigation")
    
    # Option pour le nombre d'images à afficher
    max_images = st.slider("Nombre maximum d'images par espèce", 1, 20, 8)
    
    st.markdown("---")
    
    st.header("📊 Sources de données")
    st.markdown("""
    - 🌐 [Tela Botanica](https://www.tela-botanica.org/)
    - 🇨🇭 [InfoFlora](https://www.infoflora.ch/)
    - 🏔️ [FloraAlpes](https://www.florealpes.com/)
    - 🗺️ [Biodiv'Aura Atlas](https://atlas.biodiversite-auvergne-rhone-alpes.fr/)
    """)
    
    st.markdown("---")
    st.caption("Développé pour Améten, Grenoble")
