"""Intégration du parcours Lyon 7: le même chemin données -> taux -> calcul que la V9."""
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from moteur import (secteur_automatique, localisation_automatique,
                    neutralisation_avec_teom_reference, tarif_automatique,
                    estimation, TAXES)
from historique_taux import enregistrer,resoudre_tout
ROOT=Path(__file__).resolve().parents[1]
class LyonV13Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=json.loads((ROOT/'data/referentiel_initial.json').read_text(encoding='utf8'))
    def test_le_taux_communal_sur_69123_revient_pour_la_parcelle_69387(self):
        ref=copy.deepcopy(self.base)
        enregistrer(ref,'69123',2026,'commune',31.89,'DGCL 2026')
        enregistrer(ref,'69123',2026,'epci',0.55,'DGCL 2026')
        enregistrer(ref,'69123',2025,'teom',5.19,'Données publiques 2025')
        val=resoudre_tout(ref,'69387',2026)
        self.assertEqual(val['commune']['taux'],31.89)
        self.assertEqual(val['epci']['taux'],0.55)
        self.assertEqual(val['teom']['taux'],5.19)
        self.assertEqual(val['teom']['annee_source'],2025)
    def test_neutralisations_secteur_taux_alimentent_la_meme_estimation(self):
        ref=copy.deepcopy(self.base)
        sect,_=secteur_automatique(ref,'69','Lyon 7ème','000','AC','69387')
        self.assertEqual(sect,4)
        loc,_,_=localisation_automatique(ref,'69',2025,'Lyon 7ème','000','AC','0001','69387')
        self.assertEqual(loc,1.0)
        coeffs,_,_=neutralisation_avec_teom_reference(ref,self.base,'69','Lyon 7ème',2025,'69387','000')
        self.assertEqual(set(coeffs),set(TAXES))
        self.assertTrue(all(v>0 for v in coeffs.values()))
        tariff=tarif_automatique(ref,'69',2025,'BUR2',sect)
        for taxe,rate in {'commune':31.89,'epci':0.55,'teom':5.19,'syndicat':0,
                          'taxes_speciales':0,'gemapi':0}.items():
            enregistrer(ref,'69387',2025,taxe,rate,'Fiction pour test logiciel')
        rates={k:rec['taux'] for k,rec in resoudre_tout(ref,'69387',2025).items()}
        calc=estimation({'P1':100,'P2':0,'P3':0,'PK1':0,'PK2':0},tariff,loc,coeffs,rates)
        self.assertEqual(len(calc['lignes']),6)
        self.assertGreater(calc['total_estime'],0)
        commune=next(row for row in calc['lignes'] if row['cle']=='commune')
        self.assertEqual(commune['taux_pct'],31.89)
        self.assertAlmostEqual(commune['coefficient_neutralisation'],coeffs['commune'])
    def test_anciens_taux_sous_code_cadastral_69387_sont_recuperes(self):
        ref=copy.deepcopy(self.base)
        ref['taux_annuels']={'69387':{'2025':{
            'commune':{'taux':30.5,'source':'Ancien référentiel V9', 'annee_source':2025},
            'teom':{'taux':5.19,'source':'Ancien référentiel V9', 'annee_source':2025}}}}
        result=resoudre_tout(ref,'69387',2026)
        self.assertEqual(result['commune']['taux'],30.5)
        self.assertEqual(result['commune']['annee_source'],2025)
        self.assertEqual(result['teom']['taux'],5.19)
    def test_conflit_ancien_code_et_nouveau_code_bloque_la_valeur(self):
        ref=copy.deepcopy(self.base)
        ref['taux_annuels']={'69387':{'2026':{'commune':{'taux':31.89}}},
                            '69123':{'2026':{'commune':{'taux':32.0}}}}
        with self.assertRaisesRegex(ValueError,'contradictoires'):
            resoudre_tout(ref,'69387',2026)
    def test_deux_arrondissements_partagent_taux_mais_pas_les_secteurs(self):
        ref=copy.deepcopy(self.base)
        enregistrer(ref,'69123',2026,'commune',31.89,'DGCL 2026')
        self.assertEqual(resoudre_tout(ref,'69387',2026)['commune']['taux'],31.89)
        self.assertEqual(resoudre_tout(ref,'69382',2026)['commune']['taux'],31.89)
        sect,_=secteur_automatique(ref,'69','Lyon 7ème','000','AC','69387')
        self.assertEqual(sect,4)
if __name__=='__main__':unittest.main()
