// Exercise the shipped estimator/generator, including wide enriched records.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const h=fs.readFileSync(__dirname+'/../index.html','utf8'),c={Blob,ArrayBuffer,Map,Set,WeakSet};vm.createContext(c);
const a=h.indexOf('  recordBytes('),b=h.indexOf('  async saveChunked(',a);
vm.runInContext('this.C={'+h.slice(a,b)+'}',c);
const C=c.C,limit=4*1024*1024;
for(const partial of [false,true]){
 const rows=Array.from({length:301},(_,id)=>({id,article:'000'+id,custom:{text:'Ж'.repeat(id%7===0?160000:2000)}}));
 const args={rowCount:partial?10000:rows.length,changedList:partial?rows:null,chunk:2500,withId:r=>r,slimChunk:(a,b)=>rows.slice(a,b)};
 const batches=[...C.productBatches(args)];assert(batches.length>1);
 assert.deepStrictEqual(batches.flat(),rows);
 for(const batch of batches)assert(batch.reduce((n,r)=>n+C.recordBytes(r),0)<=limit);
}
const huge={id:1,text:'x'.repeat(limit)},cycle={id:2};cycle.self=cycle;
const rows=[huge,cycle,{id:3,code:'0000042'}];
const batches=[...C.productBatches({rowCount:3,chunk:2,slimChunk:(a,b)=>rows.slice(a,b)})];
assert.equal(batches[0].length,1);assert.strictEqual(batches[0][0],huge);assert.deepStrictEqual(batches.flat(),rows);
assert(C.recordBytes(new Uint8Array(1024))>=1024);
assert(C.recordBytes(new Map([['a',new Set(['abc'])]]))>64);
console.log('PASS byte-budget product batches: full/partial, exact values/order, oversized row, cycles/binary');
