#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit app : récupération automatisée d’informations botaniques

Auteur : Robin Wojcik (Améten)
Date   : 2025-05-28 (v0.9.2 - Nouvelle URL OpenObs avec zoom et iframe agrandi)

Fonctionnement actualisé (v0.9.2)
----------------------------------
* Mode débogage activable via `?debug=true` dans l'URL pour des logs plus détaillés.
* Logique de scraping pour FloreAlpes (requests+BeautifulSoup) maintenue et commentée.
* Sélecteurs d'images et extraction de tableaux légèrement affinés.
* Récupération des CD_REF via un fichier CSV local "DATA_CD_REF.csv" avec détection améliorée du délimiteur.
* Ajout d'un onglet pour afficher les informations de l'INPN.
* Utilisation d'une nouvelle URL OpenObs permettant de spécifier une emprise géographique (WKT).
* Augmentation de la taille par défaut de l'iframe de la carte OpenObs et ajout de `allow="fullscreen"`.
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

DEFAULT_OPENOBS_BOUNDS = {
    "min_lon": 3.0791685730218887,
    "min_lat": 42.31877019535014,
    "max_lon": 8.023016229271889,
    "max_lat": 46.64266530624121
}

def is_debug_mode() -> bool:
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
# Chargement des données CD_REF depuis CSV
# -----------------------------------------------------------------------------

@st.cache_data(show_spinner="Chargement initial des données TaxRef locales...")
def load_cd_ref_data(csv_path: str) -> pd.DataFrame | None:
    df = None
    possible_delimiters = [',', '\t', ';'] 
    for delimiter in possible_delimiters:
        try:
            if DEBUG_MODE:
                st.info(f"[DEBUG load_cd_ref_data] Tentative de lecture de '{csv_path}' avec délimiteur '{repr(delimiter)}' et header=1.")
            current_df = pd.read_csv(
                csv_path, header=1, dtype=str, delimiter=delimiter,
                on_bad_lines='skip', skipinitialspace=True
            )
            if DEBUG_MODE:
                st.info(f"[DEBUG load_cd_ref_data] Colonnes lues: {current_df.columns.tolist()}")
            actual_columns = [str(col).strip() for col in current_df.columns]
            current_df.columns = actual_columns
            if "CD_REF" in actual_columns and "NOM LATIN" in actual_columns:
                df = current_df[["CD_REF", "NOM LATIN"]].copy()
                if DEBUG_MODE: st.info(f"[DEBUG load_cd_ref_data] Colonnes 'CD_REF' et 'NOM LATIN' trouvées avec délimiteur '{repr(delimiter)}'.")
                break
            elif len(actual_columns) >= 2:
                temp_df = current_df.copy()
                original_first_col_name, original_second_col_name = actual_columns[0], actual_columns[1]
                temp_df = temp_df.rename(columns={original_first_col_name: "CD_REF", original_second_col_name: "NOM LATIN"})
                if "CD_REF" in temp_df.columns and "NOM LATIN" in temp_df.columns:
                    df = temp_df[["CD_REF", "NOM LATIN"]].copy()
                    if DEBUG_MODE: st.info(f"[DEBUG load_cd_ref_data] Colonnes renommées en 'CD_REF', 'NOM LATIN' avec délimiteur '{repr(delimiter)}'.")
                    break
            df = None # Si conditions non remplies, réinitialiser pour le prochain délimiteur
        except pd.errors.EmptyDataError:
            st.error(f"Fichier CSV '{csv_path}' est vide.")
            return None
        except FileNotFoundError: 
            st.error(f"Fichier CSV '{csv_path}' non trouvé.")
            return None
        except Exception as e_read:
            if DEBUG_MODE: st.warning(f"[DEBUG load_cd_ref_data] Échec lecture avec délimiteur '{repr(delimiter)}': {e_read}")
            df = None
    if df is not None and not df.empty:
        df["CD_REF"] = df["CD_REF"].astype(str)
        df["NOM LATIN"] = df["NOM LATIN"].astype(str)
        df["NOM_LATIN_normalized"] = df["NOM LATIN"].str.strip().str.lower()
        df.dropna(subset=["CD_REF", "NOM LATIN"], inplace=True)
        df = df[df["CD_REF"].str.strip() != '']
        df = df[df["NOM LATIN"].str.strip() != '']
        if not df.empty:
            if DEBUG_MODE: st.info(f"[DEBUG load_cd_ref_data] CSV '{csv_path}' chargé: {len(df)} lignes valides. Colonnes: {df.columns.tolist()}")
            return df
        else:
            st.error(f"Après nettoyage, aucune donnée valide trouvée dans '{csv_path}'.")
            return None
    else:
        st.error(f"Impossible de lire/traiter CSV '{csv_path}' pour identifier 'CD_REF' et 'NOM LATIN'.")
        st.error("Vérifications suggérées :")
        st.markdown("- `DATA_CD_REF.csv` présent dans le répertoire du script.\n- 2ème ligne du fichier = en-têtes (ex: \"CD_REF\", \"NOM LATIN\").\n- Délimiteur standard (virgule, tabulation, point-virgule).\n- Fichier non vide, données exploitables.")
        return None

