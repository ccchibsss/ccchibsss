// Optional Linux process + CDP sampler, not application/runtime code.
// RSS sums double-count shared pages; PSS apportions them across processes.
const fs=require('fs');
exports.start=async function(browser,page){
 const start=Date.now(),samples=[];let stopped=false,cdpBusy=false,phase='boot',lastHeap=null,heapSamples=0,osSamples=0;
 const session=await page.context().newCDPSession(page);
 page.on('console',message=>{const text=message.text();if(text.startsWith('[E2E] start '))phase=text.slice(12);});
 function os(){
  const processes=[];
  for(const id of fs.readdirSync('/proc').filter(x=>/^\d+$/.test(x))){try{
   const text=fs.readFileSync('/proc/'+id+'/status','utf8');processes.push({pid:Number(id),ppid:Number(text.match(/^PPid:\s*(\d+)/m)?.[1]),rssKiB:Number(text.match(/^VmRSS:\s*(\d+)/m)?.[1]||0)});
  }catch{}}
  const children=new Set([process.pid]);let changed=true;
  while(changed){changed=false;for(const p of processes)if(children.has(p.ppid)&&!children.has(p.pid)){children.add(p.pid);changed=true;}}
  let rss=0,pss=0,count=0,pssCount=0;
  for(const p of processes)if(p.pid!==process.pid&&children.has(p.pid)){
   rss+=p.rssKiB;count++;
   try{const text=fs.readFileSync('/proc/'+p.pid+'/smaps_rollup','utf8');pss+=Number(text.match(/^Pss:\s*(\d+)/m)?.[1]||0);pssCount++;}catch{}
  }
  osSamples++;return {chromiumRssBytes:rss*1024,chromiumPssBytes:pssCount===count?pss*1024:null,processes:count,nodeRssBytes:process.memoryUsage().rss};
 }
 function sample(){if(stopped)return;const sample={ms:Date.now()-start,phase,...os(),heap:lastHeap};samples.push(sample);
  if(!cdpBusy){cdpBusy=true;session.send('Runtime.getHeapUsage').then(h=>{heapSamples++;lastHeap=h;sample.heap=h;}).catch(()=>{}).finally(()=>{cdpBusy=false;});}
 }
 sample();const timer=setInterval(sample,1000);
 return {async stop(){
  if(stopped)return;
  const settleMs=Number(process.env.E2E_MEMORY_SETTLE_MS||0);if(settleMs>0)await new Promise(resolve=>setTimeout(resolve,settleMs));
  sample();const unforcedLast=samples.at(-1);stopped=true;clearInterval(timer);let forcedGc=null;
  if(process.env.E2E_MEMORY_GC==='1'){const before=await session.send('Runtime.getHeapUsage');await session.send('HeapProfiler.collectGarbage');forcedGc={before,after:await session.send('Runtime.getHeapUsage'),...os()};}
  await session.detach().catch(()=>{});
  const peak=key=>samples.reduce((best,s)=>s[key]!=null&&(!best||s[key]>best[key])?s:best,null);
  const heapPeak=samples.filter(s=>s.heap).reduce((best,s)=>!best||s.heap.usedSize>best.heap.usedSize?s:best,null);
  const summary={intervalMs:1000,elapsedMs:Date.now()-start,osSamples,heapSamples,chromiumRssPeak:peak('chromiumRssBytes'),chromiumPssPeak:peak('chromiumPssBytes'),jsHeapPeak:heapPeak,nodeRssPeakBytes:Math.max(...samples.map(s=>s.nodeRssBytes)),last:unforcedLast,forcedGc};
  if(process.env.E2E_MEMORY_OUTPUT)fs.writeFileSync(process.env.E2E_MEMORY_OUTPUT,JSON.stringify({summary,samples},null,2));
  return summary;
 }};
};
