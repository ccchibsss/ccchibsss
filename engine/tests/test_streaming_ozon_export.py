"""File-backed row-major exports: parity, bounded iteration, cleanup and HTTP."""
import csv,hashlib,io,json,pathlib,sys,tempfile,threading,unittest,urllib.request,zipfile
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine as E

class StreamingOzonExport(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=E.DATA,E.DB_PATH,E._TOKEN_CACHE
        E.DATA=pathlib.Path(self.tmp.name);E.DB_PATH=E.DATA/'export.db';E._TOKEN_CACHE='test-stream-export'
        self.conn=E.db()
        self.conn.executemany('INSERT INTO products(article,brand,name,price,weight,length,width,height,visible,excluded) VALUES(?,?,?,?,?,?,?,?,?,?)',[
            ('0001','B','Unicode 😀 & < > "\r\n',125,1,2,3,4,1,0),
            ('0002','B','=CMD()',0,0,0,0,0,1,0),
            ('0003','B','excluded',20,1,2,3,4,1,1),
            ('0004','B','hidden',20,1,2,3,4,0,0),
            ('0005','C','Цена ₽',20,1,2,3,4,1,0)])
        self.conn.commit()
    def tearDown(self):
        self.conn.close();E.DATA,E.DB_PATH,E._TOKEN_CACHE=self.old;self.tmp.cleanup()
    def parts(self,output):
        output.seek(0)
        with zipfile.ZipFile(output) as z:return {n:z.read(n) for n in z.namelist()}
    def test_single_sheet_golden_xml(self):
        args=dict(headers=['Код','Число','Текст','Флаг','Формула'],data_rows=iter([
            ['001',12.5,'Unicode 😀 & < > "\r\n',True,42],['002',0,'=CMD()',False,None],[None,-2,'_x0041_\x01','',0]]),
            sheet_name='Лист & 1',header_rows=[['Шаблон'],['',1]],yellow={(0,1),(2,4)},formulas={(0,4):'=B4+1',(1,4):'"text"'})
        expected=json.loads((pathlib.Path(__file__).parent/'fixtures/streaming_xlsx_hashes.json').read_text())
        with E._xlsx_from_rows_file(**args) as output:
            self.assertEqual({n:hashlib.sha256(b).hexdigest() for n,b in self.parts(output).items()},expected)
    def test_ozon_rows_csv_and_xlsx(self):
        keys={('0001','B'),('0002','B'),('0004','B')}
        for selection in (None,keys,set()):
            rows,yellow=E._ozon_rows_data(self.conn,keys=selection,discount_pct=15)
            self.assertEqual([r[1] for r in rows],['0001','0002','0005'] if selection is None else ['0001','0002'] if selection else [])
            self.assertEqual([r[0] for r in rows],list(range(1,len(rows)+1)))
            text=io.StringIO();writer=csv.writer(text,delimiter=';');writer.writerow(E.OZON_HEADERS)
            for row in rows:writer.writerow([E.safe_csv_text(v) for v in row])
            with E.export_ozon_csv_file(self.conn,keys=selection,discount_pct=15) as output:
                self.assertEqual(output.read(),E.encode_csv(text.getvalue(),'utf-8'))
            tpl=E.ozon_template_rows()
            expected=E._xlsx_from_rows(tpl[1] if tpl else E.OZON_HEADERS,rows,'Ozon',header_rows=[tpl[0],tpl[2],tpl[3]] if tpl else None,yellow=yellow)
            with E.export_ozon_xlsx_file(self.conn,keys=selection,discount_pct=15) as output:
                self.assertEqual(self.parts(output),self.parts(io.BytesIO(expected)))
        with E.export_ozon_csv_file(self.conn,keys={('0005','C')},enc='cp1251') as output:
            self.assertIn('руб.'.encode('cp1251'),output.read())
        with self.assertRaisesRegex(ValueError,'Windows-1251'):
            E.export_ozon_csv_file(self.conn,enc='cp1251')
    def test_no_legacy_materialization_and_error_cleanup(self):
        with patch.object(E,'_ozon_rows_data',side_effect=AssertionError('legacy list called')):
            with E.export_ozon_xlsx_file(self.conn) as output:self.assertGreater(output.seek(0,2),100)
            with E.export_ozon_csv_file(self.conn) as output:self.assertGreater(output.seek(0,2),100)
        original=tempfile.TemporaryFile;created=[]
        def make(*a,**kw):
            result=original(*a,**kw);created.append(result);return result
        def broken():yield ['valid'];raise RuntimeError('late source failure')
        with patch('tempfile.TemporaryFile',make):
            with self.assertRaisesRegex(RuntimeError,'late source failure'):E._xlsx_from_rows_file(['A'],broken())
            with self.assertRaisesRegex(ValueError,'Windows-1251'):E.export_ozon_csv_file(self.conn,enc='cp1251')
        self.assertTrue(created);self.assertTrue(all(f.closed for f in created))
    def test_csv_protection_and_unmodified_numeric_codes(self):
        values=['=1+2','+SUM(A1:A2)','-2+CMD()','@SUM(1)','\t123','0001','00012345678901234567','a;b','quoted "value"','line\r\nbreak',None]
        def rows(*args,**kwargs):yield values,set()
        with patch.object(E,'_iter_ozon_rows_meta',rows):
            with E.export_ozon_csv_file(self.conn) as output:
                parsed=list(csv.reader(io.StringIO(output.read().decode('utf-8-sig'),newline=''),delimiter=';'))
        self.assertEqual(parsed[1],[E.safe_csv_text(v) for v in values])
        self.assertEqual(parsed[1][:5],["'=1+2","'+SUM(A1:A2)","'-2+CMD()","'@SUM(1)","'\t123"])
        self.assertEqual(parsed[1][5:7],['0001','00012345678901234567'])
    def test_xlsx_codes_keep_leading_zeroes_and_long_digit_precision(self):
        import xml.etree.ElementTree as ET
        barcode='00012345678901234567';tnved='0001234567';original='000001'
        self.conn.execute('UPDATE products SET barcode=?,tnved=?,original_article=? WHERE article=?',(barcode,tnved,original,'0001'))
        with E.export_ozon_xlsx_file(self.conn,keys={('0001','B')}) as output:
            root=ET.fromstring(self.parts(output)['xl/worksheets/sheet1.xml'])
        ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        row=root.findall('x:sheetData/x:row',ns)[-1]
        cells={c.attrib['r'].rstrip('0123456789'):c for c in row}
        for column,expected in [('B','0001'),('K',barcode),('L',tnved),('U',original)]:
            self.assertEqual(cells[column].get('t'),'inlineStr')
            self.assertEqual(cells[column].find('x:is/x:t',ns).text,expected)
    def test_csv_write_buffer_is_bounded_and_flushed(self):
        writes=[]
        class Output(io.BytesIO):
            def write(self,data):writes.append(len(data));return super().write(data)
        def rows(*args,**kwargs):
            for i in range(1000):yield [i,'0001','x'*2000],set()
        output=Output()
        with patch('tempfile.TemporaryFile',return_value=output),patch.object(E,'_iter_ozon_rows_meta',rows):
            result=E.export_ozon_csv_file(self.conn)
            self.assertIs(result,output)
            self.assertEqual(output.read().count(b'\r\n'),1001)
            self.assertLess(len(writes),40)
            self.assertLess(max(writes),70000)
        output.close()
    def test_get_and_post_use_file_response(self):
        server=E.ThreadingHTTPServer(('127.0.0.1',0),E.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch.object(E,'export_ozon_xlsx_bytes',side_effect=AssertionError('bytes API called')),patch.object(E,'export_ozon_csv_bytes',side_effect=AssertionError('bytes API called')):
                for fmt in ('csv','xlsx'):
                    for method in ('GET','POST'):
                        req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/export/ozon.'+fmt,
                            data=b'{}' if method=='POST' else None,headers={'X-UC-Token':'test-stream-export','Content-Type':'application/json'},method=method)
                        with urllib.request.urlopen(req) as response:
                            data=response.read();self.assertEqual(int(response.headers['Content-Length']),len(data))
                            if fmt=='xlsx':self.assertIn('xl/worksheets/sheet1.xml',self.parts(io.BytesIO(data)))
                            else:self.assertTrue(data.startswith(b'\xef\xbb\xbf'))
        finally:server.shutdown();server.server_close();thread.join(5)
