#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit app : récupération automatisée d'informations botaniques avec Selenium

Auteur : Robin Wojcik (Améten)
Date   : 2025-05-28

Fonctionnement actualisé (v0.4)
--------------------------------
* FloreAlpes utilise désormais Selenium pour naviguer automatiquement
* Le reste du workflow (InfoFlora, Tela Botanica) est inchangé
"""

from __future__ import annotations

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import os

# -----------------------------------------------------------------------------
# Configuration globale
# -----------------------------------------------------------------------------

st.set_page_config(page_title="Auto-scraper espèces", layout="wide", page_icon="🌿")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# -----------------------------------------------------------------------------
# Configuration Selenium
# -----------------------------------------------------------------------------

@st.cache_resource
def get_chrome_driver():
    """Configure et retourne un webdriver Chrome partagé."""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # Mode headless pour Streamlit
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception as e:
        st.error(f"Erreur lors de l'initialisation du driver Chrome: {e}")
        st.info("Assurez-vous que Chrome et ChromeDriver sont installés et compatibles.")
        return None

# -----------------------------------------------------------------------------
# Fonctions FloreAlpes avec Selenium
# -----------------------------------------------------------------------------

def florealpes_search_selenium(species: str, driver) -> str | None:
    """Recherche une espèce sur FloreAlpes via Selenium et retourne l'URL de la fiche."""
    try:
        # Accéder à la page d'accueil
        driver.get("https://www.florealpes.com/")
        time.sleep(2)
        
        # Trouver et remplir le champ de recherche
        try:
            search_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='chaine'], input[id='chaine']"))
            )
            search_input.clear()
            search_input.send_keys(species)
            
            # Cliquer sur le bouton OK
            ok_button = driver.find_element(By.XPATH, "//input[@value='OK']")
            ok_button.click()
            
        except Exception as e:
            st.warning(f"Erreur lors de la recherche FloreAlpes pour '{species}': {e}")
            return None
        
        # Attendre les résultats
        time.sleep(3)
        
        # Vérifier s'il y a des résultats
        try:
            # Chercher les liens "Fiche plante..."
            fiche_links = driver.find_elements(By.XPATH, "//a[contains(text(), 'Fiche plante')]")
            
            if not fiche_links:
                return None
            
            # Chercher le lien qui correspond exactement à l'espèce
            for fiche_link in fiche_links:
                try:
                    parent_row = fiche_link
                    while parent_row.tag_name != 'tr' and parent_row.tag_name != 'body':
                        parent_row = parent_row.find_element(By.XPATH, "./..")
                    
                    row_text = parent_row.text.lower()
                    
                    # Vérifier si cette ligne contient le nom recherché
                    if species.lower() in row_text:
                        # Cliquer sur le lien
                        fiche_link.click()
                        time.sleep(2)
                        # Retourner l'URL de la page
                        return driver.current_url
                
                except Exception:
                    continue
            
            # Si aucune correspondance exacte, prendre le premier résultat
            if fiche_links:
                fiche_links[0].click()
                time.sleep(2)
                return driver.current_url
            
        except Exception as e:
            st.warning(f"Erreur lors de l'analyse des résultats FloreAlpes: {e}")
            return None
    
    except Exception as e:
        st.error(f"Erreur générale FloreAlpes: {e}")
        return None

def scrape_florealpes_selenium(driver) -> tuple[str | None, pd.DataFrame | None]:
    """Extrait l'image principale et le tableau des caractéristiques depuis la page actuelle."""
    try:
        # Récupérer le HTML de la page
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "lxml")
        
        # Extraire l'image principale
        img_tag = soup.select_one("a[href$='.jpg'] img") or soup.select_one("img[src$='.jpg']")
        img_url = None
        if img_tag and img_tag.has_attr('src'):
            img_src_relative = img_tag['src']
            img_url = urljoin("https://www.florealpes.com/", img_src_relative)
        
        # Extraire le tableau des caractéristiques
        data_tbl = None
        tbl = soup.find("table", class_="fiche")
        if tbl:
            rows = [
                [td.get_text(strip=True) for td in tr.select("td")]
                for tr in tbl.select("tr")
                if len(tr.select("td")) == 2
            ]
            if rows:
                data_tbl = pd.DataFrame(rows, columns=["Attribut", "Valeur"])
        
        return img_url, data_tbl
    
    except Exception as e:
        st.error(f"Erreur lors de l'extraction des données FloreAlpes: {e}")
        return None, None

