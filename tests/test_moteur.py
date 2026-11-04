import json
import pathlib
import sys
import unittest
from io import BytesIO
import zipfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from moteur import (secteur_automatique,tarif_automatique,localisation_automatique,
                    neutralisation_automatique,estimation)
from imports_dgfip import (analyser_secteurs,analyser_localisations,analyser_neutralisations,
                           analyser_tarifs,tableau_ods,tableau_xlsx,url_fichier)

BASE=pathlib.Path(__file__).resolve().parents[1]
REF=json.loads((BASE/'data'/'referentiel_initial.json').read_text(encoding='utf8'))

class MoteurTests(unittest.TestCase):
    def test_identification_andrezieux(self):
        self.assertEqual(secteur_automatique(REF,'42','ANDREZIEUX-BOUTHEON','','BI','42005')[0],4)
        self.assertEqual(localisation_automatique(REF,'42',2025,'ANDREZIEUX-BOUTHEON','','BI',242,'42005')[0],1.0)
        self.assertEqual(tarif_automatique(REF,'42',2025,'BUR2',4),131.3)
    def test_regression_excel(self):
        neut,_=neutralisation_automatique(REF,'42','ANDREZIEUX-BOUTHEON')
        t={'commune':30.09,'syndicat':2.6,'epci':0,'taxes_speciales':0.224,'teom':8.3,'gemapi':0.779}
        abat={'commune':40,'syndicat':40,'epci':0,'taxes_speciales':40,'teom':0,'gemapi':40}
        result=estimation({'P1':1144,'P2':183,'P3':298,'PK1':541,'PK2':253},131.3,1.0,neut,t,abat)
        self.assertAlmostEqual(result['surface_ponderee_totale'],1616.2,places=5)
        self.assertAlmostEqual(result['valeur_locative_brute'],212207.06,places=2)
        self.assertAlmostEqual(result['total_estime'],11302.06514853,places=2)
    def test_2026_requires_tarifs_and_localisation(self):
        self.assertIsNone(tarif_automatique(REF,'42',2026,'BUR2',4))
        coef,msg,_=localisation_automatique(REF,'42',2026,'ANDREZIEUX-BOUTHEON','','BI',242,'42005')
        self.assertIsNone(coef)
    def test_missing_section_not_assumed(self):
        sector,_=secteur_automatique(REF,'42','ANDREZIEUX-BOUTHEON','','','42005')
        self.assertIsNone(sector)
    def test_location_parcel_over_section(self):
        ref={'localisations':{'42':{'2026':[
            {'commune':'TEST','code_commune':'001','prefixe':'','section':'AA','parcelle':'','coefficient':1.10},
            {'commune':'TEST','code_commune':'001','prefixe':'','section':'AA','parcelle':'0002','coefficient':1.30},
        ]}}}
        self.assertEqual(localisation_automatique(ref,'42',2026,'TEST','','AA',2,'42001')[0],1.3)
        self.assertEqual(localisation_automatique(ref,'42',2026,'TEST','','AA',3,'42001')[0],1.1)
    def test_bad_parameter(self):
        with self.assertRaises(ValueError):estimation({'P1':-1},10,1,{k:1 for k in ['commune','syndicat','epci','taxes_speciales','teom','gemapi']},{k:0 for k in ['commune','syndicat','epci','taxes_speciales','teom','gemapi']})

class ImportTests(unittest.TestCase):
    def test_parse_tarifs(self):
        data=analyser_tarifs([[s,123.4,234.5] for s in [x['code'] for x in REF['categories']]])
        self.assertEqual(len(data),39)
        self.assertEqual(data['BUR2']['2'],234.5)
    def test_secteurs_header_preference(self):
        a=[['Code commune','Libellé de commune','Préfixe','Section','Secteur']]+[[str(i),'TEST','','A',4] for i in range(100)]
        out=analyser_secteurs(a)
        self.assertEqual(out[0]['commune'],'TEST')
    def test_localisation_header_preference(self):
        a=[['Département','Code commune','Libellé de la commune','Préfixe','Section','Parcelle','Coefficient de localisation'],
           ['42','005','ANDREZIEUX-BOUTHEON','','BI',242,1.3]]
        out=analyser_localisations(a)
        self.assertEqual(out[0]['commune'],'ANDREZIEUX-BOUTHEON')
        self.assertEqual(out[0]['parcelle'],'0242')
    def test_neutralisation_parse(self):
        a=[['Commune','Coefficient de neutralisation communal','Coefficient de neutralisation syndicat de communes',
            'Coefficient de neutralisation EPCI','Coefficient de neutralisation taxes spéciales',
            'Coefficient de neutralisation TEOM','Coefficient de neutralisation GEMAPI'],
            ['TEST',.2,.2,.3,.3,.4,.3]]
        r=analyser_neutralisations(a)
        self.assertEqual(r[0]['commune'],.2)
        self.assertEqual(r[0]['nom_commune'],'TEST')
    def test_ods_xml(self):
        content='''<?xml version="1.0" encoding="UTF-8"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:spreadsheet><table:table table:name="One"><table:table-row><table:table-cell office:value-type="string"><text:p>Catégorie</text:p></table:table-cell><table:table-cell office:value-type="float" office:value="12.5"><text:p>12,5</text:p></table:table-cell></table:table-row></table:table></office:spreadsheet></office:body></office:document-content>'''
        buf=BytesIO()
        with zipfile.ZipFile(buf,'w') as z:z.writestr('content.xml',content)
        self.assertEqual(tableau_ods(buf.getvalue()),[['Catégorie',12.5]])
    def test_official_urls(self):
        self.assertEqual(url_fichier('42','tarifs',2026),
            'https://www.impots.gouv.fr/sites/default/files/media/rvllp/tarif/2026/tarif-42.xlsx')

if __name__=='__main__':unittest.main()
