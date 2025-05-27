# app.py

import streamlit as st
import pandas as pd
import webbrowser
import requests # Pour les appels API (Tela Botanica)
from bs4 import BeautifulSoup # Pour le scraping de l'ID de l'Atlas AURA
import re # Pour extraire l'ID de l'URL de l'Atlas AURA

# Potentiellement Selenium pour la navigation automatisée et le scrapping dynamique
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.common.keys import Keys
# from selenium.webdriver.chrome.service import Service as ChromeService # Pour Selenium 4+
# from webdriver_manager.chrome import ChromeDriverManager # Pour gérer le driver
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC

# Potentiellement Folium pour les cartes interactives
# import folium
# from streamlit_folium import st_folium

# Configuration de la page Streamlit
st.set_page_config(layout="wide", page_title="Agrégateur d'Informations Floristiques")

st.title("Application d'Automatisation de Recherche Floristique")

# --- 1. Interface Utilisateur et Saisie des Espèces ---
st.header("Saisie des Espèces")
st.caption("Entrez les noms scientifiques des espèces à rechercher.")

# Initialisation d'un DataFrame pour la saisie des espèces si non existant
if 'species_df' not in st.session_state:
    # Pré-remplir avec "Lamium purpureum" pour l'exemple
    st.session_state.species_df = pd.DataFrame({"Nom de l'espèce": ["Lamium purpureum", "Cardamine hirsuta"]})
else:
    # S'assurer que la colonne existe même si le dataframe est vide après suppression
    if "Nom de l'espèce" not in st.session_state.species_df.columns:
         st.session_state.species_df = pd.DataFrame(columns=["Nom de l'espèce"])


# Affichage et édition du DataFrame des espèces
edited_df = st.data_editor(
    st.session_state.species_df,
    num_rows="dynamic",
    key="species_data_editor",
    use_container_width=True,
    column_config={
        "Nom de l'espèce": st.column_config.TextColumn(
            "Nom de l'espèce (scientifique)",
            help="Entrez le nom scientifique complet de l'espèce.",
            required=True,
        )
    }
)
st.session_state.species_df = edited_df


# --- Fonctions Utilitaires ---

