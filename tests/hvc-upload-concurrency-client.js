const fs=require('fs'),vm=require('vm'),assert=require('assert'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const ctx={console};vm.createContext(ctx);
const a=h.indexOf('  async uploadHvcReference('),b=h.indexOf('  async enrichHvcRows(',a);
vm.runInContext('this.P={'+h.slice(a,b)+'};',ctx);
let active=0,peak=0,fail=false,commits=0,released=0,parts=[];
ctx.P._fetch=async(path,opts)=>{
 const p=JSON.parse(opts.body);
 if(p.action==='begin')return {token:'chunked:test'};
 if(p.action==='commit'){assert.equal(active,0);commits++;return {reference_id:'chunked:test'}}
 if(p.action==='release'){assert.equal(active,0);released++;return {}}
 active++;peak=Math.max(peak,active);
 try{await new Promise(r=>setTimeout(r,p.part%2?2:8));if(fail&&p.part===1)throw Error('failed chunk');parts.push(p.part);return {saved:p.items.length}}
 finally{active--}
};
(async()=>{
 const ref={parts:[],oe:[],byArt:[],byOe:[],unsafeKeys:Array.from({length:30000},(_,i)=>'A'+i),unsafeOe:[],groupSeparator:' / '};
 await ctx.P.uploadHvcReference(ref);
 assert.equal(peak,3);assert.equal(commits,1);assert.deepEqual(parts.sort((a,b)=>a-b),[0,1,2,3]);
 fail=true;commits=0;await assert.rejects(()=>ctx.P.uploadHvcReference(ref),/failed chunk/);
 assert.equal(active,0);assert.equal(commits,0);assert.equal(released,1);
 console.log('OK: three in-flight chunks, distinct part IDs, drain before commit/release');
})().catch(e=>{console.error(e);process.exitCode=1});
