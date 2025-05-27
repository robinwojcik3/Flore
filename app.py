# app.py (extraits modifiés)

import streamlit as st
import pandas as pd
import webbrowser
import requests # Pour les appels API (Tela Botanica)
# ... autres imports ...

# --- Fonctions Utilitaires (Mises à jour) ---

def get_tela_botanica_nn(species_name):
    """
    Interroge l'API de Tela Botanica pour obtenir le numéro national (NN) d'une espèce.
    Retourne le NN ou None si non trouvé ou en cas d'erreur.
    """
    try:
        api_url = "https://api.tela-botanica.org/service:eflore:0.1/noms/completion"
        params = {
            'q': species_name,
            'limite': 1, # On prend le premier résultat pertinent
            'type_liste': 'liste_initiale'
        }
        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status() # Lève une exception pour les codes d'erreur HTTP
        data = response.json()
        
        # La structure exacte de la réponse doit être vérifiée
        # Supposons que les résultats sont dans une liste et que le premier a 'num_nom'
        if data and isinstance(data, list) and len(data) > 0:
            # Tenter de trouver une correspondance exacte (ou la plus probable)
            # La logique de sélection peut nécessiter d'être affinée.
            # Par exemple, vérifier si 'nom_sci_complet' correspond exactement
            # Ici, on prend le premier pour simplifier
            first_result = data[0]
            if 'num_nom' in first_result:
                return first_result['num_nom']
        st.warning(f"[Tela Botanica] Impossible de trouver le NN pour '{species_name}' via API. Réponse: {data}")
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
    """
    nn_id = get_tela_botanica_nn(species_name)
    if nn_id:
        return f"https://www.tela-botanica.org/bdtfx-nn-{nn_id}-synthese"
    else:
        st.warning(f"[Tela Botanica] URL non construite pour '{species_name}' car NN non trouvé.")
        return None

def build_infoflora_url(species_name):
    """
    Construit l'URL de la fiche espèce sur InfoFlora.
    Exemple pour Lamium purpureum : https://www.infoflora.ch/fr/flore/lamium-purpureum.html
    """
    if not species_name:
        return None
    formatted_name = species_name.lower().replace(" ", "-")
    # Gérer les cas de sous-espèces ou variétés si nécessaire (ex: "subsp.", "var.")
    # Cela pourrait nécessiter un nettoyage plus avancé du nom
    return f"https://www.infoflora.ch/fr/flore/{formatted_name}.html"

# Pour Floralp, la stratégie principale reste la recherche automatisée.
# L'URL https://www.florealpes.com/fiche_lamierpourpre.php est la CIBLE de cette recherche.
def search_and_scrape_floralp(species_name):
    """
    Automatise la recherche sur Floralp et scrape les images.
    La cible pour 'Lamium purpureum' est 'https://www.florealpes.com/fiche_lamierpourpre.php'.
    Cette fonction utilisera Selenium pour naviguer et atteindre cette page, puis scraper.
    """
    st.subheader(f"Floralp : {species_name}")
    # ... (Début du Code Selenium comme précédemment)
    # L'objectif de la navigation automatisée sera d'arriver sur une URL
    # du type https://www.florealpes.com/fiche_NOMFORMATTEPOURFLORALPES.php
    # puis de scraper les images.
    # ... (Fin du Code Selenium)
    st.warning(f"[Floralp] Logique de recherche et de scrapping pour '{species_name}' à implémenter avec Selenium. Cible type : ...fiche_nomvernaculaire.php")
    return []

def display_openobs_distribution(species_name): # Ou Atlas Biodiv AURA
    """
    Affiche la répartition de l'espèce depuis l'Atlas Biodiversité Auvergne-Rhône-Alpes.
    Exemple pour Lamium purpureum (ID 10): https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/10
    """
    st.subheader(f"Atlas Biodiversité AURA - Répartition : {species_name}")
    # --- Début du Code pour Atlas Biodiv AURA ---
    # ÉTAPE 1: Obtenir l'ID de l'espèce pour l'Atlas.
    # Ceci est la partie la plus complexe et non triviale.
    # species_id_on_atlas = find_species_id_on_atlas(species_name) # Fonction à créer

    # Placeholder pour l'ID - à remplacer par une logique dynamique
    species_id_map = {
        "Lamium purpureum": "10"
        # Ajouter d'autres espèces connues ici ou implémenter une recherche dynamique
    }
    species_id_on_atlas = species_id_map.get(species_name)

    if species_id_on_atlas:
        atlas_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/{species_id_on_atlas}"
        st.markdown(f"Lien direct vers l'Atlas AURA : [{atlas_url}]({atlas_url})")
        try:
            # Tenter d'afficher dans un iframe. Vérifier les en-têtes X-Frame-Options du site.
            st.components.v1.iframe(atlas_url, height=500, scrolling=True)
        except Exception as e:
            st.warning(f"Impossible d'afficher l'iframe pour l'Atlas AURA (peut-être bloqué par le site) : {e}")
    else:
        st.warning(f"[Atlas AURA] ID non trouvé pour '{species_name}'. Logique d'obtention d'ID à implémenter.")
    # --- Fin du Code pour Atlas Biodiv AURA ---

# ... (Reste du script app.py) ...
