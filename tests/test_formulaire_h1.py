"""Conformité des rubriques H1 page 2, pondérations séparées et données descriptives."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from formulaire_h1 import valider_description_h1
from dependances_habitation import valider_dependances
from moteur_habitation import surface_totale
from dossier_habitation import calculer_scenarios
from historique_taux import COMPOSANTES, enregistrer
from export_habitation_pdf import generer_pdf_habitation, Paragraph
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]
ELEMENTS={'garages':{'surface':20,'coefficient':.6},'caves':{'surface':10,'coefficient':.2},'greniers':{'surface':15,'coefficient':.4}}
H1={'pieces':{'reception':1,'chambres':3},'chauffage':False,'pieces_chauffees':0,
    'materiaux_murs':['Pierre'],'materiaux_toitures':['Tuiles'],'annee_construction':1980,'niveaux_habitables':2,
    'emprises':{'maison':100,'dependances':30,'terrains':500}}


def champ(elements,label):return next(x for x in elements if x.label==label)


class H1CalculTests(unittest.TestCase):
    def test_elements_41b_avec_pondérations_propres(self):
        sp=surface_totale(100,'M','5',elements_incorpores=ELEMENTS,terrasse=12,coeff_terrasse=.4)
        self.assertEqual(sp['comparative'],101)
        self.assertEqual(sp['annexes_ponderees'],20)
        self.assertEqual(sp['terrasse_ponderee'],4)
        self.assertEqual(sp['surface_nette'],125)
        self.assertEqual(sp['surface_ponderee'],144)
        self.assertEqual(len(sp['detail_elements_incorpores']),3)

    def test_dependance_51_h1_decomposee_et_eval_distincte(self):
        composition={'garages':{'surface':20,'coefficient':.6},'caves':{'surface':10,'coefficient':.2}}
        r=valider_dependances([dict(type='batiment_h1',mode='incorporee',composition=composition)])
        self.assertEqual(r[0]['surface'],30)
        self.assertEqual(r[0]['surface_ponderee'],14)
        r=valider_dependances([dict(type='batiment_h1',mode='distincte',composition=composition)])
        self.assertEqual(r[0]['surface_ponderee'],0)
        with self.assertRaisesRegex(ValueError,'agrément'):
            valider_dependances([dict(type='batiment_h1',mode='incorporee',composition={'agrement':{'surface':25}})])

    def test_validation_h1_sans_deduction_du_classement(self):
        valider_description_h1(H1)
        for modif in [{'pieces':{}},{'annee_construction':-1},{'niveaux_habitables':0},{'materiaux_murs':['inconnu']},{'chauffage':False,'pieces_chauffees':2}]:
            with self.subTest(modif=modif),self.assertRaises(ValueError):
                valider_description_h1({**H1,**modif})

    def test_dossier_et_pdf_conservent_h1_sans_taxer_emprises_au_sol(self):
        saisie=dict(nature='M',annee=2026,categorie='5',surface=100,h1=H1,
            parametres={'elements_incorpores':ELEMENTS,'terrasse':12,'coeff_terrasse':.4})
        ref={}
        for k in COMPOSANTES:enregistrer(ref,'42005',2026,k,30 if k=='commune' else 0,'Fixture')
        r=calculer_scenarios(saisie,{'libelle':'Maison test','insee':'42005'},ref,
            [dict(insee='42005',nature='M',categorie='5',serie='A',origine='005',tarif_1970=10)])
        self.assertEqual(r['tarifs'][0]['surfaces']['surface_ponderee'],144)
        self.assertEqual(r['h1']['emprises']['terrains'],500)
        with patch('export_habitation_pdf.Paragraph',wraps=Paragraph) as paragraphes:
            pdf=generer_pdf_habitation({**r,'surfaces':r['tarifs'][0]['surfaces'],'serie_selectionnee':0})
        self.assertTrue(pdf.startswith(b'%PDF'))
        textes=' '.join(str(c.args[0]) for c in paragraphes.call_args_list)
        self.assertIn('1980',textes)
        self.assertIn('Pierre',textes)
        self.assertIn('Niveaux habitables',textes)
        self.assertIn('Garages incorporés',textes)


class H1UITests(unittest.TestCase):
    def test_rubriques_h1_enregistrement_et_retour(self):
        with patch.dict(os.environ,{'TF_LOCAL_MODE':'1'}):
            at=AppTest.from_file(str(ROOT/'parcours_habitation.py'))
            at.session_state['hab_etape']=2
            at.session_state['hab_saisie']={'nature':'M','annee':2026,'adresse':{'libelle':'Maison test'}}
            at.run()
            self.assertFalse(at.exception,[x.value for x in at.exception])
            titres=' '.join(x.value for x in at.markdown)
            for texte in ['41 · Consistance de la maison','41 B · Éléments incorporés','42 · Confort de la maison','43 · Caractéristiques générales','Correctifs cadastraux','6 · Renseignements']:
                self.assertIn(texte,titres)
            self.assertNotIn('Vide-ordures',[x.label for x in at.checkbox])
            self.assertNotIn('Ascenseur de l’immeuble desservant l’étage du logement',[x.label for x in at.checkbox])
            self.assertFalse(any(x.value for x in at.checkbox))
            champ(at.number_input,'Salles à manger et pièces de réception diverses').set_value(1)
            champ(at.number_input,'Surface totale des pièces et annexes affectées à l’habitation (m²)').set_value(100.)
            champ(at.number_input,'Garages incorporés (m²)').set_value(20.)
            champ(at.multiselect,'Principaux matériaux des gros murs').set_value(['Pierre'])
            champ(at.multiselect,'Matériaux des toitures').set_value(['Tuiles'])
            champ(at.number_input,'Année de construction de la maison').set_value(1980)
            champ(at.number_input,'Nombre de niveaux habitables').set_value(2)
            champ(at.selectbox,'Catégorie cadastrale du logement').select('5')
            champ(at.button,'Vérifier mes informations').click().run()
            self.assertFalse(at.exception,[x.value for x in at.exception])
            self.assertEqual(at.session_state['hab_etape'],3)
            self.assertEqual(at.session_state['hab_saisie']['h1']['annee_construction'],1980)
            self.assertEqual(at.session_state['hab_saisie']['h1']['materiaux_murs'],['Pierre'])
            champ(at.button,'Modifier mes informations').click().run()
            self.assertEqual(champ(at.number_input,'Garages incorporés (m²)').value,20.)
            self.assertEqual(champ(at.number_input,'Nombre de niveaux habitables').value,2)

    def test_dependances_h1_ligne_par_ligne_avec_composantes(self):
        with patch.dict(os.environ,{'TF_LOCAL_MODE':'1'}):
            at=AppTest.from_file(str(ROOT/'parcours_habitation.py'))
            at.session_state['hab_etape']=2
            at.session_state['hab_saisie']={'nature':'M','annee':2026,'adresse':{'libelle':'Maison test'}}
            at.run()
            champ(at.button,'＋ Ajouter une dépendance').click().run()
            self.assertIn('Matériaux des murs — dépendance',[x.label for x in at.multiselect])
            champ(at.number_input,'Garages (m²)').set_value(30.)
            champ(at.number_input,'Greniers (m²)').set_value(10.)
            champ(at.selectbox,'Traitement fiscal de cette dépendance').select('distincte').run()
            champ(at.button,'＋ Ajouter une dépendance').click().run()
            self.assertEqual(len(at.session_state['hab_dependances_h1']),2)
            self.assertEqual(at.session_state['hab_dependances_h1'][0]['surface'],40.)
            champ(at.button,'Supprimer cette dépendance').click().run()
            self.assertEqual(len(at.session_state['hab_dependances_h1']),1)
            champ(at.button,'Nouveau calcul').click().run()
            self.assertNotIn('hab_dependances_h1',at.session_state)
            self.assertFalse(at.exception)


if __name__=='__main__':unittest.main()
