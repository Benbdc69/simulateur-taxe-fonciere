"""Dépendances rattachées ou distinctes : pas de tarif ni de rattachement implicite."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dependances_habitation import valider_dependances
from moteur_habitation import surface_totale
from dossier_habitation import calculer_scenarios
from historique_taux import COMPOSANTES, enregistrer
from export_habitation_pdf import generer_pdf_habitation
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]


def champ(elements, label):
    return next(x for x in elements if x.label==label)


class DependancesCalculTests(unittest.TestCase):
    def setUp(self):
        self.saisie=dict(nature='A', categorie='5', annee=2026, surface=45., parametres={})
        self.adresse=dict(libelle='Bien test', insee='42005')
        self.tarifs=[dict(insee='42005', nature='A', categorie='5', serie='A', origine='005', tarif_1970=10)]
        self.ref={}
        for k in COMPOSANTES:
            enregistrer(self.ref,'42005',2026,k,30 if k=='commune' else 0,'Fixture')

    def calculer(self):
        return calculer_scenarios(self.saisie,self.adresse,self.ref,self.tarifs)

    def test_surface_rattachee_ponderee_sans_ajout_surface_principale(self):
        self.saisie['dependances']=[dict(type='garage',mode='incorporee',surface=20,coefficient=.4)]
        r=self.calculer()
        sp=r['tarifs'][0]['surfaces']
        self.assertEqual(r['surface_reelle'],45)
        self.assertEqual(sp['dependances_ponderees'],8)
        self.assertEqual(sp['surface_ponderee'],76)
        self.assertEqual(r['tarifs'][0]['vl_1970'],760)

    def test_evaluation_distincte_ne_recoit_pas_tarif_du_logement(self):
        self.saisie['dependances']=[dict(type='garage',mode='distincte',surface=20)]
        r=self.calculer()
        self.assertEqual(r['tarifs'][0]['surfaces']['surface_ponderee'],68)
        self.assertNotIn('total',r['dependances_distinctes'][0])
        self.assertNotIn('total_bien',r['tarifs'][0])
        self.assertFalse(r['dependances_completes'])

    def test_base_documentee_et_taux_confirmes_necessaires_pour_total_bien(self):
        d=dict(type='garage',mode='distincte',surface=20,base_tf=100.,annee_base=2026)
        self.saisie['dependances']=[d]
        self.assertNotIn('total_bien',self.calculer()['tarifs'][0])
        d['taux_logement_confirmes']=True
        r=self.calculer()
        self.assertEqual(r['dependances_distinctes'][0]['total'],30)
        self.assertEqual(r['tarifs'][0]['total_bien'],r['tarifs'][0]['total']+30)
        d['annee_base']=2025
        with self.assertRaisesRegex(ValueError,'année simulée'):
            self.calculer()

    def test_taux_absent_et_base_nulle_documentee(self):
        self.saisie['dependances']=[dict(type='garage',mode='distincte',surface=20,base_tf=0,annee_base=2026,taux_logement_confirmes=True)]
        r=self.calculer()
        self.assertEqual(r['dependances_distinctes'][0]['total'],0)
        self.assertEqual(r['tarifs'][0]['total_bien'],r['tarifs'][0]['total'])
        del self.ref['taux_annuels']['42005']['2026']['teom']
        r=self.calculer()
        self.assertNotIn('total',r['dependances_distinctes'][0])
        self.assertNotIn('total_bien',r['tarifs'][0])

    def test_plusieurs_lignes_mixtes_et_pdf(self):
        self.saisie['dependances']=[dict(type='cave',mode='incorporee',surface=10,coefficient=.3),
            dict(type='garage',designation='Garage B',mode='distincte',surface=20,base_tf=100,annee_base=2026,taux_logement_confirmes=True)]
        r=self.calculer()
        self.assertEqual(r['tarifs'][0]['surfaces']['dependances_ponderees'],3)
        d={**r,'surfaces':r['tarifs'][0]['surfaces'],'serie_selectionnee':0}
        self.assertTrue(generer_pdf_habitation(d).startswith(b'%PDF'))
        self.assertEqual(r['autres_dependances'],30)

    def test_validation_choix_surface_et_quantites(self):
        for d in [dict(type='garage',surface=12),dict(type='garage',mode='incorporee',surface=0),
                  dict(type='garage',mode='incorporee',surface=12,coefficient=.9),
                  dict(type='piece',mode='incorporee',surface=12,lavabos=1.5),
                  dict(type='garage',mode='distincte',surface=12,base_tf=-1)]:
            with self.subTest(d=d),self.assertRaises(ValueError):
                valider_dependances([d])

    def test_lavabos_uniquement_et_equivalences_par_dependance(self):
        sans=surface_totale(45,'A','5',lavabos=0)
        avec=surface_totale(45,'A','5',lavabos=1)
        self.assertEqual(avec['surface_ponderee']-sans['surface_ponderee'],3)
        dep=surface_totale(45,'A','5',dependances=[dict(type='piece',mode='incorporee',surface=10,coefficient=.4,lavabos=1)])
        self.assertEqual(dep['surface_ponderee']-avec['surface_ponderee'],7)
        self.assertEqual(dep['detail_confort']['Équipements propres aux dépendances rattachées'],3)


class DependancesUITests(unittest.TestCase):
    def test_changement_annee_efface_base_distincte_et_confirmation(self):
        with patch.dict(os.environ,{'TF_LOCAL_MODE':'1'}):
            at=AppTest.from_file(str(ROOT/'parcours_habitation.py'))
            at.session_state['hab_etape']=2
            at.session_state['hab_saisie']=dict(nature='A',annee=2027,adresse={'libelle':'Bien test'},surface=45,
                dependances=[dict(type='garage',mode='distincte',surface=20,base_tf=100,annee_base=2026,taux_logement_confirmes=True)])
            at.run()
            self.assertIsNone(champ(at.number_input,'Base imposable TFPB 2027 de la dépendance (€)').value)
            self.assertFalse(champ(at.checkbox,'Les mêmes taux et le même zonage TEOM que le logement sont confirmés pour cette dépendance').value)
            self.assertFalse(at.exception)

    def test_ajout_suppression_preservation_et_nouveau_calcul(self):
        with patch.dict(os.environ,{'TF_LOCAL_MODE':'1'}):
            at=AppTest.from_file(str(ROOT/'parcours_habitation.py'))
            at.session_state['hab_etape']=2
            at.session_state['hab_saisie']=dict(nature='A',annee=2026,adresse={'libelle':'Bien test'},surface=45)
            at.run()
            self.assertIn('Lavabos',[x.label for x in at.number_input])
            self.assertNotIn('Lavabos et éviers',[x.label for x in at.number_input])
            champ(at.number_input,'Surface totale des pièces et annexes affectées à l’habitation (m²)').set_value(60.)
            champ(at.button,'＋ Ajouter une dépendance').click().run()
            champ(at.text_input,'Désignation de l’élément').input('Garage B')
            champ(at.number_input,'Surface de la dépendance (m²)').set_value(20.)
            champ(at.selectbox,'Traitement fiscal de cette dépendance').select('distincte').run()
            champ(at.button,'＋ Ajouter une dépendance').click().run()
            self.assertEqual(champ(at.number_input,'Surface totale des pièces et annexes affectées à l’habitation (m²)').value,60.)
            self.assertEqual(len(at.session_state['hab_dependances']),2)
            champ(at.button,'Supprimer cette dépendance').click().run()
            self.assertEqual(len(at.session_state['hab_dependances']),1)
            self.assertEqual(at.session_state['hab_dependances'][0]['id'],2)
            champ(at.button,'Nouveau calcul').click().run()
            self.assertNotIn('hab_dependances',at.session_state)
            self.assertFalse(at.exception,[x.value for x in at.exception])


if __name__=='__main__':unittest.main()
