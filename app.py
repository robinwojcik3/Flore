#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Streamlit app : récupération automatisée d’informations botaniques

Auteur : Robin Wojcik (Améten)
Date   : 2025-05-27

Fonctionnement actualisé (v0.2)
--------------------------------
* La recherche FloreAlpes passe désormais **obligatoirement** par la page
  d’accueil (https://www.florealpes.com/index.php) puis soumet le champ `chaine`.
  Cela reproduit exactement le comportement utilisateur.
* Le reste du workflow (InfoFlora, Tela Botanica, OpenObs, Biodiv’RA) est inchangé.
"""

from __future__ import annotations

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin # Ajout de urljoin

# -----------------------------------------------------------------------------
# Configuration globale
# -----------------------------------------------------------------------------

st.set_page_config(page_title="Auto-scraper espèces", layout="wide", page_icon="🌿")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AutoScraper/0.2; +https://github.com/ameten)"
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
        r = sess.get(url, timeout=10)
        r.raise_for_status()
        return BeautifulSoup(r.text, "lxml")
    except requests.RequestException as e:
        st.warning(f"Erreur lors du téléchargement de {url}: {e}")
        return None


def florealpes_search(species: str) -> str | None:
    """Reproduction exacte de la recherche via le formulaire FloreAlpes."""
    st.write(f"[FloreAlpes Debug] Tentative de recherche pour : {species}")
    sess = requests.Session()
    sess.headers.update(HEADERS)

    # 1) Accueil (récupération éventuelle des cookies PHPSESSID etc.)
    try:
        index_url = "https://www.florealpes.com/index.php"
        st.write(f"[FloreAlpes Debug] Accès à : {index_url}")
        index_resp = sess.get(index_url, timeout=10)
        index_resp.raise_for_status()
        st.write(f"[FloreAlpes Debug] index.php récupéré, statut : {index_resp.status_code}, URL finale: {index_resp.url}")
    except requests.RequestException as e:
        st.warning(f"Impossible de charger la page d'accueil de FloreAlpes : {e}")
        return None

    # 2) Soumission du champ «chaine» — page résultat : recherche.php
    try:
        search_url_base = "https://www.florealpes.com/recherche.php"
        params_florealpes = {"chaine": species, "OK": "OK"}
        
        # Préparation de l'URL complète pour l'affichage debug
        req = requests.Request('GET', search_url_base, params=params_florealpes).prepare()
        st.write(f"[FloreAlpes Debug] Recherche : {req.url}")
        
        resp = sess.send(req, timeout=10) # Utilisation de send avec l'objet préparé
        resp.raise_for_status()
        st.write(f"[FloreAlpes Debug] Réponse de la recherche URL : {resp.url}, statut : {resp.status_code}")

        # Vérification simple d'un message "aucun résultat"
        if "aucun résultat à votre requête" in resp.text.lower() or "pas de résultats" in resp.text.lower():
            st.write(f"[FloreAlpes Debug] Message 'aucun résultat' trouvé pour '{species}'.")
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        page_title = soup.title.string if soup.title else "Pas de titre"
        st.write(f"[FloreAlpes Debug] Titre de la page de recherche : {page_title}")

        link_tag = soup.select_one("a[href^='fiche_']")
        
        if link_tag and link_tag.has_attr('href'):
            relative_url = link_tag['href']
            # Construction de l'URL absolue avec https://www.florealpes.com/ comme base
            absolute_url = urljoin("https://www.florealpes.com/", relative_url)
            st.write(f"[FloreAlpes Debug] Lien trouvé : {absolute_url}")
            return absolute_url
        else:
            st.write(f"[FloreAlpes Debug] Lien 'a[href^=fiche_]' non trouvé sur la page {resp.url}. Contenu (premiers 500 caractères) : {resp.text[:500]}")
            return None
            
    except requests.RequestException as e:
        st.warning(f"Erreur RequestException lors de la recherche FloreAlpes pour '{species}' : {e}")
        return None
    except Exception as e:
        st.error(f"Une erreur inattendue est survenue pendant la recherche FloreAlpes pour '{species}' : {e}")
        return None


def scrape_florealpes(url: str) -> tuple[str | None, pd.DataFrame | None]:
    """Extrait l’image principale et le tableau des caractéristiques."""
    st.write(f"[FloreAlpes Scrape Debug] Grattage de l'URL : {url}")
    soup = fetch_html(url) # fetch_html a déjà un st.warning en cas d'échec
    if soup is None:
        st.write(f"[FloreAlpes Scrape Debug] Échec du téléchargement ou de l'analyse de {url}")
        return None, None

    # Image
    img_tag = soup.select_one("a[href$='.jpg'] img") or soup.select_one("img[src$='.jpg']")
    img_url = None
    if img_tag and img_tag.has_attr('src'):
        img_src_relative = img_tag['src']
        # Les chemins d'images comme 'photos/XXXX.jpg' sont relatifs à la racine du site
        img_url = urljoin("https://www.florealpes.com/", img_src_relative)
        st.write(f"[FloreAlpes Scrape Debug] URL de l'image trouvée : {img_url}")
    else:
        st.write("[FloreAlpes Scrape Debug] Tag image non trouvé.")

    # Tableau de caractéristiques
    data_tbl = None
    tbl = soup.find("table", class_="fiche")
    if tbl:
        st.write("[FloreAlpes Scrape Debug] Tableau 'table.fiche' trouvé.")
        rows = [
            [td.get_text(strip=True) for td in tr.select("td")]
            for tr in tbl.select("tr")
            if len(tr.select("td")) == 2
        ]
        if rows:
            data_tbl = pd.DataFrame(rows, columns=["Attribut", "Valeur"])
            st.write(f"[FloreAlpes Scrape Debug] Tableau extrait avec {len(rows)} lignes.")
        else:
            st.write("[FloreAlpes Scrape Debug] Tableau trouvé mais aucune ligne extraite (longueur 2).")
    else:
        st.write("[FloreAlpes Scrape Debug] Tableau 'table.fiche' non trouvé.")
        # st.write(f"[FloreAlpes Scrape Debug] Contenu de la page (premiers 500 caractères) où le tableau est cherché : {soup.text[:500]}")


    return img_url, data_tbl


def infoflora_url(species: str) -> str:
    slug = species.lower().replace(" ", "-")
    return f"https://www.infoflora.ch/fr/flore/{slug}.html"


def tela_botanica_url(species: str) -> str | None:
    """Interroge l’API eFlore pour récupérer l’identifiant num_nomen."""
    api = (
        "https://api.tela-botanica.org/service:eflore:0.1/" "names:search?mode=exact&taxon="
        f"{quote_plus(species)}"
    )
    try:
        data = requests.get(api, headers=HEADERS, timeout=10).json()
        if not data:
            return None
        nn = data[0].get("num_nomen")
        return f"https://www.tela-botanica.org/bdtfx-nn-{nn}-synthese" if nn else None
    except requests.RequestException:
        return None


def openobs_embed(species: str) -> str:
    """HTML pour afficher la carte OpenObs dans un iframe."""
    return (
        "<iframe src='https://openobs.mnhn.fr/map.html?sp="
        f"{quote_plus(species)}' width='100%' height='500' frameborder='0'></iframe>"
    )


def biodivra_url(species: str) -> str:
    return f"https://atlas.biodiversite-auvergne-rhone-alpes.fr/recherche?keyword={quote_plus(species)}"

# -----------------------------------------------------------------------------
# Interface utilisateur
# -----------------------------------------------------------------------------

st.title("Recherche automatisée d’informations sur les espèces")
st.markdown("Saisissez les noms scientifiques (un par ligne) puis lancez la recherche.")

input_txt = st.text_area(
    "Liste d’espèces", placeholder="Lamium purpureum\nTrifolium alpinum", height=180
)

if st.button("Lancer la recherche", type="primary") and input_txt.strip():
    species_list = [s.strip() for s in input_txt.splitlines() if s.strip()]

    for sp in species_list:
        st.subheader(sp)
        # Ajout d'un expander pour les logs de débogage de FloreAlpes
        with st.expander(f"Logs de débogage FloreAlpes pour {sp}", expanded=False):
            # Les st.write des fonctions seront affichés ici si appelés dans ce contexte
            pass

        tab_fa, tab_if, tab_tb, tab_obs, tab_bio = st.tabs(
            [
                "FloreAlpes",
                "InfoFlora",
                "Tela Botanica",
                "OpenObs (carte)",
                "Biodiv'RA",
            ]
        )

        # ---- FloreAlpes ------------------------------------------------------
        with tab_fa:
            st.write(f"Recherche de '{sp}' sur FloreAlpes...")
            url_fa = florealpes_search(sp) # Les logs de cette fonction s'afficheront
            if url_fa:
                st.success(f"URL FloreAlpes trouvée : {url_fa}")
                st.markdown(f"[Fiche complète]({url_fa})")
                img, tbl = scrape_florealpes(url_fa) # Les logs de cette fonction s'afficheront
                if img:
                    st.image(img, caption=sp, use_column_width=True)
                else:
                    st.warning("Image non trouvée sur la fiche FloreAlpes.")
                if tbl is not None and not tbl.empty:
                    st.dataframe(tbl, hide_index=True)
                elif tbl is not None and tbl.empty:
                     st.info("Tableau des caractéristiques trouvé mais vide sur FloreAlpes.")
                else:
                    st.warning("Tableau des caractéristiques non trouvé sur la fiche FloreAlpes.")
            else:
                st.error(f"Fiche introuvable sur FloreAlpes pour '{sp}'. Vérifiez les logs de débogage ci-dessus.")

        # ---- InfoFlora -------------------------------------------------------
        with tab_if:
            url_if = infoflora_url(sp)
            st.markdown(f"[Fiche InfoFlora]({url_if})")
            st.components.v1.iframe(src=url_if, height=600)

        # ---- Tela Botanica ---------------------------------------------------
        with tab_tb:
            url_tb = tela_botanica_url(sp)
            if url_tb:
                st.markdown(f"[Synthèse]({url_tb})")
                st.components.v1.iframe(src=url_tb, height=600)
            else:
                st.warning(f"Aucune correspondance via l’API eFlore pour '{sp}'.")

        # ---- OpenObs ---------------------------------------------------------
        with tab_obs:
            st.write("Répartition nationale (OpenObs)")
            st.components.v1.html(openobs_embed(sp), height=600, scrolling=True)

        # ---- Biodiv'RA -------------------------------------------------------
        with tab_bio:
            url_bio = biodivra_url(sp)
            st.markdown(f"[Accéder à l’atlas]({url_bio})")
            st.components.v1.iframe(src=url_bio, height=600)
else:
    st.info("Saisissez au moins une espèce pour démarrer la recherche.")
