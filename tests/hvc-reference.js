// Execute the actual browser HVC for server parity fixtures. No copied selection logic.
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(__dirname + '/../index.html', 'utf8');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const hvc = html.match(/const HVC = \{[\s\S]*?\n\};\n/)[0];
const dim = html.slice(html.indexOf('const DimPolicy = {'), html.indexOf('\n};', html.indexOf('const DimPolicy = {')) + 3);
const anomaly = html.match(/const AnomalyDetector = \{[\s\S]*?\n\};\n/)[0];
const canonical = html.match(/function validCanonicalOvhNumber\(v\) \{[\s\S]*?\n\}/)[0];
const normalize = s => String(s || '').toUpperCase().replace(/[^A-Z0-9А-ЯЁ]/g, '');
const context = {
  console, performance, S:{settings:{enrichMode:input.mode,enrichCatMode:input.cat_mode,enrichCols:input.columns || {}},rows:input.rows},
  normArticle:normalize, num:v=>Number(v)||0, round:(v,n=2)=>Number(Number(v).toFixed(n)),
  nowISO:()=> '2026-01-01T00:00:00Z', codeList:v=>String(v||'').split(/[\/;,|]+/).map(s=>s.trim()).filter(Boolean),
  OE_DELIMITERS:{auto:{join:input.reference.groupSeparator || ' / '}}, oeMode:()=> 'auto',
  CONST:{OE_SET_CACHE_MAX:1000,OE_AGG_CACHE_MAX:1000}, productVolumeIsExplicit:p=>!!p._volumeExplicit,
  policy:input.policy || {}
};
vm.createContext(context);
vm.runInContext(canonical+'\n'+anomaly+'\n'+dim+'\n'+hvc+'\nAnomalyDetector.limits=policy.limits || []; this.H=HVC;', context);
const H=context.H, r=input.reference;
H.parts=new Map(r.parts); H.oe=new Map(r.oe);
H.byArt=new Map(r.byArt.map(([k,v])=>[k,new Set(v)]));
H.byOe=new Map(r.byOe.map(([k,v])=>[k,new Set(v)]));
// Identity verdicts are explicit snapshot inputs, shared with the server.
H.identityUnsafeKey=k=>(r.unsafeKeys||[]).includes(k);
H.identityUnsafe=p=>H.identityUnsafeKey(H.keyOf(p));
H.identityUnsafeOe=k=>(r.unsafeOe||[]).includes(k);
for(const row of input.rows) H.enrichOne(row,{});
process.stdout.write(JSON.stringify(input.rows));
