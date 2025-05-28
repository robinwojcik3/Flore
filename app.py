#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit app : récupération automatisée d’informations botaniques

Auteur : Robin Wojcik (Améten)
Date   : 2025-05-28 (v0.8 - Mode debug et raffinements)

Fonctionnement actualisé (v0.8)
--------------------------------
* Mode débogage activable via `?debug=true` dans l'URL pour des logs plus détaillés.
* Logique de scraping pour FloreAlpes (requests+BeautifulSoup) maintenue et commentée.
* Sélecteurs d'images et extraction de tableaux légèrement affinés.
* Abandon complet de Selenium au profit de `requests` pour la portabilité.
* Interface utilisateur et messages d'erreur revus pour plus de clarté.
"""

from __future__ import annotations

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin

# -----------------------------------------------------------------------------
# Configuration globale et Mode Débogage
# -----------------------------------------------------------------------------

st.set_page_config(page_title="Auto-scraper espèces", layout="wide", page_icon="🌿")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def is_debug_mode() -> bool:
    """Vérifie si le mode débogage est activé via les paramètres de requête URL."""
    try:
        # Utilise st.query_params (Streamlit 1.28+)
        # Pour les versions antérieures, st.experimental_get_query_params() peut être utilisé,
        # mais st.query_params est la méthode moderne.
        if hasattr(st, 'query_params'):
            return "true" in st.query_params.get_all("debug")
        # Fallback pour environnements où st.query_params n'est pas disponible (ex: tests unitaires simples)
        # ou versions très anciennes de Streamlit.
        if hasattr(st, 'experimental_get_query_params'):
            query_params = st.experimental_get_query_params()
            return "true" in query_params.get("debug", [])
        return False
    except Exception:
        # En cas d'erreur lors de l'accès aux query_params, désactiver le mode debug par sécurité.
        return False

DEBUG_MODE = is_debug_mode()

# -----------------------------------------------------------------------------
# Fonctions utilitaires
# -----------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=86_400) # Cache de 24 heures
def fetch_html(url: str, session: requests.Session | None = None) -> BeautifulSoup | None:
    """Télécharge une page et renvoie son contenu analysé par BeautifulSoup."""
    if DEBUG_MODE:
        st.info(f"[DEBUG fetch_html] Tentative de téléchargement de : {url}")
    sess = session or requests.Session()
    sess.headers.update(HEADERS)
    try:
        r = sess.get(url, timeout=15)
        r.raise_for_status()
        if DEBUG_MODE:
            st.info(f"[DEBUG fetch_html] Succès du téléchargement de : {url} (status: {r.status_code})")
        return BeautifulSoup(r.text, "lxml")
    except requests.RequestException as e:
        st.warning(f"Erreur lors du téléchargement de {url}: {e}")
        return None

@st.cache_data(show_spinner=False, ttl=86_400)
def florealpes_search(species: str) -> str | None:
    """
    Recherche une espèce sur FloreAlpes (requests+BeautifulSoup) en ciblant
    la "première option" pertinente sur la page de résultats.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    base_url = "https://www.florealpes.com/"
    current_page_url_for_error_reporting = base_url 

    if DEBUG_MODE:
        st.info(f"[DEBUG FloreAlpes] Début recherche pour : {species}")

    try:
        # 1. Accès optionnel à la page d'accueil (pour simuler flux et cookies)
        try:
            home_resp = session.get(base_url, timeout=10)
            home_resp.raise_for_status()
            if DEBUG_MODE:
                st.info(f"[DEBUG FloreAlpes] Page d'accueil ({base_url}) chargée (status: {home_resp.status_code}).")
        except requests.RequestException as e:
            if DEBUG_MODE:
                st.info(f"[DEBUG FloreAlpes] Avertissement: Page d'accueil ({base_url}) non chargée: {e}")
            # Non bloquant, on continue.

        # 2. Soumission de la recherche à recherche.php
        search_url = urljoin(base_url, "recherche.php")
        search_params = {"chaine": species}
        if DEBUG_MODE:
            st.info(f"[DEBUG FloreAlpes] Requête de recherche vers : {search_url} avec params : {search_params}")
        
        results_response = session.get(search_url, params=search_params, timeout=15)
        results_response.raise_for_status()
        current_page_url_for_error_reporting = results_response.url
        if DEBUG_MODE:
            st.info(f"[DEBUG FloreAlpes] Page de résultats chargée (status: {results_response.status_code}), URL: {current_page_url_for_error_reporting}")

        soup = BeautifulSoup(results_response.text, "lxml")

        # 3. Vérification "aucun résultat"
        page_text_lower = results_response.text.lower()
        no_results_messages = [
            "aucun résultat à votre requête", 
            "pas de résultats trouvés pour cette recherche", 
            "aucun taxon ne correspond à votre recherche"
        ]
        if any(msg in page_text_lower for msg in no_results_messages):
            st.info(f"[FloreAlpes] Aucun résultat trouvé pour '{species}'.")
            return None

        # 4. Sélection de la "première option" de résultat pertinente
        link_tag = None
        
        # Stratégie : Chercher la table principale des résultats, puis la première ligne de cette table
        # qui contient un lien vers une fiche espèce dans la cellule 'td.symb'.
        results_table_container = soup.select_one("#principal div.conteneur_tab")
        results_table = None
        if results_table_container:
            results_table = results_table_container.select_one("table.resultats") # Table avec class 'resultats'
            if not results_table: 
                results_table = results_table_container.select_one("table") # Première table dans le conteneur
        
        if results_table:
            if DEBUG_MODE:
                st.info(f"[DEBUG FloreAlpes] Table des résultats trouvée. Recherche du premier lien de fiche...")
            # Parcourir les lignes (<tbody><tr> ou <tr> directes)
            data_rows = results_table.select("tbody > tr, tr") 
            for i, row in enumerate(data_rows):
                link_in_row = row.select_one("td.symb > a[href^='fiche_']")
                if link_in_row:
                    link_tag = link_in_row
                    if DEBUG_MODE:
                        st.info(f"[DEBUG FloreAlpes] Lien 'première option' trouvé dans la ligne {i+1} de la table.")
                    break # On prend le premier trouvé
        elif DEBUG_MODE:
            st.warning("[DEBUG FloreAlpes] Aucune table de résultats principale n'a pu être identifiée avec les sélecteurs cibles.")
        
        if link_tag and link_tag.has_attr('href'):
            relative_url = link_tag['href']
            absolute_url = urljoin(results_response.url, relative_url)
            if DEBUG_MODE:
                st.info(f"[DEBUG FloreAlpes] URL de fiche construite : {absolute_url}")
            return absolute_url
        else:
            if DEBUG_MODE:
                st.warning("[DEBUG FloreAlpes] Logique 'première option' n'a pas trouvé de lien direct. Application des fallbacks.")
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
            
            st.error(f"[FloreAlpes] Impossible de trouver le lien de la fiche pour '{species}' après toutes les tentatives.")
            return None

    except requests.RequestException as e:
        st.error(f"[FloreAlpes] Erreur de requête pour '{species}': {e}")
        return None
    except Exception as e:
        st.error(f"[FloreAlpes] Erreur inattendue pour '{species}': {e} (URL: {current_page_url_for_error_reporting})")
        return None

