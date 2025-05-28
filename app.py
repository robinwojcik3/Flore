#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit app : récupération automatisée d’informations botaniques

Auteur : Robin Wojcik (Améten)
Date   : 2025-05-28 (Requests pour FloreAlpes avec sélecteurs précis)

Fonctionnement actualisé (v0.6 - FloreAlpes avec sélecteurs utilisateur)
--------------------------------------------------------------------
* La recherche FloreAlpes (requests+BeautifulSoup) suit les sélecteurs CSS
  spécifiques fournis par l'utilisateur pour identifier la "première option"
  sur la page de résultats.
* Maintien des fallbacks pour la recherche de lien FloreAlpes.
* Les autres modules (InfoFlora, Tela Botanica, OpenObs, Biodiv'AURA) sont inchangés.
"""

from __future__ import annotations

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin

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
    Recherche une espèce sur FloreAlpes (requests+BeautifulSoup) en suivant les instructions
    et sélecteurs spécifiques pour trouver la "première option" de résultat.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    base_url = "https://www.florealpes.com/"
    current_page_url_for_error_reporting = base_url 

    try:
        # 1. Accès optionnel à la page d'accueil
        try:
            session.get(base_url, timeout=10).raise_for_status()
        except requests.RequestException as e:
            st.info(f"[FloreAlpes Requests] Avertissement: Page d'accueil ({base_url}) non chargée: {e}")

        # 2. Soumission de la recherche à recherche.php
        search_url = urljoin(base_url, "recherche.php")
        search_params = {"chaine": species}
        results_response = session.get(search_url, params=search_params, timeout=15)
        results_response.raise_for_status()
        
        current_page_url_for_error_reporting = results_response.url
        soup = BeautifulSoup(results_response.text, "lxml")

        # 3. Vérification "aucun résultat"
        page_text_lower = results_response.text.lower()
        no_results_messages = [
            "aucun résultat à votre requête", 
            "pas de résultats trouvés pour cette recherche", 
            "aucun taxon ne correspond à votre recherche"
        ]
        if any(msg in page_text_lower for msg in no_results_messages):
            st.info(f"[FloreAlpes Requests] Aucun résultat trouvé pour '{species}'.")
            return None

        # 4. Sélection de la "première option" en utilisant les sélecteurs CSS
        link_tag = None
        
        # Priorité aux sélecteurs précis inspirés par l'utilisateur ciblant la première option de résultat.
        # `tr:nth-child(1)` ou `tr:nth-child(2)` peuvent correspondre à la 1ère ligne de données
        # selon la présence d'un <thead> ou si tbody est implicite.
        # Le sélecteur le plus général `#principal div.conteneur_tab table tr td.symb a[href^='fiche_']`
        # trouvera le premier lien de ce type dans la structure attendue.
        
        # Sélecteurs pour le lien <a> de la "première option" (liste ordonnée par priorité/spécificité)
        # Ces sélecteurs tentent de capturer la "première ligne de résultat pertinente"
        selectors_for_first_option = [
            "#principal div.conteneur_tab table > tbody > tr:nth-child(1) > td.symb > a[href^='fiche_']", # Avec tbody explicite, 1er tr de tbody
            "#principal div.conteneur_tab table > tr:nth-child(1) > td.symb > a[href^='fiche_']",       # Sans tbody explicite, 1er tr global
            "#principal div.conteneur_tab table > tbody > tr:nth-child(2) > td.symb > a[href^='fiche_']", # Avec tbody explicite, 2e tr (si 1er est un entête)
            "#principal div.conteneur_tab table > tr:nth-child(2) > td.symb > a[href^='fiche_']",       # Sans tbody explicite, 2e tr global
            "#principal div.conteneur_tab table td.symb a[href^='fiche_']" # Le premier lien dans n'importe quelle ligne de la table spécifiée
        ]
        
        for selector in selectors_for_first_option:
            link_tag = soup.select_one(selector)
            if link_tag:
                st.info(f"[FloreAlpes Requests] Lien trouvé avec sélecteur '{selector}' pour '{species}'.")
                break
        
        if link_tag and link_tag.has_attr('href'):
            relative_url = link_tag['href']
            absolute_url = urljoin(results_response.url, relative_url)
            return absolute_url
        else:
            # Fallback 1: si l'URL actuelle est déjà une fiche (redirection directe)
            if "fiche_" in results_response.url and ".php" in results_response.url:
                st.info(f"[FloreAlpes Requests] Redirection directe vers la fiche (fallback 1) pour '{species}': {results_response.url}")
                return results_response.url

            # Fallback 2: premier lien 'fiche_' générique sur la page
            generic_link_tag = soup.select_one("a[href^='fiche_']")
            if generic_link_tag and generic_link_tag.has_attr('href'):
                relative_url = generic_link_tag['href']
                absolute_url = urljoin(results_response.url, relative_url)
                st.warning(f"[FloreAlpes Requests] Sélecteurs spécifiques non trouvés. Utilisation du 1er lien 'fiche_' générique (fallback 2) pour '{species}': {absolute_url}")
                return absolute_url
            
            st.error(f"[FloreAlpes Requests] Impossible de trouver le lien de la fiche pour '{species}'.")
            return None

    except requests.RequestException as e:
        st.error(f"[FloreAlpes Requests] Erreur requête pour '{species}': {e}")
        return None
    except Exception as e:
        st.error(f"[FloreAlpes Requests] Erreur inattendue pour '{species}': {e} (URL: {current_page_url_for_error_reporting})")
        return None

def scrape_florealpes(url: str) -> tuple[str | None, pd.DataFrame | None]:
    """Extrait l’image principale et le tableau des caractéristiques."""
    soup = fetch_html(url) 
    if soup is None:
        return None, None
    
    img_url = None
    image_selectors = [
        "table.fiche img[src$='.jpg']", 
        ".flotte-g img[src$='.jpg']", 
        "img[src*='/Photos/'][src$='.jpg']",
        "a[href$='.jpg'] > img[src$='.jpg']", 
        "img[alt*='Photo principale'][src$='.jpg']",
        "img[src$='.jpg']" 
    ]
    for selector in image_selectors:
        img_tag = soup.select_one(selector)
        if img_tag and img_tag.has_attr('src'):
            img_src = img_tag['src']
            img_url = urljoin(url, img_src)
            break 

    data_tbl = None
    tbl = soup.find("table", class_="fiche") 
    
    if not tbl: 
        all_tables = soup.find_all("table")
        for potential_table in all_tables:
            text_content = potential_table.get_text(" ", strip=True).lower()
            keywords = ["famille", "floraison", "habitat", "description", "plante", "caractères"]
            if sum(keyword in text_content for keyword in keywords) >= 2:
                 if any(len(tr.select("td")) == 2 for tr in potential_table.select("tr")):
                    tbl = potential_table
                    st.info("[FloreAlpes Scraper] Tableau 'fiche' non trouvé, utilisation d'un tableau alternatif.")
                    break
    
    if tbl:
        rows = []
        for tr_element in tbl.select("tr"): # Utiliser select pour plus de robustesse
            cells = tr_element.select("td")
            if len(cells) == 2:
                attribute_html = cells[0]
                value_html = cells[1]
                
                # Extraire le texte tout en ignorant les balises <script> et <style>
                attribute = ' '.join(attribute_html.find_all(string=True, recursive=True, 
                                                              _self=lambda tag: tag.parent.name not in ['script', 'style'])).strip()
                value = ' '.join(value_html.find_all(string=True, recursive=True,
                                                     _self=lambda tag: tag.parent.name not in ['script', 'style'])).strip()
                
                if attribute: 
                     rows.append([attribute, value])
        
        if rows:
            data_tbl = pd.DataFrame(rows, columns=["Attribut", "Valeur"])
            data_tbl = data_tbl[data_tbl["Attribut"].str.strip().astype(bool)]
            if data_tbl.empty:
                data_tbl = None 
    return img_url, data_tbl


def infoflora_url(species: str) -> str:
    slug = species.lower().replace(" ", "-")
    return f"https://www.infoflora.ch/fr/flore/{slug}.html"


def tela_botanica_url(species: str) -> str | None:
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
            if taxa_list: # Si pas de match exact, prendre le premier de la liste
                first_taxon = taxa_list[0]
                st.info(f"[TaxRef] '{species_name}' non trouvé exactement. Utilisation de '{first_taxon.get('scientificName')}' (CD_REF: {first_taxon.get('id')}).")
                cd_ref = first_taxon.get("id")
                if cd_ref: return str(cd_ref)
            return None # Aucun taxon trouvé
        return None # Pas de section _embedded ou taxa
    except requests.RequestException as e:
        st.warning(f"[TaxRef API] Erreur de requête pour '{species_name}': {e}")
        return None
    except ValueError as e: 
        resp_text = response.text if 'response' in locals() and hasattr(response, 'text') else "N/A"
        st.warning(f"[TaxRef API] Erreur décodage JSON pour '{species_name}': {e}. Réponse: {resp_text[:200]}")
        return None


def openobs_embed(species: str) -> str:
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
            with st.spinner(f"Recherche de '{sp}' sur FloreAlpes..."):
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
