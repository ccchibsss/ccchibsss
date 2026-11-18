// Target-index parity against the actual legacy lookup and graph traversal.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),fidb=require('fake-indexeddb');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');let seq=0,cancel=false;
const c={...fidb,console,setTimeout,clearTimeout,queueMicrotask,AbortController,structuredClone,performance,CustomEvent:class{constructor(type){this.type=type}},location:{protocol:'http:'},navigator:{},S:{rows:[],settings:{}},uid:p=>p+(++seq),UCCancel:{check(){if(cancel)throw Error('cancelled')}},num:x=>Number(x)||0};c.self=c;c.window=c;vm.createContext(c);
vm.runInContext(h.slice(h.indexOf('const BrowserImportIO = {'),h.indexOf('const BrowserApplyCheckpoint = {')),c);
vm.runInContext([...h.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1],c);
vm.runInContext(h.slice(h.indexOf('const _normArticleCache ='),h.indexOf('/* Артикул — всегда текст.'))+';this.norm=normArticle;',c);
vm.runInContext(h.slice(h.indexOf('const OE_DELIMITERS ='),h.indexOf('function oeDelimiterHint()'))+';this.codes=codeList;this.merge=mergeCodeLists;',c);
const a=h.indexOf('const BrowserCatalogLookup = {'),b=h.indexOf('const Import = {',a);vm.runInContext(h.slice(a,b)+';this.L=BrowserCatalogLookup;this.B=BrowserImportSources;',c);
const norm=c.norm,flags={name:true,applicability:true,category:true,tnved:true,dims:['weight','length']};
c.HVC={normalizeKey:norm,keyOf:p=>norm(p.article)+'|'+norm(p.brand),byArt:new Map(),byOe:new Map(),_enrichFlags:()=>flags};
const rs=h.indexOf('  _relatedRows(imported,'),re=h.indexOf('  async saveProfile()',rs);vm.runInContext('this.legacyRelated={'+h.slice(rs,re)+'};',c);
const os=h.indexOf('      const oeMaps =',h.indexOf('const Import = {')),oe=h.indexOf('      // Detect collisions',os);
vm.runInContext('this.makeOe=(catalogLookup,mapped)=>{'+h.slice(os,oe)+';return async input=>{inputBatch=input;const out=[];for(const row of input)out.push(await findByOe(row));return out;};};',c);
function legacy(rows){const idx=new Map(),idxArt=new Map(),duplicateArt=new Set(),duplicatePair=new Set();for(const p of rows){const a=norm(p.article);if(!a)continue;const k=a+'|'+norm(p.brand);if(!idx.has(k))idx.set(k,p);else duplicatePair.add(k);if(!idxArt.has(a))idxArt.set(a,p);else duplicateArt.add(a);}return {idx,idxArt,duplicateArt,duplicatePair};}
(async()=>{
 const n=Number(process.env.TARGET_ROWS||5003),rows=Array.from({length:n},(_,i)=>({article:'A'+String(i).padStart(8,'0'),brand:i%2?'Brand':'Other',oe_numbers:'OE'+i,oe_list:'OE'+i,name:i%3?'':'name',weight:i%5?0:1}));
 rows.push({...rows[0],article:'a-00000000',name:'normalized duplicate'}, {...rows[1],brand:'Other'}, {article:'',brand:'B',oe_numbers:'OEblank'});
 // Same reference twice is an identity duplicate but NOT an OE ambiguity.
 rows.push(rows[2]);c.S.rows=rows;
 const L=c.L,B=c.B,expected=legacy(rows),lookup=await L.create(rows,'source-A');
 assert(await B.database().keyPages.count()>0);
 const broken=await B.database().keyPages.where('run').equals(lookup.run+':pair').first();
 delete broken.records[0].conflict;await B.database().keyPages.put(broken);B.invalidateKeyIndex(lookup.run+':pair');
 // Rebuild once from the frozen row references; ambiguity remains protected.
 await lookup.query('pair',[broken.first]);assert(lookup._keyRepairUsed);

 for(let off=0;off<rows.length;off+=713){
  const input=rows.slice(off,off+713).map(p=>[p.article,p.brand]);input.push(['MISSING',''],[rows[1].article,''],[rows[2].article,'Wrong']);
  const actual=await lookup.batch(input,r=>norm(r[0]),r=>norm(r[1]));
  for(const r of input){const art=norm(r[0]),pair=art+'|'+norm(r[1]);
   assert.strictEqual(actual.idx.get(pair),expected.idx.get(pair));assert.strictEqual(actual.idxArt.get(art),expected.idxArt.get(art));
   assert.equal(actual.duplicatePair.has(pair),expected.duplicatePair.has(pair));assert.equal(actual.duplicateArt.has(art),expected.duplicateArt.has(art));
  }
  assert(actual.idx.size<=input.length);assert(actual.idxArt.size<=input.length);
 }
 // Strict pair matching does not fetch the article index for branded rows,
 // but brandless rows retain the legacy article fallback and ambiguities.
 const strict=await lookup.batch([[rows[10].article,rows[10].brand],[rows[11].article,'']],r=>norm(r[0]),r=>norm(r[1]),false);
 assert.strictEqual(strict.idx.get(norm(rows[10].article)+'|'+norm(rows[10].brand)),expected.idx.get(norm(rows[10].article)+'|'+norm(rows[10].brand)));
 assert(!strict.idxArt.has(norm(rows[10].article)));assert.strictEqual(strict.idxArt.get(norm(rows[11].article)),expected.idxArt.get(norm(rows[11].article)));
 const protectedRows=[];await lookup.protectDuplicates(protectedRows);
 const uniqueProtected=[...new Set(rows.filter(p=>expected.duplicatePair.has(norm(p.article)+'|'+norm(p.brand))))];assert.deepEqual(protectedRows,uniqueProtected);
 const maps=[{target:'oe_numbers',col:0},{target:'oe_list',col:1}],ramOe=c.makeOe(null,maps),diskOe=c.makeOe(lookup,maps);
 // Preserve lazy snapshot timing: edits before first fallback participate,
 // edits after the first fallback do not change the frozen OE index.
 rows[3].oe_numbers+=' / BEFORE-FIRST';rows[4].oe_numbers+=' / OEshared';rows[5].oe_numbers+=' / OEshared';
 let input=[['BEFORE-FIRST',''],['OEshared','OE6'],['OE0',''],['OE2',''],['NONE','OE7'],['OEblank','']];
 assert.deepEqual(await diskOe(input),await ramOe(input));rows[3].oe_numbers+=' / AFTER-FIRST';
 input=[['AFTER-FIRST','OE8'],['OEshared',''],['OE2','']];assert.deepEqual(await diskOe(input),await ramOe(input));
 // Graph traversal uses the same key fallback, ordering, missing-field rules
 // and first representative even for ambiguous keys (legacy related semantics).
 const imported=rows.slice(7,57);for(const p of imported){const k=c.HVC.keyOf(p),oes=new Set(['LINK'+(norm(p.article).slice(-1))]);c.HVC.byArt.set(k,oes);for(const oe of oes)c.HVC.byOe.set(oe,new Set(rows.slice(0,80).map(p=>c.HVC.keyOf(p))));}
 const related=c.legacyRelated._relatedRows(imported,new Set(imported),expected.idx,expected.idxArt);
 assert.deepEqual(Array.from(await lookup.related(imported,new Set(imported))),Array.from(related));
 // Post-dedup replacement of S.rows must not change frozen index references.
 c.S.rows=rows.slice(20);const got=await lookup.batch([[rows[0].article,rows[0].brand]],r=>norm(r[0]),r=>norm(r[1]));assert.strictEqual(got.idxArt.get(norm(rows[0].article)),rows[0]);
 // Dense range reads must filter non-requested keys, and overflowing sparse
 // ranges must fall back to exact bulkGet without returning arbitrary hits.
 const denseKeys=rows.slice(100,164).map(p=>norm(p.article));
 const queryDense=await lookup.query('article',denseKeys);assert.equal(queryDense.size,64);
 const sparseKeys=rows.filter((_,i)=>i%53===0).slice(0,64).map(p=>norm(p.article));
 const querySparse=await lookup.query('article',sparseKeys);assert.equal(querySparse.size,new Set(sparseKeys).size);for(const key of querySparse.keys())assert(sparseKeys.includes(key));
 const mostlyMissing=Array.from({length:60},(_,i)=>'MISSING'+i).concat(denseKeys.slice(0,4));
 assert.equal((await lookup.query('article',mostlyMissing)).size,4);
 await lookup.dispose();assert.equal(await B.database().catalogKeys.count(),0);assert.equal(await B.database().keyPages.count(),0);assert.equal(await B.database().catalogRuns.count(),0);
 // Reordered catalog positions exercise leaf insertion/splits rather than
 // only the append path; first representatives must follow the new order.
 const shuffled=rows.slice();let seed=77;for(let i=shuffled.length-1;i>0;i--){seed=(Math.imul(seed,1664525)+1013904223)>>>0;const j=seed%(i+1);[shuffled[i],shuffled[j]]=[shuffled[j],shuffled[i]];}
 const reordered=await L.create(shuffled,'reordered'),ref=legacy(shuffled);
 for(let off=0;off<shuffled.length;off+=900){const input=shuffled.slice(off,off+900).map(p=>[p.article,p.brand]),found=await reordered.batch(input,r=>norm(r[0]),r=>norm(r[1]));for(const r of input){const a=norm(r[0]),k=a+'|'+norm(r[1]);assert.strictEqual(found.idx.get(k),ref.idx.get(k));assert.equal(found.duplicatePair.has(k),ref.duplicatePair.has(k));assert.strictEqual(found.idxArt.get(a),ref.idxArt.get(a));assert.equal(found.duplicateArt.has(a),ref.duplicateArt.has(a));}}
 await reordered.dispose();
 // Aborted builds cannot leak a usable partial index; next Apply cleans old
 // same-source runs (e.g. after tab crash), and removing source cleans all runs.
 cancel=true;await assert.rejects(()=>L.create(rows,'cancel-source'),/cancelled/);cancel=false;assert.equal(await B.database().catalogRuns.count(),0);
 const old=await L.create(rows.slice(0,8),'same-source'),newer=await L.create(rows.slice(0,9),'same-source');assert(!await B.database().catalogRuns.get(old.run));await newer.dispose();
 await B.database().sources.add({id:'remove-source',status:'ready',total:0});await L.create(rows.slice(0,5),'remove-source');await B.remove('remove-source');assert.equal(await B.database().catalogKeys.count(),0);assert.equal(await B.database().catalogRuns.count(),0);assert.equal(await B.database().keyPages.count(),0);
 await B.database().delete();
 console.log('OK: disk target indexes vs RAM: exact/article duplicates, bounded batch maps, lazy OE snapshot, ambiguity, graph traversal, frozen row references, abort and stale-run cleanup; catalog rows',rows.length);
})().catch(e=>{console.error(e);process.exitCode=1});
