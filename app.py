#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit app : récupération automatisée d'informations botaniques

Auteur : Robin Wojcik (Améten)
Date   : 2025-05-28

Fonctionnement actualisé (v0.5)
--------------------------------
* FloreAlpes utilise une approche améliorée avec requests pour extraire les fiches
* Analyse plus robuste des résultats de recherche
* Extraction améliorée des données depuis les fiches
"""

from __future__ import annotations

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin, urlparse
import re
import time

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


def florealpes_search_improved(species: str) -> str | None:
    """Recherche améliorée sur FloreAlpes avec analyse des résultats."""
    sess = requests.Session()
    sess.headers.update(HEADERS)
    
    try:
        # D'abord charger la page d'accueil pour établir la session
        index_url = "https://www.florealpes.com/index.php"
        index_resp = sess.get(index_url, timeout=15)
        index_resp.raise_for_status()
        
        # Ensuite faire la recherche
        search_url = "https://www.florealpes.com/recherche.php"
        params = {"chaine": species}
        resp = sess.get(search_url, params=params, timeout=15)
        resp.raise_for_status()
        
        # Analyser les résultats
        soup = BeautifulSoup(resp.text, "lxml")
        
        # Chercher tous les liens vers les fiches
        fiche_links = soup.find_all("a", href=re.compile(r"fiche_.*\.php"))
        
        if not fiche_links:
            # Essayer une autre approche - chercher dans le tableau de résultats
            results_table = soup.find("table", {"class": ["resultats", "results"]})
            if results_table:
                fiche_links = results_table.find_all("a", href=re.compile(r"fiche_"))
        
        if fiche_links:
            # Chercher la meilleure correspondance
            species_lower = species.lower().replace(" ", "")
            best_match = None
            
            for link in fiche_links:
                # Récupérer le contexte autour du lien (la ligne du tableau)
                parent = link.parent
                while parent and parent.name != "tr":
                    parent = parent.parent
                
                if parent:
                    row_text = parent.get_text(strip=True).lower().replace(" ", "")
                    if species_lower in row_text:
                        best_match = link
                        break
            
            # Si pas de correspondance exacte, prendre le premier
            if not best_match and fiche_links:
                best_match = fiche_links[0]
            
            if best_match:
                href = best_match.get('href')
                if href:
                    return urljoin("https://www.florealpes.com/", href)
        
        return None
        
    except Exception as e:
        st.warning(f"Erreur lors de la recherche FloreAlpes pour '{species}': {e}")
        return None


def scrape_florealpes_enhanced(url: str) -> tuple[str | None, pd.DataFrame | None, dict]:
    """Extrait de manière améliorée les données depuis une fiche FloreAlpes."""
    soup = fetch_html(url)
    if soup is None:
        return None, None, {}
    
    # Extraire l'image principale
    img_url = None
    # Chercher d'abord dans les liens
    img_link = soup.find("a", href=re.compile(r"\.jpg$", re.I))
    if img_link:
        img_tag = img_link.find("img")
        if img_tag and img_tag.has_attr('src'):
            img_url = urljoin("https://www.florealpes.com/", img_tag['src'])
    else:
        # Chercher directement les images
        img_tag = soup.find("img", src=re.compile(r"\.jpg$", re.I))
        if img_tag and img_tag.has_attr('src'):
            img_url = urljoin("https://www.florealpes.com/", img_tag['src'])
    
    # Extraire le tableau des caractéristiques
    data_tbl = None
    tbl = soup.find("table", class_="fiche")
    if not tbl:
        # Essayer d'autres sélecteurs
        tbl = soup.find("table", attrs={"border": "0", "cellpadding": True})
    
    if tbl:
        rows = []
        for tr in tbl.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if key and value:
                    rows.append([key, value])
        
        if rows:
            data_tbl = pd.DataFrame(rows, columns=["Attribut", "Valeur"])
    
    # Extraire des informations supplémentaires
    extra_info = {}
    
    # Nom scientifique
    sci_name = soup.find(["h1", "h2", "b"], string=re.compile(r"^[A-Z][a-z]+ [a-z]+"))
    if sci_name:
        extra_info["nom_scientifique"] = sci_name.get_text(strip=True)
    
    # Famille
    famille_pattern = re.compile(r"Famille\s*:\s*([^,\n]+)", re.I)
    famille_match = famille_pattern.search(soup.get_text())
    if famille_match:
        extra_info["famille"] = famille_match.group(1).strip()
    
    # Description
    desc_section = soup.find(text=re.compile(r"Description|Caractères", re.I))
    if desc_section:
        desc_parent = desc_section.parent
        desc_text = desc_parent.find_next_sibling()
        if desc_text:
            extra_info["description"] = desc_text.get_text(strip=True)[:500] + "..."
    
    return img_url, data_tbl, extra_info


def infoflora_url(species: str) -> str:
    slug = species.lower().replace(" ", "-")
    return f"https://www.infoflora.ch/fr/flore/{slug}.html"


def tela_botanica_url(species: str) -> str | None:
    """Interroge l'API eFlore pour récupérer l'identifiant num_nomen."""
    api_url = f"https://api.tela-botanica.org/service:eflore:0.1/names:search?mode=exact&taxon={quote_plus(species)}"
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        response = s.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            nn = data[0].get("num_nomen")
            return f"https://www.tela-botanica.org/bdtfx-nn-{nn}-synthese" if nn else None
        return None
    except Exception:
        return None


def get_taxref_cd_ref(species_name: str) -> str | None:
    """Interroge l'API TaxRef pour récupérer le CD_REF."""
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
        if data and "_embedded" in data and "taxa" in data["_embedded"]:
            taxa = data["_embedded"]["taxa"]
            if taxa:
                # Chercher correspondance exacte
                normalized_name = species_name.strip().lower()
                for taxon in taxa:
                    if taxon.get("scientificName", "").strip().lower() == normalized_name:
                        return str(taxon.get("id"))
                # Sinon prendre le premier
                return str(taxa[0].get("id")) if taxa[0].get("id") else None
        return None
    except Exception:
        return None


