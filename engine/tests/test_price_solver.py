"""Differential tests execute the actual browser solver, not a copied JS fixture."""
import json
import pathlib
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from price_solver import solve_integer, stable_floor
import uc_engine as E


class BrowserSolverParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node required to execute browser reference')
    def test_actual_js_solver(self):
        html = (pathlib.Path(__file__).resolve().parents[2] / 'index.html').read_text()
        source = html.split('function solveEcoInteger(initial, metric) {', 1)[1].split('\nfunction solveMarketplacePrices', 1)[0]
        js = 'const num = x => Number(x) || 0;\nfunction solveEcoInteger(initial, metric) {' + source
        expressions = [
            ('p * .83 - 123.45', lambda p: p * .83 - 123.45),
            ('p < 250 ? p - 100 : p - 700', lambda p: p - 100 if p < 250 else p - 700),
            ('p >= 100 && p <= 120 ? 1 : p - 5000', lambda p: 1 if 100 <= p <= 120 else p - 5000),
            ('Math.round(p * .17) - 50', lambda p: int(p * .17 + .5) - 50),
        ]
        cases = [(initial, expression, fn) for initial in (0, 110, 350, 1000) for expression, fn in expressions]
        js += '\nconsole.log(JSON.stringify([' + ','.join(
            f'solveEcoInteger({initial}, p => {expression})' for initial, expression, _ in cases) + ']));'
        expected = json.loads(subprocess.check_output(['node', '-e', js], text=True))
        self.assertEqual([solve_integer(initial, fn) for initial, _, fn in cases], expected)

    def test_stable_tariff_boundary(self):
        metric = lambda p: p - 100 if p <= 300 else p - 700
        self.assertEqual(stable_floor(100, metric, 300), 100)

    def test_monthly_rounding(self):
        unit = {'_monthly_parts': [.333333, .666666], 'tax': 0, 'total': 101}
        net = E._net_unit(200, 100, {'_fixed_month': 1}, 3, unit)
        self.assertEqual(net, (600 - 300 - 1 - 2 - 1) / 3)
