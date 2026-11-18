"""Mesures indicatives dessinées sur les fonds IGN du parcours professionnel."""
from hashlib import sha256

import folium
from folium.plugins import Draw
from pyproj import Geod
from shapely import orient_polygons
from shapely.errors import GEOSException
from shapely.geometry import shape
from shapely.ops import unary_union
import streamlit as st
from streamlit_folium import st_folium

from cadastre import adresses, parcelles_a_l_adresse
from recherche_bien import identifier_par_reference, libelle_parcelle
from session_calcul import cle_calcul

GEODE = Geod(ellps='WGS84')
WMTS = ('https://data.geopf.fr/wmts?SERVICE=WMTS&VERSION=1.0.0&REQUEST=GetTile'
        '&LAYER={couche}&STYLE=normal&TILEMATRIXSET=PM&FORMAT=image/{format_image}'
        '&TILEMATRIX={{z}}&TILEROW={{y}}&TILECOL={{x}}')


def surface_dessinee(dessins):
    polygones = []
    for dessin in dessins:
        polygone = shape(dessin['geometry'])
        if polygone.geom_type != 'Polygon' or polygone.is_empty or not polygone.is_valid:
            raise ValueError('Retracez les contours de manière à ce que leurs bords ne se croisent pas.')
        polygones.append(polygone)
    if not polygones:
        return 0.0
    emprise = orient_polygons(unary_union(polygones))
    surface, _ = GEODE.geometry_area_perimeter(emprise)
    return round(abs(surface), 2)


def carte_mesure(parcelle, cle):
    contours = shape(parcelle['geometry'])
    ouest, sud, est, nord = contours.bounds
    carte = folium.Map(location=[(sud+nord)/2, (ouest+est)/2], tiles=None, max_zoom=20)
    folium.TileLayer(WMTS.format(couche='ORTHOIMAGERY.ORTHOPHOTOS', format_image='jpeg'), name='Photo aérienne IGN',
                     attr='IGN – Géoplateforme', max_native_zoom=19, max_zoom=20).add_to(carte)
    folium.TileLayer(WMTS.format(couche='GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2', format_image='png'), name='Plan IGN',
                     attr='IGN – Géoplateforme', max_native_zoom=19, max_zoom=20, show=False).add_to(carte)
    folium.GeoJson(parcelle['geometry'], name='Parcelle cadastrale',
                   style_function=lambda _: {'color': '#e99616', 'weight': 3, 'fillOpacity': 0.08}).add_to(carte)
    carte.fit_bounds([[sud, ouest], [nord, est]], padding=(40, 40), max_zoom=19)
    folium.LayerControl().add_to(carte)
    dessin = Draw(show_geometry_on_click=False, draw_options={
        'polyline': False, 'marker': False, 'circle': False, 'circlemarker': False,
        'polygon': {'allowIntersection': False}, 'rectangle': True,
    })
    cdn = 'https://cdn.jsdelivr.net/npm/leaflet-draw@1.0.4/dist/leaflet.draw'
    dessin.default_js = [('leaflet_draw_js', cdn + '.js')]
    dessin.default_css = [('leaflet_draw_css', cdn + '.css')]
    dessin.add_to(carte)
    resultat = st_folium(carte, key=cle, use_container_width=True, height=410,
                        returned_objects=['all_drawings'])
    try:
        return surface_dessinee(resultat.get('all_drawings') or [])
    except (ValueError, KeyError, TypeError, GEOSException):
        st.warning('Le tracé ne forme pas un polygone valide. Supprimez-le ou corrigez-le sur la carte.')
        return 0.0


def reporter_surfaces(surfaces):
    st.session_state.update({cle_calcul('express_' + cle): valeur for cle, valeur in surfaces.items()})