TAXREF_DATA = load_cd_ref_data(CD_REF_CSV_PATH)

# -----------------------------------------------------------------------------
# Fonctions utilitaires (inchangées par rapport à v0.9.2, sauf openobs_embed)
# -----------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=86_400)
def fetch_html(url: str, session: requests.Session | None = None) -> BeautifulSoup | None:
    if DEBUG_MODE: st.info(f"[DEBUG fetch_html] Téléchargement de : {url}")
    sess = session or requests.Session(); sess.headers.update(HEADERS)
    try:
        r = sess.get(url, timeout=15); r.raise_for_status()
        if DEBUG_MODE: st.info(f"[DEBUG fetch_html] Succès: {url} (status: {r.status_code})")
        return BeautifulSoup(r.text, "lxml")
    except requests.RequestException as e:
        st.warning(f"Erreur téléchargement {url}: {e}"); return None

@st.cache_data(show_spinner=False, ttl=86_400)
def florealpes_search(species: str) -> str | None:
    session = requests.Session(); session.headers.update(HEADERS)
    base_url = "https://www.florealpes.com/"; current_page_url_for_error_reporting = base_url 
    if DEBUG_MODE: st.info(f"[DEBUG FloreAlpes] Recherche pour : {species}")
    try:
        try: 
            home_resp = session.get(base_url, timeout=10); home_resp.raise_for_status()
            if DEBUG_MODE: st.info(f"[DEBUG FloreAlpes] Accueil ({base_url}) chargé (status: {home_resp.status_code}).")
        except requests.RequestException as e:
            if DEBUG_MODE: st.info(f"[DEBUG FloreAlpes] Avertissement: Accueil ({base_url}) non chargé: {e}")
        search_url = urljoin(base_url, "recherche.php"); search_params = {"chaine": species}
        if DEBUG_MODE: st.info(f"[DEBUG FloreAlpes] Requête recherche: {search_url}, params: {search_params}")
        results_response = session.get(search_url, params=search_params, timeout=15); results_response.raise_for_status()
        current_page_url_for_error_reporting = results_response.url
        if DEBUG_MODE: st.info(f"[DEBUG FloreAlpes] Résultats chargés (status: {results_response.status_code}), URL: {current_page_url_for_error_reporting}")
        soup = BeautifulSoup(results_response.text, "lxml")
        if any(msg in results_response.text.lower() for msg in ["aucun résultat à votre requête", "pas de résultats trouvés", "aucun taxon ne correspond"]):
            st.info(f"[FloreAlpes] Aucun résultat pour '{species}'."); return None
        link_tag = None; results_table_container = soup.select_one("#principal div.conteneur_tab")
        if results_table_container:
            results_table = results_table_container.select_one("table.resultats") or results_table_container.select_one("table")
            if results_table:
                if DEBUG_MODE: st.info(f"[DEBUG FloreAlpes] Table résultats trouvée. Recherche lien...")
                for i, row in enumerate(results_table.select("tbody > tr, tr")):
                    if link_in_row := row.select_one("td.symb > a[href^='fiche_']"):
                        link_tag = link_in_row
                        if DEBUG_MODE: st.info(f"[DEBUG FloreAlpes] Lien trouvé ligne {i+1}."); break
            elif DEBUG_MODE: st.warning("[DEBUG FloreAlpes] Table résultats non identifiée.")
        if link_tag and link_tag.has_attr('href'):
            abs_url = urljoin(results_response.url, link_tag['href'])
            if DEBUG_MODE: st.info(f"[DEBUG FloreAlpes] URL fiche construite: {abs_url}"); return abs_url
        else: 
            if DEBUG_MODE: st.warning("[DEBUG FloreAlpes] Lien direct non trouvé. Application fallbacks.")
            if "fiche_" in results_response.url and ".php" in results_response.url:
                st.info(f"[FloreAlpes] URL actuelle est une fiche (fallback 1) pour '{species}': {results_response.url}"); return results_response.url
            if generic_link_tag := soup.select_one("a[href^='fiche_']"):
                if generic_link_tag.has_attr('href'):
                    abs_url = urljoin(results_response.url, generic_link_tag['href'])
                    st.warning(f"[FloreAlpes] Utilisation 1er lien 'fiche_' générique (fallback 2) pour '{species}': {abs_url}"); return abs_url
            st.error(f"[FloreAlpes] Lien fiche introuvable pour '{species}'."); return None
    except requests.RequestException as e: st.error(f"[FloreAlpes] Erreur requête pour '{species}': {e}"); return None
    except Exception as e: st.error(f"[FloreAlpes] Erreur inattendue pour '{species}': {e} (URL: {current_page_url_for_error_reporting})"); return None

