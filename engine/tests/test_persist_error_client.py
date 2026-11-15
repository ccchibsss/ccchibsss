import pathlib,subprocess,unittest

class PersistErrorClient(unittest.TestCase):
    def test_nested_persistence_errors(self):
        subprocess.check_call(['node',str(pathlib.Path(__file__).resolve().parents[2]/'tests/persist-error-client.js')])
