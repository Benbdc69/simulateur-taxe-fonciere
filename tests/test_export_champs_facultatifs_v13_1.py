"""Empêche la régression de NameError lors du calcul sans détails de bâtiment."""
import ast
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'page_calcul_v9.py'


class ExportChampsFacultatifsTests(unittest.TestCase):
    def test_champs_facultatifs_initialises_hors_case_cochee(self):
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        # Chercher l'initialisation inconditionnelle avant le groupe de champs facultatifs.
        assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                       and len(node.targets) == 4
                       and {elt.id for elt in node.targets if isinstance(elt, ast.Name)}
                       == {'bat', 'ent', 'niv', 'porte'}]
        self.assertEqual(1, len(assignments), 'Initialisation commune aux quatre champs manquante')
        assignment = assignments[0]
        self.assertIsInstance(assignment.value, ast.Constant)
        self.assertEqual('', assignment.value.value)
        # Exécution isolée de l'affectation telle qu'elle se trouve dans la vraie page.
        namespace = {}
        code = compile(ast.fix_missing_locations(ast.Module(body=[assignment], type_ignores=[])),
                       str(SOURCE), 'exec')
        exec(code, {}, namespace)
        self.assertEqual({k: '' for k in ('bat', 'ent', 'niv', 'porte')}, namespace)
        # Les champs restent utilisés dans l'export en cas de saisie facultative.
        contents = SOURCE.read_text(encoding='utf-8')
        for field, variable in [('batiment', 'bat'), ('entree', 'ent'), ('niveau', 'niv'), ('porte', 'porte')]:
            self.assertIn(f"'{field}':{variable}", contents)


if __name__ == '__main__':
    unittest.main()
