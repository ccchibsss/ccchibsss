"""The consolidated engine must work without any legacy module files."""
import json,pathlib,shutil,subprocess,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]

class SingleFileEngine(unittest.TestCase):
    def test_isolated_copy_imports_every_internal_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=pathlib.Path(tmp)
            shutil.copy2(ROOT/'engine/uc_engine.py',dest)
            for source in (ROOT/'engine').glob('*.json'):shutil.copy2(source,dest)
            script='''import sys,importlib,json,pickle
sys.path.insert(0,sys.argv[1])
import uc_engine as E
for name in E._BUNDLED_SOURCES:
    module=importlib.import_module(name)
    assert module.__file__==E.__file__,(name,module.__file__)
from enrichment_transport import JSDate
value=JSDate(None,'Invalid Date',None)
assert pickle.loads(pickle.dumps(value))==value
assert E.calc_row({'price':100,'cost':50,'sales':10},{}) is not None
print(json.dumps(sorted(E._BUNDLED_SOURCES)))
'''
            names=json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',script,str(dest)],cwd=tmp,text=True))
            self.assertEqual(len(names),28)
            self.assertEqual([p.name for p in dest.glob('*.py')],['uc_engine.py'])
            cli=subprocess.run([sys.executable,'-I','-B',str(dest/'uc_engine.py'),'calc'],cwd=tmp,capture_output=True,text=True)
            self.assertEqual(cli.returncode,0,cli.stderr)
            self.assertIn('DEMO-CLT-001',cli.stdout)

    def test_only_one_runtime_python_file(self):
        self.assertEqual(sorted(p.name for p in (ROOT/'engine').glob('*.py')),['uc_engine.py'])

    def test_no_non_test_python_files_outside_engine(self):
        tracked=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','*.py'],cwd=ROOT,text=True).splitlines()
        runtime=[name for name in tracked if (ROOT/name).exists() and not name.startswith('engine/tests/')]
        self.assertEqual(runtime,['engine/uc_engine.py'])
        result=subprocess.run([sys.executable,str(ROOT/'engine/uc_engine.py'),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('poc',result.stdout)
