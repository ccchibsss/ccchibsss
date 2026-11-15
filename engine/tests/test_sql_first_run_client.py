import pathlib,subprocess,unittest

class SqlFirstRun(unittest.TestCase):
    def test_first_run_and_first_price(self):
        subprocess.check_call(['node',str(pathlib.Path(__file__).resolve().parents[2]/'tests/sql-first-run-client.js')])