def scrape_florealpes(url: str) -> tuple[str | None, pd.DataFrame | None]:
    """Extrait l’image principale et le tableau des caractéristiques de la page FloreAlpes."""
    if DEBUG_MODE:
        st.info(f"[DEBUG scrape_florealpes] Début de l'extraction pour URL : {url}")
    soup = fetch_html(url) 
    if soup is None:
        return None, None
    
    img_url = None
    # Liste de sélecteurs d'image, du plus spécifique/fiable au plus général
    image_selectors = [
        "table.fiche img[src$='.jpg']",                 # Image dans la table 'fiche' principale
        ".flotte-g img[src$='.jpg']",                   # Classe souvent utilisée pour l'image principale
        "img.illustration_details[src$='.jpg']",        # Autre classe potentielle pour l'image principale
        "img[alt*='Photo principale'][src$='.jpg']",    # Image avec alt text indicatif
        "div#photo_principale img[src$='.jpg']",        # Image dans un div avec ID spécifique
        "img[src*='/Photos/'][src$='.jpg']",            # Images dans un dossier /Photos/ (peut être une galerie)
        "a[href$='.jpg'] > img[src$='.jpg']",           # Image cliquable vers version plus grande
        "img[src$='.jpg'][width]",                      # Image avec une largeur définie (tente d'éviter les icônes)
        "img[src$='.jpg']"                              # Fallback général pour toute image jpg
    ]
    for selector in image_selectors:
        img_tag = soup.select_one(selector)
        if img_tag and img_tag.has_attr('src'):
            # Simple heuristique pour éviter les très petites images (icônes) si width est spécifié
            width_attr = img_tag.get('width', '9999') # grand par défaut si absent
            try:
                if int(str(width_attr).replace('px','')) > 50 : # Seuil pour considérer comme non-miniature
                    img_src = img_tag['src']
                    img_url = urljoin(url, img_src)
                    if DEBUG_MODE:
                        st.info(f"[DEBUG scrape_florealpes] Image trouvée avec sélecteur '{selector}': {img_url}")
                    break 
            except ValueError: # Si width n'est pas un nombre
                 img_src = img_tag['src'] # prendre l'image quand même
                 img_url = urljoin(url, img_src)
                 if DEBUG_MODE:
                     st.info(f"[DEBUG scrape_florealpes] Image (width non numérique) trouvée avec sélecteur '{selector}': {img_url}")
                 break


    data_tbl = None
    # Chercher la table des caractéristiques avec la classe "fiche"
    tbl = soup.find("table", class_="fiche") 
    
    if not tbl: # Fallback si table.fiche non trouvée
        if DEBUG_MODE:
            st.info("[DEBUG scrape_florealpes] Tableau 'table.fiche' non trouvé. Tentative de recherche d'un tableau alternatif.")
        all_tables = soup.find_all("table")
        for potential_table in all_tables:
            text_content = potential_table.get_text(" ", strip=True).lower()
            # Mots-clés indiquant une table de caractéristiques botaniques
            keywords = ["famille", "floraison", "habitat", "description", "plante", "caractères", "altitude", "taille"]
            if sum(keyword in text_content for keyword in keywords) >= 2: # Au moins 2 mots-clés
                 # S'assurer que la table a des lignes avec 2 cellules (format attribut-valeur)
                 if any(len(tr.select("td")) == 2 for tr in potential_table.select("tr")):
                    tbl = potential_table
                    if DEBUG_MODE:
                        st.info("[DEBUG scrape_florealpes] Tableau alternatif trouvé basé sur mots-clés.")
                    break
    
    if tbl:
        rows = []
        for tr_element in tbl.select("tr"): # Utiliser select pour plus de robustesse
            cells = tr_element.select("td")
            if len(cells) == 2:
                attribute = cells[0].get_text(separator=' ', strip=True)
                value = cells[1].get_text(separator=' ', strip=True)
                if attribute: # Ajouter seulement si l'attribut n'est pas vide
                     rows.append([attribute, value])
        
        if rows:
            data_tbl = pd.DataFrame(rows, columns=["Attribut", "Valeur"])
            data_tbl = data_tbl[data_tbl["Attribut"].str.strip().astype(bool)] # Nettoyer lignes vides post-strip
            if data_tbl.empty: # Si le DataFrame est vide après nettoyage
                data_tbl = None 
                if DEBUG_MODE:
                    st.info("[DEBUG scrape_florealpes] Tableau de données extrait mais vide après nettoyage.")
            elif DEBUG_MODE:
                 st.info(f"[DEBUG scrape_florealpes] Tableau de données extrait avec {len(data_tbl)} lignes.")
        elif DEBUG_MODE:
            st.info("[DEBUG scrape_florealpes] Tableau trouvé mais aucune ligne (attribut/valeur) n'a pu en être extraite.")
            
    elif DEBUG_MODE:
        st.warning("[DEBUG scrape_florealpes] Aucun tableau de caractéristiques n'a pu être trouvé sur la page.")
            
    return img_url, data_tbl


