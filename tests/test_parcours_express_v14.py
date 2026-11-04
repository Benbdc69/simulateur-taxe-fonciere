"""Tests sans Streamlit : fonctions métier extraites sans exécuter l'interface."""
import ast
import json
import unittest
from pathlib import Path
from moteur import (COEFF_SURFACES, TAXES, insee_cadastral_adresse, nom_commune_cadastrale,
                    secteur_automatique, localisation_automatique,
                    neutralisation_avec_teom_reference, tarif_automatique, estimation)
from historique_taux import resoudre_tout, enregistrer

HERE=Path(__file__).resolve().parents[1]


def functions():
    tree=ast.parse((HERE/'parcours_express.py').read_text(encoding='utf-8'))
    selected=[node for node in tree.body if isinstance(node,ast.FunctionDef)
              and node.name in ('normaliser_identite','calculer_dossier')]
    ns=globals().copy()
    exec(compile(ast.Module(body=selected,type_ignores=[]),'parcours_express.py','exec'),ns)
    return ns

class TestParcoursExpress(unittest.TestCase):
    def setUp(self):
        self.fn=functions();self.ref=json.loads((HERE/'data/referentiel_initial.json').read_text(encoding='utf8'))
        self.bien=self.fn['normaliser_identite'](
            {'insee':'69387','departement':'69','section':'AC','numero':'0001','prefixe':'000'},
            {'insee':'69123','code_postal':'69007','commune':'Lyon'},self.ref)
        self.surfaces={'P1':100,'P2':20,'P3':0,'PK1':5,'PK2':0}

    def test_lyon_arrondissement_sans_commune_manuelle(self):
        self.assertEqual(self.bien['commune'],'LYON 7EME')
        self.assertEqual(self.bien['code_insee'],'69387')

    def test_ne_pas_inventer_total_sans_taux(self):
        result=self.fn['calculer_dossier'](self.ref,self.ref,self.bien,'BUR2',self.surfaces,2025)
        self.assertIsNone(result['result'])
        self.assertEqual(result['partial']['secteur'],4)
        self.assertGreater(result['partial']['valeur_locative_brute'],0)
        self.assertTrue(any('taux' in missing for missing in result['missing']))

    def test_un_total_avec_taux_documentes(self):
        import copy
        d=copy.deepcopy(self.ref)
        for k in TAXES:
            enregistrer(d,'69123',2025,k,0 if k not in ('commune','epci') else 0.55,
                        'Fixture de test')
        result=self.fn['calculer_dossier'](d,self.ref,self.bien,'BUR2',self.surfaces,2025)
        self.assertIsNotNone(result['result'])
        self.assertEqual(len(result['result']['lignes']),6)
        self.assertGreater(result['result']['total_estime'],0)

if __name__=='__main__': unittest.main()
