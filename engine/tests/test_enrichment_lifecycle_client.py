import pathlib,subprocess,unittest

class EnrichmentLifecycleClient(unittest.TestCase):
    def test_sql_export_and_hydration_lifecycle(self):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/enrichment-lifecycle-client.js'
        subprocess.check_call(['node',str(path)])