def scrape_florealpes(url: str) -> tuple[str | None, pd.DataFrame | None]:
    if DEBUG_MODE: st.info(f"[DEBUG scrape_florealpes] Extraction pour URL : {url}")
    soup = fetch_html(url); img_url = None; data_tbl = None
    if soup is None: return None, None
    image_selectors = ["table.fiche img[src$='.jpg']", ".flotte-g img[src$='.jpg']", "img.illustration_details[src$='.jpg']", "img[alt*='Photo principale'][src$='.jpg']", "div#photo_principale img[src$='.jpg']", "img[src*='/Photos/'][src$='.jpg']", "a[href$='.jpg'] > img[src$='.jpg']", "img[src$='.jpg'][width]", "img[src$='.jpg']"]
    for selector in image_selectors:
        if img_tag := soup.select_one(selector):
            if img_tag.has_attr('src'):
                try:
                    if int(str(img_tag.get('width', '9999')).replace('px','')) > 50 :
                        img_url = urljoin(url, img_tag['src'])
                        if DEBUG_MODE: st.info(f"[DEBUG scrape_florealpes] Image trouvée (sélecteur '{selector}'): {img_url}"); break 
                except ValueError: 
                    img_url = urljoin(url, img_tag['src'])
                    if DEBUG_MODE: st.info(f"[DEBUG scrape_florealpes] Image (width non num., sélecteur '{selector}'): {img_url}"); break
    tbl = soup.find("table", class_="fiche") 
    if not tbl:
        if DEBUG_MODE: st.info("[DEBUG scrape_florealpes] Table 'table.fiche' non trouvée. Tentative alternative.")
        for ptbl in soup.find_all("table"):
            txt = ptbl.get_text(" ", strip=True).lower()
            if sum(k in txt for k in ["famille", "floraison", "habitat", "description", "plante", "caractères"]) >= 2:
                if any(len(tr.select("td")) == 2 for tr in ptbl.select("tr")):
                    tbl = ptbl;
                    if DEBUG_MODE: st.info("[DEBUG scrape_florealpes] Table alternative trouvée."); break
    if tbl:
        rows = [[c[0].get_text(separator=' ', strip=True), c[1].get_text(separator=' ', strip=True)] for tr in tbl.select("tr") if (c := tr.select("td")) and len(c) == 2 and c[0].get_text(strip=True)]
        if rows:
            data_tbl = pd.DataFrame(rows, columns=["Attribut", "Valeur"])
            if data_tbl.empty: data_tbl = None; 
            if DEBUG_MODE: st.info(f"[DEBUG scrape_florealpes] Tableau extrait: {len(data_tbl) if data_tbl is not None else 0} lignes.")
        elif DEBUG_MODE: st.info("[DEBUG scrape_florealpes] Table trouvée mais aucune ligne (attr/val) extraite.")
    elif DEBUG_MODE: st.warning("[DEBUG scrape_florealpes] Aucun tableau de caractéristiques trouvé.")
    return img_url, data_tbl

