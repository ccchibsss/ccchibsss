import pathlib,subprocess,unittest

class ProcessingSwitch(unittest.TestCase):
    def test_actual_mode_switch_and_settings_markup(self):
        subprocess.check_call(['node',str(pathlib.Path(__file__).resolve().parents[2]/'tests/processing-switch-client.js')])
