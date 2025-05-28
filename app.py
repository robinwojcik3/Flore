#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit app : récupération automatisée d’informations botaniques

Auteur : Robin Wojcik (Améten)
Date   : 2025-05-28 (v0.9.1 - Amélioration chargement CSV et onglet INPN)

Fonctionnement actualisé (v0.9.1)
----------------------------------
* Mode débogage activable via `?debug=true` dans l'URL pour des logs plus détaillés.
* Logique de scraping pour FloreAlpes (requests+BeautifulSoup) maintenue et commentée.
* Sélecteurs d'images et extraction de tableaux légèrement affinés.
* Abandon complet de Selenium au profit de `requests` pour la portabilité.
* Interface utilisateur et messages d'erreur revus pour plus de clarté.
* Récupération des CD_REF via un fichier CSV local "DATA_CD_REF.csv" avec détection améliorée du délimiteur.
* Ajout d'un onglet pour afficher les informations de l'INPN.
"""

from __future__ import annotations

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin
import os

# -----------------------------------------------------------------------------
# Configuration globale et Mode Débogage
# -----------------------------------------------------------------------------

st.set_page_config(page_title="Auto-scraper espèces", layout="wide", page_icon="🌿")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

CD_REF_CSV_PATH = "DATA_CD_REF.csv"

def is_debug_mode() -> bool:
    """Vérifie si le mode débogage est activé via les paramètres de requête URL."""
    try:
        if hasattr(st, 'query_params'):
            return "true" in st.query_params.get_all("debug")
        if hasattr(st, 'experimental_get_query_params'):
            query_params = st.experimental_get_query_params()
            return "true" in query_params.get("debug", [])
        return False
    except Exception:
        return False

DEBUG_MODE = is_debug_mode()

# -----------------------------------------------------------------------------
# Chargement des données CD_REF depuis CSV (Version améliorée)
# -----------------------------------------------------------------------------

@st.cache_data(show_spinner="Chargement initial des données TaxRef locales...")
def load_cd_ref_data(csv_path: str) -> pd.DataFrame | None:
    """Charge les données CD_REF et NOM LATIN depuis le fichier CSV spécifié,
       en essayant plusieurs délimiteurs courants."""
    df = None
    # Délimiteurs courants à essayer
    possible_delimiters = [',', '\t', ';'] 

    for delimiter in possible_delimiters:
        try:
            if DEBUG_MODE:
                st.info(f"[DEBUG load_cd_ref_data] Tentative de lecture de '{csv_path}' avec délimiteur '{repr(delimiter)}' et header=1.")
            
            # Lire le CSV en utilisant la deuxième ligne (index 1) comme en-têtes
            current_df = pd.read_csv(
                csv_path, 
                header=1, 
                dtype=str, # Lire toutes les colonnes comme chaînes initialement pour éviter les erreurs de type
                delimiter=delimiter,
                on_bad_lines='skip', # Ignorer les lignes potentiellement malformées
                skipinitialspace=True # Ignorer les espaces après le délimiteur
            )

            if DEBUG_MODE:
                st.info(f"[DEBUG load_cd_ref_data] Colonnes lues avec délimiteur '{repr(delimiter)}': {current_df.columns.tolist()}")

            # Nettoyer les noms des colonnes lues (supprimer les espaces superflus)
            actual_columns = [str(col).strip() for col in current_df.columns]
            current_df.columns = actual_columns # Appliquer les noms de colonnes nettoyés

            # Scénario 1: Les colonnes sont déjà nommées "CD_REF" et "NOM LATIN"
            if "CD_REF" in actual_columns and "NOM LATIN" in actual_columns:
                df = current_df[["CD_REF", "NOM LATIN"]].copy()
                if DEBUG_MODE:
                    st.info(f"[DEBUG load_cd_ref_data] Colonnes 'CD_REF' et 'NOM LATIN' trouvées directement avec délimiteur '{repr(delimiter)}'.")
                break  # Le bon délimiteur et les bonnes colonnes ont été trouvés

            # Scénario 2: Il y a au moins deux colonnes, on suppose que ce sont les bonnes dans le bon ordre
            elif len(actual_columns) >= 2:
                temp_df = current_df.copy()
                original_first_col_name = actual_columns[0]
                original_second_col_name = actual_columns[1]
                
                # Renommer les deux premières colonnes
                temp_df = temp_df.rename(columns={
                    original_first_col_name: "CD_REF",
                    original_second_col_name: "NOM LATIN"
                })
                
                # Vérifier si le renommage a bien créé les colonnes attendues
                if "CD_REF" in temp_df.columns and "NOM LATIN" in temp_df.columns:
                    df = temp_df[["CD_REF", "NOM LATIN"]].copy()
                    if DEBUG_MODE:
                        st.info(f"[DEBUG load_cd_ref_data] Colonnes renommées en 'CD_REF' (depuis '{original_first_col_name}') et 'NOM LATIN' (depuis '{original_second_col_name}') avec délimiteur '{repr(delimiter)}'.")
                    break # Le bon délimiteur a été trouvé, et les colonnes ont été renommées avec succès
                else: # Le renommage a échoué pour une raison inconnue
                    df = None 
            else: # Moins de 2 colonnes lues
                df = None
        
        except pd.errors.EmptyDataError:
            st.error(f"Le fichier CSV '{csv_path}' est vide.")
            return None # Pas la peine d'essayer d'autres délimiteurs si le fichier est vide
        except FileNotFoundError: 
            st.error(f"Fichier CSV '{csv_path}' non trouvé.")
            return None
        except Exception as e_read:
            if DEBUG_MODE:
                st.warning(f"[DEBUG load_cd_ref_data] Échec de la lecture de '{csv_path}' avec délimiteur '{repr(delimiter)}': {e_read}")
            df = None # Réinitialiser df pour s'assurer que la boucle continue ou échoue proprement

    # Après avoir essayé tous les délimiteurs
    if df is not None and not df.empty:
        # S'assurer que les types de données sont corrects après sélection/renommage
        df["CD_REF"] = df["CD_REF"].astype(str)
        df["NOM LATIN"] = df["NOM LATIN"].astype(str)
        
        # Créer la colonne normalisée pour la recherche
        df["NOM_LATIN_normalized"] = df["NOM LATIN"].str.strip().str.lower()
        
        # Supprimer les lignes où CD_REF ou NOM LATIN pourraient être vides après le traitement
        df.dropna(subset=["CD_REF", "NOM LATIN"], inplace=True)
        df = df[df["CD_REF"].str.strip() != '']
        df = df[df["NOM LATIN"].str.strip() != '']

        if not df.empty:
            if DEBUG_MODE:
                st.info(f"[DEBUG load_cd_ref_data] Fichier CSV '{csv_path}' chargé avec succès. {len(df)} lignes valides après nettoyage. Colonnes: {df.columns.tolist()}")
            return df
        else:
            st.error(f"Après nettoyage, aucune donnée valide n'a été trouvée dans '{csv_path}'.")
            return None # Aucune donnée valide après nettoyage
            
    else: # df is None or df.empty
        st.error(f"Impossible de lire ou de traiter le fichier CSV '{csv_path}' pour identifier les colonnes 'CD_REF' et 'NOM LATIN'.")
        st.error("Veuillez vérifier les points suivants :")
        st.markdown("""
            - Le fichier `DATA_CD_REF.csv` est bien présent dans le même répertoire que le script.
            - La deuxième ligne du fichier contient bien les en-têtes (par exemple, "CD_REF" et "NOM LATIN").
            - Le fichier utilise un délimiteur standard : virgule (,), tabulation (invisible, souvent copiée depuis Excel) ou point-virgule (;).
            - Le fichier n'est pas vide et contient des données exploitables.
        """)
        return None

TAXREF_DATA = load_cd_ref_data(CD_REF_CSV_PATH)

# -----------------------------------------------------------------------------
# Fonctions utilitaires
# -----------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=86_400)
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
        try:
            home_resp = session.get(base_url, timeout=10)
            home_resp.raise_for_status()
            if DEBUG_MODE:
                st.info(f"[DEBUG FloreAlpes] Page d'accueil ({base_url}) chargée (status: {home_resp.status_code}).")
        except requests.RequestException as e:
            if DEBUG_MODE:
                st.info(f"[DEBUG FloreAlpes] Avertissement: Page d'accueil ({base_url}) non chargée: {e}")

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
        results_table_container = soup.select_one("#principal div.conteneur_tab")
        results_table = None
        if results_table_container:
            results_table = results_table_container.select_one("table.resultats")
            if not results_table: 
                results_table = results_table_container.select_one("table")
        
        if results_table:
            if DEBUG_MODE:
                st.info(f"[DEBUG FloreAlpes] Table des résultats trouvée. Recherche du premier lien de fiche...")
            data_rows = results_table.select("tbody > tr, tr") 
            for i, row in enumerate(data_rows):
                link_in_row = row.select_one("td.symb > a[href^='fiche_']")
                if link_in_row:
                    link_tag = link_in_row
                    if DEBUG_MODE:
                        st.info(f"[DEBUG FloreAlpes] Lien 'première option' trouvé dans la ligne {i+1} de la table.")
                    break 
        elif DEBUG_MODE:
            st.warning("[DEBUG FloreAlpes] Aucune table de résultats principale n'a pu être identifiée.")
        
        if link_tag and link_tag.has_attr('href'):
            relative_url = link_tag['href']
            absolute_url = urljoin(results_response.url, relative_url)
            if DEBUG_MODE:
                st.info(f"[DEBUG FloreAlpes] URL de fiche construite : {absolute_url}")
            return absolute_url
        else:
            if DEBUG_MODE:
                st.warning("[DEBUG FloreAlpes] Logique 'première option' n'a pas trouvé de lien direct. Application des fallbacks.")
            if "fiche_" in results_response.url and ".php" in results_response.url:
                st.info(f"[FloreAlpes] URL actuelle est déjà une fiche (fallback 1) pour '{species}': {results_response.url}")
                return results_response.url

            generic_link_tag = soup.select_one("a[href^='fiche_']")
            if generic_link_tag and generic_link_tag.has_attr('href'):
                relative_url = generic_link_tag['href']
                absolute_url = urljoin(results_response.url, relative_url)
                st.warning(f"[FloreAlpes] Logique 'première option' échouée. Utilisation du 1er lien 'fiche_' (fallback 2) pour '{species}': {absolute_url}")
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
    """Extrait l’image principale et le tableau des caractéristiques de la page FloreAlpes."""
    if DEBUG_MODE:
        st.info(f"[DEBUG scrape_florealpes] Début de l'extraction pour URL : {url}")
    soup = fetch_html(url) 
    if soup is None:
        return None, None
    
    img_url = None
    image_selectors = [
        "table.fiche img[src$='.jpg']", ".flotte-g img[src$='.jpg']", 
        "img.illustration_details[src$='.jpg']", "img[alt*='Photo principale'][src$='.jpg']",
        "div#photo_principale img[src$='.jpg']", "img[src*='/Photos/'][src$='.jpg']",
        "a[href$='.jpg'] > img[src$='.jpg']", "img[src$='.jpg'][width]", "img[src$='.jpg']"
    ]
    for selector in image_selectors:
        img_tag = soup.select_one(selector)
        if img_tag and img_tag.has_attr('src'):
            width_attr = img_tag.get('width', '9999') 
            try:
                if int(str(width_attr).replace('px','')) > 50 : 
                    img_src = img_tag['src']
                    img_url = urljoin(url, img_src)
                    if DEBUG_MODE:
                        st.info(f"[DEBUG scrape_florealpes] Image trouvée avec sélecteur '{selector}': {img_url}")
                    break 
            except ValueError: 
                img_src = img_tag['src'] 
                img_url = urljoin(url, img_src)
                if DEBUG_MODE:
                    st.info(f"[DEBUG scrape_florealpes] Image (width non num.) trouvée avec '{selector}': {img_url}")
                break

    data_tbl = None
    tbl = soup.find("table", class_="fiche") 
    
    if not tbl: 
        if DEBUG_MODE:
            st.info("[DEBUG scrape_florealpes] Tableau 'table.fiche' non trouvé. Tentative alternative.")
        all_tables = soup.find_all("table")
        for potential_table in all_tables:
            text_content = potential_table.get_text(" ", strip=True).lower()
            keywords = ["famille", "floraison", "habitat", "description", "plante", "caractères", "altitude", "taille"]
            if sum(keyword in text_content for keyword in keywords) >= 2: 
                if any(len(tr.select("td")) == 2 for tr in potential_table.select("tr")):
                    tbl = potential_table
                    if DEBUG_MODE:
                        st.info("[DEBUG scrape_florealpes] Tableau alternatif trouvé.")
                    break
    
    if tbl:
        rows = []
        for tr_element in tbl.select("tr"): 
            cells = tr_element.select("td")
            if len(cells) == 2:
                attribute = cells[0].get_text(separator=' ', strip=True)
                value = cells[1].get_text(separator=' ', strip=True)
                if attribute: 
                    rows.append([attribute, value])
        
        if rows:
            data_tbl = pd.DataFrame(rows, columns=["Attribut", "Valeur"])
            data_tbl = data_tbl[data_tbl["Attribut"].str.strip().astype(bool)] 
            if data_tbl.empty: 
                data_tbl = None 
                if DEBUG_MODE:
                    st.info("[DEBUG scrape_florealpes] Tableau extrait mais vide après nettoyage.")
            elif DEBUG_MODE:
                st.info(f"[DEBUG scrape_florealpes] Tableau extrait avec {len(data_tbl)} lignes.")
        elif DEBUG_MODE:
            st.info("[DEBUG scrape_florealpes] Tableau trouvé mais aucune ligne (attribut/valeur) extraite.")
            
    elif DEBUG_MODE:
        st.warning("[DEBUG scrape_florealpes] Aucun tableau de caractéristiques trouvé.")
            
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
            if DEBUG_MODE: st.info(f"[DEBUG Tela Botanica] Aucune donnée API pour '{species}'.")
            return None
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            nn = data[0].get("num_nomen")
            if nn:
                url = f"https://www.tela-botanica.org/bdtfx-nn-{nn}-synthese"
                if DEBUG_MODE: st.info(f"[DEBUG Tela Botanica] URL de synthèse trouvée: {url}")
                return url
            else:
                if DEBUG_MODE: st.warning(f"[DEBUG Tela Botanica] 'num_nomen' non trouvé pour '{species}'.")
                return None
        else:
            st.warning(f"[Tela Botanica] Réponse API eFlore inattendue pour '{species}'.")
            return None
    except requests.RequestException as e:
        st.warning(f"[Tela Botanica] Erreur API eFlore pour '{species}': {e}")
        return None
    except ValueError as e: 
        resp_text = response.text if 'response' in locals() and hasattr(response, 'text') else "N/A"
        st.warning(f"[Tela Botanica] Erreur JSON API eFlore pour '{species}': {e}. Réponse: {resp_text[:200]}...")
        return None

def get_cd_ref_from_csv(species_name: str) -> str | None:
    """Récupère le CD_REF à partir du DataFrame TAXREF_DATA chargé depuis le CSV."""
    if TAXREF_DATA is None:
        if DEBUG_MODE:
            st.warning("[DEBUG CD_REF CSV] DataFrame TAXREF_DATA non chargé.")
        return None

    normalized_species_name = species_name.strip().lower()
    if DEBUG_MODE:
        st.info(f"[DEBUG CD_REF CSV] Recherche de '{normalized_species_name}' dans le CSV.")

    match = TAXREF_DATA[TAXREF_DATA["NOM_LATIN_normalized"] == normalized_species_name]

    if not match.empty:
        cd_ref = match["CD_REF"].iloc[0]
        if DEBUG_MODE:
            st.info(f"[DEBUG CD_REF CSV] CD_REF '{cd_ref}' trouvé pour '{species_name}'.")
        return str(cd_ref)
    else:
        if DEBUG_MODE:
            st.warning(f"[DEBUG CD_REF CSV] Aucun CD_REF trouvé pour '{species_name}' dans CSV.")
        return None

def openobs_embed(species: str) -> str:
    """Génère le HTML pour l'iframe OpenObs, utilisant le CD_REF du CSV si possible."""
    cd_ref = get_cd_ref_from_csv(species)
    if cd_ref:
        iframe_url = f"https://openobs.mnhn.fr/redirect/inpn/taxa/{cd_ref}?view=map"
        if DEBUG_MODE: st.info(f"[DEBUG OpenObs] Utilisation CD_REF {cd_ref} (CSV) pour iframe OpenObs.")
        return f"<iframe src='{iframe_url}' width='100%' height='100%' frameborder='0' style='min-height: 450px;'></iframe>"
    else:
        st.warning(f"[OpenObs] CD_REF non trouvé dans CSV pour '{species}'. Tentative avec URL OpenObs par nom.")
        old_iframe_url = f"https://openobs.mnhn.fr/map.html?sp={quote_plus(species)}"
        return (
            f"<p style='color: orange; border: 1px solid orange; padding: 5px; border-radius: 3px;'>"
            f"Avertissement : CD_REF pour '{species}' non récupéré depuis CSV. Carte OpenObs basée sur recherche par nom.</p>"
            f"<iframe src='{old_iframe_url}' width='100%' height='100%' frameborder='0' style='min-height: 400px;'></iframe>"
        )

