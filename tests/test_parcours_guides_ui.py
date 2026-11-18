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
        champ(at.radio, 'Saisie de l’adresse').set_value('Saisie manuelle').run()
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
        rows = [dict(insee='69387', nature='A', categorie=c, serie=serie, origine='387', tarif_1970=t, annee_tarif=2024)
                for c, serie, t in [('5', 'A', 10.), ('5', 'B', 12.), ('6', 'A', 8.)]]
        with patch('cadastre.adresses', return_value=[adr]) as geo, \
             patch('tarifs_habitation.tarifs_nationaux', return_value=rows) as tarifs, \
             patch('historique_taux.resoudre_tout', return_value=rates), \
             patch('dossier_habitation.resoudre_tout', return_value=rates), \
             patch('mise_a_jour_simple.synchroniser_taux') as sync:
            at = AppTest.from_file(str(ROOT / 'parcours_habitation.py')).run()
            champ(at.button, 'Rechercher cette adresse').click().run()
            self.assertTrue(at.error)
            geo.assert_not_called()
            champ(at.radio, 'Saisie de l’adresse').set_value('Saisie manuelle').run()
            champ(at.text_input, 'Adresse du bien').input(adr['libelle'])
            champ(at.button, 'Rechercher cette adresse').click().run()
            self.assertTrue(champ(at.button, 'Continuer vers les surfaces').disabled)
            champ(at.selectbox, 'Confirmez l’adresse du logement').select(0).run()
            champ(at.button, 'Continuer vers les surfaces').click().run()
            self.assertEqual(at.session_state['hab_etape'], 2)
            champ(at.button, 'Vérifier mes informations').click().run()
            self.assertTrue(any('supérieure à zéro' in x.value for x in at.error))
            self.assertNotIn('Pièces avec chauffage admissible', [x.label for x in at.number_input])
            self.assertIn('Lavabos', [x.label for x in at.number_input])
            champ(at.number_input, 'Salles à manger et pièces de réception diverses').set_value(1)
            champ(at.number_input, 'Chambres et autres pièces habitables').set_value(2)
            champ(at.number_input, 'Cuisines de moins de 9 m²').set_value(1)
            champ(at.checkbox, 'Chauffage ou climatisation dans les DOM').check()
            champ(at.number_input, 'Niveau du logement pour le correctif d’ascenseur').set_value(4)
            champ(at.checkbox, 'Ascenseur de l’immeuble desservant l’étage du logement').check()
            champ(at.number_input, 'Surface totale des pièces et annexes affectées à l’habitation (m²)').set_value(45.)
            champ(at.button, '＋ Ajouter une dépendance').click().run()
            champ(at.number_input, 'Surface de la dépendance (m²)').set_value(12.)
            champ(at.selectbox, 'Traitement fiscal de cette dépendance').select('distincte')
            champ(at.button, 'Vérifier mes informations').click().run()
            self.assertEqual(at.session_state['hab_etape'], 2)
            self.assertTrue(any('Choisissez une catégorie' in x.value for x in at.error))
            self.assertTrue(any('M’aider à choisir la catégorie la plus pertinente' in x.value for x in at.markdown))
            champ(at.selectbox, 'Catégorie cadastrale du logement').select('5')
            champ(at.button, 'Vérifier mes informations').click().run()
            self.assertEqual(at.session_state['hab_etape'], 3)
            tarifs.assert_not_called()
            champ(at.button, 'Calculer mon estimation').click().run()
            self.assertFalse(at.exception, [str(x.value) for x in at.exception])
            self.assertEqual(len(at.session_state['hab_resultat']['tarifs']), 2)
            self.assertIn('Télécharger le H2', [bouton.label for bouton in at.button])
            self.assertEqual(at.session_state['hab_resultat']['tarifs'][0]['surfaces']['correctif_ascenseur'], .05)
            self.assertFalse(any('Correctif article 324 S' in x.value for x in at.caption))
            self.assertFalse(any('choisie à titre indicatif' in x.value for x in at.warning))
            self.assertFalse(any('Le zonage TEOM n’est pas confirmé' in x.value for x in at.warning))
            self.assertTrue(any('évaluation distincte non chiffrée' in x.value for x in at.warning))
            self.assertNotIn('Hypothèse de chauffage à examiner', [x.label for x in at.selectbox])
            self.assertTrue(any('Majoration chauffage : 4 × 2 m² = +8 m²' in x.value for x in at.markdown))
            champ(at.selectbox, 'Scénario à examiner').select(1).run()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['hab_resultat']['tarifs'][1]['categorie'], '5')
            details = next(x for x in at.expander if x.label == 'Détail des cotisations, du calcul et des sources')
            taxes = next(table.value for table in details.get('table') if 'Taxe' in table.value.columns)
            self.assertEqual(len(taxes), 6)
            self.assertTrue(any('Cotisations annuelles estimées' in x.value for x in at.markdown))
            self.assertTrue(any('Fourchette des séries — catégorie 5' in x.value for x in at.markdown))
            self.assertEqual(len(champ(at.selectbox, 'Scénario à examiner').options), 2)
            comparables = [x for x in at.session_state['hab_resultat']['tarifs'] if x['pieces_chauffage_scenario'] == 4]
            euro = lambda n: f'{n:,.2f}'.replace(',', ' ').replace('.', ',') + ' €'
            fourchette = next(x.value for x in at.markdown if 'Fourchette des séries — catégorie 5' in x.value)
            self.assertIn(euro(min(x['total'] for x in comparables)), fourchette)
            self.assertIn(euro(max(x['total'] for x in comparables)), fourchette)
            self.assertEqual({x['categorie'] for x in at.session_state['hab_resultat']['tarifs']}, {'5'})
            self.assertIn('Intercommunalité', list(taxes['Taxe']))
            self.assertFalse(details.proto.expanded)
            self.assertEqual(at.session_state['hab_resultat']['h2']['pieces']['chambres'], 2)
            self.assertEqual(at.session_state['hab_resultat']['tarifs'][1]['pieces_chauffage_scenario'], 4)
            sync.assert_not_called()
            tarifs.assert_called_once()
            champ(at.button, 'Modifier mes informations').click().run()
            self.assertNotIn('hab_resultat', at.session_state)
            self.assertEqual(champ(at.number_input, 'Surface totale des pièces et annexes affectées à l’habitation (m²)').value, 45.)
            self.assertEqual(champ(at.number_input, 'Surface de la dépendance (m²)').value, 12.)
            self.assertEqual(champ(at.number_input, 'Chambres et autres pièces habitables').value, 2)
            self.assertTrue(champ(at.checkbox, 'Chauffage ou climatisation dans les DOM').value)
            self.assertNotIn('Nombre de pièces chauffées', [x.label for x in at.number_input])
            self.assertEqual(champ(at.number_input, 'Niveau du logement pour le correctif d’ascenseur').value, 4)
            self.assertTrue(champ(at.checkbox, 'Ascenseur de l’immeuble desservant l’étage du logement').value)

    def test_resultat_incomplet_affiche_valeur_locative_sans_cotisations(self):
        from dossier_habitation import calculer_scenarios
        adr = {'libelle': 'Adresse test, Lyon', 'commune': 'Lyon', 'insee': '69387'}
        saisie = {'nature': 'A', 'annee': 2026, 'categorie': '5', 'surface': 45., 'adresse': adr,
                  'parametres': {'annexes': 0., 'terrasse': 0., 'entretien': 'Passable',
                                  'situation_generale': 'Ordinaire', 'situation_particuliere': 'Ordinaire'}}
        rows = [dict(insee='69387', nature='A', categorie='5', serie='A', origine='387', tarif_1970=10., annee_tarif=2024)]
        with patch('dossier_habitation.resoudre_tout', return_value={k: None for k in COMPOSANTES}):
            r = calculer_scenarios(saisie, adr, {}, rows)
        at = AppTest.from_file(str(ROOT / 'parcours_habitation.py'))
        at.session_state['hab_etape'] = 3
        at.session_state['hab_saisie'] = saisie
        at.session_state['hab_resultat'] = {**r, 'incidents': [], 'source_tarifs': 'Fixture'}
        at.run()
        self.assertFalse(at.exception, [x.value for x in at.exception])
        self.assertTrue(any('Valeur locative estimée' in x.value for x in at.markdown))
        self.assertFalse(any('Cotisations annuelles estimées' in x.value for x in at.markdown))
        self.assertFalse(any('hab-result-card hab-tax-card' in x.value for x in at.markdown))
        self.assertTrue(any('Taux non documentés' in x.value for x in at.warning))


if __name__ == '__main__':
    unittest.main()
