import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from historique_taux import (enregistrer,supprimer,resoudre,resoudre_tout,lignes_historique,
                             integrer_publication,code_reference)
from collecte_taux import preparer
from taux_composantes import extraire_rei,_classifier_libelle_rei,lire_tableur_dgcl
from openpyxl import Workbook
import io

class HistoriquesV7(unittest.TestCase):
    def setUp(self):
        self.ref={}
    def save(self,y,part,val,**kw):
        return enregistrer(self.ref,'69387',y,part,val,'Avis de TF',**kw)
    def test_2026_repli_2025_avec_alerte_et_provenance(self):
        self.save(2025,'teom',8.3)
        v=resoudre(self.ref,'69387',2026,'teom')
        self.assertEqual(v['annee_source'],2025)
        self.assertEqual(v['annee_imposition'],2026)
        self.assertEqual(v['taux'],8.3)
        self.assertEqual(v['decalage'],1)
        self.assertIn('2025',v['statut'])
        self.assertFalse(v['zonage_confirme'])
    def test_repli_par_composante_et_2026_prioritaire(self):
        self.save(2025,'commune',28.0)
        self.save(2025,'syndicat',2.0)
        self.save(2025,'teom',9.3)
        self.save(2026,'commune',29.0)
        got=resoudre_tout(self.ref,'69387',2026)
        self.assertEqual((got['commune']['annee_source'],got['commune']['taux']),(2026,29))
        self.assertEqual((got['syndicat']['annee_source'],got['syndicat']['taux']),(2025,2))
        self.assertIsNone(got['epci'])
        self.assertEqual(got['teom']['annee_source'],2025)
    def test_zero_explicite_est_preserve(self):
        self.save(2025,'epci','0,00')
        value=resoudre(self.ref,'69387',2026,'epci')
        self.assertIsNotNone(value)
        self.assertEqual(value['taux'],0)
        self.assertEqual(value['annee_source'],2025)
    def test_pas_d_annee_future(self):
        self.save(2026,'commune',40)
        self.assertIsNone(resoudre(self.ref,'69387',2025,'commune'))
    def test_last_known_even_n_2_with_year(self):
        self.save(2023,'gemapi',0.6)
        v=resoudre(self.ref,'69387',2026,'gemapi')
        self.assertEqual(v['decalage'],3)
        self.assertIn('2023',v['statut'])
    def test_arrondissement_lyon_vers_commune_fiscale(self):
        self.assertEqual(code_reference('69387'),'69123')
        self.assertEqual(code_reference('69123'),'69123')
        self.save(2025,'commune',31)
        self.assertEqual(resoudre(self.ref,'69123',2025,'commune')['taux'],31)
    def test_interdit_ecrasement_sans_confirmation(self):
        self.save(2025,'commune',30)
        with self.assertRaisesRegex(ValueError,'remplacement'):
            self.save(2025,'commune',40)
        self.save(2025,'commune',40,remplacer=True)
        self.assertEqual(resoudre(self.ref,'69387',2025,'commune')['taux'],40)
    def test_mise_a_jour_2026_ne_modifie_pas_2025(self):
        self.save(2025,'commune',28.1)
        self.save(2026,'commune',31.1)
        self.save(2026,'commune',31.2,remplacer=True)
        self.assertEqual(resoudre(self.ref,'69387',2025,'commune')['taux'],28.1)
        self.assertEqual(resoudre(self.ref,'69387',2026,'commune')['taux'],31.2)
    def test_source_obligatoire_valeur_invalide(self):
        with self.assertRaisesRegex(ValueError,'Source'):enregistrer(self.ref,'69387',2025,'commune',31,'')
        with self.assertRaisesRegex(ValueError,'compris'):self.save(2025,'commune',120)
    def test_suppression_fait_ressortir_repli(self):
        self.save(2025,'teom',8)
        self.save(2026,'teom',9)
        supprimer(self.ref,'69387',2026,'teom')
        self.assertEqual(resoudre(self.ref,'69387',2026,'teom')['annee_source'],2025)
    def test_listing_tracabilite(self):
        self.save(2025,'commune',20)
        ls=lignes_historique(self.ref,'69387')
        self.assertEqual(ls[0]['Année'],2025)
        self.assertEqual(ls[0]['Source'],'Avis de TF')
    def test_importation_conserve_annee_reelle(self):
        pub={'code_insee':'69387','annee':2025,'source':'OFGL','nature':'REI',
             'taux':{'teom':8.9,'commune':33,'tfb_global':45.0},
             'preuves':{'teom':{'source':'OFGL','methode':'taux net'},'commune':{'source':'OFGL'}}}
        saved,errors=integrer_publication(self.ref,pub)
        self.assertEqual(len(saved),2)
        self.assertEqual(errors,[])
        self.assertEqual(resoudre(self.ref,'69387',2026,'commune')['annee_source'],2025)
        self.assertIsNone(resoudre(self.ref,'69387',2026,'syndicat'))

