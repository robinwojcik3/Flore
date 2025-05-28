#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit app : récupération automatisée d’informations botaniques

Auteur : Robin Wojcik (Améten)
Date   : 2025-05-28 (MàJ Selenium pour FloreAlpes)

Fonctionnement actualisé (v0.4 - Intégration Selenium pour FloreAlpes)
--------------------------------------------------------------------
* La recherche FloreAlpes utilise Selenium pour la navigation et l'obtention de l'URL de la fiche espèce.
  Cela simule la navigation utilisateur via la page d'accueil et la soumission du champ `chaine`.
* La fonction `scrape_florealpes` utilise ensuite cette URL avec requests/BeautifulSoup pour l'extraction.
* La carte OpenObs (si CD_REF trouvé) est affichée sur la page principale des résultats par espèce.
* Biodiv'AURA Atlas utilise désormais le CD_REF de TaxRef si disponible pour un accès direct.
* Correction de la graphie "Biodiv'RA" en "Biodiv'AURA".
* Le reste du workflow (InfoFlora, Tela Botanica) est inchangé.
"""

from __future__ import annotations

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin

# Selenium imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions

# -----------------------------------------------------------------------------
# Configuration globale
# -----------------------------------------------------------------------------

st.set_page_config(page_title="Auto-scraper espèces", layout="wide", page_icon="🌿")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# -----------------------------------------------------------------------------
# Fonctions utilitaires
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

@st.cache_data(show_spinner=False, ttl=86_400)
def florealpes_search(species: str) -> str | None:
    """
    Recherche une espèce sur FloreAlpes en utilisant Selenium pour naviguer
    et retourne l'URL de la page de l'espèce.
    """
    options = ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("window-size=1920,1080")
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")

    driver = None
    try:
        # Assumes chromedriver is in PATH. For robust deployment, consider:
        # from selenium.webdriver.chrome.service import Service as ChromeService
        # from webdriver_manager.chrome import ChromeDriverManager
        # driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        driver = webdriver.Chrome(options=options)

        driver.get("https://www.florealpes.com/")
        
        search_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='chaine'], input[id='chaine']"))
        )
        search_input.clear()
        search_input.send_keys(species)

        try:
            ok_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='OK'] | //button[contains(text(),'OK')] | //input[@value='OK']"))
            )
            ok_button.click()
        except TimeoutException:
            try:
                search_input.submit() # Fallback: submit form
            except Exception as e_submit:
                st.warning(f"[FloreAlpes Selenium] Impossible de trouver/cliquer bouton OK et soumission échouée pour '{species}': {e_submit}")
                if driver: driver.quit()
                return None
        
        WebDriverWait(driver, 15).until(EC.url_contains("recherche.php"))

        page_text_lower = driver.page_source.lower()
        if "aucun résultat à votre requête" in page_text_lower or "pas de résultats" in page_text_lower:
            st.info(f"[FloreAlpes Selenium] Aucun résultat trouvé pour '{species}' sur FloreAlpes.")
            if driver: driver.quit()
            return None

        target_url = None
        normalized_species_input = species.strip().lower()

        try:
            # Prioritize rows containing the species name
            result_rows = driver.find_elements(By.XPATH, "//table//tr[.//a[contains(@href, 'fiche_')]]")
            if not result_rows:
                 result_rows = driver.find_elements(By.XPATH, "//tr[.//a[contains(@href, 'fiche_')]]")

            for row in result_rows:
                row_text_lower = ""
                try:
                    row_text_lower = row.text.lower()
                except StaleElementReferenceException: # Element might disappear
                    continue 
                
                if normalized_species_input in row_text_lower:
                    try:
                        link_element = row.find_element(By.XPATH, ".//a[contains(@href, 'fiche_')]")
                        href = link_element.get_attribute('href')
                        if href:
                            target_url = urljoin("https://www.florealpes.com/", href)
                            break 
                    except NoSuchElementException:
                        continue
            if target_url:
                if driver: driver.quit()
                return target_url
        except Exception as e_complex_find:
            st.info(f"[FloreAlpes Selenium] Erreur pendant la recherche de lien complexe pour '{species}': {e_complex_find}. Essai méthodes alternatives.")

        # Fallback 1: Simple CSS selector (original Streamlit app v0.3 approach, but with Selenium)
        if not target_url:
            try:
                link_tag = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[href^='fiche_'][href$='.php']")) 
                )
                href = link_tag.get_attribute('href')
                if href:
                    target_url = urljoin("https://www.florealpes.com/", href)
                    st.info(f"[FloreAlpes Selenium] Utilisation du sélecteur CSS simple (fallback) pour '{species}'.")
                    if driver: driver.quit()
                    return target_url
            except TimeoutException:
                st.info(f"[FloreAlpes Selenium] Sélecteur CSS simple (fallback) n'a pas trouvé de lien pour '{species}'.")

        # Fallback 2: First 'fiche_' link available if any other method failed
        if not target_url:
            all_fiche_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'fiche_')]")
            if all_fiche_links:
                href = all_fiche_links[0].get_attribute('href')
                if href:
                    target_url = urljoin("https://www.florealpes.com/", href)
                    st.warning(f"[FloreAlpes Selenium] Utilisation du premier lien 'fiche_' disponible (dernier recours) pour '{species}'.")
                    if driver: driver.quit()
                    return target_url
        
        st.warning(f"[FloreAlpes Selenium] Aucun lien de fiche approprié trouvé pour '{species}' après toutes les tentatives.")
        if driver: driver.quit()
        return None

    except TimeoutException as e:
        st.warning(f"[FloreAlpes Selenium] Timeout lors de la recherche de '{species}': {e}")
        return None # driver.quit() will be called in finally
    except NoSuchElementException as e:
        st.warning(f"[FloreAlpes Selenium] Élément non trouvé lors de la recherche de '{species}': {e}")
        return None
    except WebDriverException as e:
        st.error(f"[FloreAlpes Selenium] Erreur WebDriver pour '{species}': {e}. Vérifiez l'installation/PATH de ChromeDriver.")
        return None
    except Exception as e:
        st.error(f"[FloreAlpes Selenium] Erreur inattendue pour '{species}': {e}")
        return None
    finally:
        if driver:
            driver.quit()


def scrape_florealpes(url: str) -> tuple[str | None, pd.DataFrame | None]:
    """Extrait l’image principale et le tableau des caractéristiques."""
    soup = fetch_html(url)
    if soup is None:
        return None, None
    
    img_url = None
    # Try to find image within the main content area first
    main_content_img = soup.select_one(".page-content img[src$='.jpg'], .content img[src$='.jpg']")
    if main_content_img and main_content_img.has_attr('src'):
        img_src_relative = main_content_img['src']
        img_url = urljoin(url, img_src_relative) # Use current page URL as base for relative links
    else: # Fallback to broader search
        img_tag = soup.select_one("a[href$='.jpg'] img") or soup.select_one("img[src$='.jpg']")
        if img_tag and img_tag.has_attr('src'):
            img_src_relative = img_tag['src']
            img_url = urljoin("https://www.florealpes.com/", img_src_relative) # Fallback base

    data_tbl = None
    # Updated selector for table to be more specific if possible, or keep general one
    tbl = soup.find("table", class_="fiche") # Assuming 'fiche' is the correct class
    if not tbl: # Fallback if 'fiche' class table not found
        tbl = soup.find("table") # More general table search, might need refinement

    if tbl:
        rows = []
        for tr in tbl.select("tr"):
            cells = tr.select("td")
            if len(cells) == 2: # Expecting two cells: Attribut, Valeur
                attribute = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if attribute: # Only add row if attribute is not empty
                     rows.append([attribute, value])
        
        if rows:
            data_tbl = pd.DataFrame(rows, columns=["Attribut", "Valeur"])
            # Clean up empty rows that might have been parsed if attribute was initially present but value made it look empty
            data_tbl = data_tbl[data_tbl["Attribut"].str.strip().astype(bool)]
    return img_url, data_tbl


def infoflora_url(species: str) -> str:
    slug = species.lower().replace(" ", "-")
    return f"https://www.infoflora.ch/fr/flore/{slug}.html"


def tela_botanica_url(species: str) -> str | None:
    """Interroge l’API eFlore pour récupérer l’identifiant num_nomen."""
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
    except ValueError as e: # Catch JSON decoding errors
        resp_text = response.text if 'response' in locals() and hasattr(response, 'text') else "N/A"
        st.warning(f"[Tela Botanica Debug] Erreur décodage JSON API eFlore pour '{species}': {e}. Réponse: {resp_text[:200]}")
        return None


def get_taxref_cd_ref(species_name: str) -> str | None:
    """Interroge l'API TaxRef pour récupérer le CD_REF (id TaxRef)."""
    taxref_api_url = "https://taxref.mnhn.fr/api/taxa/search"
    params = {
        "scientificNames": species_name,
        "territories": "fr", # Search for taxa present in France
        "page": 1,
        "size": 10 # Increased size to better find exact matches among variants
    }
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        response = s.get(taxref_api_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data and "_embedded" in data and "taxa" in data["_embedded"] and data["_embedded"]["taxa"]:
            taxa_list = data["_embedded"]["taxa"]
            
            # Try to find an exact match for scientificName (case-insensitive)
            normalized_species_name = species_name.strip().lower()
            for taxon in taxa_list:
                if taxon.get("scientificName", "").strip().lower() == normalized_species_name:
                    cd_ref = taxon.get("id")
                    if cd_ref: return str(cd_ref)
            
            # If no exact match, take the first result if it's reasonably confident (e.g. check rank)
            # For now, if no exact match, we'll take the first one if list is not empty
            if taxa_list:
                first_taxon = taxa_list[0]
                # Optionally, add more checks here, e.g., on taxon rank if important
                # st.info(f"[TaxRef] '{species_name}' non trouvé exactement. Utilisation de '{first_taxon.get('scientificName')}' (CD_REF: {first_taxon.get('id')}) comme meilleur candidat.")
                cd_ref = first_taxon.get("id")
                if cd_ref: return str(cd_ref)
            return None
        return None
    except requests.RequestException as e:
        st.warning(f"[TaxRef API] Erreur de requête pour '{species_name}': {e}")
        return None
    except ValueError as e: # Catch JSON decoding errors
        resp_text = response.text if 'response' in locals() and hasattr(response, 'text') else "N/A"
        st.warning(f"[TaxRef API] Erreur décodage JSON pour '{species_name}': {e}. Réponse: {resp_text[:200]}")
        return None


def openobs_embed(species: str) -> str:
    """HTML pour afficher la carte OpenObs dans un iframe en utilisant le CD_REF."""
    cd_ref = get_taxref_cd_ref(species)
    if cd_ref:
        iframe_url = f"https://openobs.mnhn.fr/redirect/inpn/taxa/{cd_ref}?view=map"
        return f"<iframe src='{iframe_url}' width='100%' height='100%' frameborder='0' style='min-height: 450px;'></iframe>"
    else:
        # Fallback to old method if CD_REF not found
        st.warning(f"[OpenObs] CD_REF non trouvé pour '{species}'. Tentative avec l'ancienne URL OpenObs (peut être imprécis/obsolète).")
        old_iframe_url = f"https://openobs.mnhn.fr/map.html?sp={quote_plus(species)}"
        return (
            f"<p style='color: orange; border: 1px solid orange; padding: 5px; border-radius: 3px;'>"
            f"Avertissement : L'identifiant TaxRef (CD_REF) pour '{species}' n'a pas pu être récupéré via l'API TaxRef. "
            f"La carte OpenObs ci-dessous est basée sur une recherche par nom, ce qui peut être moins précis ou obsolète.</p>"
            f"<iframe src='{old_iframe_url}' width='100%' height='100%' frameborder='0' style='min-height: 400px;'></iframe>"
        )


def biodivaura_url(species: str) -> str:
    """Construit l'URL pour la page de l'espèce sur Biodiv'AURA Atlas, en utilisant le CD_REF si possible."""
    cd_ref = get_taxref_cd_ref(species)
    if cd_ref:
        direct_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/{cd_ref}"
        return direct_url
    else:
        # Fallback to search URL if CD_REF not found
        st.warning(f"[Biodiv'AURA] CD_REF non trouvé pour '{species}'. Utilisation de l'URL de recherche.")
        search_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/recherche?keyword={quote_plus(species)}"
        return search_url

# -----------------------------------------------------------------------------
# Interface utilisateur
# -----------------------------------------------------------------------------

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
    st.title("Recherche automatisée d’informations sur les espèces")

st.markdown("---")

st.markdown("Saisissez les noms scientifiques (un par ligne) puis lancez la recherche.")

input_txt = st.text_area(
    "Liste d’espèces", placeholder="Lamium purpureum\nTrifolium alpinum", height=180
)

if st.button("Lancer la recherche", type="primary") and input_txt.strip():
    species_list = [s.strip() for s in input_txt.splitlines() if s.strip()]

    # Global session for requests to reuse connections
    req_session = requests.Session()

    for sp in species_list:
        st.subheader(sp)
        st.markdown("---")

        col_map, col_intro = st.columns([2, 1]) # Adjusted column ratio

        with col_map:
            st.markdown("##### Carte de répartition (OpenObs)")
            html_openobs_main = openobs_embed(sp) # cd_ref is fetched inside
            st.components.v1.html(html_openobs_main, height=465)

        with col_intro:
            st.markdown("##### Sources d'Information")
            st.info("Les informations détaillées pour cette espèce sont disponibles dans les onglets ci-dessous. Les éventuels messages (erreurs, avertissements) des APIs s'affichent au fur et à mesure des appels.")
        
        st.markdown("---") # Separator before tabs

        tab_names = ["FloreAlpes", "InfoFlora", "Tela Botanica", "Biodiv'AURA"]
        tab_fa, tab_if, tab_tb, tab_ba = st.tabs(tab_names)

        with tab_fa:
            st.markdown("##### FloreAlpes")
            with st.spinner(f"Recherche de '{sp}' sur FloreAlpes via Selenium..."):
                url_fa = florealpes_search(sp) # Uses Selenium
            
            if url_fa:
                st.markdown(f"**FloreAlpes** : [Fiche complète]({url_fa})")
                with st.spinner(f"Extraction des données FloreAlpes pour '{sp}'..."):
                    img, tbl = scrape_florealpes(url_fa) # Uses requests+bs4
                
                if img:
                    st.image(img, caption=f"{sp} (FloreAlpes)", use_column_width=True)
                else:
                    st.warning("Image non trouvée sur FloreAlpes.")
                
                if tbl is not None and not tbl.empty:
                    st.dataframe(tbl, hide_index=True)
                elif tbl is not None and tbl.empty: # Table was found but had no data rows
                    st.info("Tableau des caractéristiques trouvé mais vide sur FloreAlpes.")
                else: # tbl is None, meaning table not found
                    st.warning("Tableau des caractéristiques non trouvé sur FloreAlpes.")
            else:
                st.error(f"Fiche introuvable sur FloreAlpes pour '{sp}' (après recherche Selenium).")

        with tab_if:
            st.markdown("##### InfoFlora")
            url_if = infoflora_url(sp)
            st.markdown(f"**InfoFlora** : [Fiche complète]({url_if})")
            st.components.v1.iframe(src=url_if, height=600)

        with tab_tb:
            st.markdown("##### Tela Botanica (eFlore)")
            url_tb = tela_botanica_url(sp)
            if url_tb:
                st.markdown(f"**Tela Botanica** : [Synthèse eFlore]({url_tb})")
                st.components.v1.iframe(src=url_tb, height=600)
            else:
                st.warning(f"Aucune correspondance via l’API eFlore de Tela Botanica pour '{sp}'.")

        with tab_ba:
            st.markdown("##### Biodiv'AURA Atlas")
            url_ba_val = biodivaura_url(sp) # cd_ref is fetched inside
            st.markdown(f"**Biodiv'AURA** : [Accéder à l’atlas]({url_ba_val})")
            st.components.v1.iframe(src=url_ba_val, height=600)
        
        st.markdown("---") # Separator after each species block

else:
    st.info("Saisissez au moins une espèce pour démarrer la recherche.")