def infoflora_url(species: str) -> str:
    """Construit l'URL InfoFlora pour une espèce."""
    slug = species.lower().replace(" ", "-")
    return f"https://www.infoflora.ch/fr/flore/{slug}.html"


def tela_botanica_url(species: str) -> str | None:
    """Interroge l’API eFlore de Tela Botanica pour l'URL de synthèse."""
    api_url = (
        "https://api.tela-botanica.org/service:eflore:0.1/" "names:search?mode=exact&taxon="
        f"{quote_plus(species)}"
    )
    if DEBUG_MODE:
        st.info(f"[DEBUG Tela Botanica] Interrogation API eFlore pour '{species}': {api_url}")
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        response = s.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data: 
            if DEBUG_MODE: st.info(f"[DEBUG Tela Botanica] Aucune donnée retournée par l'API pour '{species}'.")
            return None
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            nn = data[0].get("num_nomen")
            if nn:
                url = f"https://www.tela-botanica.org/bdtfx-nn-{nn}-synthese"
                if DEBUG_MODE: st.info(f"[DEBUG Tela Botanica] URL de synthèse trouvée: {url}")
                return url
            else:
                if DEBUG_MODE: st.warning(f"[DEBUG Tela Botanica] 'num_nomen' non trouvé dans la réponse API pour '{species}'.")
                return None
        else:
            st.warning(f"[Tela Botanica] Réponse API eFlore inattendue pour '{species}': {str(data)[:200]}...")
            return None
    except requests.RequestException as e:
        st.warning(f"[Tela Botanica] Erreur RequestException API eFlore pour '{species}': {e}")
        return None
    except ValueError as e: # Erreur de décodage JSON
        resp_text = response.text if 'response' in locals() and hasattr(response, 'text') else "N/A"
        st.warning(f"[Tela Botanica] Erreur décodage JSON API eFlore pour '{species}': {e}. Réponse: {resp_text[:200]}...")
        return None


