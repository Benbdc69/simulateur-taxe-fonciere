"""Ouverture de Google Street View à partir des coordonnées déjà géocodées."""

from html import escape
from urllib.parse import urlencode

from shapely.errors import GEOSException
from shapely.geometry import shape
import streamlit as st
from streamlit.components.v1 import html

from cadastre import adresses
from session_calcul import cle_calcul


def url_street_view(adresse, parcelle=None):
    """Cible le point d’adresse ou, à défaut, un point situé dans la parcelle."""
    adresse = adresse or {}
    try:
        lat, lon = float(adresse.get('lat')), float(adresse.get('lon'))
    except (ValueError, TypeError):
        lat = lon = None
    if lat is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
        point = f'{lat:.7f},{lon:.7f}'
    else:
        geometry = (parcelle or {}).get('geometry')
        if (not isinstance(geometry, dict) or geometry.get('type') not in {'Polygon', 'MultiPolygon'}
                or not geometry.get('coordinates')):
            return None
        try:
            centre = shape(geometry).representative_point()
        except (GEOSException, ValueError, TypeError):
            return None
        if centre.is_empty or not (-90 <= centre.y <= 90 and -180 <= centre.x <= 180):
            return None
        point = f'{centre.y:.7f},{centre.x:.7f}'

    params = urlencode({'api': 1, 'map_action': 'pano', 'viewpoint': point})
    return 'https://www.google.com/maps/@?' + params


def afficher_lien_street_view(url):
    if not url:
        return
    # La fenêtre s’ouvre depuis le clic de l’utilisateur, directement dans le navigateur.
    # Le lien ordinaire reste utilisable si le navigateur bloque window.open.
    afficher_iframe = getattr(st, 'iframe', html)
    afficher_iframe(f"""
        <style>
        body {{ margin: 4px 0; font: 0.95rem system-ui, sans-serif; }}
        a {{ color: #246a9d; }}
        @media (prefers-color-scheme: dark) {{ a {{ color: #579ad0; }} }}
        </style>
        <a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer"
           aria-label="Voir le bâtiment dans Street View (nouvelle fenêtre)">
            Voir le bâtiment dans Street View ↗
        </a>
        <script>
        const lien = document.querySelector("a");
        lien.addEventListener("click", (event) => {{
            if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
            const fenetre = window.open("", "_blank", "popup,width=1100,height=750");
            if (!fenetre) return;
            fenetre.opener = null;
            fenetre.location.replace(lien.href);
            event.preventDefault();
        }});
        </script>
    """, height=30)


def afficher_street_view_adresse(texte, selection):
    if selection:
        afficher_lien_street_view(url_street_view(selection))
        return

    recherche = texte.strip()
    cle = cle_calcul('express_street_view_adresses')
    cle_choix = cle + '_choix'
    adresse_precedente, options = st.session_state.get(cle, (None, []))
    if recherche != adresse_precedente:
        st.session_state.pop(cle, None)
        st.session_state.pop(cle_choix, None)
        options = []
    if len(recherche) < 5:
        return

    if st.button('Localiser l’adresse pour Street View', key=cle + '_rechercher', type='tertiary'):
        st.session_state.pop(cle, None)
        st.session_state.pop(cle_choix, None)
        try:
            options = [adresse for adresse in adresses(recherche) if url_street_view(adresse)]
        except (ConnectionError, ValueError):
            st.warning('La recherche d’adresse est momentanément indisponible.')
            return
        st.session_state[cle] = recherche, options
        if not options:
            st.info('Adresse introuvable. Précisez le numéro, la voie et le code postal.')

    if len(options) == 1:
        st.caption(options[0]['libelle'])
        afficher_lien_street_view(url_street_view(options[0]))
    elif options:
        choix = st.selectbox('Adresse pour Street View', range(len(options)), index=None,
                             format_func=lambda i: options[i]['libelle'],
                             key=cle_choix)
        if choix is not None:
            afficher_lien_street_view(url_street_view(options[choix]))
