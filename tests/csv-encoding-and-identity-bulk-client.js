// Regression: CSV encoding must be decided on the whole probe buffer, and the
// import must not rebuild the catalogue-wide identity index per batch.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');
const c={console,TextDecoder};
vm.createContext(c);
const da=h.indexOf('function decodeCsvText(bytes, opts) {'),db_=h.indexOf('const normArticle = s => {',da);
assert(da>0&&db_>da,'decodeCsvText must exist');
vm.runInContext('this.decodeCsvText='+h.slice(da,db_).trim()+';',c);
const decode=c.decodeCsvText;

// CP1251 encoder that actually produces CP1251 bytes (not latin1 mangling).
function cp1251(str){
  const out=[];
  for(const ch of str){
    const p=ch.codePointAt(0);
    if(p<128)out.push(p);
    else if(ch==='Ё')out.push(0xA8);
    else if(ch==='ё')out.push(0xB8);
    else if(p>=0x410&&p<=0x44F)out.push(p-0x410+0xC0);
    else out.push(0x3F);
  }
  return Uint8Array.from(out);
}
function concat(parts){
  const n=parts.reduce((s,p)=>s+p.length,0),out=new Uint8Array(n);
  let o=0;for(const p of parts){out.set(p,o);o+=p.length;}
  return out;
}
// ASCII-only header long enough that Cyrillic starts past the old 400-char probe.
let buf=cp1251('article;brand;code1;code2;code3;code4;code5;code6;code7\n');
for(let i=0;i<8;i++)buf=concat([buf,cp1251('A'+String(i).padStart(6,'0')+';BOSCH;'+'123456789012;'.repeat(6)+'\n')]);
const firstNonAscii=buf.length;
buf=concat([buf,cp1251('Z1;BOSCH;Фильтр масляный;777\n')]);
assert(firstNonAscii>400*1,'fixture must place Cyrillic beyond the old 400-char probe');

const probe=decode(buf,{truncated:false});
assert.equal(probe.encoding,'windows-1251','whole-buffer probe must detect CP1251');
assert(!/\uFFFD/.test(probe.text),'no replacement characters after detection');
assert(probe.text.includes('Фильтр масляный'),'Cyrillic text preserved');
assert(probe.text.includes('Z1;BOSCH;Фильтр масляный;777'),'row intact');

// Valid UTF-8 must never be re-read as CP1251.
const utf8=new TextEncoder().encode('артикул;бренд\nA1;Bosch\n');
assert.equal(decode(utf8,{truncated:false}).encoding,'utf-8');
// A probe cut mid-character must not be mistaken for CP1251.
const long=new TextEncoder().encode('name\n'+'Ж'.repeat(5000)+'\n');
const cut=long.subarray(0,1002); // 5-byte header + odd offset: lands inside a two-byte character
const partial=decode(cut,{truncated:true});
assert.equal(partial.encoding,'utf-8','truncated utf-8 probe is not a cp1251 signal');
// Even without the flag, a single replacement char at the very end is a cut
// character, not evidence of CP1251.
assert.equal(decode(cut,{truncated:false}).encoding,'utf-8','trailing cut is not a cp1251 signal');
// Non-streaming decode turns the cut tail into ONE replacement char at the end;
// that is a truncated symbol, not evidence of CP1251.
const cutPlain=decode(cut,{truncated:false});
assert.equal(cutPlain.text.indexOf('\uFFFD'),cutPlain.text.length-1,'only the last character is replaced');
// A UTF-8 BOM is consumed by the decoder and must not break detection.
const withBom=decode(concat([Uint8Array.from([0xEF,0xBB,0xBF]),utf8]),{truncated:false});
assert.equal(withBom.encoding,'utf-8');
assert(!withBom.text.includes('\uFEFF')&&!withBom.text.includes('\uFFFD'));
assert(withBom.text.startsWith('артикул'));

