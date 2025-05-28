#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit app : récupération automatisée d'informations botaniques

Auteur : Robin Wojcik (Améten)
Date   : 2025-05-27

Fonctionnement actualisé (v0.3)
--------------------------------
* La recherche FloreAlpes passe désormais **obligatoirement** par la page
  d'accueil (https://www.florealpes.com/index.php) puis soumet le champ `chaine`.
  Cela reproduit exactement le comportement utilisateur.
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


def florealpes_search(species: str) -> str | None:
    """Reproduction exacte de la recherche via le formulaire FloreAlpes."""
    # st.write(f"[FloreAlpes Debug] Tentative de recherche pour : {species}") # Devenu verbeux pour cette fonction souvent appelée
    sess = requests.Session()
    sess.headers.update(HEADERS)

    try:
        index_url = "https://www.florealpes.com/index.php"
        index_resp = sess.get(index_url, timeout=15)
        index_resp.raise_for_status()
    except requests.RequestException as e:
        st.warning(f"Impossible de charger la page d'accueil de FloreAlpes : {e}")
        return None

    try:
        search_url_base = "https://www.florealpes.com/recherche.php"
        params_florealpes = {"chaine": species}
        
        resp = sess.get(search_url_base, params=params_florealpes, timeout=15)
        # st.write(f"[FloreAlpes Debug] Réponse de la recherche URL finale : {resp.url}, statut : {resp.status_code}")
        resp.raise_for_status()

        if "florealpes.com" not in resp.url:
            st.error(f"[FloreAlpes Debug] Redirection inattendue vers : {resp.url} depuis FloreAlpes. La recherche a échoué.")
            return None

        if "aucun résultat à votre requête" in resp.text.lower() or "pas de résultats" in resp.text.lower():
            # st.write(f"[FloreAlpes Debug] Message 'aucun résultat' trouvé pour '{species}'.")
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        # page_title = soup.title.string if soup.title else "Pas de titre"
        # st.write(f"[FloreAlpes Debug] Titre de la page de recherche : {page_title}")

        link_tag = soup.select_one("a[href^='fiche_']")
        
        if link_tag and link_tag.has_attr('href'):
            relative_url = link_tag['href']
            absolute_url = urljoin("https://www.florealpes.com/", relative_url)
            # st.write(f"[FloreAlpes Debug] Lien FloreAlpes trouvé : {absolute_url}")
            return absolute_url
        else:
            # st.write(f"[FloreAlpes Debug] Lien 'a[href^=fiche_]' non trouvé sur la page FloreAlpes pour {species}.")
            return None
            
    except requests.RequestException as e:
        st.warning(f"Erreur RequestException lors de la recherche FloreAlpes pour '{species}' : {e}")
        return None
    except Exception as e:
        st.error(f"Une erreur inattendue est survenue pendant la recherche FloreAlpes pour '{species}' : {e}")
        return None


def scrape_florealpes(url: str) -> tuple[str | None, pd.DataFrame | None]:
    """Extrait l'image principale et le tableau des caractéristiques."""
    soup = fetch_html(url)
    if soup is None:
        return None, None

    img_tag = soup.select_one("a[href$='.jpg'] img") or soup.select_one("img[src$='.jpg']")
    img_url = None
    if img_tag and img_tag.has_attr('src'):
        img_src_relative = img_tag['src']
        img_url = urljoin("https://www.florealpes.com/", img_src_relative)

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
        st.warning(f"[Tela Botanica Debug] Erreur décodage JSON API eFlore pour '{species}': {e}. Réponse: {response.text if 'response' in locals() else 'N/A'}")
        return None


def get_taxref_cd_ref(species_name: str) -> str | None:
    """Interroge l'API TaxRef pour récupérer le CD_REF (id TaxRef)."""
    # st.write(f"[TaxRef API Debug] Recherche du CD_REF pour : {species_name}") # Devenu verbeux
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
                # st.write(f"[TaxRef API Debug] Pas de correspondance exacte pour '{species_name}', utilisation du premier taxon : {found_taxon.get('scientificName')}")

            cd_ref = found_taxon.get("id")
            if cd_ref:
                # st.write(f"[TaxRef API Debug] CD_REF trouvé pour '{species_name}' (taxon: {found_taxon.get('scientificName')}): {cd_ref}")
                return str(cd_ref)
            # else:
                # st.warning(f"[TaxRef API Debug] CD_REF (champ 'id') non trouvé pour '{found_taxon.get('scientificName', 'N/A')}'. Réponse: {found_taxon}")
            return None # cd_ref non trouvé dans le taxon
        # else:
            # st.warning(f"[TaxRef API Debug] Aucune donnée '_embedded.taxa' trouvée pour '{species_name}'. Réponse: {data}")
        return None # Pas de _embedded.taxa
    except requests.RequestException: # Erreurs réseau, HTTP >400, etc.
        # st.warning(f"[TaxRef API Debug] Erreur API TaxRef (RequestException) pour '{species_name}': {e}")
        return None
    except ValueError: # Erreur de décodage JSON
        # st.warning(f"[TaxRef API Debug] Erreur décodage JSON API TaxRef pour '{species_name}': {e}. Réponse: {response.text if 'response' in locals() else 'N/A'}")
        return None