def infoflora_url(species: str) -> str:
    return f"https://www.infoflora.ch/fr/flore/{species.lower().replace(' ', '-')}.html"

def tela_botanica_url(species: str) -> str | None:
    api_url = f"https://api.tela-botanica.org/service:eflore:0.1/names:search?mode=exact&taxon={quote_plus(species)}"
    if DEBUG_MODE: st.info(f"[DEBUG Tela Botanica] API eFlore pour '{species}': {api_url}")
    try:
        s = requests.Session(); s.headers.update(HEADERS)
        response = s.get(api_url, timeout=10); response.raise_for_status(); data = response.json()
        if not data: 
            if DEBUG_MODE: st.info(f"[DEBUG Tela Botanica] Aucune donnée API pour '{species}'."); return None
        if isinstance(data, list) and data and isinstance(data[0], dict):
            if nn := data[0].get("num_nomen"):
                url = f"https://www.tela-botanica.org/bdtfx-nn-{nn}-synthese"
                if DEBUG_MODE: st.info(f"[DEBUG Tela Botanica] URL synthèse: {url}"); return url
            else: 
                if DEBUG_MODE: st.warning(f"[DEBUG Tela Botanica] 'num_nomen' non trouvé pour '{species}'."); return None
        else: st.warning(f"[Tela Botanica] Réponse API eFlore inattendue pour '{species}'."); return None
    except requests.RequestException as e: st.warning(f"[Tela Botanica] Erreur API pour '{species}': {e}"); return None
    except ValueError: st.warning(f"[Tela Botanica] Erreur JSON API pour '{species}'."); return None

def get_cd_ref_from_csv(species_name: str) -> str | None:
    if TAXREF_DATA is None:
        if DEBUG_MODE: st.warning("[DEBUG CD_REF CSV] DataFrame TAXREF_DATA non chargé.")
        return None
    norm_sp_name = species_name.strip().lower()
    if DEBUG_MODE: st.info(f"[DEBUG CD_REF CSV] Recherche de '{norm_sp_name}' dans CSV.")
    match = TAXREF_DATA[TAXREF_DATA["NOM_LATIN_normalized"] == norm_sp_name]
    if not match.empty:
        cd_ref = str(match["CD_REF"].iloc[0])
        if DEBUG_MODE: st.info(f"[DEBUG CD_REF CSV] CD_REF '{cd_ref}' trouvé pour '{species_name}'.")
        return cd_ref
    else: 
        if DEBUG_MODE: st.warning(f"[DEBUG CD_REF CSV] Aucun CD_REF trouvé pour '{species_name}' dans CSV.")
        return None

def openobs_embed(species: str) -> str:
    """Génère le HTML pour l'iframe OpenObs, utilisant la nouvelle URL avec WKT si CD_REF disponible."""
    cd_ref = get_cd_ref_from_csv(species)
    if cd_ref:
        b = DEFAULT_OPENOBS_BOUNDS
        wkt_polygon = (
            f"MULTIPOLYGON((("
            f"{b['min_lon']}+{b['max_lat']},"
            f"{b['min_lon']}%20{b['min_lat']},"
            f"{b['max_lon']}%20{b['min_lat']},"
            f"{b['max_lon']}%20{b['max_lat']},"
            f"{b['min_lon']}%20{b['max_lat']}"
            f")))"
        )
        q_param = f"lsid%3A{cd_ref}%20AND%20(dynamicProperties_diffusionGP%3A%22true%22)"
        iframe_url = (
            f"https://openobs.mnhn.fr/openobs-hub/occurrences/search"
            f"?q={q_param}&qc=&wkt={wkt_polygon}#tab_mapView"
        )
        if DEBUG_MODE: st.info(f"[DEBUG OpenObs] Utilisation nouvelle URL OpenObs (CD_REF {cd_ref}, WKT). URL: {iframe_url}")
        return f"<iframe src='{iframe_url}' width='100%' height='100%' frameborder='0' style='min-height: 650px;' allow='fullscreen'></iframe>"
    else: 
        st.warning(f"[OpenObs] CD_REF non trouvé pour '{species}'. Utilisation ancienne URL OpenObs par nom.")
        fallback_url = f"https://openobs.mnhn.fr/map.html?sp={quote_plus(species)}" # Fallback sans WKT
        return (
            f"<p style='color: orange; border: 1px solid orange; padding: 5px; border-radius: 3px;'>"
            f"Avertissement : CD_REF pour '{species}' non récupéré. Carte OpenObs basée sur recherche par nom simple.</p>"
            f"<iframe src='{fallback_url}' width='100%' height='100%' frameborder='0' style='min-height: 400px;' allow='fullscreen'></iframe>"
        )

