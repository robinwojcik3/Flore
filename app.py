# app.py

import streamlit as st
import pandas as pd
import webbrowser
import requests # Pour les appels API (Tela Botanica)

# Potentiellement Selenium pour la navigation automatisée et le scrapping dynamique
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.common.keys import Keys
# from selenium.webdriver.chrome.service import Service as ChromeService # Pour Selenium 4+
# from webdriver_manager.chrome import ChromeDriverManager # Pour gérer le driver
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC

# Configuration de la page Streamlit
st.set_page_config(layout="wide", page_title="Agrégateur d'Informations Floristiques")

st.title("Application d'Automatisation de Recherche Floristique")

# --- 1. Interface Utilisateur et Saisie des Espèces ---
st.header("Saisie des Espèces")
st.caption("Entrez les noms scientifiques des espèces à rechercher.")

# Initialisation d'un DataFrame pour la saisie des espèces si non existant
if 'species_df' not in st.session_state:
    # Pré-remplir avec "Lamium purpureum" pour l'exemple
    st.session_state.species_df = pd.DataFrame({"Nom de l'espèce": ["Lamium purpureum"]})
else:
    # S'assurer que la colonne existe même si le dataframe est vide après suppression
    if "Nom de l'espèce" not in st.session_state.species_df.columns:
         st.session_state.species_df = pd.DataFrame(columns=["Nom de l'espèce"])