// --- identity index: one rebuild per import, not per batch ---
const hvc=h.match(/const HVC = \{[\s\S]*?\n\};\n/)[0];
const ctx={
  console,performance,S:{rows:[],settings:{enrichMode:'auto',enrichCatMode:'artbrand',enrichCols:{}},catalogVersion:1},
  normArticle:s=>String(s==null?'':s).toUpperCase().replace(/[^A-Z0-9А-ЯЁ]/g,''),
  num:v=>Number(v)||0, round:(v,n=2)=>Number(Number(v).toFixed(n)), nowISO:()=>'2026-01-01T00:00:00Z',
  codeList:v=>String(v||'').split(/[\/;,|]+/).map(s=>s.trim()).filter(Boolean),
  OE_DELIMITERS:{auto:{join:' / '}}, oeMode:()=>'auto',
  CONST:{OE_SET_CACHE_MAX:1000,OE_AGG_CACHE_MAX:1000}, productVolumeIsExplicit:p=>!!p._volumeExplicit, policy:{},
  codeFieldsToStr:p=>p, AnomalyDetector:{limits:[],loadLocal(){},quarantineRow(){}}, AnomalyOE:{autoEvidence(){return null},codes(){return []},finishImportTuple(){}},
  OzonCat:{norm:v=>String(v||'').trim().toLowerCase()},
  mergeCodeLists:(...vs)=>vs.filter(Boolean).join(' / '), STD:[{k:'weight',n:'Вес'},{k:'length',n:'Длина'},{k:'width',n:'Ширина'},{k:'height',n:'Высота'}]
};
vm.createContext(ctx);
vm.runInContext(hvc+'\nthis.H=HVC;',ctx);
const H=ctx.H;
H.parts=new Map();H.oe=new Map();H.byArt=new Map();H.byOe=new Map();H.cross=new Map();H.prices=new Map();H.bySku=new Map();
H.ozonApplicability=new Map();

// Reference: the pre-12.9.170 implementation (two maps on the same key, JSON
// literal) kept here so the rewrite is proven equivalent, not just plausible.
function legacyIndex(partsRegistry, norm, lists) {
  const seen=new Map(), normalized=new Map(), unsafe=new Set();
  for(const rows of lists) for(const q of rows){
    if(!q || typeof q!=='object')continue;
    if(!q.article && !q.brand)continue;
    const key=norm(q.article)+'|'+norm(q.brand);if(!key||key==='|')continue;
    const literal=JSON.stringify([norm(q.article),norm(q.brand)]), prior=seen.get(key), part=partsRegistry.get(key);
    if(prior===undefined)seen.set(key,literal);else if(prior!==literal)unsafe.add(key);
    if(part && ((part.artikul && norm(part.artikul)!==norm(q.article)) || (part.brand && norm(part.brand)!==norm(q.brand))))unsafe.add(key);
    const a=norm(q.article),b=norm(q.brand), nk=a&&b?a+'|'+b:'';
    if(nk){const old=normalized.get(nk);if(!old)normalized.set(nk,{literal,key});else if(old.literal!==literal){unsafe.add(old.key);unsafe.add(key);}}
  }
  return unsafe;
}
const norm=s=>String(s==null?'':s).toUpperCase().replace(/[^A-Z0-9А-ЯЁ]/g,'');
let seed=12345;const rnd=()=>((seed=(seed*1103515245+12345)&0x7fffffff)/0x7fffffff);
const words=['Bosch','BOSCH','b o s c h','A-B','A B','абв','АБВ','W71275','w 712/75','','  '];
const arts=['A1','a1','A 1','A-1','B2','B 2','Z9'];
const sample=Array.from({length:1500},()=>({article:arts[Math.floor(rnd()*arts.length)],brand:words[Math.floor(rnd()*words.length)],name:''}));
/* Registry spells the brand differently from the rows ("Bosch" vs "BOSCH"):
   keyOf normalizes it, so the key agrees while the literal does not — that is
   exactly the ambiguity the index must quarantine. */
for(const r of sample) H.parts.set(norm(r.article)+'|'+norm(r.brand),{artikul:r.article,brand:'Bosch'});
const expected=legacyIndex(H.parts,norm,[sample]);
const actual=H._buildIdentityIndex([sample]).unsafe;
assert.deepEqual([...actual].sort(),[...expected].sort(),'identity verdicts must match the legacy implementation');
assert(actual.size>0,'fixture must produce at least one unsafe key');

