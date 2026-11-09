"""Accueil, formulaires vierges, remise à zéro et millésimes habitation libres."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest
from facteurs_habitation import facteur_departement_annee, FICHIER
from dossier_habitation import calculer_scenarios
from historique_taux import COMPOSANTES, enregistrer

ROOT = Path(__file__).resolve().parents[1]


def champ(elements, label):
    return next(x for x in elements if x.label == label)


class AccueilEtSaisieTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'TF_LOCAL_MODE': '1'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_accueil_et_deux_boutons_de_navigation(self):
        for label, titre in [('Local professionnel', 'Estimez votre taxe foncière'), ('Local d’habitation', 'Estimez la taxe foncière de votre logement')]:
            with self.subTest(label=label):
                at = AppTest.from_file(str(ROOT/'app.py')).run()
                self.assertFalse(at.exception)
                self.assertEqual([x.label for x in at.button], ['Local professionnel', 'Local d’habitation'])
                self.assertEqual(len(at.text_input), 0)
                champ(at.button, label).click().run()
                self.assertFalse(at.exception, [x.value for x in at.exception])
                self.assertIn(titre, [x.value for x in at.title])
                self.assertIn('Nouveau calcul', [x.label for x in at.button])
                champ(at.button, 'Nouveau calcul').click().run()
                self.assertFalse(at.exception)
                self.assertIn(titre, [x.value for x in at.title])
                champ(at.button, 'Retour à l’accueil').click().run()
                self.assertFalse(at.exception)
                self.assertEqual([x.label for x in at.button], ['Local professionnel', 'Local d’habitation'])

    def test_nouveau_calcul_professionnel_efface_saisies_sans_deconnexion(self):
        at = AppTest.from_file(str(ROOT/'parcours_express.py'))
        at.session_state['_acces_valide'] = True
        at.session_state['hab_saisie'] = {'surface': 80}
        at.session_state['express_ref_communes'] = [{'commune':'Ancienne recherche'}]
        at.run()
        champ(at.radio, 'Saisie de l’adresse').set_value('Saisie manuelle').run()
        champ(at.text_input, 'Adresse complète du bien').input('Adresse saisie')
        champ(at.selectbox, 'Catégorie du local').select('BUR2')
        champ(at.number_input, 'P1 · Principale').set_value(100.)
        champ(at.checkbox, 'Construction nouvelle, reconstruction ou addition de construction (hors habitation)').check().run()
        champ(at.button, 'Nouveau calcul').click().run()
        self.assertFalse(at.exception)
        champ(at.radio, 'Saisie de l’adresse').set_value('Saisie manuelle').run()
        self.assertEqual(champ(at.text_input, 'Adresse complète du bien').value, '')
        self.assertEqual(champ(at.number_input, 'P1 · Principale').value, 0.)
        self.assertIsNone(champ(at.selectbox, 'Catégorie du local').value)
        self.assertFalse(any(x.value for x in at.checkbox))
        self.assertTrue(at.session_state['_acces_valide'])
        self.assertNotIn('hab_saisie', at.session_state)
        self.assertNotIn('express_ref_communes', at.session_state)

    def test_habitation_cases_decoches_et_retour_a_un_formulaire_vierge(self):
        for nature in ['A', 'M']:
            with self.subTest(nature=nature):
                at = AppTest.from_file(str(ROOT/'parcours_habitation.py'))
                at.session_state['hab_etape'] = 2
                at.session_state['hab_saisie'] = {'nature': nature, 'annee': 2027, 'adresse': {'libelle': 'Ancien bien'}}
                at.run()
                self.assertFalse(at.exception)
                self.assertFalse(any(x.value for x in at.checkbox))
                champ(at.button, 'Nouveau calcul').click().run()
                self.assertFalse(at.exception)
                champ(at.radio, 'Saisie de l’adresse').set_value('Saisie manuelle').run()
                self.assertEqual(champ(at.text_input, 'Adresse du bien').value, '')
                self.assertNotIn('hab_resultat', at.session_state)
                self.assertEqual(at.session_state['hab_saisie'], {})

    def test_annee_2027_saisissable_et_transmise(self):
        with patch('cadastre.adresses', return_value=[dict(libelle='Adresse test', insee='42005', commune='Andrézieux-Bouthéon')]):
            at = AppTest.from_file(str(ROOT/'parcours_habitation.py')).run()
            champ(at.number_input, 'Année d’imposition').set_value(2027)
            champ(at.radio, 'Saisie de l’adresse').set_value('Saisie manuelle').run()
            champ(at.text_input, 'Adresse du bien').input('Adresse test')
            champ(at.button, 'Rechercher cette adresse').click().run()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['hab_saisie']['annee'], 2027)
            self.assertEqual(champ(at.number_input, 'Année d’imposition').value, 2027)


class MillesimesHabitationTests(unittest.TestCase):
    def test_collecte_tente_le_millesime_demande_sans_modifier_annee_source(self):
        from collecte_taux import preparer
        appel = Mock(side_effect=lambda code, annee: {'taux': {'commune': 30 if annee == 2027 else 28}, 'source': 'Fixture officielle', 'preuves': {}})
        r = preparer('42005', 2027, cherche_dgcl=appel)
        self.assertEqual([x.args[1] for x in appel.call_args_list], [2027, 2026])
        self.assertEqual(r['propositions']['commune']['annee'], 2027)
        self.assertFalse(r['propositions']['commune']['repli'])

    def test_coefficient_2027_absent_ne_reprend_pas_2026(self):
        with self.assertRaisesRegex(ValueError, '2027 non disponible'):
            facteur_departement_annee('42005', 2027)

    def test_annee_future_utilisable_avec_coefficients_et_sources_documentes(self):
        data = json.loads(FICHIER.read_text())
        data['coefficients_amalgames'] = {'2027': 4.}
        data['sources_revalorisation'] = {'2027': 'Fixture de test — pas une valeur fiscale réelle'}
        fichier = Mock()
        fichier.read_text.return_value = json.dumps(data)
        ref = {}
        for k in COMPOSANTES:
            enregistrer(ref, '42005', 2027, k, 30 if k == 'commune' else 0, 'Fixture taux 2027')
        with patch('facteurs_habitation.FICHIER', fichier):
            r = calculer_scenarios(dict(nature='A', categorie='5', annee=2027, surface=45, parametres={}),
                dict(libelle='Adresse test', insee='42005'), ref,
                [dict(insee='42005', nature='A', categorie='5', serie='A', origine='005', tarif_1970=10)])
        self.assertEqual(r['annee'], 2027)
        self.assertTrue(r['taux_complets'])
        self.assertGreater(r['tarifs'][0]['total'], 0)
        self.assertEqual(r['facteur']['revalorisation_nationale'], 4.)
        self.assertEqual(r['taux']['commune']['annee_source'], 2027)


if __name__ == '__main__':
    unittest.main()