def afficher_mesures(mode, reference, adresse, selection):
    with st.expander('Mesurer le local ou le stationnement sur la carte'):
        st.caption('Tracez le contour de la zone occupée. Le contour cadastral sert de repère. La mesure est indicative et doit être vérifiée avant déclaration.')
        adresse_courante = (mode, reference, adresse, selection)
        identifiant = sha256(repr(adresse_courante).encode()).hexdigest()[:16]
        cle = cle_calcul('mesure_cadastrale')
        if st.button('Charger la carte du bien', key=cle + '_charger'):
            st.session_state.pop(cle, None)
            try:
                if mode == 'Parcelle cadastrale':
                    parcelles = [item['parcelle'] for item in identifier_par_reference(reference)]
                else:
                    if not selection and len(adresse.strip()) < 6:
                        raise ValueError('Indiquez l’adresse complète du bien.')
                    choix_adresses = [selection] if selection else adresses(adresse)
                    if not choix_adresses:
                        raise ValueError('Adresse introuvable. Précisez la voie ou recherchez par référence cadastrale.')
                    parcelles = [
                        {**parcelle, 'adresse_carte': option['libelle']}
                        for option in choix_adresses[:3]
                        for parcelle in parcelles_a_l_adresse(option)
                    ]
                parcelles = [p for p in parcelles if (p.get('geometry') or {}).get('type') in {'Polygon', 'MultiPolygon'}]
                st.session_state[cle] = identifiant, parcelles
            except (ValueError, ConnectionError) as exc:
                st.warning(str(exc))

        cible, parcelles = st.session_state.get(cle, (None, []))
        if cible != identifiant:
            return
        if not parcelles:
            st.info('Aucun contour cadastral trouvé. Vérifiez la référence ou saisissez les surfaces ci-dessous.')
            return
        choix = st.selectbox('Parcelle à afficher', range(len(parcelles)), index=0 if len(parcelles) == 1 else None,
                             format_func=lambda i: ' · '.join(filter(None, (parcelles[i].get('adresse_carte'),
                                                                             libelle_parcelle(parcelles[i])))),
                             key=f'{cle}_{identifiant}_parcelle')
        if choix is None:
            return
        cle_carte = f'{cle}_{identifiant}_{choix}'
        local, parking = st.tabs(['Emprise du local', 'Stationnement non couvert'])
        with local:
            st.write('Tracez la partie du bâtiment occupée par le local. Utilisez les outils polygone ou rectangle à gauche de la carte.')
            emprise = carte_mesure(parcelles[choix], cle_carte + '_local')
            niveaux = st.number_input('Nombre de niveaux occupés, rez-de-chaussée compris', min_value=1, value=1,
                                      key=cle_carte + '_niveaux')
            st.caption('La multiplication suppose une emprise identique à chaque niveau occupé. Si les niveaux diffèrent, vérifiez le total à partir des plans.')
            total = round(float(emprise) * niveaux, 2)
            if total > 0:
                st.metric('Surface à ventiler entre P1 et P2', f'{total:g} m²')
                st.caption(f'{emprise:g} m² d’emprise × {niveaux} niveau(x)')
                if total <= 1_000_000:
                    p1 = st.number_input('Part du total à affecter à P1 (m²)', min_value=0.0, max_value=total,
                                         value=None, step=0.01, key=f'{cle_carte}_p1_{total}')
                    if p1 is not None:
                        p2 = round(total - p1, 2)
                        st.write(f'P2 · Solde de la surface couverte : **{p2:g} m²**')
                        st.button('Reporter P1 et P2 dans l’estimation', key=cle_carte + '_report_local',
                                  on_click=reporter_surfaces, args=({'P1': p1, 'P2': p2},))
        with parking:
            st.write('Tracez les zones de stationnement non couvertes rattachées au local. Vous pouvez dessiner plusieurs zones.')
            pk2 = carte_mesure(parcelles[choix], cle_carte + '_parking')
            if pk2 > 0:
                st.metric('Stationnement non couvert mesuré', f'{pk2:g} m²')
                if pk2 <= 1_000_000:
                    st.button('Reporter dans PK2', key=cle_carte + '_report_pk2',
                              on_click=reporter_surfaces, args=({'PK2': pk2},))
