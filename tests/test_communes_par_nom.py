"""Résolution officielle des communes, homonymes et arrondissements cadastraux."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recherche_bien import rechercher_communes, code_arrondissement
from streamlit.testing.v1 import AppTest
from test_recherche_parcelle import ROW, champ, ROOT


class CommunesTests(unittest.TestCase):
    def test_codes_et_homonymes_preserves(self):
        response = Mock()
        response.json.return_value = [dict(nom='Saint-Sauveur', code='42005', codeDepartement='42'),
                                      dict(nom='Saint-Sauveur', code='70005', codeDepartement='70'),
                                      dict(nom='Commune corse', code='2A004', codeDepartement='2A'),
                                      dict(nom='Invalide', code='abc')]
        with patch('recherche_bien.requests.get', return_value=response) as api:
            rows = rechercher_communes('Saint-Sauveur')
            filtres = rechercher_communes('Saint-Sauveur', '42')
        self.assertEqual([r['insee'] for r in filtres], ['42005'])
        self.assertEqual({r['insee'] for r in rows}, {'42005', '70005', '2A004'})
        self.assertEqual(api.call_args.kwargs['params']['codeDepartement'], '42')
        self.assertEqual(api.call_args.kwargs['params']['nom'], 'Saint-Sauveur')

    def test_erreurs_service_et_reponses_invalides(self):
        with patch('recherche_bien.requests.get', side_effect=requests.Timeout):
            with self.assertRaisesRegex(ConnectionError, 'manuellement'):
                rechercher_communes('Lyon')
        response = Mock()
        response.json.return_value = {'erreur': 'réponse incorrecte'}
        with patch('recherche_bien.requests.get', return_value=response):
            with self.assertRaises(ConnectionError):
                rechercher_communes('Lyon')
        with patch('recherche_bien.requests.get') as api:
            for nom, dep in [('A', ''), ('Lyon', 'abc')]:
                with self.assertRaises(ValueError):
                    rechercher_communes(nom, dep)
            api.assert_not_called()

    def test_arrondissements_cadastraux(self):
        for code, nombre, debut, fin in [('75056', 20, '75101', '75120'), ('69123', 9, '69381', '69389'), ('13055', 16, '13201', '13216')]:
            self.assertEqual(code_arrondissement(code, 1), debut)
            self.assertEqual(code_arrondissement(code, nombre), fin)
            with self.assertRaises(ValueError):
                code_arrondissement(code, nombre + 1)
        self.assertEqual(code_arrondissement('69123', 7), '69387')


class CommunesUI(unittest.TestCase):
    def test_nom_commune_alimente_recherche_parcelle_dans_les_deux_parcours(self):
        rows = [dict(commune='Andrézieux-Bouthéon', insee='42005', departement='42'),
                dict(commune='Andrézieux autre commune', insee='70005', departement='70')]
        for page in ['parcours_express.py', 'parcours_habitation.py']:
            with self.subTest(page=page), patch.dict(os.environ, {'TF_LOCAL_MODE': '1'}), \
                 patch('recherche_bien.rechercher_communes', return_value=rows), \
                 patch('recherche_bien.rechercher_parcelle', return_value=[ROW]) as api:
                at = AppTest.from_file(str(ROOT / page)).run()
                champ(at.radio, 'Rechercher le bien par').set_value('Parcelle cadastrale').run()
                champ(at.text_input, 'Nom de la commune').input('Andrézieux')
                champ(at.button, 'Rechercher la commune').click().run()
                self.assertIsNone(champ(at.selectbox, 'Commune à retenir').value)
                self.assertIn('département 70', champ(at.selectbox, 'Commune à retenir').options[1])
                champ(at.selectbox, 'Commune à retenir').select(0).run()
                self.assertNotIn('Code INSEE cadastral de la commune', [x.label for x in at.text_input])
                champ(at.text_input, 'Section cadastrale').input('BI')
                champ(at.text_input, 'Numéro de parcelle').input('242')
                if page == 'parcours_express.py':
                    champ(at.selectbox, 'Catégorie du local').select('BUR2')
                    champ(at.number_input, 'P1 · Principale').set_value(100.)
                    bouton = 'Calculer mon estimation'
                else:
                    bouton = 'Rechercher cette parcelle'
                champ(at.button, bouton).click().run()
                self.assertFalse(at.exception, [str(x.value) for x in at.exception])
                api.assert_called_once_with('42005', 'BI', '0242', None)
                # Changer le nom invalide immédiatement le code et la recherche précédente.
                champ(at.text_input, 'Nom de la commune').input('Autre commune').run()
                self.assertNotIn('Commune à retenir', [x.label for x in at.selectbox])
                self.assertFalse(any('Commune retenue :' in x.value for x in at.caption))

    def test_arrondissement_obligatoire_apres_choix_lyon(self):
        rows = [dict(commune='Lyon', insee='69123', departement='69')]
        with patch.dict(os.environ, {'TF_LOCAL_MODE': '1'}), patch('recherche_bien.rechercher_communes', return_value=rows):
            at = AppTest.from_file(str(ROOT / 'parcours_habitation.py')).run()
            champ(at.radio, 'Rechercher le bien par').set_value('Parcelle cadastrale').run()
            champ(at.text_input, 'Nom de la commune').input('Lyon')
            champ(at.button, 'Rechercher la commune').click().run()
            champ(at.selectbox, 'Commune à retenir').select(0).run()
            self.assertIsNone(champ(at.selectbox, 'Arrondissement cadastral').value)
            champ(at.selectbox, 'Arrondissement cadastral').select(7).run()
            self.assertTrue(any('69387' in x.value for x in at.caption))
            self.assertFalse(at.exception)


if __name__ == '__main__':
    unittest.main()
