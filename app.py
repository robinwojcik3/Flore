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
from urllib.parse import quote_plus

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
    except requests.RequestException:
        return None


def florealpes_search(species: str) -> str | None:
    """Reproduction exacte de la recherche via le formulaire FloreAlpes."""

    sess = requests.Session()
    sess.headers.update(HEADERS)

    # 1) Accueil (récupération éventuelle des cookies PHPSESSID etc.)
    try:
        sess.get("https://www.florealpes.com/index.php", timeout=10)
    except requests.RequestException:
        return None

    # 2) Soumission du champ «chaine» — page résultat : recherche.php
    try:
        resp = sess.get(
            "https://www.florealpes.com/recherche.php",
            params={"rech": species, "L": "0"},
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        link = soup.select_one("a[href^='fiche_']")
        return f"https://www.florealpes.com/{link['href']}" if link else None
    except requests.RequestException:
        return None


def scrape_florealpes(url: str) -> tuple[str | None, pd.DataFrame | None]:
    """Extrait l’image principale et le tableau des caractéristiques."""
    soup = fetch_html(url)
    if soup is None:
        return None, None

    # Image
    img_tag = soup.select_one("a[href$='.jpg'] img") or soup.select_one("img[src$='.jpg']")
    img_url = (
        f"https://www.florealpes.com/{img_tag['src'].lstrip('/')}" if img_tag else None
    )

    # Tableau de caractéristiques
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
            url_fa = florealpes_search(sp)
            if url_fa:
                st.markdown(f"[Fiche complète]({url_fa})")
                img, tbl = scrape_florealpes(url_fa)
                if img:
                    st.image(img, caption=sp, use_column_width=True)
                if tbl is not None:
                    st.dataframe(tbl, hide_index=True)
            else:
                st.warning("Fiche introuvable sur FloreAlpes.")

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
                st.warning("Aucune correspondance via l’API eFlore.")

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