# Affichage et édition du DataFrame des espèces
# Utiliser key pour éviter les recréations intempestives
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
            'limite': 5, # On prend quelques résultats pour vérifier la pertinence
            'type_liste': 'liste_initiale'
        }
        response = requests.get(api_url, params=params, timeout=15) # Augmentation du timeout
        response.raise_for_status()
        data = response.json()
        
        if data and isinstance(data, list) and len(data) > 0:
            # Chercher une correspondance exacte du nom scientifique complet
            for result in data:
                # La clé peut varier, vérifier la documentation de l'API ou un exemple de réponse.
                # Clés possibles: 'nom_sci_complet', 'nom_scientifique', 'libelle_nom_scientifique'
                # Pour l'API eflore: 'nom_sci_complet' ou 'nom_sci_cf_nom_francais'
                # On va essayer plusieurs clés communes
                potential_name_keys = ['nom_sci_complet', 'nom_scientifique', 'libelle_nom_scientifique']
                nom_scientifique_api = None
                for key_try in potential_name_keys:
                    if key_try in result and result[key_try]:
                        nom_scientifique_api = result[key_try]
                        break
                
                if nom_scientifique_api and nom_scientifique_api.strip().lower() == species_name.strip().lower() and 'num_nom' in result:
                    return result['num_nom']
            
            # Si pas de correspondance exacte, on prend le premier résultat (moins fiable)
            # st.warning(f"[Tela Botanica] Correspondance exacte non trouvée pour '{species_name}'. Utilisation du premier résultat API.")
            # if 'num_nom' in data[0]:
            #     return data[0]['num_nom']

        st.warning(f"[Tela Botanica] Impossible de trouver un NN pertinent pour '{species_name}' via API. Réponse brute: {str(data)[:200]}...")
        return None
    except requests.exceptions.Timeout:
        st.error(f"[Tela Botanica] Timeout lors de la requête API pour '{species_name}'.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"[Tela Botanica] Erreur API pour '{species_name}': {e}")
        return None
    except ValueError as e: # Erreur de parsing JSON
        st.error(f"[Tela Botanica] Erreur de parsing JSON pour '{species_name}': {e}")
        return None

def build_tela_botanica_url(species_name):
    """
    Construit l'URL de la fiche espèce sur Tela Botanica en utilisant l'ID (NN).
    Exemple pour Lamium purpureum : https://www.tela-botanica.org/bdtfx-nn-37538-synthese
    """
    nn_id = get_tela_botanica_nn(species_name)
    if nn_id:
        return f"https://www.tela-botanica.org/bdtfx-nn-{nn_id}-synthese"
    else:
        # st.warning(f"[Tela Botanica] URL non construite pour '{species_name}' car NN non trouvé.")
        return None

def build_infoflora_url(species_name):
    """
    Construit l'URL de la fiche espèce sur InfoFlora.
    Exemple pour Lamium purpureum : https://www.infoflora.ch/fr/flore/lamium-purpureum.html
    """
    if not species_name:
        return None
    # Nettoyage basique : enlever les "subsp." ou "var." pour la recherche URL simplifiée
    # InfoFlora gère souvent bien les noms de base.
    base_name = species_name.split(" subsp.")[0].split(" var.")[0].strip()
    formatted_name = base_name.lower().replace(" ", "-")
    return f"https://www.infoflora.ch/fr/flore/{formatted_name}.html"

def search_and_scrape_floralp(species_name):
    """
    CIBLE: Automatiser la recherche sur Floralp et scraper les images.
    Pour 'Lamium purpureum', la cible est 'https://www.florealpes.com/fiche_lamierpourpre.php'.
    Cette fonction devrait utiliser Selenium pour naviguer, rechercher et atteindre cette page, puis scraper.
    """
    st.subheader(f"Floralp : {species_name}")
    # --- DÉBUT DU CODE POUR FLORALP (Selenium) ---
    # Exemple de ce que le code Selenium pourrait faire :
    # 1. Initialiser le driver (ex: ChromeDriver)
    #    try:
    #        options = webdriver.ChromeOptions()
    #        # options.add_argument('--headless') # Exécuter en arrière-plan
    #        options.add_argument('--no-sandbox')
    #        options.add_argument('--disable-dev-shm-usage')
    #        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    #    except Exception as e:
    #        st.error(f"[Floralp Selenium] Erreur d'initialisation du driver: {e}")
    #        return []

    # 2. Aller sur la page d'accueil de Floralp
    #    driver.get("https://www.florealpes.com/") # Vérifier l'URL exacte

    # 3. Localiser la barre de recherche (inspecter le site pour le bon sélecteur)
    #    try:
    #        search_bar = WebDriverWait(driver, 10).until(
    #            EC.presence_of_element_located((By.NAME, "recherche")) # Exemple de sélecteur
    #        )
    #        search_bar.send_keys(species_name) # Ou nom vernaculaire si plus pertinent pour Floralp
    #        search_bar.send_keys(Keys.RETURN)
    #    except Exception as e:
    #        st.error(f"[Floralp Selenium] Erreur lors de la recherche: {e}")
    #        driver.quit()
    #        return []
    
    # 4. Attendre les résultats et naviguer vers la page de l'espèce
    #    (Cette partie est complexe et dépend de la structure des résultats de Floralp)
    #    Exemple: Cliquer sur le premier lien pertinent
    #    WebDriverWait(driver, 10).until(...) # Attendre un élément spécifique de la page espèce
    #    target_url_example = "https://www.florealpes.com/fiche_lamierpourpre.php" # C'est ce type d'URL qu'on vise
    #    st.write(f"URL actuelle après recherche (pour débogage): {driver.current_url}")


    # 5. Une fois sur la page espèce, scraper les images
    #    image_elements = driver.find_elements(By.XPATH, "//img[contains(@src, 'photos')]") # Exemple XPATH
    #    image_urls = []
    #    for img in image_elements:
    #        src = img.get_attribute('src')
    #        if src and src.startswith('http'):
    #             image_urls.append(src)
    #        elif src: # Gérer les URLs relatives
    #             image_urls.append(f"https://www.florealpes.com/{src.lstrip('/')}")


    #    for url in image_urls:
    #        st.image(url, caption=f"Image de {species_name} depuis Floralp", width=300)
    #    driver.quit()
    #    return image_urls
    # --- FIN DU CODE POUR FLORALP ---
    
    st.warning(f"[Floralp] Logique de recherche et de scrapping pour '{species_name}' à implémenter avec Selenium. Cible type : ...fiche_nomvernaculaire.php")
    st.markdown("Exemple d'URL cible pour *Lamium purpureum* : [https://www.florealpes.com/fiche_lamierpourpre.php](https://www.florealpes.com/fiche_lamierpourpre.php)")
    return [] # Retourner une liste vide en attendant l'implémentation

def find_species_id_on_atlas(species_name):
    """
    Fonction à implémenter pour trouver l'ID d'une espèce sur l'Atlas Biodiversité AURA.
    Peut nécessiter du scrapping ou une recherche sur leur site si pas d'API directe.
    """
    # Placeholder - Ceci est la partie la plus complexe pour cette source
    # Option 1: Maintenir un mapping local (limité)
    species_id_map = {
        "Lamium purpureum": "10",
        # Ajouter d'autres espèces si connues
    }
    if species_name in species_id_map:
        return species_id_map[species_name]

    # Option 2: Tenter une recherche sur le site de l'Atlas (nécessiterait Selenium/Requests+BS)
    # Exemple de logique (très simplifiée):
    # 1. Construire une URL de recherche pour l'atlas
    #    search_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/recherche/especes?recherche_valeur={species_name.replace(' ', '+')}&recherche_type=mixte"
    # 2. Scraper la page de résultats pour trouver le lien vers la fiche espèce et en extraire l'ID.
    #    st.info(f"[Atlas AURA] Tentative de recherche d'ID pour {species_name} (logique à implémenter). URL de recherche indicative : {search_url}")
    
    return None


def display_atlas_biodivaura_distribution(species_name):
    """
    Affiche la répartition de l'espèce depuis l'Atlas Biodiversité Auvergne-Rhône-Alpes.
    Exemple pour Lamium purpureum (ID 10): https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/10
    """
    st.subheader(f"Atlas Biodiversité AURA - Répartition & Écologie : {species_name}")
    
    species_id_on_atlas = find_species_id_on_atlas(species_name)

    if species_id_on_atlas:
        atlas_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/{species_id_on_atlas}"
        st.markdown(f"Lien direct vers l'Atlas AURA : [{atlas_url}]({atlas_url})")
        
        # Tentative d'affichage dans un iframe.
        # Note: Le site cible doit autoriser l'intégration via iframe (X-Frame-Options).
        # Il semble que atlas.biodiversite-auvergne-rhone-alpes.fr bloque les iframes.
        # st.components.v1.iframe(atlas_url, height=600, scrolling=True)
        st.warning("L'intégration directe de l'Atlas Biodiversité AURA via iframe semble être bloquée par le site. Veuillez utiliser le lien direct ci-dessus.")
    else:
        st.warning(f"[Atlas AURA] ID non trouvé pour '{species_name}'. L'affichage de la répartition et de l'écologie est impossible sans ID. Une logique de recherche d'ID plus avancée est nécessaire.")

# --- 2. Bouton de Lancement et Traitement ---
if st.button("🚀 Lancer la recherche", type="primary", use_container_width=True):
    # Récupérer la liste des espèces depuis le DataFrame édité
    if "Nom de l'espèce" in st.session_state.species_df.columns:
        species_list = st.session_state.species_df["Nom de l'espèce"].dropna().unique().tolist()
        species_list = [name for name in species_list if name.strip()] # Enlever les noms vides
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
                # 2.a. Tela Botanica
                with st.spinner(f"Recherche du lien Tela Botanica pour {species_name}..."):
                    tela_url = build_tela_botanica_url(species_name)
                if tela_url:
                    st.markdown(f"🌿 **Tela Botanica**: [{species_name}]({tela_url})")
                    # Si vous voulez ouvrir automatiquement (peut être bloqué par les navigateurs):
                    # webbrowser.open_new_tab(tela_url)
                else:
                    st.markdown(f"🌿 **Tela Botanica**: Lien non trouvé pour {species_name}.")

                # 2.b. InfoFlora
                with st.spinner(f"Recherche du lien InfoFlora pour {species_name}..."):
                    infoflora_url = build_infoflora_url(species_name) # Toujours généré, même si la page 404
                if infoflora_url: # Toujours vrai si species_name n'est pas vide
                     st.markdown(f"🇨🇭 **InfoFlora**: [{species_name}]({infoflora_url})")
                    # webbrowser.open_new_tab(infoflora_url)
                else: # Ne devrait pas arriver si species_name est valide
                    st.markdown(f"🇨🇭 **InfoFlora**: Lien non généré pour {species_name}.")
            
            with col2:
                st.markdown("#### Intégrations et Scrapping (🚧 en développement)")
                # 2.c. Traitement Floralp (Recherche automatisée + Scrapping images)
                # Note : l'exécution de Selenium peut être longue et bloquante.
                # Envisager des indicateurs de chargement (st.spinner) ou des exécutions asynchrones.
                with st.spinner(f"Tentative de recherche sur Floralp pour {species_name}... (Fonctionnalité Selenium à implémenter)"):
                    floralp_image_urls = search_and_scrape_floralp(species_name)
                    if floralp_image_urls:
                        # st.image(floralp_image_urls, caption=[f"Image Floralp {j+1}" for j in range(len(floralp_image_urls))])
                        st.success(f"Images de Floralp pour {species_name} récupérées (logique d'affichage à finaliser).")
                    # else: Pas besoin de message ici car search_and_scrape_floralp envoie déjà un warning

            # 2.d. Afficher répartition et écologie Atlas Biodiv'AURA (anciennement OpenObs dans la demande)
            with st.spinner(f"Chargement des informations de l'Atlas Biodiversité AURA pour {species_name}..."):
                display_atlas_biodivaura_distribution(species_name)

            st.markdown("---") # Séparateur entre espèces

        st.success("Recherche terminée pour toutes les espèces.")
        st.balloons()

# Pied de page ou informations supplémentaires
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

# Pour le débogage, afficher l'état de session
# st.sidebar.subheader("État de Session (Débogage)")
# st.sidebar.json(st.session_state)
