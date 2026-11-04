"""Régressions V6 : restitutions des en-têtes indiqués par l'utilisateur, 42/43/69.
Les données de test reprennent les extraits fournis, sans prétendre être des ODS officiels complets.
"""
import io
import sys
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from imports_dgfip import analyser_neutralisations, importer
from referentiel import integrer_jeu
from moteur import neutralisation_automatique

HEADER_2021 = [
 'DÉPARTEMENT', 'CODE INSEE DE LA COMMUNE', 'PRÉFIXE', 'LIBELLE DE LA COMMUNE',
 'COEFFICIENT DE NEUTRALISATION COMMUNE/SYND',
 'COEFFICIENT DE NEUTRALISATION TSE/GEMAPI',
 'COEFFICIENT DE NEUTRALISATION EPCI']
HEADER_2017 = [
 'Code commune', 'Préfixe', 'LIB-CNE', 'Coefficient de neutralisation communal',
 'Coefficient de neutralisation syndicat de',
 'Coefficient de neutralisation EPCI',
 'Coefficient de neutralisation départementale']

BASES = {'42': ('ABOEN', .354183, .275358, .424353),
         '43': ('AGNAT', .336245, .32429, .342185),
         '69': ('AFFOUX', .278778, .241176, .323096)}


def jeu_2021(dep):
    nom, communal, other, _ = BASES[dep]
    rows = [['Informations générales'], HEADER_2021,
            [float(dep), 1.0, '', nom, communal, other, other]]
    # En-têtes et lignes cohérents d'un fichier départemental.
    rows.extend([float(dep), float(i), '', f'COMMUNE-{i}', communal, other, other]
                for i in range(2, 50))
    return rows


def jeu_2017(dep):
    nom, _, other, departement = BASES[dep]
    rows = [['Notice de publication'], HEADER_2017,
            [1.0, '', nom, other, other, other, departement]]
    rows.extend([float(i), '', f'COMMUNE-{i}', other, other, other, departement]
                for i in range(2, 50))
    return rows


def creer_ods(rows, name='coef-neut-ap21-01'):
    def cell(x):
        if x is None or x == '':
            return '<table:table-cell/>'
        if isinstance(x, (int,float)):
            return f'<table:table-cell office:value-type="float" office:value="{x}"/>'
        return '<table:table-cell office:value-type="string"><text:p>'+escape(str(x))+'</text:p></table:table-cell>'
    content = ('<?xml version="1.0" encoding="utf-8"?>'
          '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
          'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
          'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
          '<office:body><office:spreadsheet><table:table table:name="'+name+'">'
          + ''.join('<table:table-row>'+''.join(cell(c) for c in r)+'</table:table-row>' for r in rows)
          +'</table:table></office:spreadsheet></office:body></office:document-content>')
    out=io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:z.writestr('content.xml',content)
    return out.getvalue()

class NeutralisationV6Tests(unittest.TestCase):
    def test_2021_42_43_69(self):
        for dep,(name,communal,other,_) in BASES.items():
            with self.subTest(dep=dep):
                data=analyser_neutralisations(jeu_2021(dep))
                self.assertEqual(len(data),49)
                first=data[0]
                self.assertEqual(first['nom_commune'],name)
                self.assertEqual(first['code_commune'],'001')
                self.assertEqual(first['prefixe'],'')
                self.assertAlmostEqual(first['commune'],communal)
                self.assertAlmostEqual(first['syndicat'],communal)
                self.assertAlmostEqual(first['epci'],other)
                self.assertAlmostEqual(first['taxes_speciales'],other)
                self.assertAlmostEqual(first['gemapi'],other)
                self.assertIsNone(first['teom'])

    def test_2017_42_43_69(self):
        for dep,(name,_,other,departement) in BASES.items():
            with self.subTest(dep=dep):
                data=analyser_neutralisations(jeu_2017(dep))
                self.assertEqual(len(data),49)
                first=data[0]
                self.assertEqual(first['nom_commune'],name)
                self.assertEqual(first['code_commune'],'001')
                self.assertEqual(first['prefixe'],'')
                self.assertAlmostEqual(first['commune'],other)
                self.assertAlmostEqual(first['syndicat'],other)
                self.assertAlmostEqual(first['epci'],other)
                self.assertAlmostEqual(first['coef_departement'],departement)
                self.assertIsNone(first['teom'])
                self.assertIsNone(first['gemapi'])

    def test_import_ods_2021_et_2017(self):
        for dep in BASES:
            for year,rows in [(2021,jeu_2021(dep)),(2017,jeu_2017(dep))]:
                with self.subTest(dep=dep,year=year):
                    blob=creer_ods(rows,'coef-neut-ap21-01' if year==2021 else 'Feuille1')
                    data, sha=importer(blob,f'coef-neut-{dep}.ods','neutralisations')
                    self.assertEqual(len(data),49)
                    self.assertEqual(len(sha),64)

    def test_versions_separees_ne_remplacent_pas_period_previous(self):
        ref={'tarifs':{},'localisations':{},'secteurs':{},'neutralisations':{},'sources':{}}
        intégration = lambda year, data: integrer_jeu(ref,'42','neutralisations',year,data,{'origine':'test'})
        intégration(2017,analyser_neutralisations(jeu_2017('42')))
        intégration(2021,analyser_neutralisations(jeu_2021('42')))
        old,_=neutralisation_automatique(ref,'42','ABOEN',2020)
        new,_=neutralisation_automatique(ref,'42','ABOEN',2026)
        self.assertAlmostEqual(old['commune'],.275358)
        self.assertAlmostEqual(new['commune'],.354183)
        self.assertIsNone(new['teom'])

if __name__=='__main__':unittest.main()