# -----------------------------------------------------------------------------
# Fonctions utilitaires (inchangées)
# -----------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=86_400)
def fetch_html(url: str, session: requests.Session | None = None) -> BeautifulSoup | None:
    """Télécharge une page et renvoie son contenu analysé par BeautifulSoup."""
    sess = session or requests.Session()
    sess.headers.update(HEADERS)
    try:
        r = sess.get(url, timeout=15)
        r.raise_for_status()
        return BeautifulSoup(r.text, "lxml")
    except requests.RequestException as e:
        st.warning(f"Erreur lors du téléchargement de {url}: {e}")
        return None

def infoflora_url(species: str) -> str:
    slug = species.lower().replace(" ", "-")
    return f"https://www.infoflora.ch/fr/flore/{slug}.html"

def tela_botanica_url(species: str) -> str | None:
    """Interroge l'API eFlore pour récupérer l'identifiant num_nomen."""
    api_url = (
        "https://api.tela-botanica.org/service:eflore:0.1/" "names:search?mode=exact&taxon="
        f"{quote_plus(species)}"
    )
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        response = s.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data: return None
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            nn = data[0].get("num_nomen")
            return f"https://www.tela-botanica.org/bdtfx-nn-{nn}-synthese" if nn else None
        else:
            st.warning(f"[Tela Botanica Debug] Réponse API eFlore inattendue pour '{species}': {data}")
            return None
    except requests.RequestException as e:
        st.warning(f"[Tela Botanica Debug] Erreur RequestException API eFlore pour '{species}': {e}")
        return None
    except ValueError as e:
        st.warning(f"[Tela Botanica Debug] Erreur décodage JSON API eFlore pour '{species}': {e}")
        return None