def biodivaura_url(species: str) -> str:
    """Construit l'URL pour Biodiv'AURA Atlas, utilisant le CD_REF du CSV si possible."""
    cd_ref = get_cd_ref_from_csv(species)
    if cd_ref:
        direct_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/{cd_ref}"
        if DEBUG_MODE: st.info(f"[DEBUG Biodiv'AURA] Utilisation CD_REF {cd_ref} (CSV) pour URL Biodiv'AURA.")
        return direct_url
    else:
        st.warning(f"[Biodiv'AURA] CD_REF non trouvé dans CSV pour '{species}'. Utilisation URL de recherche.")
        search_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/recherche?keyword={quote_plus(species)}"
        return search_url

def inpn_species_url(species: str) -> str | None:
    """Construit l'URL de la fiche espèce INPN en utilisant le CD_REF du CSV."""
    cd_ref = get_cd_ref_from_csv(species)
    if cd_ref:
        url = f"https://inpn.mnhn.fr/espece/cd_nom/{cd_ref}"
        if DEBUG_MODE: st.info(f"[DEBUG INPN] URL INPN construite avec CD_REF {cd_ref} (CSV): {url}")
        return url
    else:
        if DEBUG_MODE: st.warning(f"[DEBUG INPN] CD_REF non trouvé dans CSV pour '{species}'. Lien de recherche INPN.")
        search_url_inpn = f"https://inpn.mnhn.fr/collTerr/nomenclature/espece/recherche?texteRecherche={quote_plus(species)}"
        return search_url_inpn