def get_taxref_cd_ref(species_name: str) -> str | None:
    """Interroge l'API TaxRef pour récupérer le CD_REF (id TaxRef)."""
    taxref_api_url = "https://taxref.mnhn.fr/api/taxa/search"
    params = {
        "scientificNames": species_name,
        "territories": "fr", # Taxons présents en France (métropolitaine et outre-mer)
        "page": 1,
        "size": 10 # Augmenter la taille peut aider à trouver le bon taxon parmi les homonymes/variantes
    }
    if DEBUG_MODE:
        st.info(f"[DEBUG TaxRef] Interrogation API TaxRef pour '{species_name}': {taxref_api_url} avec params {params}")
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        response = s.get(taxref_api_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data and "_embedded" in data and "taxa" in data["_embedded"] and data["_embedded"]["taxa"]:
            taxa_list = data["_embedded"]["taxa"]
            normalized_species_name = species_name.strip().lower()
            # Chercher une correspondance exacte du nom scientifique
            for taxon in taxa_list:
                if taxon.get("scientificName", "").strip().lower() == normalized_species_name:
                    cd_ref = taxon.get("id")
                    if cd_ref:
                        if DEBUG_MODE: st.info(f"[DEBUG TaxRef] CD_REF trouvé (correspondance exacte): {cd_ref} pour '{species_name}'.")
                        return str(cd_ref)
            # Si pas de correspondance exacte, prendre le premier résultat (comportement par défaut)
            if taxa_list:
                first_taxon = taxa_list[0]
                cd_ref = first_taxon.get("id")
                if cd_ref:
                    st.info(f"[TaxRef] '{species_name}' non trouvé exactement. Utilisation de '{first_taxon.get('scientificName')}' (CD_REF: {cd_ref}) comme meilleur candidat.")
                    return str(cd_ref)
            if DEBUG_MODE: st.warning(f"[DEBUG TaxRef] Aucun taxon correspondant trouvé dans la liste pour '{species_name}'.")
            return None 
        else:
            if DEBUG_MODE: st.warning(f"[DEBUG TaxRef] Réponse API TaxRef malformée ou vide pour '{species_name}'. Data: {str(data)[:200]}...")
            return None 
    except requests.RequestException as e:
        st.warning(f"[TaxRef API] Erreur de requête pour '{species_name}': {e}")
        return None
    except ValueError as e: 
        resp_text = response.text if 'response' in locals() and hasattr(response, 'text') else "N/A"
        st.warning(f"[TaxRef API] Erreur décodage JSON pour '{species_name}': {e}. Réponse: {resp_text[:200]}...")
        return None


def openobs_embed(species: str) -> str:
    """Génère le HTML pour l'iframe OpenObs, utilisant le CD_REF si possible."""
    cd_ref = get_taxref_cd_ref(species)
    if cd_ref:
        iframe_url = f"https://openobs.mnhn.fr/redirect/inpn/taxa/{cd_ref}?view=map"
        if DEBUG_MODE: st.info(f"[DEBUG OpenObs] Utilisation CD_REF {cd_ref} pour l'iframe OpenObs.")
        return f"<iframe src='{iframe_url}' width='100%' height='100%' frameborder='0' style='min-height: 450px;'></iframe>"
    else:
        st.warning(f"[OpenObs] CD_REF non trouvé pour '{species}'. Tentative avec l'ancienne URL OpenObs (peut être imprécis/obsolète).")
        old_iframe_url = f"https://openobs.mnhn.fr/map.html?sp={quote_plus(species)}"
        return (
            f"<p style='color: orange; border: 1px solid orange; padding: 5px; border-radius: 3px;'>"
            f"Avertissement : L'identifiant TaxRef (CD_REF) pour '{species}' n'a pas pu être récupéré. "
            f"La carte OpenObs ci-dessous est basée sur une recherche par nom.</p>"
            f"<iframe src='{old_iframe_url}' width='100%' height='100%' frameborder='0' style='min-height: 400px;'></iframe>"
        )


def biodivaura_url(species: str) -> str:
    """Construit l'URL pour Biodiv'AURA Atlas, utilisant le CD_REF si possible."""
    cd_ref = get_taxref_cd_ref(species)
    if cd_ref:
        direct_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/{cd_ref}"
        if DEBUG_MODE: st.info(f"[DEBUG Biodiv'AURA] Utilisation CD_REF {cd_ref} pour URL Biodiv'AURA.")
        return direct_url
    else:
        st.warning(f"[Biodiv'AURA] CD_REF non trouvé pour '{species}'. Utilisation de l'URL de recherche.")
        search_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/recherche?keyword={quote_plus(species)}"
        return search_url

# -----------------------------------------------------------------------------
# Interface utilisateur Streamlit
# -----------------------------------------------------------------------------

# Section pour la note Google Keep et titre principal
col_keep_section, col_main_title = st.columns([1, 3], gap="large")

with col_keep_section:
    st.markdown("##### 📝 Notes de Projet")
    keep_url = "https://keep.google.com/#NOTE/1dHuU90VKwWzZAgoXzTsjNiRp_QgDB1BRCfthK5hH-23Vxb_A86uTPrroczclhg"
    st.markdown(
        "L'intégration directe de Google Keep est restreinte. Lien direct :"
    )
    button_html = f"""
    <a href="{keep_url}" target="_blank"
        style="display: inline-block; padding: 0.4em 0.8em; margin-top: 0.5em; background-color: #E8E8E8; color: #31333F;
               text-align: center; text-decoration: none; border-radius: 0.25rem; font-weight: 500;
               border: 1px solid #B0B0B0;">
        Accéder à la note Google Keep
    </a>
    """
    st.markdown(button_html, unsafe_allow_html=True)
    st.caption("S'ouvrira dans un nouvel onglet.")

with col_main_title:
    st.title("🌿 Recherche Infos Espèces") # Ajout d'un emoji au titre

if DEBUG_MODE:
    st.sidebar.info("Mode Débogage Activé", icon="🛠️")
    st.sidebar.markdown("Ajoutez `?debug=true` à l'URL pour activer les logs détaillés.")

st.markdown("---") # Séparateur

st.markdown("Saisissez les noms scientifiques (un par ligne) puis lancez la recherche.")

input_txt = st.text_area(
    "Liste d’espèces", 
    placeholder="Exemples :\nLamium purpureum\nTrifolium alpinum\nVicia sativa", 
    height=150 # Légère réduction de la hauteur
)

if st.button("🚀 Lancer la recherche", type="primary") and input_txt.strip():
    species_list = [s.strip() for s in input_txt.splitlines() if s.strip()]

    if DEBUG_MODE:
        st.info(f"[DEBUG Main] Espèces à rechercher : {species_list}")

    for sp_idx, sp in enumerate(species_list):
        st.subheader(f"{sp_idx + 1}. {sp}")
        st.markdown("---")

        # Layout principal pour carte et sources
        col_map, col_intro = st.columns([2, 1]) 

        with col_map:
            st.markdown("##### 🗺️ Carte de répartition (OpenObs)")
            with st.spinner(f"Chargement de la carte OpenObs pour '{sp}'..."):
                html_openobs_main = openobs_embed(sp)
            st.components.v1.html(html_openobs_main, height=465)

        with col_intro:
            st.markdown("##### ℹ️ Sources d'Information")
            st.info("Les informations détaillées pour cette espèce sont disponibles dans les onglets ci-dessous. Les messages de débogage (si activés) ou d'erreur s'affichent au fur et à mesure.")
        
        st.markdown("<br>", unsafe_allow_html=True) # Espace avant les onglets

        # Onglets pour chaque source de données
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
                    st.image(img, caption=f"{sp} (Source: FloreAlpes)", use_column_width="auto") # 'auto' ou True
                else:
                    st.warning(f"Image non trouvée sur FloreAlpes pour '{sp}'.")
                
                if tbl is not None and not tbl.empty:
                    st.dataframe(tbl, hide_index=True, use_container_width=True)
                elif tbl is not None and tbl.empty: 
                    st.info(f"Tableau des caractéristiques trouvé mais vide sur FloreAlpes pour '{sp}'.")
                else: 
                    st.warning(f"Tableau des caractéristiques non trouvé sur FloreAlpes pour '{sp}'.")
            else:
                st.error(f"Fiche introuvable sur FloreAlpes pour '{sp}'.")

        with tab_if:
            st.markdown("##### InfoFlora")
            url_if = infoflora_url(sp)
            st.markdown(f"**InfoFlora** : [Fiche complète]({url_if})")
            with st.spinner(f"Chargement de la page InfoFlora pour '{sp}'..."):
                st.components.v1.iframe(src=url_if, height=600, scrolling=True)

        with tab_tb:
            st.markdown("##### Tela Botanica (eFlore)")
            with st.spinner(f"Recherche sur Tela Botanica API pour '{sp}'..."):
                 url_tb = tela_botanica_url(sp)
            if url_tb:
                st.markdown(f"**Tela Botanica** : [Synthèse eFlore]({url_tb})")
                with st.spinner(f"Chargement de la page Tela Botanica pour '{sp}'..."):
                    st.components.v1.iframe(src=url_tb, height=600, scrolling=True)
            else:
                st.warning(f"Aucune correspondance via l’API eFlore de Tela Botanica pour '{sp}'.")

        with tab_ba:
            st.markdown("##### Biodiv'AURA Atlas")
            with st.spinner(f"Recherche sur Biodiv'AURA Atlas pour '{sp}'..."):
                url_ba_val = biodivaura_url(sp)
            st.markdown(f"**Biodiv'AURA** : [Accéder à l’atlas]({url_ba_val})")
            with st.spinner(f"Chargement de la page Biodiv'AURA pour '{sp}'..."):
                st.components.v1.iframe(src=url_ba_val, height=600, scrolling=True)
        
        st.markdown("---") # Séparateur entre les espèces

else:
    if not input_txt.strip() and st.session_state.get('button_clicked', False): # Si bouton cliqué mais champ vide
        st.warning("Veuillez saisir au moins un nom d'espèce.")
    else:
        st.info("Saisissez au moins une espèce pour démarrer la recherche.")

# Pour gérer l'état du bouton si nécessaire (pour le message d'avertissement ci-dessus)
if 'button_clicked' not in st.session_state:
    st.session_state.button_clicked = False
if st.button: # Si un bouton a été pressé (celui de recherche ici)
    st.session_state.button_clicked = True