def biodivaura_url(species: str) -> str:
    cd_ref = get_cd_ref_from_csv(species)
    if cd_ref:
        url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/{cd_ref}"
        if DEBUG_MODE: st.info(f"[DEBUG Biodiv'AURA] Utilisation CD_REF {cd_ref} (CSV) pour URL: {url}")
        return url
    else: 
        st.warning(f"[Biodiv'AURA] CD_REF non trouvé pour '{species}'. Utilisation URL de recherche.")
        return f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/recherche?keyword={quote_plus(species)}"

def inpn_species_url(species: str) -> str | None:
    cd_ref = get_cd_ref_from_csv(species)
    if cd_ref:
        url = f"https://inpn.mnhn.fr/espece/cd_nom/{cd_ref}"
        if DEBUG_MODE: st.info(f"[DEBUG INPN] URL INPN avec CD_REF {cd_ref} (CSV): {url}")
        return url
    else: 
        if DEBUG_MODE: st.warning(f"[DEBUG INPN] CD_REF non trouvé pour '{species}'. Lien de recherche INPN.")
        return f"https://inpn.mnhn.fr/collTerr/nomenclature/espece/recherche?texteRecherche={quote_plus(species)}"

# -----------------------------------------------------------------------------
# Interface utilisateur Streamlit
# -----------------------------------------------------------------------------

col_keep_section, col_main_title = st.columns([1, 3], gap="large")
with col_keep_section:
    st.markdown("##### 📝 Notes de Projet")
    st.markdown("Lien direct vers la [note Google Keep](https://keep.google.com/#NOTE/1dHuU90VKwWzZAgoXzTsjNiRp_QgDB1BRCfthK5hH-23Vxb_A86uTPrroczclhg).", unsafe_allow_html=True)
    st.caption("S'ouvrira dans un nouvel onglet.")

with col_main_title:
    st.title("🌿 Recherche Infos Espèces") 

if DEBUG_MODE:
    st.sidebar.info("Mode Débogage Activé", icon="🛠️")
    st.sidebar.markdown("Ajoutez `?debug=true` à l'URL pour logs détaillés.")
    if TAXREF_DATA is None: st.sidebar.error("Fichier CSV CD_REF non chargé.")
    elif TAXREF_DATA.empty: st.sidebar.warning("CSV CD_REF chargé mais vide/sans données valides.")
    else: st.sidebar.success(f"{len(TAXREF_DATA)} taxons chargés depuis CSV.")

st.markdown("---") 
st.markdown("Saisissez les noms scientifiques (un par ligne) puis lancez la recherche.")
input_txt = st.text_area(
    "Liste d’espèces", 
    placeholder="Exemples :\nLamium purpureum\nTrifolium alpinum\nVicia sativa\nAbies alba", 
    height=150 
)

if 'button_clicked' not in st.session_state: st.session_state.button_clicked = False
if st.button("🚀 Lancer la recherche", type="primary"): st.session_state.button_clicked = True