// Import batching: no catalogue-wide walk per batch, one rebuild afterwards.
const rows=Array.from({length:3000},(_,i)=>({article:'Q'+i,brand:'B',name:'',oe_numbers:'OE'+i}));
const target=rows[0];               // its key is 'Q0|B'
rows.push({article:"Q_0",brand:'B',name:''}); // same key only after normalization
ctx.S.rows=rows;
let catalogueBuilds=0,batchBuilds=0;const build=H._buildIdentityIndex;
H._buildIdentityIndex=function(lists){
  if(lists.some(l=>l===ctx.S.rows))catalogueBuilds++;else batchBuilds++;
  return build.call(this,lists);
};
H.identityCache();
const warm=catalogueBuilds;
H.identityBulkBegin();
for(let b=0;b<30;b++)H.ingest(rows.slice(b*100,b*100+100));
assert.equal(catalogueBuilds,warm,'ingest must not rebuild the catalogue identity index per batch (was: one full walk per batch)');
assert.equal(batchBuilds,30,'each batch is still indexed on its own');
H.identityBulkEnd();
H.identityCache();
assert.equal(catalogueBuilds-warm,1,'exactly one post-import rebuild');
H._buildIdentityIndex=build;
// A legacy/hand-edited registry entry whose brand literal disagrees with the
// row under the same key must still be quarantined (this branch fires on real
// data only for registries written before brands were normalized).
H.parts.set('Q0|B',{artikul:'Q0',brand:'B-X'});
assert.equal(H.identityUnsafe(target),true,'registry brand mismatch still quarantined');
H.parts.set('Q0|B',{artikul:'Q0',brand:'B'});
// The mismatch was already merged into the cached index for this version, and
// that is the intended behaviour: quarantine is sticky until the registry is
// actually fixed.
assert.equal(H.identityUnsafe(target),true,'quarantine stays until the registry is rebuilt');
H._identityCache=null;ctx.S.catalogVersion+=1;
assert.equal(H.identityUnsafe(target),false,'matching registry entry stays clean after rebuild');

// --- search string lives outside the record ---
const srchStart=h.indexOf('let _srchVer = -1;'),srchEnd=h.indexOf('/* v10.7.2: флаги качества данных',srchStart);
vm.runInContext(h.slice(srchStart,srchEnd)+';this.ensureSrch=ensureSrch;this.srchOf=srchOf;',ctx);
ctx.S.rows=[{article:'W71275',brand:'BOSCH',name:'Фильтр масляный'}];
ctx.S.catalogVersion=7;
ctx.ensureSrch();
assert.equal(ctx.srchOf(ctx.S.rows[0]).includes('ФИЛЬТР'),true,'search text is built');
assert.equal(ctx.S.rows[0]._srch,ctx.srchOf(ctx.S.rows[0]),'search text is cached on the row');
const slimOf=h.slice(h.indexOf('    const slimOf = src => {'),h.indexOf('    /* v12.9.7-mem',h.indexOf('    const slimOf = src => {')));
vm.runInContext('this.slimOf='+slimOf.match(/const slimOf = (src => \{[\s\S]*?\n    \});/)[1]+';',ctx);
const stored=ctx.slimOf({article:'A1',brand:'B',_srch:'X',_sv:7,salesSeries:[],name:'n'});
assert(!('_srch' in stored)&&!('_sv' in stored),'derived search fields are not persisted');
assert(!('_srch' in ctx.S.rows[0])===false,'the cached text stays in RAM only');
assert(!('salesSeries' in stored),'empty sales series is not persisted');
/* oe_list — дубль oe_numbers, читатели берут mergeCodeLists; oe_norm — производное. */
const dupOe=ctx.slimOf({article:'A2',brand:'B',oe_numbers:'W712/75',oe_list:'W712/75',oe_norm:'W712/75'});
assert(!('oe_list' in dupOe)&&!('oe_norm' in dupOe),'duplicated OE fields are not persisted');
const diffOe=ctx.slimOf({article:'A3',brand:'B',oe_numbers:'W712/75',oe_list:'W712/75 / 0451103316',oe_norm:'W71275'});
assert(diffOe.oe_list==='W712/75 / 0451103316'&&diffOe.oe_norm==='W71275','distinct OE lists are persisted as is');
const onlyOe=ctx.slimOf({article:'A4',brand:'B',oe_list:'W712/75'});
assert(onlyOe.oe_list==='W712/75','a lone oe_list is not dropped');

/* --- HVC.cross: значение не дублирует ключ, но разбор ключа обратим --- */
const ck=H.crossKey('OE1','ART1|BOSCH'), parts=H.crossParts(ck);
assert.equal(parts.oeNorm,'OE1');assert.equal(parts.artKey,'ART1|BOSCH');
/* Связка с '|' и \u001F внутри artKey не должна разъезжаться: разделитель один. */
assert.deepEqual(H.crossParts(H.crossKey('OE|2','A\u001FB|B')),{oeNorm:'OE|2',artKey:'A\u001FB|B'});
H.cross.set(ck,1);
assert.equal(H.cross.get(ck),1,'the link value is a constant, not a copy of the key');
H.cross.delete(H.crossKey('OE1','ART1|BOSCH'));
assert(!H.cross.has(ck),'deleting by OE+article removes the link (the "|" key never matched)');
console.log('OK: CSV encoding decided on the full probe, identity index rebuilt once per import, derived fields kept off the record');
