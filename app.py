import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib.parse
import streamlit.components.v1 as components

# Configuration de l'application
st.set_page_config(page_title="Recherche automatisée de fiches espèces", layout="wide")

# Titre principal
st.title("Recherche automatisée de fiches espèces")

# Saisie des espèces via une zone de texte
st.sidebar.header("Entrée des espèces")
species_input = st.sidebar.text_area(
    "Entrez les noms d'espèces (une par ligne)", height=200
)

# Dictionnaires d'identifiants pour Atlas AuRA et Tela Botanica
atlas_ids = {
    "Lamium purpureum": "10",
    # Ajouter d'autres espèces ici
}
tela_ids = {
    "Lamium purpureum": "37538",
    # Ajouter d'autres espèces ici
}

# Bouton de lancement
if st.sidebar.button("Lancer la recherche"):
    # Préparation de la liste d'espèces
    species_list = [s.strip() for s in species_input.splitlines() if s.strip()]
    
    for species in species_list:
        st.header(species)
        
        # Construction des slugs et URL
        slug = species.lower().replace(" ", "-")
        florealpes_url = f"https://www.florealpes.com/fiche_{slug}.php"
        atlas_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/{atlas_ids.get(species, '')}"
        tela_url = f"https://www.tela-botanica.org/bdtfx-nn-{tela_ids.get(species, '')}-synthese"
        infoflora_url = f"https://www.infoflora.ch/fr/flore/{slug}.html"
        openobs_url = f"https://openobs.mnhn.fr/#/?species={urllib.parse.quote_plus(species)}"
        
        # Affichage des liens
        st.markdown(f"- [Fiche FloreAlpes]({florealpes_url})")
        st.markdown(f"- [Atlas AuRA]({atlas_url})")
        st.markdown(f"- [Tela Botanica]({tela_url})")
        st.markdown(f"- [InfoFlora]({infoflora_url})")
        
        # Scraping de l'image sur FloreAlpes
        try:
            resp = requests.get(florealpes_url, timeout=10)
            soup = BeautifulSoup(resp.content, "html.parser")
            img = soup.find("img", {"class": "ficheimage"})
            if img and img.get("src"):
                img_url = urllib.parse.urljoin(florealpes_url, img["src"])
                st.image(img_url, caption="Image extraite de FloreAlpes", use_column_width=True)
        except Exception as e:
            st.write(f"Échec du scraping FloreAlpes : {e}")
        
        # Encadré de répartition via OpenObs
        st.subheader("Répartition (OpenObs)")
        components.iframe(openobs_url, height=400)
        
        # Encadré d'écologie via Atlas AuRA
        st.subheader("Écologie (Atlas AuRA)")
        components.iframe(atlas_url, height=400)