if st.session_state.button_clicked and input_txt.strip():
    species_list = [s.strip() for s in input_txt.splitlines() if s.strip()]
    if DEBUG_MODE: st.info(f"[DEBUG Main] Espèces à rechercher : {species_list}")

    for sp_idx, sp in enumerate(species_list):
        st.subheader(f"{sp_idx + 1}. {sp}"); st.markdown("---")
        col_map, col_intro = st.columns([2, 1]) 

        with col_map:
            st.markdown("##### 🗺️ Carte de répartition (OpenObs)")
            with st.spinner(f"Chargement carte OpenObs pour '{sp}'..."):
                html_openobs_main = openobs_embed(sp)
            st.components.v1.html(html_openobs_main, height=650) # Hauteur augmentée

        with col_intro:
            st.markdown("##### ℹ️ Sources d'Information")
            st.info("Infos détaillées dans les onglets. Messages debug/erreur affichés au fur et à mesure.")
        
        st.markdown("<br>", unsafe_allow_html=True) 
        tabs = st.tabs(["FloreAlpes", "InfoFlora", "Tela Botanica", "Biodiv'AURA", "INPN"])

        with tabs[0]: # FloreAlpes
            st.markdown("##### FloreAlpes")
            with st.spinner(f"Recherche '{sp}' sur FloreAlpes..."): url_fa = florealpes_search(sp) 
            if url_fa:
                st.markdown(f"**FloreAlpes** : [Fiche complète]({url_fa})")
                with st.spinner(f"Extraction données FloreAlpes pour '{sp}'..."): img, tbl = scrape_florealpes(url_fa)
                if img: st.image(img, caption=f"{sp} (Source: FloreAlpes)", use_column_width="auto")
                else: st.warning(f"Image non trouvée sur FloreAlpes pour '{sp}'.")
                if tbl is not None and not tbl.empty: st.dataframe(tbl, hide_index=True, use_container_width=True)
                elif tbl is not None: st.info(f"Tableau caract. vide sur FloreAlpes pour '{sp}'.")
                else: st.warning(f"Tableau caract. non trouvé sur FloreAlpes pour '{sp}'.")
            else: st.error(f"Fiche introuvable sur FloreAlpes pour '{sp}'.")

        with tabs[1]: # InfoFlora
            st.markdown("##### InfoFlora")
            url_if = infoflora_url(sp); st.markdown(f"**InfoFlora** : [Fiche complète]({url_if})")
            with st.spinner(f"Chargement page InfoFlora pour '{sp}'..."):
                st.components.v1.iframe(src=url_if, height=600, scrolling=True)

        with tabs[2]: # Tela Botanica
            st.markdown("##### Tela Botanica (eFlore)")
            with st.spinner(f"Recherche API Tela Botanica pour '{sp}'..."): url_tb = tela_botanica_url(sp)
            if url_tb:
                st.markdown(f"**Tela Botanica** : [Synthèse eFlore]({url_tb})")
                with st.spinner(f"Chargement page Tela Botanica pour '{sp}'..."):
                    st.components.v1.iframe(src=url_tb, height=600, scrolling=True)
            else: st.warning(f"Aucune correspondance API eFlore (Tela Botanica) pour '{sp}'.")

        with tabs[3]: # Biodiv'AURA
            st.markdown("##### Biodiv'AURA Atlas")
            with st.spinner(f"Recherche Biodiv'AURA Atlas pour '{sp}'..."): url_ba = biodivaura_url(sp)
            st.markdown(f"**Biodiv'AURA** : [Accéder à l’atlas]({url_ba})")
            with st.spinner(f"Chargement page Biodiv'AURA pour '{sp}'..."):
                st.components.v1.iframe(src=url_ba, height=600, scrolling=True)
        
        with tabs[4]: # INPN
            st.markdown("##### INPN - Inventaire National du Patrimoine Naturel")
            with st.spinner(f"Recherche infos INPN pour '{sp}'..."): url_inpn = inpn_species_url(sp)
            if url_inpn:
                st.markdown(f"**INPN** : [Fiche espèce INPN]({url_inpn})")
                if "cd_nom" in url_inpn: 
                    with st.spinner(f"Chargement page INPN pour '{sp}'..."):
                        st.components.v1.iframe(src=url_inpn, height=600, scrolling=True)
                else: st.info("URL INPN est une page de recherche. Affichage direct non tenté. Utilisez lien.")
            else: st.error(f"Impossible de générer lien INPN pour '{sp}'.")
        st.markdown("---")

elif st.session_state.button_clicked and not input_txt.strip():
    st.warning("Veuillez saisir au moins un nom d'espèce.")
    st.session_state.button_clicked = False 
else:
    if not st.session_state.button_clicked : 
        st.info("Saisissez au moins une espèce pour démarrer la recherche.")