# -----------------------------------------------------------------------------
# Interface utilisateur Streamlit
# -----------------------------------------------------------------------------

col_keep_section, col_main_title = st.columns([1, 3], gap="large")
with col_keep_section:
    st.markdown("##### 📝 Notes de Projet")
    keep_url = "https://keep.google.com/#NOTE/1dHuU90VKwWzZAgoXzTsjNiRp_QgDB1BRCfthK5hH-23Vxb_A86uTPrroczclhg"
    st.markdown("Lien direct vers la note Google Keep :")
    button_html = f"""
    <a href="{keep_url}" target="_blank"
        style="display: inline-block; padding: 0.4em 0.8em; margin-top: 0.5em; background-color: #E8E8E8; color: #31333F;
               text-align: center; text-decoration: none; border-radius: 0.25rem; font-weight: 500;
               border: 1px solid #B0B0B0;">Accéder à la note Google Keep</a>"""
    st.markdown(button_html, unsafe_allow_html=True)
    st.caption("S'ouvrira dans un nouvel onglet.")

with col_main_title:
    st.title("🌿 Recherche Infos Espèces") 

if DEBUG_MODE:
    st.sidebar.info("Mode Débogage Activé", icon="🛠️")
    st.sidebar.markdown("Ajoutez `?debug=true` à l'URL pour activer les logs détaillés.")
    if TAXREF_DATA is None:
        st.sidebar.error("Fichier CSV des CD_REF non chargé. Vérifiez les messages d'erreur.")
    elif TAXREF_DATA.empty:
        st.sidebar.warning("Fichier CSV des CD_REF chargé mais vide ou sans données valides.")
    else:
        st.sidebar.success(f"{len(TAXREF_DATA)} taxons chargés depuis le CSV.")

