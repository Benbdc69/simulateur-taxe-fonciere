"""Référence cadastrale sans adresse : validation, identité et parcours interactifs."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recherche_bien import normaliser_reference, identifier_par_reference
from dossier_habitation import calculer_scenarios
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = dict(commune='Andrézieux-Bouthéon', insee='42005', prefixe='000', section='BI', numero='242')
ROW = dict(code_dep='42', code_com='005', com_abs='000', section='BI', numero='0242', idu='42005000BI0242', nom_com='Andrézieux-Bouthéon')


def champ(elements, label):
    return next(x for x in elements if x.label == label)


class RechercheParcelleTests(unittest.TestCase):
    def test_normalisation_et_requete_sans_geocodage(self):
        with patch('recherche_bien.rechercher_parcelle', return_value=[ROW, ROW]) as api:
            r = identifier_par_reference({**REFERENCE, 'prefixe': '0', 'section': 'bi'})
        api.assert_called_once_with('42005', 'BI', '0242', '000')
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]['parcelle']['prefixe'], '000')
        self.assertEqual(r[0]['parcelle']['numero'], '0242')
        self.assertNotIn('lon', r[0])
        self.assertIn('BI 0242', r[0]['libelle'])

    def test_correspondances_inexactes_ecartees(self):
        rows = [{**ROW, 'code_com': '006'}, {**ROW, 'numero': '0243'}, {**ROW, 'section': 'AB'},
                {**ROW, 'com_abs': '123'}, ROW]
        with patch('recherche_bien.rechercher_parcelle', return_value=rows):
            self.assertEqual(len(identifier_par_reference(REFERENCE)), 1)

    def test_prefixe_inconnu_conserve_plusieurs_parcelles(self):
        with patch('recherche_bien.rechercher_parcelle', return_value=[ROW, {**ROW, 'com_abs': '123'}]) as api:
            r = identifier_par_reference({**REFERENCE, 'prefixe': ''})
        self.assertEqual(api.call_args.args[-1], None)
        self.assertEqual({x['parcelle']['prefixe'] for x in r}, {'000', '123'})

    def test_codes_corse_dom_et_section_une_lettre(self):
        self.assertEqual(normaliser_reference({**REFERENCE, 'insee': '2a004', 'section': 'A'})['section'], '0A')
        self.assertEqual(normaliser_reference({**REFERENCE, 'section': '1'})['section'], '01')
        for code, dep, commune in [('2A004', '2A', '004'), ('97101', '971', '01')]:
            with self.subTest(code=code), patch('recherche_bien.rechercher_parcelle', return_value=[{**ROW, 'code_dep': dep, 'code_com': commune} ]):
                r = identifier_par_reference({**REFERENCE, 'insee': code})
                self.assertEqual(r[0]['insee'], code)
                self.assertEqual(r[0]['parcelle']['departement'], dep)

    def test_entrees_invalides_avant_tout_appel(self):
        for key, value in [('insee', '1234'), ('insee', '../42'), ('section', ''), ('section', 'ABC'),
                           ('numero', '0'), ('numero', '-1'), ('numero', '10000'), ('prefixe', 'ABC'), ('commune', '')]:
            with self.subTest(key=key, value=value), patch('recherche_bien.rechercher_parcelle') as api:
                with self.assertRaises(ValueError):
                    identifier_par_reference({**REFERENCE, key: value})
                api.assert_not_called()

    def test_absence_et_indisponibilite_non_transformees_en_resultat(self):
        with patch('recherche_bien.rechercher_parcelle', return_value=[]):
            self.assertEqual(identifier_par_reference(REFERENCE), [])
        with patch('recherche_bien.rechercher_parcelle', side_effect=ConnectionError('indisponible')):
            with self.assertRaises(ConnectionError):
                identifier_par_reference(REFERENCE)

    def test_dossier_habitation_accepte_parcelle_sans_adresse(self):
        with patch('recherche_bien.rechercher_parcelle', return_value=[ROW]):
            adr = identifier_par_reference(REFERENCE)[0]
        saisie = dict(nature='A', categorie='5', annee=2026, surface=45, parametres={})
        tarifs = [dict(insee='42005', nature='A', categorie='5', serie='A', origine='005', tarif_1970=10)]
        r = calculer_scenarios(saisie, adr, {}, tarifs)
        self.assertEqual(r['code_insee'], '42005')
        self.assertEqual(r['parcelle']['numero'], '0242')
        self.assertGreater(r['tarifs'][0]['base_tf'], 0)


class RechercheParcelleUI(unittest.TestCase):
    def remplir(self, at):
        champ(at.radio, 'Choisir la commune').set_value('Saisir le code INSEE').run()
        for label, val in [('Commune de la parcelle', 'Andrézieux-Bouthéon'), ('Code INSEE cadastral de la commune', '42005'),
                           ('Préfixe cadastral (facultatif)', '000'), ('Section cadastrale', 'BI'), ('Numéro de parcelle', '242')]:
            champ(at.text_input, label).input(val)

    def test_habitation_confirmation_et_changement_de_mode(self):
        with patch.dict(os.environ, {'TF_LOCAL_MODE': '1'}), patch('recherche_bien.rechercher_parcelle', return_value=[ROW]) as api, patch('cadastre.adresses') as geo:
            at = AppTest.from_file(str(ROOT / 'parcours_habitation.py')).run()
            champ(at.radio, 'Rechercher le bien par').set_value('Parcelle cadastrale').run()
            self.remplir(at)
            champ(at.button, 'Rechercher cette parcelle').click().run()
            self.assertFalse(at.exception)
            self.assertTrue(champ(at.button, 'Continuer vers les surfaces').disabled)
            champ(at.selectbox, 'Confirmez la parcelle du logement').select(0).run()
            champ(at.button, 'Continuer vers les surfaces').click().run()
            self.assertEqual(at.session_state['hab_etape'], 2)
            self.assertEqual(at.session_state['hab_saisie']['adresse']['insee'], '42005')
            self.assertEqual(at.session_state['hab_saisie']['parcelle']['section'], 'BI')
            champ(at.button, 'Retour au logement').click().run()
            self.assertEqual(champ(at.text_input, 'Numéro de parcelle').value, '242')
            champ(at.radio, 'Rechercher le bien par').set_value('Adresse').run()
            self.assertNotIn('Continuer vers les surfaces', [x.label for x in at.button])
            api.assert_called_once()
            geo.assert_not_called()

    def test_professionnel_confirmation_obligatoire_et_calcul(self):
        with patch.dict(os.environ, {'TF_LOCAL_MODE': '1'}), patch('recherche_bien.rechercher_parcelle', return_value=[ROW]), \
             patch('cadastre.adresses') as geo, patch('mise_a_jour_simple.synchroniser_dgfip', return_value={'echecs': []}), \
             patch('mise_a_jour_simple.synchroniser_taux', return_value={'incidents': []}):
            at = AppTest.from_file(str(ROOT / 'parcours_express.py')).run()
            champ(at.radio, 'Rechercher le bien par').set_value('Parcelle cadastrale').run()
            self.remplir(at)
            champ(at.selectbox, 'Catégorie du local').select('BUR2')
            champ(at.number_input, 'P1 · Principale').set_value(100.)
            champ(at.button, 'Calculer mon estimation').click().run()
            self.assertFalse(at.exception)
            self.assertIn('_parcelles_attente', at.session_state)
            self.assertNotIn('_calcul_express', at.session_state)
            champ(at.button, 'Obtenir le résultat').click().run()
            self.assertFalse(at.exception, [str(x.value) for x in at.exception])
            self.assertEqual(at.session_state['_calcul_express']['bien']['code_insee'], '42005')
            self.assertEqual(at.session_state['_calcul_express']['bien']['numero'], '0242')
            telechargements = [bouton.proto.label for bouton in at.get('download_button')]
            self.assertIn('Télécharger le 6660-REV prérempli', telechargements)
            self.assertIn('Télécharger mon estimation en PDF', telechargements)
            geo.assert_not_called()

    def test_professionnel_prefixes_distincts_exigent_selection(self):
        with patch.dict(os.environ, {'TF_LOCAL_MODE': '1'}), patch('recherche_bien.rechercher_parcelle', return_value=[ROW, {**ROW, 'com_abs': '123'}]):
            at = AppTest.from_file(str(ROOT / 'parcours_express.py')).run()
            champ(at.radio, 'Rechercher le bien par').set_value('Parcelle cadastrale').run()
            self.remplir(at)
            champ(at.text_input, 'Préfixe cadastral (facultatif)').input('')
            champ(at.selectbox, 'Catégorie du local').select('BUR2')
            champ(at.number_input, 'P1 · Principale').set_value(100.)
            champ(at.button, 'Calculer mon estimation').click().run()
            self.assertTrue(champ(at.button, 'Obtenir le résultat').disabled)
            options = champ(at.selectbox, 'Parcelle cadastrale').options
            self.assertIn('123', options[1])
            champ(at.selectbox, 'Parcelle cadastrale').select(1).run()
            self.assertFalse(champ(at.button, 'Obtenir le résultat').disabled)
            champ(at.text_input, 'Numéro de parcelle').input('243').run()
            self.assertNotIn('_parcelles_attente', at.session_state)


if __name__ == '__main__':
    unittest.main()