class CollecteV7(unittest.TestCase):
    def test_mixte_2026_2025_pour_composantes(self):
        calls=[]
        def dgcl(code,year):
            calls.append(('dgcl',year))
            if year==2026:
                return {'taux':{'commune':33.2,'epci':2.4},'source':'DGCL 2026','preuves':{}}
            return {'taux':{'commune':32.9,'epci':2.4},'source':'DGCL 2025','preuves':{}}
        def rei(code,year):
            calls.append(('rei',year))
            return {'taux':{'commune':32.9,'teom':8.8,'gemapi':0.3},'source':'REI 2025',
                    'preuves':{},'avertissements':['Zonage TEOM à confirmer']}
        got=preparer('69387',2026,cherche_dgcl=dgcl,cherche_rei=rei)
        self.assertEqual(got['propositions']['commune']['annee'],2026)
        self.assertEqual(got['propositions']['commune']['taux'],33.2)
        self.assertEqual(got['propositions']['teom']['annee'],2025)
        self.assertTrue(got['propositions']['teom']['repli'])
        self.assertEqual(calls,[('dgcl',2026),('dgcl',2025),('rei',2025)])
    def test_echec_2026_n_empeche_pas_2025(self):
        def dgcl(code,y):
            if y==2026:raise ValueError('Indisponible')
            return {'taux':{'commune':23},'source':'DGCL 2025','preuves':{}}
        def rei(code,y):
            return {'taux':{'teom':8},'source':'REI 2025','preuves':{}}
        got=preparer('42005',2026,cherche_dgcl=dgcl,cherche_rei=rei)
        self.assertEqual(got['propositions']['commune']['annee'],2025)
        self.assertTrue(got['incidents'])
        self.assertIn('teom',got['propositions'])

class ReiV7(unittest.TestCase):
    def test_libelles_et_secret_stat(self):
        items=[{'libelle':'FB - COMMUNE / TAUX VOTÉ','valeur':35.2},
               {'libelle':'FB - COMMUNE / TAUX NET','valeur':35.1},
               {'libelle':'FB - INTERCOMMUNALITÉ / TAUX VOTÉ','valeur':2.1},
               {'libelle':'FB - GEMAPI / TAUX NET GFP','valeur':0.32},
               {'libelle':'TEOM - INTERCOMMUNALITÉ / TAUX NET','valeur':8.1},
               {'libelle':'FB - SYNDICAT / MONTANT NET','valeur':700000},
               {'libelle':'FB - SYNDICAT / TAUX NET','valeur':1.5,'sec_stat':'sec_stat'}]
        data,proof,warns=extraire_rei(items,2025,'42005')
        self.assertEqual(data['commune'],35.1)
        self.assertEqual(data['epci'],2.1)
        self.assertEqual(data['gemapi'],0.32)
        self.assertEqual(data['teom'],8.1)
        self.assertNotIn('syndicat',data)
        self.assertTrue(any('zonage' in w.lower() for w in warns))
    def test_plusieurs_zones_teom_bloque_taux(self):
        items=[{'libelle':'TEOM - INTERCOMMUNALITÉ / TAUX NET ZONE 1','valeur':8.1},
               {'libelle':'TEOM - INTERCOMMUNALITÉ / TAUX NET ZONE 2','valeur':9.3}]
        data,_,warns=extraire_rei(items,2025,'42005')
        self.assertNotIn('teom',data)
        self.assertTrue(warns)

class DgclV7(unittest.TestCase):
    def test_xlsx_minimal_2026(self):
        wb=Workbook();ws=wb.active
        ws.append(['Code INSEE','Taux TFPB'])
        ws.append(['69123',31.23])
        ws.append(['42005',27.1])
        buf=io.BytesIO();wb.save(buf)
        parsed=lire_tableur_dgcl(buf.getvalue(),'communes',2026)
        self.assertEqual(parsed['taux']['69123'],31.23)

if __name__=='__main__':unittest.main()
