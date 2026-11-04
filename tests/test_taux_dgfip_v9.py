import io
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openpyxl import Workbook
from taux_composantes import lire_tableur_dgcl, rechercher_rei, code_commune_fiscale
from taux_territoriaux_dgfip import analyser_taux_dgfip_2025, rechercher_taux_detailles
from collecte_taux import preparer
from historique_taux import enregistrer, resoudre_tout


class MockResponse:
    def __init__(self,p):self.p=p
    def raise_for_status(self):pass
    def json(self):return self.p

class DGFIPSession:
    def __init__(self,rows):self.rows=rows;self.queries=[]
    def get(self,url,params=None,timeout=None):
        self.queries.append((url,params))
        if url.endswith('records'):
            return MockResponse({'total_count':len(self.rows),'results':self.rows})
        return MockResponse({'fields':[{'name':k} for k in self.rows[0].keys()]})


class TauxV9(unittest.TestCase):
    def test_tfb_reconnait_libelles_dgcl_2026(self):
        wb=Workbook();ws=wb.active
        ws.append(['Statistiques 2026'])
        ws.append(['Département','Code commune','Libellé commune','Taxe sur le foncier bâti','Taxe sur le foncier non bâti'])
        ws.append([69,123,'LYON',31.89,19.97])
        ws.append([69,387,'LYON 7EME',31.89,19.97])
        output=io.BytesIO();wb.save(output)
        result=lire_tableur_dgcl(output.getvalue(),'communes',2026)
        self.assertAlmostEqual(result['taux']['69123'],31.89)
        self.assertAlmostEqual(result['taux']['69387'],31.89)
        self.assertEqual(code_commune_fiscale('69387'),'69123')

    def test_tfb_format_variants(self):
        for title in ('TFB','Taux voté FB 2026','Taxe foncière sur les propriétés bâties'):
            with self.subTest(title=title):
                wb=Workbook();ws=wb.active
                ws.append(['Code INSEE de la commune',title])
                ws.append(['69123',31.89])
                b=io.BytesIO();wb.save(b)
                result=lire_tableur_dgcl(b.getvalue(),'communes',2026)
                self.assertEqual(result['taux']['69123'],31.89)

    def test_rei_2025_lyon_cinq_composantes_et_0_verifie(self):
        record={'insee_com':'69123','e12vote':31.89,'e22':0.12,'e32vote':0.55,'e52':0.0,
                'e52a':0.0,'e52tasa':0.0,'e52ggemapi':0.26,'taux_plein_teom':5.19,
                'taux_global_tfb':32.82}
        s=DGFIPSession([record]);result=rechercher_taux_detailles('69387',2025,session=s)
        self.assertEqual(result['code_commune_taux'],'69123')
        self.assertEqual(result['taux']['commune'],31.89)
        self.assertEqual(result['taux']['teom'],5.19)
        self.assertEqual(result['taux']['taxes_speciales'],0.0)
        self.assertIn('insee_com = "69123"',s.queries[-1][1]['where'])
        self.assertTrue(any('zonage' in v.lower() for v in result['avertissements']))

    def test_valeur_absente_nest_jamais_zero(self):
        r={'insee_com':'69123','e12vote':31.89,'e22':None,'e32vote':0.55,
           'e52':0.0,'e52a':0.0,'e52tasa':0.0,'e52ggemapi':0.0,'taux_plein_teom':None}
        d=analyser_taux_dgfip_2025([r],code_insee='69123')
        self.assertNotIn('syndicat',d['taux'])
        self.assertNotIn('teom',d['taux'])
        self.assertEqual(d['taux']['gemapi'],0.0)

    def test_millesime_separe_2025_2026(self):
        def dgcl(code,annee):return {'taux':{'commune':31.89,'epci':0.55},'source':'DGCL'}
        def rei(code,annee):return {'taux':{'syndicat':0.12,'gemapi':0.26,'teom':5.19},'source':'DGFiP'}
        p=preparer('69387',2026,cherche_dgcl=dgcl,cherche_rei=rei)
        self.assertEqual((p['propositions']['commune']['annee'],p['propositions']['commune']['taux']),(2026,31.89))
        self.assertEqual((p['propositions']['teom']['annee'],p['propositions']['teom']['taux']),(2025,5.19))
        self.assertTrue(p['propositions']['gemapi']['repli'])
        ref={}
        for k,v in p['propositions'].items():
            enregistrer(ref,'69387',v['annee'],k,v['taux'],'Publication vérifiée')
        all_rates=resoudre_tout(ref,'69387',2026)
        self.assertEqual(all_rates['commune']['annee_source'],2026)
        self.assertEqual(all_rates['gemapi']['annee_source'],2025)

    def test_refuse_un_millesime_2026_a_la_place_de_2025(self):
        with self.assertRaises(ValueError):analyser_taux_dgfip_2025([{'insee_com':'69123'}],code_insee='69123',millesime=2026)
        with self.assertRaises(ValueError):rechercher_taux_detailles('69123',2026)

    def test_territoire_incorrect_refuse(self):
        with self.assertRaises(ValueError):analyser_taux_dgfip_2025([{'insee_com':'69124','e12vote':31.89}],code_insee='69123')

if __name__=='__main__':unittest.main()
