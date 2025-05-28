#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit app : récupération automatisée d’informations botaniques

Auteur : Robin Wojcik (Améten)
Date   : 2025-05-28 (FloreAlpes - logique "première option" affinée)

Fonctionnement actualisé (v0.7 - FloreAlpes "première option" robuste)
--------------------------------------------------------------------
* FloreAlpes: Logique améliorée pour trouver le lien de la "première option"
  sur la page de résultats, en parcourant les lignes de la table de résultats
  plutôt qu'en se fiant à des sélecteurs :nth-child stricts.
* Nettoyage mineur de l'extraction de texte dans scrape_florealpes.
* Les autres modules restent inchangés.
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
    session = requests.Session()
    session.headers.update(HEADERS)
    base_url = "https://www.florealpes.com/"
    current_page_url_for_error_reporting = base_url 

    try:
        try:
            session.get(base_url, timeout=10).raise_for_status()
        except requests.RequestException:
            # Pas critique si la page d'accueil ne charge pas, le message est déjà géré par st.info/warning si besoin
            pass

        search_url = urljoin(base_url, "recherche.php")
        search_params = {"chaine": species}
        results_response = session.get(search_url, params=search_params, timeout=15)
        results_response.raise_for_status()
        
        current_page_url_for_error_reporting = results_response.url
        soup = BeautifulSoup(results_response.text, "lxml")

        page_text_lower = results_response.text.lower()
        no_results_messages = [
            "aucun résultat à votre requête", 
            "pas de résultats trouvés pour cette recherche", 
            "aucun taxon ne correspond à votre recherche"
        ]
        if any(msg in page_text_lower for msg in no_results_messages):
            st.info(f"[FloreAlpes] Aucun résultat trouvé pour '{species}'.")
            return None

        link_tag = None
        
        # Tentative 1: Trouver la table des résultats et le lien de la première option pertinente
        # Cible: #principal div.conteneur_tab table.resultats (ou table générique si non trouvée)
        results_table_container = soup.select_one("#principal div.conteneur_tab")
        results_table = None
        if results_table_container:
            results_table = results_table_container.select_one("table.resultats")
            if not results_table: # Fallback si table.resultats n'est pas trouvée dans le conteneur
                results_table = results_table_container.select_one("table")
        
        if results_table:
            # Parcourir les lignes (<tbody><tr> ou <tr> directes)
            # et prendre le premier lien 'fiche_' dans un 'td.symb'
            # Ceci correspond à la "première option"
            data_rows = results_table.select("tbody > tr, tr") 
            for row in data_rows:
                link_in_row = row.select_one("td.symb > a[href^='fiche_']")
                if link_in_row:
                    link_tag = link_in_row
                    st.info(f"[FloreAlpes] Lien de la 'première option' trouvé pour '{species}'.")
                    break 
        
        if link_tag and link_tag.has_attr('href'):
            relative_url = link_tag['href']
            absolute_url = urljoin(results_response.url, relative_url)
            return absolute_url
        else:
            # Fallback 1: l'URL actuelle est déjà une fiche (redirection directe)
            if "fiche_" in results_response.url and ".php" in results_response.url:
                st.info(f"[FloreAlpes] URL actuelle est déjà une fiche (fallback 1) pour '{species}': {results_response.url}")
                return results_response.url

            # Fallback 2: premier lien 'fiche_' générique sur la page
            generic_link_tag = soup.select_one("a[href^='fiche_']")
            if generic_link_tag and generic_link_tag.has_attr('href'):
                relative_url = generic_link_tag['href']
                absolute_url = urljoin(results_response.url, relative_url)
                st.warning(f"[FloreAlpes] Logique 'première option' échouée. Utilisation du 1er lien 'fiche_' générique (fallback 2) pour '{species}': {absolute_url}")
                return absolute_url
            
            st.error(f"[FloreAlpes] Impossible de trouver le lien de la fiche pour '{species}'.")
            return None

    except requests.RequestException as e:
        st.error(f"[FloreAlpes] Erreur de requête pour '{species}': {e}")
        return None
    except Exception as e:
        st.error(f"[FloreAlpes] Erreur inattendue pour '{species}': {e} (URL: {current_page_url_for_error_reporting})")
        return None

def scrape_florealpes(url: str) -> tuple[str | None, pd.DataFrame | None]:
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
        for tr_element in tbl.select("tr"):
            cells = tr_element.select("td")
            if len(cells) == 2:
                # Utiliser get_text() pour une extraction plus simple et robuste du texte
                attribute = cells[0].get_text(separator=' ', strip=True)
                value = cells[1].get_text(separator=' ', strip=True)
                
                if attribute: 
                     rows.append([attribute, value])
        
        if rows:
            data_tbl = pd.DataFrame(rows, columns=["Attribut", "Valeur"])
            # S'assurer que les lignes avec attributs vides après strip sont bien retirées
            data_tbl = data_tbl[data_tbl["Attribut"].str.strip().astype(bool)]
            if data_tbl.empty: # Si le DataFrame est vide après nettoyage
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
