#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit app : récupération automatisée d’informations botaniques

Auteur : Robin Wojcik (Améten)
Date   : 2025-05-28 (Retour à requests+BeautifulSoup pour FloreAlpes)

Fonctionnement actualisé (v0.5 - Requests pour FloreAlpes)
--------------------------------------------------------------------
* La recherche FloreAlpes utilise requests et BeautifulSoup pour la navigation et l'obtention de l'URL.
  Ceci évite les dépendances lourdes et problèmes potentiels de Selenium/WebDriver.
* Logique d'extraction du lien de la fiche espèce améliorée dans la fonction `florealpes_search`.
* La fonction `scrape_florealpes` utilise requests/BeautifulSoup pour l'extraction depuis l'URL obtenue.
* Les autres modules (InfoFlora, Tela Botanica, OpenObs, Biodiv'AURA) sont inchangés.
"""

from __future__ import annotations

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup, NavigableString, Tag # Ajout pour type checking potentiel
from urllib.parse import quote_plus, urljoin

# Selenium imports sont retirés

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
    Recherche une espèce sur FloreAlpes en utilisant requests et BeautifulSoup
    et retourne l'URL de la page de l'espèce.
    """
    search_url_base = "https://www.florealpes.com/recherche.php"
    params_florealpes = {"chaine": species}
    
    sess = requests.Session()
    sess.headers.update(HEADERS)

    try:
        # Accès initial à la page d'accueil peut aider avec certains cookies/sessions
        index_url = "https://www.florealpes.com/index.php"
        try:
            sess.get(index_url, timeout=10, headers=HEADERS).raise_for_status()
        except requests.RequestException as e:
            st.info(f"[FloreAlpes Requests] Avertissement: Impossible de charger la page d'accueil avant recherche: {e}")

        resp = sess.get(search_url_base, params=params_florealpes, timeout=15)
        resp.raise_for_status()
        current_page_url = resp.url # URL réelle après d'éventuelles redirections

        soup = BeautifulSoup(resp.text, "lxml")

        page_text_lower = resp.text.lower()
        if "aucun résultat à votre requête" in page_text_lower or "pas de résultats trouvés pour cette recherche" in page_text_lower:
            st.info(f"[FloreAlpes Requests] Aucun résultat trouvé pour '{species}' sur FloreAlpes.")
            return None

        # Cas où FloreAlpes redirige directement vers la fiche espèce
        if "fiche_" in current_page_url and ".php" in current_page_url:
            st.info(f"[FloreAlpes Requests] Redirection directe vers la fiche pour '{species}': {current_page_url}")
            return current_page_url

        target_url = None
        normalized_species_input = species.strip().lower()
        
        # Recherche structurée du lien :
        # Les résultats sont souvent dans des <tr> d'une <table>
        # Chaque <tr> pertinente contient le nom de l'espèce (souvent en <i>) et un lien vers la fiche.
        result_rows = soup.select("tr") # Sélection large, puis filtrage
        
        candidate_links = []

        for row in result_rows:
            row_text_lower = row.get_text(strip=True).lower()
            
            if normalized_species_input in row_text_lower:
                # L'espèce est mentionnée, maintenant trouver le lien 'fiche_' dans cette ligne
                link_tag = row.select_one("a[href^='fiche_']")
                if link_tag and link_tag.has_attr('href'):
                    # Vérifier si le nom de l'espèce est bien associé à ce lien (plus précis)
                    # Souvent, le nom scientifique est en italique <i> ou gras <b> près du lien
                    name_elements = row.select("i, b")
                    is_precise_match = False
                    if name_elements:
                        for el in name_elements:
                            if normalized_species_input in el.get_text(strip=True).lower():
                                is_precise_match = True
                                break
                    else: # Si pas de <i> ou <b>, le fait que le nom soit dans row_text_lower est un bon indicateur
                        is_precise_match = True 
                    
                    if is_precise_match:
                        relative_url = link_tag['href']
                        absolute_url = urljoin(current_page_url, relative_url)
                        # Prioriser les liens qui contiennent explicitement le nom ou une partie (ex: fiche_viciasativa.php)
                        if species.split(" ")[0].lower() in relative_url.lower():
                            st.info(f"[FloreAlpes Requests] Lien spécifique trouvé pour '{species}': {absolute_url}")
                            return absolute_url 
                        candidate_links.append(absolute_url) # Ajouter comme candidat

        if candidate_links:
            st.info(f"[FloreAlpes Requests] Utilisation du premier candidat trouvé pour '{species}': {candidate_links[0]}")
            return candidate_links[0]

        # Fallback: si aucune correspondance précise de ligne, prendre le premier lien 'fiche_' global
        # C'était le comportement de la v0.3 et peut fonctionner si un seul résultat principal est retourné
        generic_link_tag = soup.select_one("a[href^='fiche_']")
        if generic_link_tag and generic_link_tag.has_attr('href'):
            relative_url = generic_link_tag['href']
            absolute_url = urljoin(current_page_url, relative_url)
            st.warning(f"[FloreAlpes Requests] Pas de match spécifique pour '{species}'. Utilisation du premier lien 'fiche_' générique: {absolute_url}")
            return absolute_url
            
        st.error(f"[FloreAlpes Requests] Fiche introuvable pour '{species}' après analyse.")
        return None

    except requests.RequestException as e:
        st.error(f"[FloreAlpes Requests] Erreur de requête lors de la recherche FloreAlpes pour '{species}': {e}")
        return None
    except Exception as e:
        st.error(f"[FloreAlpes Requests] Erreur inattendue pendant la recherche FloreAlpes ('{species}'): {e}")
        return None

def scrape_florealpes(url: str) -> tuple[str | None, pd.DataFrame | None]:
    """Extrait l’image principale et le tableau des caractéristiques."""
    soup = fetch_html(url) 
    if soup is None:
        return None, None
    
    img_url = None
    # Sélecteurs pour l'image, du plus spécifique au plus général
    # urljoin utilise l'URL de la page actuelle ('url') comme base pour les chemins relatifs.
    image_selectors = [
        "table.fiche img[src$='.jpg']", # Image dans la table 'fiche' (souvent principale)
        ".flotte-g img[src$='.jpg']", # Classe souvent utilisée pour l'image principale
        "img[src*='/Photos/'][src$='.jpg']", # Images dans un dossier /Photos/
        "a[href$='.jpg'] > img[src$='.jpg']", # Image cliquable vers version plus grande
        "img[alt*='Photo principale'][src$='.jpg']", # Image avec alt text indicatif
        "img[src$='.jpg']" # Fallback général
    ]
    for selector in image_selectors:
        img_tag = soup.select_one(selector)
        if img_tag and img_tag.has_attr('src'):
            img_src = img_tag['src']
            img_url = urljoin(url, img_src)
            break 

    data_tbl = None
    tbl = soup.find("table", class_="fiche") # Le tableau principal des caractéristiques
    
    if not tbl: # Si table.fiche non trouvée, chercher une table alternative
        all_tables = soup.find_all("table")
        for potential_table in all_tables:
            text_content = potential_table.get_text(" ", strip=True).lower()
            keywords = ["famille", "floraison", "habitat", "description", "plante", "caractères"]
            # Compter combien de mots-clés sont présents
            if sum(keyword in text_content for keyword in keywords) >= 2:
                 # Vérifier si la table a des lignes avec 2 cellules (format attribut-valeur)
                 if any(len(tr.select("td")) == 2 for tr in potential_table.select("tr")):
                    tbl = potential_table
                    st.info("[FloreAlpes Scraper] Tableau 'fiche' non trouvé, utilisation d'un tableau alternatif.")
                    break
    
    if tbl:
        rows = []
        for tr_element in tbl.find_all("tr", recursive=False): # Direct children tr
            # recursive=False peut être trop restrictif si la structure a des tbody
            # Si cela ne fonctionne pas, utiliser tbl.select("tr")
            # cells = tr_element.find_all("td", recursive=False)
            # Préférer select pour plus de flexibilité avec les structures HTML variables
            cells = tr_element.select("td")
            
            if len(cells) == 2:
                # Nettoyer le texte des balises <script> ou <style> si elles existent dans les <td>
                attribute = ' '.join(string for string in cells[0].strings if not isinstance(string, (NavigableString)) or string.parent.name not in ['script', 'style'])
                value = ' '.join(string for string in cells[1].strings if not isinstance(string, (NavigableString)) or string.parent.name not in ['script', 'style'])
                
                attribute = attribute.strip()
                value = value.strip()

                if attribute: 
                     rows.append([attribute, value])
        
        if rows:
            data_tbl = pd.DataFrame(rows, columns=["Attribut", "Valeur"])
            data_tbl = data_tbl[data_tbl["Attribut"].str.strip().astype(bool)]
            if data_tbl.empty:
                data_tbl = None # DataFrame vide après nettoyage n'est pas utile
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
    except ValueError as e: 
        resp_text = response.text if 'response' in locals() and hasattr(response, 'text') else "N/A"
        st.warning(f"[Tela Botanica Debug] Erreur décodage JSON API eFlore pour '{species}': {e}. Réponse: {resp_text[:200]}")
        return None


def get_taxref_cd_ref(species_name: str) -> str | None:
    """Interroge l'API TaxRef pour récupérer le CD_REF (id TaxRef)."""
    taxref_api_url = "https://taxref.mnhn.fr/api/taxa/search"
    params = {
        "scientificNames": species_name,
        "territories": "fr",
        "page": 1,
        "size": 10 
    }
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        response = s.get(taxref_api_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data and "_embedded" in data and "taxa" in data["_embedded"] and data["_embedded"]["taxa"]:
            taxa_list = data["_embedded"]["taxa"]
            normalized_species_name = species_name.strip().lower()
            for taxon in taxa_list:
                if taxon.get("scientificName", "").strip().lower() == normalized_species_name:
                    cd_ref = taxon.get("id")
                    if cd_ref: return str(cd_ref)
            if taxa_list:
                first_taxon = taxa_list[0]
                st.info(f"[TaxRef] '{species_name}' non trouvé exactement. Utilisation de '{first_taxon.get('scientificName')}' (CD_REF: {first_taxon.get('id')}).")
                cd_ref = first_taxon.get("id")
                if cd_ref: return str(cd_ref)
            return None
        return None
    except requests.RequestException as e:
        st.warning(f"[TaxRef API] Erreur de requête pour '{species_name}': {e}")
        return None
    except ValueError as e: 
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
        st.warning(f"[OpenObs] CD_REF non trouvé pour '{species}'. Tentative avec l'ancienne URL OpenObs.")
        old_iframe_url = f"https://openobs.mnhn.fr/map.html?sp={quote_plus(species)}"
        return (
            f"<p style='color: orange; border: 1px solid orange; padding: 5px; border-radius: 3px;'>"
            f"Avertissement : L'identifiant TaxRef (CD_REF) pour '{species}' n'a pas pu être récupéré. "
            f"La carte OpenObs ci-dessous est basée sur une recherche par nom (peut être moins précise ou obsolète).</p>"
            f"<iframe src='{old_iframe_url}' width='100%' height='100%' frameborder='0' style='min-height: 400px;'></iframe>"
        )


def biodivaura_url(species: str) -> str:
    """Construit l'URL pour la page de l'espèce sur Biodiv'AURA Atlas, en utilisant le CD_REF si possible."""
    cd_ref = get_taxref_cd_ref(species)
    if cd_ref:
        direct_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/{cd_ref}"
        return direct_url
    else:
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
        "L'intégration directe de Google Keep via `iframe` est généralement restreinte. Un lien direct est fourni :"
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
    "Liste d’espèces", placeholder="Lamium purpureum\nTrifolium alpinum\nVicia sativa", height=180
)

if st.button("Lancer la recherche", type="primary") and input_txt.strip():
    species_list = [s.strip() for s in input_txt.splitlines() if s.strip()]

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
            st.markdown("##### FloreAlpes")
            with st.spinner(f"Recherche de '{sp}' sur FloreAlpes (via requests)..."):
                url_fa = florealpes_search(sp) 
            
            if url_fa:
                st.markdown(f"**FloreAlpes** : [Fiche complète]({url_fa})")
                with st.spinner(f"Extraction des données FloreAlpes pour '{sp}'..."):
                    img, tbl = scrape_florealpes(url_fa)
                
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
            url_ba_val = biodivaura_url(sp)
            st.markdown(f"**Biodiv'AURA** : [Accéder à l’atlas]({url_ba_val})")
            st.components.v1.iframe(src=url_ba_val, height=600)
        
        st.markdown("---")

else:
    st.info("Saisissez au moins une espèce pour démarrer la recherche.")