def openobs_embed(species: str) -> str:
    """HTML pour afficher la carte OpenObs."""
    cd_ref = get_taxref_cd_ref(species)
    if cd_ref:
        iframe_url = f"https://openobs.mnhn.fr/redirect/inpn/taxa/{cd_ref}?view=map"
        return f"<iframe src='{iframe_url}' width='100%' height='450' frameborder='0'></iframe>"
    else:
        return f"""
        <div style='padding: 20px; background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 5px;'>
            <p style='margin: 0; color: #856404;'>
                ⚠️ Impossible de récupérer l'identifiant TaxRef pour '{species}'.
                La carte de répartition n'est pas disponible.
            </p>
        </div>
        """


def biodivaura_url(species: str) -> str:
    """Construit l'URL pour Biodiv'AURA Atlas."""
    cd_ref = get_taxref_cd_ref(species)
    if cd_ref:
        return f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/espece/{cd_ref}"
    else:
        return f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/recherche?keyword={quote_plus(species)}"


# -----------------------------------------------------------------------------
# Interface utilisateur
# -----------------------------------------------------------------------------

# En-tête avec colonnes
col_keep, col_title = st.columns([1, 3], gap="large")

with col_keep:
    st.markdown("##### 📝 Notes")
    keep_url = "https://keep.google.com/#NOTE/1dHuU90VKwWzZAgoXzTsjNiRp_QgDB1BRCfthK5hH-23Vxb_A86uTPrroczclhg"
    st.markdown(f"[Ouvrir la note Keep]({keep_url})")
    st.caption("S'ouvre dans un nouvel onglet")

with col_title:
    st.title("🌿 Recherche d'informations botaniques")
    st.markdown("Récupération automatisée depuis FloreAlpes, InfoFlora, Tela Botanica et Biodiv'AURA")

st.markdown("---")

# Zone de saisie
input_txt = st.text_area(
    "**Entrez les noms scientifiques** (un par ligne)", 
    placeholder="Lamium purpureum\nTrifolium alpinum\nGentiana lutea",
    height=150,
    help="Utilisez les noms scientifiques complets (genre + espèce)"
)