def openobs_embed(species: str) -> str:
    """HTML pour afficher la carte OpenObs dans un iframe en utilisant le CD_REF."""
    cd_ref = get_taxref_cd_ref(species)
    
    if cd_ref:
        iframe_url = f"https://openobs.mnhn.fr/redirect/inpn/taxa/{cd_ref}?view=map"
        # st.write(f"[OpenObs Debug] URL Iframe OpenObs (avec CD_REF {cd_ref}) : {iframe_url}")
        return f"<iframe src='{iframe_url}' width='100%' height='100%' frameborder='0' style='min-height: 450px;'></iframe>"
    else:
        # st.warning(f"[OpenObs Debug] CD_REF non trouvé pour '{species}'. Tentative avec l'ancienne méthode OpenObs.")
        old_iframe_url = f"https://openobs.mnhn.fr/map.html?sp={quote_plus(species)}"
        return (
            f"<p style='color: orange; border: 1px solid orange; padding: 5px;'>"
            f"Avertissement : L'identifiant TaxRef (CD_REF) pour '{species}' n'a pas pu être récupéré. "
            f"Tentative d'affichage de la carte OpenObs avec l'ancienne méthode (peut être moins précise ou obsolète).</p>"
            f"<iframe src='{old_iframe_url}' width='100%' height='100%' frameborder='0' style='min-height: 400px;'></iframe>"
        )


def biodivaura_url(species: str) -> str: # Fonction renommée
    """Construit l'URL pour la page de l'espèce sur Biodiv'AURA Atlas, en utilisant le CD_REF si possible."""
    # st.write(f"[Biodiv'AURA Debug] Tentative de construction de l'URL pour : {species}") # Moins verbeux
    cd_ref = get_taxref_cd_ref(species) 

    if cd_ref:
        direct_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/{cd_ref}"
        # st.write(f"[Biodiv'AURA Debug] URL directe (avec CD_REF {cd_ref}) : {direct_url}")
        return direct_url
    else:
        # st.warning(f"[Biodiv'AURA Debug] CD_REF non trouvé pour '{species}'. Utilisation de l'URL de recherche.")
        search_url = f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/recherche?keyword={quote_plus(species)}"
        return search_url

# -----------------------------------------------------------------------------
# Interface utilisateur
# -----------------------------------------------------------------------------

st.title("Recherche automatisée d'informations sur les espèces")

# Section Google Keep en haut à gauche
st.markdown("---")
col_keep, col_main_content = st.columns([1, 2])

with col_keep:
    st.markdown("##### 📝 Notes Google Keep")
    
    # URL de la note Google Keep
    keep_url = "https://keep.google.com/#NOTE/1dHuU90VKwWzZAgoXzTsjNiRp_QgDB1BRCfthK5hH-23Vxb_A86uTPrroczclhg"
    
    # Tentative d'affichage avec iframe
    try:
        st.components.v1.iframe(src=keep_url, height=400, scrolling=True)
    except Exception as e:
        # Alternative si l'iframe ne fonctionne pas
        st.markdown(f"**[📝 Ouvrir la note Google Keep]({keep_url})**")
        st.info("⚠️ Google Keep ne peut pas être affiché directement dans l'application en raison des restrictions de sécurité. Cliquez sur le lien ci-dessus pour ouvrir dans un nouvel onglet.")

with col_main_content:
    st.markdown("##### Interface de recherche")
    st.markdown("Saisissez les noms scientifiques (un par ligne) puis lancez la recherche.")
    
    input_txt = st.text_area(
        "Liste d'espèces", placeholder="Lamium purpureum\nTrifolium alpinum", height=180
    )

st.markdown("---")

if st.button("Lancer la recherche", type="primary") and input_txt.strip():
    species_list = [s.strip() for s in input_txt.splitlines() if s.strip()]

    for sp in species_list:
        st.subheader(sp)
        st.markdown("---") 

        # Section principale avec carte OpenObs et introduction aux onglets
        col_map, col_intro = st.columns([2, 1]) # 2/3 pour la carte, 1/3 pour l'intro

        with col_map:
            st.markdown("##### Carte de répartition (OpenObs)")
            html_openobs_main = openobs_embed(sp) 
            st.components.v1.html(html_openobs_main, height=465) # Hauteur ajustée

        with col_intro:
            st.markdown("##### Sources d'Information")
            st.info("Les informations détaillées pour cette espèce sont disponibles dans les onglets ci-dessous. Les éventuels messages de débogage des APIs s'affichent au fur et à mesure des appels.")

        st.markdown("---") 

        # Onglets pour les détails (OpenObs est maintenant en haut, donc retiré des onglets)
        tab_names = ["FloreAlpes", "InfoFlora", "Tela Botanica", "Biodiv'AURA"] # Nom d'onglet corrigé
        tab_fa, tab_if, tab_tb, tab_ba = st.tabs(tab_names)

        with tab_fa:
            url_fa = florealpes_search(sp)
            if url_fa:
                st.markdown(f"**FloreAlpes** : [Fiche complète]({url_fa})")
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

        with tab_ba: # Utilisation de la variable d'onglet pour Biodiv'AURA
            url_ba_val = biodivaura_url(sp) # Appel de la fonction renommée
            st.markdown(f"**Biodiv'AURA** : [Accéder à l'atlas]({url_ba_val})") # Nom corrigé
            st.components.v1.iframe(src=url_ba_val, height=600)
else:
    st.info("Saisissez au moins une espèce pour démarrer la recherche.")
