"""Suggestions : seuil de recherche, choix explicite et coordonnées conservées."""
import os
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from saisie_adresse import suggestions_adresses
from vue_rue import url_street_view
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
ADRESSE = dict(libelle='10 Rue de la Paix 75002 Paris', commune='Paris', insee='75102', code_postal='75002', lon=2.33, lat=48.87)


class SuggestionsTests(unittest.TestCase):
    def test_seuil_et_coordonnees_conservees(self):
        with patch('saisie_adresse.adresses', return_value=[ADRESSE]) as api:
            self.assertEqual(suggestions_adresses('10 r'), [])
            api.assert_not_called()
            self.assertEqual(suggestions_adresses('10 rue de la Paix'), [(ADRESSE['libelle'], ADRESSE)])
            api.assert_called_once_with('10 rue de la Paix')

    def test_habitation_selection_sans_second_geocodage_et_invalidation(self):
        with patch.dict(os.environ, {'TF_LOCAL_MODE':'1'}), patch('saisie_adresse.st_searchbox', return_value=ADRESSE) as champ, patch('cadastre.adresses') as api:
            at=AppTest.from_file(str(ROOT/'parcours_habitation.py')).run()
            next(x for x in at.button if x.label=='Rechercher cette adresse').click().run()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['hab_adresses'], [ADRESSE])
            self.assertFalse(next(x for x in at.button if x.label=='Continuer vers les surfaces').disabled)
            api.assert_not_called()
            champ.return_value={**ADRESSE, 'lon': 2.34}
            at.run()
            self.assertNotIn('Continuer vers les surfaces', [x.label for x in at.button])
            champ.return_value='nouvelle adresse en cours de frappe'
            at.run()
            self.assertNotIn('Continuer vers les surfaces', [x.label for x in at.button])

    def test_professionnel_reutilise_adresse_selectionnee(self):
        parcelle = dict(insee='75102', departement='75', section='AB', numero='0001', prefixe='000', recherche='Parcelle voisine — confirmation obligatoire', distance_m=5)
        with patch.dict(os.environ, {'TF_LOCAL_MODE':'1'}), patch('saisie_adresse.st_searchbox', return_value=ADRESSE), patch('cadastre.adresses') as api, patch('cadastre.parcelles_a_l_adresse', return_value=[parcelle]) as parcelles:
            at=AppTest.from_file(str(ROOT/'parcours_express.py')).run()
            lien = next(element.proto.srcdoc for element in at.get('iframe')
                        if 'Voir le bâtiment dans Street View' in element.proto.srcdoc)
            self.assertIn('map_action=pano', lien)
            self.assertIn('viewpoint=48.8700000%2C2.3300000', lien)
            next(x for x in at.selectbox if x.label=='Catégorie du local').select('BUR2')
            next(x for x in at.number_input if x.label=='P1 · Principale').set_value(100.)
            next(x for x in at.button if x.label=='Calculer mon estimation').click().run()
            self.assertFalse(at.exception)
            parcelles.assert_called_once_with(ADRESSE)
            api.assert_not_called()
            self.assertEqual(at.session_state['_parcelles_attente']['candidats'][0][0], ADRESSE)

    def test_professionnel_street_view_adresse_manuelle(self):
        with patch('vue_rue.adresses', return_value=[ADRESSE, {**ADRESSE, 'libelle': '11 Rue de la Paix', 'lon': 2.34}]) as api:
            at = AppTest.from_file(str(ROOT/'parcours_express.py')).run()
            next(x for x in at.radio if x.label == 'Saisie de l’adresse').set_value('Saisie manuelle').run()
            next(x for x in at.text_input if x.label == 'Adresse complète du bien').input('11 Rue de la Paix').run()
            api.assert_not_called()
            next(x for x in at.button if x.label == 'Localiser l’adresse pour Street View').click().run()
            api.assert_called_once_with('11 Rue de la Paix')
            next(x for x in at.selectbox if x.label == 'Adresse pour Street View').select(1).run()
            self.assertTrue(any('viewpoint=48.8700000%2C2.3400000' in x.proto.srcdoc for x in at.get('iframe')))
            next(x for x in at.text_input if x.label == 'Adresse complète du bien').input('12 Rue de la Paix').run()
            self.assertFalse(any('map_action=pano' in x.proto.srcdoc for x in at.get('iframe')))
            self.assertFalse(at.exception)

    def test_street_view_coordonnees_de_la_parcelle_en_repli(self):
        parcelle = {'geometry': {'type': 'Polygon', 'coordinates': [[[2, 48], [4, 48], [4, 50], [2, 50], [2, 48]]]}}
        url = urlsplit(url_street_view({'lat': 100, 'lon': 200}, parcelle))
        self.assertEqual(url.hostname, 'www.google.com')
        self.assertEqual(parse_qs(url.query), {'api': ['1'], 'map_action': ['pano'], 'viewpoint': ['49.0000000,3.0000000']})
        self.assertIsNone(url_street_view({'lat': 'nan', 'lon': 2}))

    def test_service_indisponible_et_repli_manuel(self):
        def composant(recherche, **kwargs):
            recherche('adresse complète')
            return None
        with patch.dict(os.environ, {'TF_LOCAL_MODE':'1'}), patch('saisie_adresse.st_searchbox', side_effect=composant), patch('saisie_adresse.adresses', side_effect=ConnectionError('indisponible')):
            at=AppTest.from_file(str(ROOT/'parcours_habitation.py')).run()
            self.assertFalse(at.exception)
            self.assertTrue(any('Suggestions indisponibles' in x.value for x in at.warning))
            next(x for x in at.radio if x.label=='Saisie de l’adresse').set_value('Saisie manuelle').run()
            self.assertIn('Adresse du bien', [x.label for x in at.text_input])


if __name__=='__main__':
    unittest.main()