# Bouton de recherche
if st.button("🔍 Lancer la recherche", type="primary", use_container_width=True):
    if input_txt.strip():
        species_list = [s.strip() for s in input_txt.splitlines() if s.strip()]
        
        # Barre de progression
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, sp in enumerate(species_list):
            progress = (idx + 1) / len(species_list)
            progress_bar.progress(progress)
            status_text.text(f"Recherche en cours pour : {sp}")
            
            # Conteneur pour chaque espèce
            with st.container():
                st.subheader(f"📌 {sp}")
                
                # Colonnes principales
                col_map, col_info = st.columns([3, 2])
                
                with col_map:
                    st.markdown("**Carte de répartition (OpenObs)**")
                    html_openobs = openobs_embed(sp)
                    st.components.v1.html(html_openobs, height=460)
                
                with col_info:
                    st.info("""
                    **Sources consultées :**
                    - 🌺 FloreAlpes : Photos et caractéristiques
                    - 🇨🇭 InfoFlora : Distribution en Suisse
                    - 🌿 Tela Botanica : Base eFlore
                    - 🗺️ Biodiv'AURA : Atlas régional
                    """)
                
                # Onglets pour les différentes sources
                tabs = st.tabs(["🌺 FloreAlpes", "🇨🇭 InfoFlora", "🌿 Tela Botanica", "🗺️ Biodiv'AURA"])
                
                # FloreAlpes
                with tabs[0]:
                    with st.spinner("Recherche sur FloreAlpes..."):
                        url_fa = florealpes_search_improved(sp)
                    
                    if url_fa:
                        st.markdown(f"✅ [Accéder à la fiche complète]({url_fa})")
                        
                        with st.spinner("Extraction des données..."):
                            img, tbl, extra = scrape_florealpes_enhanced(url_fa)
                        
                        col1, col2 = st.columns([1, 1])
                        
                        with col1:
                            if img:
                                st.image(img, caption=f"{sp}", use_column_width=True)
                            else:
                                st.warning("Image non disponible")
                        
                        with col2:
                            if extra:
                                for key, value in extra.items():
                                    st.markdown(f"**{key.replace('_', ' ').title()}:** {value}")
                        
                        if tbl is not None and not tbl.empty:
                            st.markdown("**Caractéristiques détaillées:**")
                            st.dataframe(tbl, hide_index=True, use_container_width=True)
                    else:
                        st.error(f"❌ Aucune fiche trouvée pour '{sp}'")
                
                # InfoFlora
                with tabs[1]:
                    url_if = infoflora_url(sp)
                    st.markdown(f"🔗 [Ouvrir sur InfoFlora]({url_if})")
                    with st.expander("Afficher la page InfoFlora"):
                        st.components.v1.iframe(src=url_if, height=600)
                
                # Tela Botanica
                with tabs[2]:
                    with st.spinner("Recherche dans eFlore..."):
                        url_tb = tela_botanica_url(sp)
                    
                    if url_tb:
                        st.markdown(f"✅ [Accéder à la synthèse eFlore]({url_tb})")
                        with st.expander("Afficher la page Tela Botanica"):
                            st.components.v1.iframe(src=url_tb, height=600)
                    else:
                        st.warning("❌ Espèce non trouvée dans la base eFlore")
                
                # Biodiv'AURA
                with tabs[3]:
                    url_ba = biodivaura_url(sp)
                    st.markdown(f"🔗 [Ouvrir sur Biodiv'AURA]({url_ba})")
                    with st.expander("Afficher la page Biodiv'AURA"):
                        st.components.v1.iframe(src=url_ba, height=600)
                
                st.markdown("---")
        
        # Fin de la recherche
        progress_bar.empty()
        status_text.empty()
        st.success(f"✅ Recherche terminée pour {len(species_list)} espèce(s)")
    else:
        st.warning("⚠️ Veuillez saisir au moins un nom d'espèce")
else:
    # Message d'accueil
    st.info("""
    👋 **Bienvenue !**
    
    Cette application permet de récupérer automatiquement des informations botaniques 
    depuis plusieurs sources de référence. 
    
    **Comment utiliser l'application :**
    1. Entrez un ou plusieurs noms scientifiques d'espèces (un par ligne)
    2. Cliquez sur "Lancer la recherche"
    3. Consultez les résultats dans les différents onglets
    
    **Exemple :** Essayez avec *Gentiana lutea* ou *Arnica montana*
    """)

# Footer
st.markdown("---")
st.caption("💡 Astuce : Les résultats sont mis en cache pendant 24h pour améliorer les performances")
