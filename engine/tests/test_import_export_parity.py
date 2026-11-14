"""Differential checks against actual browser CSV safety/header implementations."""
import json
import pathlib
import shutil
import subprocess
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine as E


class ImportExportParity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node required for browser reference')
    def test_csv_safety_actual_browser(self):
        values=['=SUM(A1:A2)',' +cmd','-2+cmd','-2','-2,5','@link','\tcode','normal','a\x00b','😀',None,'\u00a0=1']
        script=r"""
const fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('index.html','utf8');
const context={};vm.createContext(context);
for(const name of ['stripXmlIllegal','safeCsvText']){
 const start=html.indexOf('function '+name+'('), end=html.indexOf('\n}',start)+2;
 vm.runInContext(html.slice(start,end),context);
}
process.stdout.write(JSON.stringify(JSON.parse(fs.readFileSync(0,'utf8')).map(v=>context.safeCsvText(v))));
"""
        expected=json.loads(subprocess.check_output(['node','-e',script],cwd=pathlib.Path(__file__).resolve().parents[2],input=json.dumps(values),text=True))
        self.assertEqual([E.safe_csv_text(v) for v in values],expected)

    def test_import_preamble_csv_and_xlsx(self):
        rows=[['Отчёт'],[''],['Артикул','Бренд','Цена'],['00123','B','12,5']]
        import csv,io
        text=io.StringIO();csv.writer(text,delimiter=';').writerows(rows)
        csv_rows=E.rows_from_csv_bytes(text.getvalue().encode('utf-8'))
        xlsx=E._xlsx_from_rows(rows[0],rows[1:])
        xlsx_rows=E.rows_from_xlsx_bytes(xlsx)
        self.assertEqual(csv_rows,xlsx_rows)
        self.assertEqual(csv_rows[0]['article'],'00123')
        self.assertEqual(E.num(csv_rows[0]['price']),12.5)

    def test_cp1251_no_silent_replacement(self):
        self.assertEqual(E.encode_csv('Цена ₽','cp1251').decode('cp1251'),'Цена руб.')
        with self.assertRaisesRegex(ValueError,'подмена символов запрещена'):
            E.encode_csv('😀','cp1251')

    def test_explicit_mapping_replaces_autodetection(self):
        data='Vendor;Maker;Retail\n00123;B;12,5\n'.encode()
        mapping=[{'src':'Vendor','field':'article','enabled':True},
                 {'src':'Maker','field':'brand','enabled':True},
                 {'src':'Retail','field':'price','enabled':True}]
        rows=E.rows_from_csv_bytes(data,mapping)
        self.assertEqual(rows[0]['article'],'00123')
        self.assertEqual(rows[0]['price'],'12,5')
        mapping[2]['enabled']=False
        self.assertNotIn('price',E.rows_from_csv_bytes(data,mapping)[0])

    def test_export_selected_columns_and_delimiter(self):
        from unittest.mock import patch
        import csv,io
        with patch.object(E,'export_catalog_records',return_value=[{'article':'00123','country':'Россия','price':12.5}]):
            data=E.export_catalog_csv_bytes(None,columns=[('country','Страна'),('article','Код'),('price','Цена')],delimiter=',')
            rows=list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
            self.assertEqual(rows,[['Страна','Код','Цена'],['Россия','00123','12.5']])
            data=E.export_catalog_csv_bytes(None,columns=[('price','Цена')],delimiter=';')
            self.assertIn('12,5',data.decode('utf-8-sig'))

    def test_sql_export_custom_and_computed_snapshot(self):
        import sqlite3,csv,io,zipfile
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        conn.executescript("CREATE TABLE products(article TEXT,brand TEXT);"
            "CREATE TABLE eco_results(article TEXT,brand TEXT,total REAL,profit REAL,margin REAL,roi REAL,break_even REAL,target REAL,fields_json TEXT);"
            "INSERT INTO products VALUES('001','B'),('001','C');")
        columns=[['__export_0','Пользовательское'],['__export_1','Вычисляемое'],['__export_2','Код']]
        E.store_export_cells(conn,[{'article':'001','brand':'B','values':['=опасно',12.5,'00042']},
                                  {'article':'001','brand':'C','values':['другой бренд',0,'00043']}],columns)
        records=E.export_catalog_records(conn)
        self.assertEqual(records[0]['__export_2'],'00042')
        data=E.export_catalog_csv_bytes(conn,columns=columns,keys=[('001','B')])
        rows=list(csv.reader(io.StringIO(data.decode('utf-8-sig')),delimiter=';'))
        self.assertEqual(rows[1],["'=опасно",'12,5','00042'])
        data=E.export_catalog_xlsx_bytes(conn,columns=columns,keys=[('001','B')])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml=archive.read('xl/worksheets/sheet1.xml').decode()
        self.assertIn('<v>12.5</v>',xml)
        self.assertIn('00042',xml)
        self.assertNotIn('00043',xml)
        with self.assertRaises(ValueError):
            E.store_export_cells(conn,[{'values':[1]}],columns)
        conn.close()

    def test_formula_cache_row_order_and_csv_values(self):
        import sqlite3,csv,io,zipfile,xml.etree.ElementTree as ET
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        conn.executescript("CREATE TABLE products(article TEXT,brand TEXT);"
            "CREATE TABLE eco_results(article TEXT,brand TEXT,total REAL,profit REAL,margin REAL,roi REAL,break_even REAL,target REAL,fields_json TEXT);"
            "INSERT INTO products VALUES('A','B'),('Z','B'),('unselected','B');")
        cols=[['__export_0','Цена'],['__export_1','Расчёт']]
        E.store_export_cells(conn,[{'article':'Z','brand':'B','values':[10,20],'formulas':[None,'=A2*2']},
                                  {'article':'A','brand':'B','values':[30,60],'formulas':[None,'=A3*2']}],cols)
        records=E.export_catalog_records(conn)
        self.assertEqual([r['article'] for r in records],['Z','A'])
        with zipfile.ZipFile(io.BytesIO(E.export_catalog_xlsx_bytes(conn,columns=cols))) as archive:
            sheet=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        formulas=sheet.findall('.//s:f',ns)
        self.assertEqual([f.text for f in formulas],['A2*2','A3*2'])
        self.assertEqual(sheet.find(".//s:c[@r='B2']/s:v",ns).text,'20')
        csv_data=E.export_catalog_csv_bytes(conn,columns=cols).decode('utf-8-sig')
        self.assertNotIn('A2*2',csv_data)
        self.assertIn('10;20',csv_data)
        E.store_export_cells(conn,[],cols)
        self.assertEqual(E.export_catalog_records(conn),[])
        with self.assertRaises(ValueError):
            E.store_export_cells(conn,[{'values':[1,2],'formulas':[1,2]}],cols)
        conn.close()

    def test_multisheet_relationships_and_cross_sheet_formula(self):
        import io,zipfile,xml.etree.ElementTree as ET
        blob=E._xlsx_workbook([
            {'name':'Юнит-экономика','headers':['Артикул','Итого'],
             'rows':[['001',24]],'formulas':{(0,1):"'Вводы и ставки'!B2*2"}},
            {'name':'Вводы и ставки','headers':['Артикул','Цена'],'rows':[['001',12]]}])
        ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
            'r':'http://schemas.openxmlformats.org/package/2006/relationships'}
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            workbook=ET.fromstring(archive.read('xl/workbook.xml'))
            self.assertEqual([s.get('name') for s in workbook.findall('s:sheets/s:sheet',ns)],
                             ['Юнит-экономика','Вводы и ставки'])
            rels=ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
            for rel in rels:
                self.assertIn('xl/'+rel.get('Target'),archive.namelist())
            root=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            self.assertEqual(root.find('.//s:f',ns).text,"'Вводы и ставки'!B2*2")
            self.assertIn('12',archive.read('xl/worksheets/sheet2.xml').decode())
        try:
            import openpyxl
        except ImportError:
            return
        wb=openpyxl.load_workbook(io.BytesIO(blob),data_only=False)
        self.assertEqual(wb['Юнит-экономика']['B2'].value,"='Вводы и ставки'!B2*2")
        wb.close()
        wb=openpyxl.load_workbook(io.BytesIO(blob),data_only=True)
        self.assertEqual(wb['Юнит-экономика']['B2'].value,24)
        wb.close()

    def test_xlsx_formats_freeze_filter_and_protection(self):
        import io,zipfile,xml.etree.ElementTree as ET
        sheets=[{'name':'Юнит-экономика','indices':[0,1],'headers':['Код','Сумма'],
                 'rows':[['00042',12.5]],'formulas':{}},
                {'name':'Вводы и ставки','indices':[0],'headers':['Код'],'rows':[['00042']]}]
        blob=E._xlsx_workbook(sheets,[{'width':22,'format':'@'},{'width':15,'format':'#,##0.00'}],True)
        ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            main=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            inputs=ET.fromstring(archive.read('xl/worksheets/sheet2.xml'))
            self.assertEqual(main.find('.//s:pane',ns).get('state'),'frozen')
            self.assertEqual(main.find('s:autoFilter',ns).get('ref'),'A1:B2')
            self.assertIsNotNone(main.find('s:sheetProtection',ns))
            self.assertIsNone(inputs.find('s:sheetProtection',ns))
            self.assertEqual(main.find('s:cols/s:col',ns).get('width'),'22.0')
        try:
            import openpyxl
        except ImportError:
            return
        wb=openpyxl.load_workbook(io.BytesIO(blob))
        main=wb['Юнит-экономика']
        self.assertEqual(main['A2'].value,'00042')
        self.assertEqual(main['A2'].number_format,'@')
        self.assertEqual(main['B2'].number_format,'#,##0.00')
        self.assertTrue(main.protection.sheet)
        self.assertEqual(main.freeze_panes,'A2')
        self.assertFalse(wb['Вводы и ставки'].protection.sheet)
        wb.close()

    def test_conditional_formatting_ranges_and_rules(self):
        import io,zipfile,xml.etree.ElementTree as ET
        sheets=[{'name':'Юнит-экономика','indices':[2,0],'headers':['Прибыль','Маржа'],
                 'rows':[[12,15],[-4,0]]},
                {'name':'Вводы и ставки','indices':[1],'headers':['Цена'],'rows':[[20],[30]]}]
        meta=[{'key':'margin','width':12},{'key':'price','width':14},{'key':'netProfit','width':16}]
        blob=E._xlsx_workbook(sheets,meta)
        ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            main=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            inputs=ET.fromstring(archive.read('xl/worksheets/sheet2.xml'))
            margin=main.find("s:conditionalFormatting[@sqref='B2:B3']/s:cfRule/s:colorScale",ns)
            self.assertEqual([v.get('val') for v in margin.findall('s:cfvo',ns)],['0','15','30'])
            self.assertEqual([v.get('rgb') for v in margin.findall('s:color',ns)],['FFFF6B6B','FFFFD166','FF5FF0A6'])
            profit=main.findall("s:conditionalFormatting[@sqref='A2:A3']/s:cfRule[@type='cellIs']",ns)
            self.assertEqual([r.get('operator') for r in profit],['greaterThan','lessThan'])
            self.assertIsNotNone(inputs.find("s:conditionalFormatting[@sqref='A2:A3']/s:cfRule/s:dataBar",ns))
            styles=ET.fromstring(archive.read('xl/styles.xml'))
            self.assertEqual(len(styles.find('s:dxfs',ns)),2)
        try:
            import openpyxl
        except ImportError:
            return
        wb=openpyxl.load_workbook(io.BytesIO(blob))
        self.assertEqual(len(wb['Юнит-экономика'].conditional_formatting),2)
        self.assertEqual(len(wb['Вводы и ставки'].conditional_formatting),1)
        wb.close()
