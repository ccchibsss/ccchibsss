"""CSV security policy equivalence: fast common case must not weaken guards."""
import pathlib,random,re,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine as E

def original(value):
    s='' if value is None else str(value)
    s=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]',' ',s)
    if (re.match(r'^[\s\u00a0]*[=+@]',s) or re.match(r'^[ \u00a0]*[\t\r\n]',s) or
        (re.match(r'^[\s\u00a0]*-',s) and not re.fullmatch(r'\s*-\d+(?:[.,]\d+)?\s*',s,flags=re.ASCII))):
        s="'"+s
    return s

class CsvFastPath(unittest.TestCase):
    def test_every_bmp_prefix_and_mixed_whitespace(self):
        suffixes=('plain','=CMD()','-12.5','-2+CMD()','\t123','@SUM(1)')
        for cp in range(65536):
            prefix=chr(cp)
            for suffix in suffixes:
                value=prefix+suffix
                if E.safe_csv_text(value)!=original(value):self.fail('CSV mismatch '+repr(value))
        for a in ('',' ','\xa0','\u2028','\u2003','\t','\r','\n','\x1c'):
            for b in ('',' ','\xa0','\t','\u2028'):
                for suffix in suffixes:self.assertEqual(E.safe_csv_text(a+b+suffix),original(a+b+suffix))
    def test_random_full_unicode_and_scalar_values(self):
        rng=random.Random(73)
        for _ in range(10000):
            value=''.join(chr(rng.randrange(0x110000)) for _ in range(rng.randrange(1,20)))
            self.assertEqual(E.safe_csv_text(value),original(value))
        for value in (None,False,True,0,-12,1.5,float('inf'),float('-inf'),float('nan'),[],{},['=CMD()'],
                      '0001','-12,5','-1e3','-１２','\u2028-12','\u2028plain','\xa0=1','\t123','name\x00value'):
            self.assertEqual(E.safe_csv_text(value),original(value))
