"""Régression du problème signalé par l'utilisateur : localisation 69 / 2026.
Les exemples reprennent la STRUCTURE de l'aperçu utilisateur, pas le fichier
DGFiP réel (non téléchargable dans l'environnement de création). 
"""
import io
import sys
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from imports_dgfip import importer, analyser_localisations
from moteur import comm_code, parcel_code, localisation_automatique


def ods_fixture(rows):
    def cell(v):
        if v is None:
            return '<table:table-cell/>'
        if isinstance(v,(float,int)):
            return (f'<table:table-cell office:value-type="float" '
                    f'office:value="{v}"/>')
        return ('<table:table-cell office:value-type="string">'
                '<text:p>'+escape(str(v))+'</text:p></table:table-cell>')
    body=''.join('<table:table-row>'+''.join(cell(x) for x in row)+'</table:table-row>' for row in rows)
    xml=('<?xml version="1.0" encoding="UTF-8"?>'
         '<office:document-content '
         'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
         'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
         'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
         '<office:body><office:spreadsheet>'
         '<table:table table:name="Feuille1">'+body+'</table:table>'
         '</office:spreadsheet></office:body></office:document-content>')
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as f:f.writestr('content.xml',xml)
    return buf.getvalue()


class DonneesLocalisations2026SansEnTetes(unittest.TestCase):
    def test_identifiants_cadastraux_numeriques_ods(self):
        self.assertEqual(comm_code(10.0), '010')
        self.assertEqual(comm_code('10.0'), '010')
        self.assertEqual(comm_code('010'), '010')
        self.assertEqual(parcel_code(70.0), '0070')
        self.assertEqual(parcel_code('70.0'), '0070')
        self.assertEqual(parcel_code('0070'), '0070')
        self.assertEqual(parcel_code(0.0), '')

    def test_69_format_sans_entetes_reproduit_message(self):
        rows=[['Pour les lignes où une section figure sans numéro, la section entière est concernée'],
              [69.0,10.0,'L ARBRESLE','AT',70.0,1.0],
              [69.0,10.0,'L ARBRESLE','AT',141.0,1.0],
              [69.0,10.0,'L ARBRESLE','AT',142.0,1.0],
              [69.0,10.0,'L ARBRESLE','AT',143.0,1.0],
              [69.0,20.0,'AUTRE COMMUNE','AB',50.0,0.9]]
        data,sha=importer(ods_fixture(rows),'coef-loc-69.ods','localisations')
        self.assertEqual(len(data),5)
        self.assertEqual(data[0]['commune'],'L ARBRESLE')
        self.assertEqual(data[0]['code_commune'],'010')
        self.assertEqual(data[0]['section'],'AT')
        self.assertEqual(data[0]['parcelle'],'0070')
        self.assertEqual(data[0]['coefficient'],1.0)
        ref={'localisations':{'69':{'2026':data}}}
        coeff, msg, mill=localisation_automatique(ref,'69',2026,'L ARBRESLE','000','AT','0070','010')
        self.assertEqual((coeff,mill),(1.0,2026))
        coeff,_,_=localisation_automatique(ref,'69',2026,'AUTRE COMMUNE','','AB','0050','020')
        self.assertEqual(coeff,0.9)

    def test_section_entiere_sans_numero_de_parcelle(self):
        rows=[[69.0,10.0,'L ARBRESLE','AA','',1.1]]*4
        data,sha=importer(ods_fixture(rows),'coef-loc-69.ods','localisations')
        self.assertEqual(data[0]['parcelle'],'')
        ref={'localisations':{'69':{'2026':data}}}
        coeff,_,_=localisation_automatique(ref,'69',2026,'L ARBRESLE','','AA','0822','010')
        self.assertEqual(coeff,1.1)

    def test_un_fichier_atypique_non_reconnu_reste_refuse(self):
        rows=[['Ceci est un fichier sans références cadastrales'], ['Bonjour','Monde',2.0]]*5
        with self.assertRaises(ValueError):
            analyser_localisations(rows)

    def test_colonnes_avec_entetes_reste_compatible(self):
        rows=[['Code commune','Nom commune','Section','Numéro de parcelle','Coefficient de localisation']]
        rows.extend([[10.0,'L ARBRESLE','AT',float(n),1.1] for n in range(70,82)])
        got=analyser_localisations(rows)
        self.assertEqual(got[0]['code_commune'],'010')
        self.assertEqual(got[0]['parcelle'],'0070')

if __name__=='__main__':unittest.main()
