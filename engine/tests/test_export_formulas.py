import io,json,pathlib,sqlite3,subprocess,sys,unittest,zipfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from export_formulas import FORMULA_KEYS,cached_formula,column_letter,unavailable
import uc_engine as E

class ExportFormulas(unittest.TestCase):
    def reference(self,cases):
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/export-formulas-reference.js'
        return json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(cases),text=True))

    def test_all_browser_formula_definitions(self):
        refs={k:column_letter(i) for i,k in enumerate('stock minStock visible visibleReason weight length width height excluded deletePending markRequired markCompliant deficit shipReady effPrice costMult commPct cheapFbsFlag cheapFbsRate acqPct boostPct cofinPct uTransitPack prUnit netProfit revenue cogs perUnitNet price cost multUsed markupPct tgtPrice volumeExplicit volumeInput agencyFeePerSku buyerDeliveryUnit uLog uSc uPack storageUnit returnStorageUnit slaPenaltyPerUnit nonStdUnit lateShipUnit listingUnit uRet taxUnit'.split())}
        # Include all expense fields required by netProfit; specialFee/penalties
        # intentionally absent in another profile to exercise YM-only omission.
        for key in FORMULA_KEYS:refs.setdefault(key,column_letter(len(refs)))
        cases=[]
        for unit in ['cm','mm']:
            for row in [2,999]:
                for key in sorted(FORMULA_KEYS):
                    cases.append(dict(key=key,row=row,unit=unit,refs=refs,value=1.25))
                    cases.append(dict(key=key,row=row,unit=unit,refs={k:"'Вводы и ставки'!"+v for k,v in refs.items()},value='да'))
                    for omitted in refs:
                        cases.append(dict(key=key,row=row,unit=unit,refs={k:v for k,v in refs.items() if k!=omitted},value=0))
        response=self.reference(cases)
        self.assertEqual(set(response['keys']),set(FORMULA_KEYS),'Every browser formula must have a Python implementation')
        for case,want in zip(cases,response['result']):
            with self.subTest(case=case):self.assertEqual(cached_formula(case['key'],case['row'],case['refs'],case['value'],dim_unit=case['unit']),want)

    def test_actual_availability_guards(self):
        keys=list(FORMULA_KEYS)+['profitWB','beMM','tgtYM','commOzon','volume','priceToSet','c_text']
        contexts=[{}, {'modelReviewRequired':True},{'noBuyInconsistent':True},{'priceInputsIncomplete':True},{'missingTariffBlocked':'missing'},
                  {'mp':{'WB':{},'MM':{},'YM':{},'OZON':{}}}, {'mp':{'OZON':{'inputUnavailable':True}}},
                  {'mp':{'YM':{'comparisonEligible':False}}}]
        cases=[dict(key=k,group=g,context=p,availability=True) for k in keys for g in ['in','calc','ana'] for p in contexts]
        for case,want in zip(cases,self.reference(cases)['result']):
            with self.subTest(case=case):self.assertEqual(bool(unavailable(case['context'],case['key'],case['group'])),want)

    def test_http_export_filtering_and_warning_headers(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        conn.executescript("CREATE TABLE products(article TEXT,brand TEXT);CREATE TABLE eco_results(article TEXT,brand TEXT,total REAL,profit REAL,margin REAL,roi REAL,break_even REAL,target REAL,fields_json TEXT);INSERT INTO products VALUES('A','B'),('Z','B');")
        body={'articles':[{'article':'A','brand':'B'}],
              'columns':[['d','Дефицит'],['s','Остаток'],['m','Мин']],
              'column_meta':[{'key':'deficit','group':'calc','server_formula':True},{'key':'stock'},{'key':'minStock'}],
              'sheets':[{'name':'Юнит-экономика','indices':[0]},{'name':'Вводы и ставки','indices':[1,2]}],
              'formula_options':{'enabled':True,'dim_unit':'cm'},
              'export_cells':[{'article':a,'brand':'B','values':[2,5,3]} for a in ['Z','A']]}
        headers={};status=[]
        handler=SimpleNamespace(path='/export/catalog.xlsx',_deny_bad_host=lambda:False,_auth=lambda:True,
            _body=lambda:body,send_response=status.append,send_header=lambda k,v:headers.update({k:v}),
            end_headers=lambda:None,_maybe_gzip=lambda data:(data,{}),wfile=io.BytesIO(),
            _send=lambda code,value:self.fail(str((code,value))))
        handler._send_bytes=E.Handler._send_bytes.__get__(handler)
        try:
            with patch.object(E,'db',return_value=conn):E.Handler.do_POST(handler)
            self.assertEqual(status,[200])
            self.assertEqual(json.loads(headers['X-UC-Export-Warnings']),{'skipped_formulas':[]})
            self.assertEqual(headers['Access-Control-Expose-Headers'],'X-UC-Export-Warnings')
            with zipfile.ZipFile(io.BytesIO(handler.wfile.getvalue())) as z:
                text=z.read('xl/worksheets/sheet1.xml').decode()
                self.assertIn("'Вводы и ставки'!A2",text);self.assertNotIn("'Вводы и ставки'!A3",text)
            body['sheets']=[{'name':'Юнит-экономика','indices':[0]}]
            with patch.object(E,'db',return_value=conn):E.Handler.do_POST(handler)
            self.assertEqual(json.loads(headers['X-UC-Export-Warnings']),{'skipped_formulas':['deficit']})
        finally:conn.close()

    def test_sql_formula_preparation_and_cached_values(self):
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        conn.executescript("CREATE TABLE products(article TEXT,brand TEXT);CREATE TABLE eco_results(article TEXT,brand TEXT,total REAL,profit REAL,margin REAL,roi REAL,break_even REAL,target REAL,fields_json TEXT);INSERT INTO products VALUES('A','B');")
        cols=[['v','Дефицит'],['s','Остаток'],['m','Мин']]
        meta=[{'key':'deficit','group':'calc','server_formula':True},{'key':'stock'},{'key':'minStock'}]
        sheets=[{'name':'Юнит-экономика','indices':[0]},{'name':'Вводы и ставки','indices':[1,2]}]
        rows=[{'article':'A','brand':'B','values':[2,5,3],'formulas':['MALICIOUS()',None,None]}]
        try:
            summary=E.store_export_cells(conn,rows,cols,meta,{'enabled':True,'dim_unit':'cm'},sheets)
            self.assertEqual(summary,{'skipped_formulas':[]})
            expected='IFERROR(\'Вводы и ставки\'!A2-\'Вводы и ставки\'!B2,"")'
            self.assertEqual(E.export_catalog_records(conn)[0]['__export_formulas']['v'],expected)
            blob=E.export_catalog_xlsx_bytes(conn,columns=cols,sheets=sheets,column_meta=meta)
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                text=z.read('xl/worksheets/sheet1.xml').decode()
                import xml.etree.ElementTree as ET
                root=ET.fromstring(text);ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                self.assertEqual(root.find('.//s:row[@r="2"]/s:c/s:v',ns).text,'2')
                self.assertIn('IFERROR',text);self.assertNotIn('MALICIOUS',text)
            summary=E.store_export_cells(conn,rows,cols,meta,{'enabled':True},[dict(sheets[0],indices=[0])])
            self.assertEqual(summary,{'skipped_formulas':['deficit']})
            E.store_export_cells(conn,rows,cols,meta,{'enabled':False})
            self.assertEqual(E.export_catalog_records(conn)[0]['__export_formulas'],{})
        finally:conn.close()