st.markdown("---") 
st.markdown("Saisissez les noms scientifiques (un par ligne) puis lancez la recherche.")
input_txt = st.text_area(
    "Liste d’espèces", 
    placeholder="Exemples :\nLamium purpureum\nTrifolium alpinum\nVicia sativa\nAbies alba", 
    height=150 
)

if 'button_clicked' not in st.session_state:
    st.session_state.button_clicked = False

button_pressed = st.button("🚀 Lancer la recherche", type="primary")
if button_pressed:
    st.session_state.button_clicked = True

if st.session_state.button_clicked and input_txt.strip():
    species_list = [s.strip() for s in input_txt.splitlines() if s.strip()]
    if DEBUG_MODE:
        st.info(f"[DEBUG Main] Espèces à rechercher : {species_list}")

    for sp_idx, sp in enumerate(species_list):
        st.subheader(f"{sp_idx + 1}. {sp}")
        st.markdown("---")
        col_map, col_intro = st.columns([2, 1]) 

        with col_map:
            st.markdown("##### 🗺️ Carte de répartition (OpenObs/INPN)")
            with st.spinner(f"Chargement carte OpenObs pour '{sp}'..."):
                html_openobs_main = openobs_embed(sp)
            st.components.v1.html(html_openobs_main, height=465)

        with col_intro:
            st.markdown("##### ℹ️ Sources d'Information")
            st.info("Infos détaillées dans les onglets ci-dessous. Messages de debug/erreur affichés au fur et à mesure.")
        
        st.markdown("<br>", unsafe_allow_html=True) 
        tab_names = ["FloreAlpes", "InfoFlora", "Tela Botanica", "Biodiv'AURA", "INPN"]
        tab_fa, tab_if, tab_tb, tab_ba, tab_inpn = st.tabs(tab_names)

        with tab_fa:
            st.markdown("##### FloreAlpes")
            with st.spinner(f"Recherche '{sp}' sur FloreAlpes..."):
                url_fa = florealpes_search(sp) 
            if url_fa:
                st.markdown(f"**FloreAlpes** : [Fiche complète]({url_fa})")
                with st.spinner(f"Extraction données FloreAlpes pour '{sp}'..."):
                    img, tbl = scrape_florealpes(url_fa)
                if img:
                    st.image(img, caption=f"{sp} (Source: FloreAlpes)", use_column_width="auto")
                else:
                    st.warning(f"Image non trouvée sur FloreAlpes pour '{sp}'.")
                if tbl is not None and not tbl.empty:
                    st.dataframe(tbl, hide_index=True, use_container_width=True)
                elif tbl is not None and tbl.empty: 
                    st.info(f"Tableau caractéristiques vide sur FloreAlpes pour '{sp}'.")
                else: 
                    st.warning(f"Tableau caractéristiques non trouvé sur FloreAlpes pour '{sp}'.")
            else:
                st.error(f"Fiche introuvable sur FloreAlpes pour '{sp}'.")

        with tab_if:
            st.markdown("##### InfoFlora")
            url_if = infoflora_url(sp)
            st.markdown(f"**InfoFlora** : [Fiche complète]({url_if})")
            with st.spinner(f"Chargement page InfoFlora pour '{sp}'..."):
                st.components.v1.iframe(src=url_if, height=600, scrolling=True)

        with tab_tb:
            st.markdown("##### Tela Botanica (eFlore)")
            with st.spinner(f"Recherche API Tela Botanica pour '{sp}'..."):
                url_tb = tela_botanica_url(sp)
            if url_tb:
                st.markdown(f"**Tela Botanica** : [Synthèse eFlore]({url_tb})")
                with st.spinner(f"Chargement page Tela Botanica pour '{sp}'..."):
                    st.components.v1.iframe(src=url_tb, height=600, scrolling=True)
            else:
                st.warning(f"Aucune correspondance API eFlore (Tela Botanica) pour '{sp}'.")

        with tab_ba:
            st.markdown("##### Biodiv'AURA Atlas")
            with st.spinner(f"Recherche Biodiv'AURA Atlas pour '{sp}'..."):
                url_ba_val = biodivaura_url(sp)
            st.markdown(f"**Biodiv'AURA** : [Accéder à l’atlas]({url_ba_val})")
            with st.spinner(f"Chargement page Biodiv'AURA pour '{sp}'..."):
                st.components.v1.iframe(src=url_ba_val, height=600, scrolling=True)
        
        with tab_inpn:
            st.markdown("##### INPN - Inventaire National du Patrimoine Naturel")
            with st.spinner(f"Recherche infos INPN pour '{sp}'..."):
                url_inpn_val = inpn_species_url(sp)
            if url_inpn_val:
                st.markdown(f"**INPN** : [Fiche espèce INPN]({url_inpn_val})")
                if "cd_nom" in url_inpn_val: 
                    with st.spinner(f"Chargement page INPN pour '{sp}'..."):
                        st.components.v1.iframe(src=url_inpn_val, height=600, scrolling=True)
                else: 
                    st.info("URL INPN est une page de recherche. Affichage direct non tenté. Utilisez le lien ci-dessus.")
            else: 
                st.error(f"Impossible de générer un lien INPN pour '{sp}'.")
        st.markdown("---")

elif st.session_state.button_clicked and not input_txt.strip():
    st.warning("Veuillez saisir au moins un nom d'espèce.")
    st.session_state.button_clicked = False 
else:
    if not st.session_state.button_clicked : 
        st.info("Saisissez au moins une espèce pour démarrer la recherche.")
