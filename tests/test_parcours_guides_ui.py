"""Parcours interactifs avec services publics simulés : aucune écriture métier."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest
from historique_taux import COMPOSANTES

ROOT = Path(__file__).resolve().parents[1]


def champ(elements, label):
    return next(x for x in elements if x.label == label)


class ParcoursGuidesUI(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'TF_LOCAL_MODE': '1'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_professionnel_champs_conditionnels_et_validation(self):
        at = AppTest.from_file(str(ROOT / 'parcours_express.py')).run()
        self.assertFalse(at.exception)
        self.assertIsNone(champ(at.selectbox, 'Catégorie du local').value)
        champ(at.text_input, 'Adresse complète du bien').input('18 cours Gambetta, 69007 Lyon')
        champ(at.button, 'Calculer mon estimation').click().run()
        self.assertTrue(any('catégorie fiscale' in e.value for e in at.error))
        champ(at.checkbox, 'Construction nouvelle, reconstruction ou addition de construction (hors habitation)').check().run()
        self.assertIn('Année d’achèvement des travaux', [x.label for x in at.number_input])
        champ(at.selectbox, 'Le local existait-il comme local professionnel au 1er janvier 2017 ?').select('ancien').run()
        self.assertEqual(len([x for x in at.text_input if 'correction de base' in x.label]), 6)
        self.assertFalse(at.exception)

    def test_habitation_confirmation_navigation_calcul_et_modification(self):
        adr = {'libelle': '18 cours Gambetta, 69007 Lyon', 'commune': 'Lyon', 'insee': '69387', 'code_postal': '69007'}
        rates = {k: {'taux': 30 if k == 'commune' else 0, 'annee_source': 2026,
                     'source': 'Fixture', 'zonage_confirme': True} for k in COMPOSANTES}
        rows = [dict(insee='69387', nature='A', categorie=c, serie='A', origine='387', tarif_1970=t, annee_tarif=2024)
                for c, t in [('5', 10.), ('6', 8.)]]
        with patch('cadastre.adresses', return_value=[adr]) as geo, \
             patch('tarifs_habitation.tarifs_nationaux', return_value=rows) as tarifs, \
             patch('historique_taux.resoudre_tout', return_value=rates), \
             patch('dossier_habitation.resoudre_tout', return_value=rates), \
             patch('mise_a_jour_simple.synchroniser_taux') as sync:
            at = AppTest.from_file(str(ROOT / 'parcours_habitation.py')).run()
            champ(at.button, 'Rechercher cette adresse').click().run()
            self.assertTrue(at.error)
            geo.assert_not_called()
            champ(at.text_input, 'Adresse du bien').input(adr['libelle'])
            champ(at.button, 'Rechercher cette adresse').click().run()
            self.assertTrue(champ(at.button, 'Continuer vers les surfaces').disabled)
            champ(at.selectbox, 'Confirmez l’adresse du logement').select(0).run()
            champ(at.button, 'Continuer vers les surfaces').click().run()
            self.assertEqual(at.session_state['hab_etape'], 2)
            champ(at.button, 'Vérifier mes informations').click().run()
            self.assertTrue(any('supérieure à zéro' in x.value for x in at.error))
            champ(at.number_input, 'Surface des pièces et annexes intérieures (m²)').set_value(45.)
            champ(at.number_input, 'Garage, cave, grenier et autres dépendances (m²)').set_value(12.)
            champ(at.button, 'Vérifier mes informations').click().run()
            self.assertEqual(at.session_state['hab_etape'], 3)
            tarifs.assert_not_called()
            champ(at.button, 'Calculer mon estimation').click().run()
            self.assertFalse(at.exception, [str(x.value) for x in at.exception])
            self.assertEqual(len(at.session_state['hab_resultat']['tarifs']), 2)
            self.assertTrue(any('non confirmée' in x.value for x in at.warning))
            self.assertTrue(any('Estimation partielle' in x.value for x in at.warning))
            champ(at.selectbox, 'Scénario à examiner').select(1).run()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['hab_resultat']['tarifs'][1]['categorie'], '6')
            sync.assert_not_called()
            tarifs.assert_called_once()
            champ(at.button, 'Modifier mes informations').click().run()
            self.assertNotIn('hab_resultat', at.session_state)
            self.assertEqual(champ(at.number_input, 'Surface des pièces et annexes intérieures (m²)').value, 45.)
            self.assertEqual(champ(at.number_input, 'Garage, cave, grenier et autres dépendances (m²)').value, 12.)


if __name__ == '__main__':
    unittest.main()
