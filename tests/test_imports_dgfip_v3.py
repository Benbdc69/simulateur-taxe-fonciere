"""Tests d'adaptation aux grilles et fichiers ODS multi-feuilles.
Données synthétiques : les tests ne certifient pas les formats de toutes les publications DGFiP.
"""
import sys, io, zipfile, json, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from imports_dgfip import (analyser_tarifs, analyser_secteurs, analyser_localisations,
                           analyser_neutralisations, importer, apercu_fichier)

ROOT = Path(__file__).resolve().parents[1]
REF = json.loads((ROOT/'data'/'referentiel_initial.json').read_text())

class ImportAdaptatifTest(unittest.TestCase):
    def test_tarifs_category_in_second_column(self):
        d = REF['tarifs']['42']['2025']
        rows = [['DGFiP - Grille tarifaire'],['Désignation','Code de catégorie','Secteur 1','Secteur 2','Secteur 3','Secteur 4','Secteur 5','Secteur 6','Secteur 7']]
        rows.extend([['Description',key]+[value.get(str(i),'') for i in range(1,8)] for key,value in d.items()])
        got = analyser_tarifs(rows)
        self.assertAlmostEqual(got['BUR2']['4'],d['BUR2']['4'])
        self.assertGreaterEqual(len(got),35)

    def test_secteur_multiline_and_bounded_headers(self):
        base = REF['secteurs']['42']
        rows = [['Tableau officiel des secteurs'],
                ['Code INSEE','Nom de la','Section','Secteur','Préfixe'],
                ['', 'commune', 'cadastrale','locatif','cadastral']]
        rows += [[r['code_commune'],r['commune'],r['section'],r['secteur'],r['prefixe']] for r in base[:80]]
        got = analyser_secteurs(rows)
        self.assertEqual(got[0]['commune'],base[0]['commune'])
        self.assertEqual(got[0]['secteur'],base[0]['secteur'])
        self.assertGreaterEqual(len(got),79)

    def test_localisations_abbreviated_headers(self):
        base = REF['localisations']['42']['2024']
        rows = [['Références de localisation'],
                ['Code INSEE', 'Libellé de la commune', 'Préfixe', 'Section cadastrale', 'Numéro de parcelle', 'Coef. localisation']]
        rows += [[r['code_commune'],r['commune'],r['prefixe'],r['section'],r['parcelle'],r['coefficient']] for r in base[:30]]
        got = analyser_localisations(rows)
        self.assertEqual(got[0]['parcelle'],base[0]['parcelle'])
        self.assertEqual(len(got),min(30,len(base)))

    def test_neutralisations_multiline_headers(self):
        base = REF['neutralisations']['42']
        rows = [['Coefficient de neutralisation de taxe foncière'],
                ['Libellé commune','Part communale','Syndicat de communes','EPCI','Taxes spéciales','TEOM','GEMAPI']]
        fields = ['commune','syndicat','epci','taxes_speciales','teom','gemapi']
        rows += [[r['nom_commune']]+[r[k] for k in fields] for r in base[:90]]
        got = analyser_neutralisations(rows)
        self.assertEqual(got[0]['nom_commune'],base[0]['nom_commune'])
        self.assertAlmostEqual(got[0]['gemapi'],base[0]['gemapi'])

    def test_neutralisations_manual_columns(self):
        base=REF['neutralisations']['69']
        fields=['nom_commune','commune','syndicat','epci','taxes_speciales','teom','gemapi']
        rows=[['Codes colonnes spécifiques']] + [[r[k] for k in fields] for r in base[:40]]
        mapping=dict(zip(fields,range(7)))
        got=analyser_neutralisations(rows,colonnes=mapping,ligne_debut=1)
        self.assertEqual(len(got),40)

    def test_ods_multisheet_import_and_preview(self):
        base=REF['localisations']['43']['2024']
        def row(vals):
            cells=[]
            for value in vals:
                if isinstance(value,(int,float)):
                    cells.append('<table:table-cell office:value-type="float" office:value="%s"/>' % value)
                else:
                    text=str(value).replace('&','&amp;').replace('<','&lt;')
                    cells.append('<table:table-cell office:value-type="string"><text:p>%s</text:p></table:table-cell>' % text)
            return '<table:table-row>'+''.join(cells)+'</table:table-row>'
        def sheet(name,rr):
            return '<table:table table:name="'+name+'">'+''.join(row(x) for x in rr)+'</table:table>'
        header=['Code commune','Nom commune','Section','N° plan','Coef. de localisation']
        content = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            '<office:body><office:spreadsheet>'+sheet('NOTICE',[['Notice d utilisation']])+
            sheet('COEFF',[header]+[[r['code_commune'],r['commune'],r['section'],r['parcelle'],r['coefficient']] for r in base[:55]])+
            '</office:spreadsheet></office:body></office:document-content>')
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z:z.writestr('content.xml',content)
        parsed,sha=importer(buffer.getvalue(),'coef-loc-43.ods','localisations')
        self.assertGreater(len(parsed),10)
        preview=apercu_fichier(buffer.getvalue(),'coef-loc-43.ods')
        self.assertEqual([s['nom'] for s in preview],['NOTICE','COEFF'])

if __name__=='__main__':unittest.main()
