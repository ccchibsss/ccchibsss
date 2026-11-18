"""Optional isolated-process benchmark; baseline source is supplied explicitly.
python engine/tests/benchmark_streaming_export.py --baseline .arena/engine-before-stream.py --out .arena/python-stream-results.json
"""
import argparse,ast,gc,hashlib,io,json,pathlib,resource,sqlite3,subprocess,sys,tempfile,time,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'engine'))
import uc_engine as E

def checksum(output,fmt):
    h=hashlib.sha256();output.seek(0)
    if fmt=='csv':
        for block in iter(lambda:output.read(65536),b''):h.update(block)
    else:
        with zipfile.ZipFile(output) as z:
            for name in sorted(z.namelist()):
                h.update(name.encode())
                with z.open(name) as entry:
                    for block in iter(lambda:entry.read(65536),b''):h.update(block)
    return h.hexdigest()

def sample(args):
    conn=sqlite3.connect(args.database);conn.row_factory=sqlite3.Row
    # Compile the baseline in BOTH processes to equalize setup/AST overhead.
    names={'_xlsx_from_rows','_ozon_rows_data','export_ozon_xlsx_bytes','export_ozon_csv_bytes','export_ozon_csv_file','_iter_ozon_rows_meta','safe_csv_text'}
    scope=dict(E.__dict__)
    tree=ast.parse(pathlib.Path(args.baseline).read_text())
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'<baseline>','exec'),scope)
    del tree
    fn=scope['export_ozon_'+args.format+'_'+args.baseline_api] if args.version=='before' else getattr(E,'export_ozon_'+args.format+'_file')
    E._pairs_map(conn);E.ozon_template_rows();gc.collect()
    rss_start=int(next(line.split()[1] for line in pathlib.Path('/proc/self/status').read_text().splitlines() if line.startswith('VmRSS:')))*1024
    start=time.perf_counter();result=fn(conn);elapsed=time.perf_counter()-start
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    output=io.BytesIO(result) if isinstance(result,bytes) else result
    try:
        size=output.seek(0,2);digest=checksum(output,args.format)
    finally:output.close();conn.close()
    print(json.dumps(dict(version=args.version,format=args.format,seconds=elapsed,rss_start=rss_start,peak_rss=peak,size=size,content_sha256=digest)))

def main(args):
    with tempfile.TemporaryDirectory() as tmp:
        E.DATA=pathlib.Path(tmp);E.DB_PATH=E.DATA/'benchmark.db';conn=E.db()
        def rows():
            import random
            rng=random.Random(73)
            for i in range(args.rows):
                text=' '.join(format(rng.getrandbits(64),'016x') for _ in range(32))
                yield (str(i).zfill(8),'BRAND','Товар '+str(i),text,25,1,2,3,4)
        conn.executemany('INSERT INTO products(article,brand,name,description,price,weight,length,width,height) VALUES(?,?,?,?,?,?,?,?,?)',rows());conn.commit();conn.close()
        samples=[]
        for repeat in range(args.repeats):
            for fmt in args.formats.split(','):
                for version in (('before','after') if repeat%2==0 else ('after','before')):
                    raw=subprocess.check_output([sys.executable,__file__,'--baseline',args.baseline,'--version',version,'--format',fmt,'--database',str(E.DB_PATH),'--baseline-api',args.baseline_api],text=True)
                    item=json.loads(raw);item['repeat']=repeat+1;samples.append(item);print(json.dumps(item),flush=True)
        for fmt in args.formats.split(','):
            assert len({r['content_sha256'] for r in samples if r['format']==fmt})==1,'content parity failed'
        if args.out:pathlib.Path(args.out).write_text(json.dumps(dict(rows=args.rows,description_random_words=32,baseline_api=args.baseline_api,samples=samples),indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',required=True);parser.add_argument('--rows',type=int,default=20000);parser.add_argument('--out');parser.add_argument('--database');parser.add_argument('--version');parser.add_argument('--format');parser.add_argument('--formats',default='xlsx,csv');parser.add_argument('--repeats',type=int,default=2);parser.add_argument('--baseline-api',choices=('bytes','file'),default='bytes')
    args=parser.parse_args();sample(args) if args.version else main(args)
