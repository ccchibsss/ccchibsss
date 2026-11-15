import json,pathlib,subprocess,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from uc_engine import match_condition

class MatchConditionRegex(unittest.TestCase):
    def test_browser_regex_matrix(self):
        patterns=[r'^\d+$',r'^\w+$',r'\bфильтр\b',r'\bword\b',r'^.$',r'^..$',r'^x$',r'x.$',
                  r'\s',r'\a',r'\z',r'\q',r'\u0061',r'\x61',r'\cA',r'[^]',r'[]',r'^[a-z]+$',
                  r'^[а-яё]+$',r'^s$',r'^k$',r'^i$',r'^σ$',r'^[µ-ÿ]$',r'(a)\1',r'(?<part>a)\k<part>',
                  r'a(?=b)',r'a(?!b)',r'(?<=a)b',r'(?<!a)b',r'a{2,3}',r'[\d_]+',r'[\w-]+',
                  r'[\s_]',r'[^\w]+',r'(?i)a',r'(?>a)',r'a++',r'a*+',r'a?+',r'a{1,2}+',
                  r'(',r'[',r'*','\\',r'a|b',r'^true$',r'^false$',r'^0$',r'^1,2$',r'object',r'^$',
                  r'^\ud83d\ude00$',r'^[\u0061-\u007a]+$',r'^[\u00b5-\u00ff]$',
                  r'^[\d-a]+$',r'^[a-\d]+$',r'[^-z]',r'[\b]',r'[\8]',r'[\141-\172]',
                  r'(a|(b))\2c',r'^(a)?\1$',r'^\1(a)$',r'^(a\1)$',r'\8',r'\9',
                  r'\11',r'\123',r'\400',r'\08',r'(a)\12',r'(a)\1',r'\k<word>',
                  r'(?<word>a)?\k<word>',r'\k<word>(?<word>a)',r'(?<word>a)\k<wrong>',
                  r'(?<1bad>a)',r'(?<has-dash>a)',r'(?<$ok>a)\k<$ok>']
        values=['123','١٢٣','１２３','word','фильтр','ФИЛЬТР','A','a','aa','ab','b','x','x\n','x\r',
                'x\u2028','x\u2029','\n','\r','\u2028','\u2029','😀','ſ','s','K','k','İ','ı','i','Σ','ς','σ',
                'ac','bc','c','a2','aa2','a\n','a\x02','S',' 0','\x00'+'8','\t',' 0','µ','μ','Μ','ÿ','Ÿ','\ufeff','\x1c',' ', 'q','z','\x01',False,True,0,1,[],[1,2],{},None,'']
        cases=[{'v':v,'pattern':p} for p in patterns for v in values]
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/match-condition-reference.js'
        expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(cases),text=True))
        for case,want in zip(cases,expected):
            with self.subTest(case=case):self.assertEqual(match_condition({'v':case['v']},'v','regex',case['pattern']),want)

    def test_core_character_set_unions(self):
        from js_regex import search
        patterns=[r'[\D_]',r'[\W_]',r'[a-\D]',r'[^\S_]',r'[\s\S]',r'[\D\d]',
                  r'[\u00b5-\u00ff]',r'[\u0061-\u007a]',r'[\d-\w]',r'[\c0-\c9]']
        values=['a','A','1','_','-','µ','μ','Μ','ÿ','Ÿ','\n','\x1c','😀','\x10','\x19']
        cases=[{'v':v,'pattern':p,'direct':True} for p in patterns for v in values]
        path=pathlib.Path(__file__).resolve().parents[2]/'tests/match-condition-reference.js'
        expected=json.loads(subprocess.check_output(['node',str(path)],input=json.dumps(cases),text=True))
        for case,want in zip(cases,expected):
            with self.subTest(case=case):self.assertEqual(search(case['pattern'],case['v']),want)

    def test_regex_enrichment_and_policy_persistence(self):
        import sqlite3
        from uc_engine import enrich_rule_rows,apply_product_policies
        rows=[dict(article='A',brand='B',name='１２３'),dict(article='B',brand='B',name='123')]
        rule=dict(enabled=True,kind='enrich',field='name',op='regex',value=r'^\d+$',target_val='price',formula='42')
        conn=sqlite3.connect(':memory:')
        try:
            response=enrich_rule_rows(conn,rows,[rule],{})['rows']
            self.assertNotIn('price',response[0]['fields'])
            self.assertEqual(response[1]['fields']['price'],42)
            policies=apply_product_policies(conn,rows,[dict(rule,action='exclude')])['rows']
            self.assertFalse(policies[0]['fields'].get('excluded',False))
            self.assertTrue(policies[1]['fields']['excluded'])
        finally:conn.close()