def get_taxref_cd_ref(species_name: str) -> str | None:
    """Interroge l'API TaxRef pour récupérer le CD_REF (id TaxRef)."""
    taxref_api_url = "https://taxref.mnhn.fr/api/taxa/search"
    params = {
        "scientificNames": species_name,
        "territories": "fr",
        "page": 1,
        "size": 5
    }
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        response = s.get(taxref_api_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data and "_embedded" in data and "taxa" in data["_embedded"] and data["_embedded"]["taxa"]:
            found_taxon = None
            normalized_species_name = species_name.strip().lower()
            for taxon_candidate in data["_embedded"]["taxa"]:
                if taxon_candidate.get("scientificName","").strip().lower() == normalized_species_name:
                    found_taxon = taxon_candidate
                    break
            if not found_taxon:
                found_taxon = data["_embedded"]["taxa"][0]
            cd_ref = found_taxon.get("id")
            if cd_ref:
                return str(cd_ref)
            return None
        return None
    except requests.RequestException:
        return None
    except ValueError:
        return None

def openobs_embed(species: str) -> str:
    """HTML pour afficher la carte OpenObs dans un iframe en utilisant le CD_REF."""
    cd_ref = get_taxref_cd_ref(species)
    if cd_ref:
        iframe_url = f"https://openobs.mnhn.fr/redirect/inpn/taxa/{cd_ref}?view=map"
        return f"<iframe src='{iframe_url}' width='100%' height='100%' frameborder='0' style='min-height: 450px;'></iframe>"
    else:
        old_iframe_url = f"https://openobs.mnhn.fr/map.html?sp={quote_plus(species)}"
        return (
            f"<p style='color: orange; border: 1px solid orange; padding: 5px;'>"
            f"Avertissement : L'identifiant TaxRef (CD_REF) pour '{species}' n'a pas pu être récupéré. "
            f"Tentative d'affichage de la carte OpenObs avec l'ancienne méthode (peut être moins précise ou obsolète).</p>"
            f"<iframe src='{old_iframe_url}' width='100%' height='100%' frameborder='0' style='min-height: 400px;'></iframe>"
        )

def biodivaura_url(species: str) -> str:
    """Construit l'URL pour la page de l'espèce sur Biodiv'AURA Atlas, en utilisant le CD_REF si possible."""
    cd_ref = get_taxref_cd_ref(species)
    if cd_ref:
        direct_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/{cd_ref}"
        return direct_url
    else:
        search_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/recherche?keyword={quote_plus(species)}"
        return search_url

# -----------------------------------------------------------------------------
# Interface utilisateur
# -----------------------------------------------------------------------------

# Section pour la note Google Keep et titre principal
col_keep_section, col_main_title = st.columns([1, 3], gap="large")

with col_keep_section:
    st.markdown("##### Notes de Projet")
    keep_url = "https://keep.google.com/#NOTE/1dHuU90VKwWzZAgoXzTsjNiRp_QgDB1BRCfthK5hH-23Vxb_A86uTPrroczclhg"

    st.markdown(
        "L'intégration directe de Google Keep via `iframe` est généralement restreinte "
        "par les politiques de sécurité de Google. Un lien direct est fourni ci-dessous :"
    )
    
    button_html = f"""
    <a href="{keep_url}" target="_blank" 
       style="display: inline-block; padding: 0.4em 0.8em; margin-top: 0.5em; background-color: #E8E8E8; color: #31333F; 
              text-align: center; text-decoration: none; border-radius: 0.25rem; font-weight: 500;
              border: 1px solid #B0B0B0;">
        📝 Accéder à la note Google Keep
    </a>
    """
    st.markdown(button_html, unsafe_allow_html=True)
    st.caption("La note s'ouvrira dans un nouvel onglet.")

with col_main_title:
    st.title("Recherche automatisée d'informations sur les espèces")

st.markdown("---")

# Avertissement sur Selenium
st.info("""
    **Note importante :** Cette application utilise Selenium pour FloreAlpes. 
    Assurez-vous que Chrome et ChromeDriver sont installés sur votre système.
    La première recherche peut prendre quelques secondes pour initialiser le navigateur.
""")

st.markdown("Saisissez les noms scientifiques (un par ligne) puis lancez la recherche.")

input_txt = st.text_area(
    "Liste d'espèces", placeholder="Lamium purpureum\nTrifolium alpinum", height=180
)

if st.button("Lancer la recherche", type="primary") and input_txt.strip():
    species_list = [s.strip() for s in input_txt.splitlines() if s.strip()]
    
    # Initialiser le driver une seule fois
    driver = get_chrome_driver()
    
    if driver is None:
        st.error("Impossible d'initialiser le driver Chrome. Vérifiez votre installation.")
    else:
        try:
            for sp in species_list:
                st.subheader(sp)
                st.markdown("---")

                col_map, col_intro = st.columns([2, 1])

                with col_map:
                    st.markdown("##### Carte de répartition (OpenObs)")
                    html_openobs_main = openobs_embed(sp)
                    st.components.v1.html(html_openobs_main, height=465)

                with col_intro:
                    st.markdown("##### Sources d'Information")
                    st.info("Les informations détaillées pour cette espèce sont disponibles dans les onglets ci-dessous.")

                st.markdown("---")

                tab_names = ["FloreAlpes", "InfoFlora", "Tela Botanica", "Biodiv'AURA"]
                tab_fa, tab_if, tab_tb, tab_ba = st.tabs(tab_names)

                with tab_fa:
                    with st.spinner("Recherche sur FloreAlpes..."):
                        url_fa = florealpes_search_selenium(sp, driver)
                        
                    if url_fa:
                        st.markdown(f"**FloreAlpes** : [Fiche complète]({url_fa})")
                        img, tbl = scrape_florealpes_selenium(driver)
                        
                        if img:
                            st.image(img, caption=f"{sp} (FloreAlpes)", use_column_width=True)
                        else:
                            st.warning("Image non trouvée sur FloreAlpes.")
                        
                        if tbl is not None and not tbl.empty:
                            st.dataframe(tbl, hide_index=True)
                        elif tbl is not None and tbl.empty:
                            st.info("Tableau des caractéristiques trouvé mais vide sur FloreAlpes.")
                        else:
                            st.warning("Tableau des caractéristiques non trouvé sur FloreAlpes.")
                    else:
                        st.error(f"Fiche introuvable sur FloreAlpes pour '{sp}'.")

                with tab_if:
                    url_if = infoflora_url(sp)
                    st.markdown(f"**InfoFlora** : [Fiche complète]({url_if})")
                    st.components.v1.iframe(src=url_if, height=600)

                with tab_tb:
                    url_tb = tela_botanica_url(sp)
                    if url_tb:
                        st.markdown(f"**Tela Botanica** : [Synthèse eFlore]({url_tb})")
                        st.components.v1.iframe(src=url_tb, height=600)
                    else:
                        st.warning(f"Aucune correspondance via l'API eFlore de Tela Botanica pour '{sp}'.")

                with tab_ba:
                    url_ba_val = biodivaura_url(sp)
                    st.markdown(f"**Biodiv'AURA** : [Accéder à l'atlas]({url_ba_val})")
                    st.components.v1.iframe(src=url_ba_val, height=600)
        
        finally:
            # Fermer le driver à la fin
            try:
                driver.quit()
            except:
                pass

else:
    st.info("Saisissez au moins une espèce pour démarrer la recherche.")