def get_tela_botanica_nn(species_name):
    """
    Interroge l'API de Tela Botanica pour obtenir le numéro national (NN) d'une espèce.
    Retourne le NN ou None si non trouvé ou en cas d'erreur.
    """
    if not species_name:
        return None
    try:
        api_url = "https://api.tela-botanica.org/service:eflore:0.1/noms/completion"
        params = {
            'q': species_name,
            'limite': 5, 
            'type_liste': 'liste_initiale'
        }
        response = requests.get(api_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data and isinstance(data, list) and len(data) > 0:
            for result in data:
                potential_name_keys = ['nom_sci_complet', 'nom_scientifique', 'libelle_nom_scientifique']
                nom_scientifique_api = None
                for key_try in potential_name_keys:
                    if key_try in result and result[key_try]:
                        nom_scientifique_api = result[key_try]
                        break
                
                if nom_scientifique_api and nom_scientifique_api.strip().lower() == species_name.strip().lower() and 'num_nom' in result:
                    return result['num_nom']
        
        st.warning(f"[Tela Botanica] Impossible de trouver un NN pertinent pour '{species_name}' via API. Réponse brute: {str(data)[:200]}...")
        return None
    except requests.exceptions.Timeout:
        st.error(f"[Tela Botanica] Timeout lors de la requête API pour '{species_name}'.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"[Tela Botanica] Erreur API pour '{species_name}': {e}")
        return None
    except ValueError as e: 
        st.error(f"[Tela Botanica] Erreur de parsing JSON pour '{species_name}': {e}")
        return None

def build_tela_botanica_url(species_name):
    """
    Construit l'URL de la fiche espèce sur Tela Botanica en utilisant l'ID (NN).
    """
    nn_id = get_tela_botanica_nn(species_name)
    if nn_id:
        return f"https://www.tela-botanica.org/bdtfx-nn-{nn_id}-synthese"
    return None

def build_infoflora_url(species_name):
    """
    Construit l'URL de la fiche espèce sur InfoFlora.
    """
    if not species_name:
        return None
    base_name = species_name.split(" subsp.")[0].split(" var.")[0].strip()
    formatted_name = base_name.lower().replace(" ", "-")
    return f"https://www.infoflora.ch/fr/flore/{formatted_name}.html"

def search_and_scrape_floralp(species_name):
    """
    CIBLE: Automatiser la recherche sur Floralp et scraper les images.
    Nécessite Selenium.
    """
    st.subheader(f"Floralp : {species_name}")
    # --- DÉBUT DU CODE POUR FLORALP (Selenium) ---
    # ... (Implémentation Selenium comme esquissée précédemment) ...
    # --- FIN DU CODE POUR FLORALP ---
    st.warning(f"[Floralp] Logique de recherche et de scrapping pour '{species_name}' à implémenter avec Selenium. Cible type : ...fiche_nomvernaculaire.php")
    st.markdown("Exemple d'URL cible pour *Lamium purpureum* : [https://www.florealpes.com/fiche_lamierpourpre.php](https://www.florealpes.com/fiche_lamierpourpre.php)")
    return [] 

def find_species_id_on_atlas(species_name):
    """
    Tente de trouver l'ID d'une espèce sur l'Atlas Biodiversité AURA par scraping.
    Retourne l'ID (string) ou None.
    """
    if not species_name:
        return None

    # Option 1: Maintenir un mapping local (limité, pour tests rapides)
    species_id_map = {
        "Lamium purpureum": "10",
        "Cardamine hirsuta": "250" # Exemple, ID à vérifier
    }
    if species_name in species_id_map:
        return species_id_map[species_name]

    # Option 2: Scraper le site de l'Atlas pour l'ID
    search_query = species_name.replace(" ", "+")
    # L'URL de recherche peut changer, il faut l'inspecter sur le site de l'Atlas.
    # search_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/recherche/especes?recherche_valeur={search_query}&recherche_type=mixte"
    # Une autre URL de recherche possible (plus simple)
    search_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/recherche/especes/{search_query}"
    
    st.info(f"[Atlas AURA] Tentative de recherche d'ID pour '{species_name}' sur : {search_url}")

    headers = { # Simuler un navigateur pour éviter les blocages basiques
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(search_url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # La logique de parsing dépendra de la structure HTML de la page de résultats de l'Atlas.
        # Il faut inspecter le HTML pour trouver comment identifier le bon lien vers la fiche espèce.
        # Exemple : chercher un lien <a> dont le texte correspond au nom de l'espèce
        # et dont le href contient "/espece/ID_NUMERIQUE"

        # Tentative de trouver un lien contenant "/espece/" et le nom de l'espèce dans le texte ou titre du lien
        # Ceci est une heuristique et peut nécessiter un ajustement précis.
        species_links = soup.find_all('a', href=re.compile(r'/espece/\d+'))
        
        found_id = None
        for link in species_links:
            # Vérifier si le texte du lien ou un attribut title correspond au nom de l'espèce
            link_text_matches = species_name.lower() in link.get_text().lower()
            link_title_matches = link.get('title') and species_name.lower() in link.get('title').lower()
            
            if link_text_matches or link_title_matches:
                href = link.get('href')
                match = re.search(r'/espece/(\d+)', href)
                if match:
                    found_id = match.group(1)
                    st.success(f"[Atlas AURA] ID trouvé pour '{species_name}': {found_id} via le lien '{href}'")
                    return found_id
        
        if not found_id:
            # Si la recherche directe mène à la page de l'espèce, l'ID peut être dans l'URL de la réponse
            current_url_match = re.search(r'/espece/(\d+)', response.url)
            if current_url_match:
                found_id = current_url_match.group(1)
                st.success(f"[Atlas AURA] ID trouvé pour '{species_name}': {found_id} via l'URL de redirection '{response.url}'")
                return found_id

        st.warning(f"[Atlas AURA] Aucun lien direct vers une fiche espèce trouvée pour '{species_name}' sur la page de résultats. Le scraping a besoin d'être affiné.")
        # st.html(str(soup)[:2000]) # Pour déboguer le HTML reçu

    except requests.exceptions.Timeout:
        st.error(f"[Atlas AURA] Timeout lors de la requête de recherche d'ID pour '{species_name}'.")
    except requests.exceptions.RequestException as e:
        st.error(f"[Atlas AURA] Erreur de requête pour la recherche d'ID de '{species_name}': {e}")
    except Exception as e:
        st.error(f"[Atlas AURA] Erreur inattendue lors du scraping pour l'ID de '{species_name}': {e}")
        
    return None


def display_atlas_biodivaura_distribution(species_name):
    """
    Affiche la répartition de l'espèce depuis l'Atlas Biodiversité Auvergne-Rhône-Alpes.
    """
    st.subheader(f"Atlas Biodiversité AURA - Répartition & Écologie : {species_name}")
    
    species_id_on_atlas = find_species_id_on_atlas(species_name)

    if species_id_on_atlas:
        atlas_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/{species_id_on_atlas}"
        st.markdown(f"Lien direct vers l'Atlas AURA : [{atlas_url}]({atlas_url})")
        
        st.warning("L'intégration directe de l'Atlas Biodiversité AURA via iframe semble être bloquée par le site. Veuillez utiliser le lien direct ci-dessus.")
        
        # Idée pour carte interactive (nécessite scraping des données de localisation + Folium):
        # 1. Scraper la page de l'espèce sur l'Atlas AURA (atlas_url) pour obtenir les données de répartition (points GPS, polygones, etc.).
        #    Ceci est une tâche de scraping complexe et spécifique à la structure du site de l'Atlas.
        # 2. Si des coordonnées sont obtenues:
        #    coords = [(lat1, lon1), (lat2, lon2), ...]
        #    if coords:
        #        m = folium.Map(location=[coords[0][0], coords[0][1]], zoom_start=9) # Centrer sur le premier point
        #        for lat, lon in coords:
        #            folium.Marker([lat, lon], popup=species_name).add_to(m)
        #        with st.expander("Carte de répartition interactive (Concept)"):
        #             st_folium(m, width=700, height=500)
        #    else:
        #        st.info("[Carte Interactive] Données de localisation non récupérées pour créer une carte.")

    else:
        st.warning(f"[Atlas AURA] ID non trouvé pour '{species_name}'. L'affichage de la répartition et de l'écologie est impossible sans ID. La logique de scraping pour l'ID a peut-être échoué ou doit être affinée.")

# --- 2. Bouton de Lancement et Traitement ---
if st.button("🚀 Lancer la recherche", type="primary", use_container_width=True):
    if "Nom de l'espèce" in st.session_state.species_df.columns:
        species_list = st.session_state.species_df["Nom de l'espèce"].dropna().unique().tolist()
        species_list = [name for name in species_list if name.strip()] 
    else:
        species_list = []

    if not species_list:
        st.warning("Veuillez entrer au moins un nom d'espèce dans le tableau ci-dessus.")
    else:
        st.info(f"Lancement de la recherche pour : {', '.join(species_list)}")

        for species_name in species_list:
            st.markdown(f"--- \n ## Résultats pour : *{species_name}*")
            
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### Liens directs (ouverture manuelle)")
                with st.spinner(f"Recherche du lien Tela Botanica pour {species_name}..."):
                    tela_url = build_tela_botanica_url(species_name)
                if tela_url:
                    st.markdown(f"🌿 **Tela Botanica**: [{species_name}]({tela_url})")
                else:
                    st.markdown(f"🌿 **Tela Botanica**: Lien non trouvé pour {species_name}.")

                with st.spinner(f"Recherche du lien InfoFlora pour {species_name}..."):
                    infoflora_url = build_infoflora_url(species_name) 
                if infoflora_url:
                     st.markdown(f"🇨🇭 **InfoFlora**: [{species_name}]({infoflora_url})")
                else: 
                    st.markdown(f"🇨🇭 **InfoFlora**: Lien non généré pour {species_name}.")
            
            with col2:
                st.markdown("#### Intégrations et Scrapping (🚧 en développement)")
                with st.spinner(f"Tentative de recherche sur Floralp pour {species_name}... (Fonctionnalité Selenium à implémenter)"):
                    floralp_image_urls = search_and_scrape_floralp(species_name)
                    # if floralp_image_urls:
                        # Affichage des images si récupérées

            with st.spinner(f"Chargement des informations de l'Atlas Biodiversité AURA pour {species_name}..."):
                display_atlas_biodivaura_distribution(species_name)

            st.markdown("---") 

        st.success("Recherche terminée pour toutes les espèces.")
        st.balloons()

# Pied de page
st.sidebar.header("À propos")
st.sidebar.info(
    "Cette application vise à automatiser la recherche d'informations sur les espèces végétales "
    "à partir de diverses plateformes.\n\n"
    "Développée par Robin Wojcik, Améten."
)
st.sidebar.markdown("---")
st.sidebar.markdown("**Plateformes Cibles (Exemples) :**")
st.sidebar.markdown("- Tela Botanica")
st.sidebar.markdown("- InfoFlora")
st.sidebar.markdown("- Floralp (images)")
st.sidebar.markdown("- Atlas Biodiversité Auvergne-Rhône-Alpes (répartition, écologie)")
