"""Synthetic, non-production CSV memory probe. No files/data are retained.
Run: python engine/tests/perf_io_probe.py --rows 40000 [--xlsx]
"""
import argparse,csv,gc,hashlib,io,json,pathlib,sqlite3,sys,time,tracemalloc
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uc_engine as E

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--rows',type=int,default=40000);ap.add_argument('--xlsx',action='store_true');args=ap.parse_args()
    c=sqlite3.connect(':memory:');c.executescript('CREATE TABLE app_catalog_head(id INTEGER PRIMARY KEY,revision TEXT);CREATE TABLE app_catalog_chunks(revision TEXT,part INTEGER,data TEXT);INSERT INTO app_catalog_head VALUES(1,"r");')
    for part,off in enumerate(range(0,args.rows,1000)):
        batch=[dict(article=str(i).zfill(8),name='Наименование '+str(i),oe_numbers='OE1 / OE2',custom={'car':'MITSUBISHI'}) for i in range(off,min(args.rows,off+1000))]
        c.execute('INSERT INTO app_catalog_chunks VALUES(?,?,?)',('r',part,json.dumps({'rows':batch},ensure_ascii=False)))
    c.commit();del batch
    cols=[dict(key=k,name=k) for k in ['article','name','oe_numbers']]+[dict(key='car',name='car',custom=True)]
    def previous_csv():
        rows=[]
        for raw, in c.execute('SELECT data FROM app_catalog_chunks ORDER BY part'):rows.extend(json.loads(raw)['rows'])
        out=io.StringIO(newline='');writer=csv.writer(out,delimiter=';',lineterminator='\r\n',quoting=csv.QUOTE_ALL)
        writer.writerow(['article','name','oe_numbers','car [пользовательская: car]'])
        for p in rows:writer.writerow([E.safe_csv_text(p[k]) for k in ['article','name','oe_numbers']]+[E.safe_csv_text(p['custom']['car'])])
        return ('\ufeff'+out.getvalue()).encode()
    hashes={}
    jobs=[('previous_csv',previous_csv),('streamed_csv',lambda:E.export_data_only_file(c,cols,'csv'))]
    if args.xlsx:jobs.append(('streamed_xlsx',lambda:E.export_data_only_file(c,cols,'xlsx')))
    for label,fn in jobs:
        gc.collect();tracemalloc.start();t=time.perf_counter();result=fn();seconds=time.perf_counter()-t;_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        digest=hashlib.sha256();size=0
        if isinstance(result,bytes):digest.update(result);size=len(result)
        else:
            while True:
                data=result.read(1024*1024)
                if not data:break
                digest.update(data);size+=len(data)
            result.close()
        hashes[label]=digest.hexdigest()
        print(json.dumps(dict(mode=label,rows=args.rows,seconds=round(seconds,3),peak_traced_MiB=round(peak/1024**2,2),bytes=size,sha256=digest.hexdigest())))
    assert hashes['previous_csv']==hashes['streamed_csv'],'CSV values/escaping differ'
    c.close()
if __name__=='__main__':main()
