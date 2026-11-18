// Optional before/after benchmark. Each sample gets a fresh Chromium process.
// RSS sampled from /proc (browser + its subprocesses); JS heap sampled at yields.
// Correctness/parity belongs to browser-io-memory-e2e.js, not timing assertions.
const fs=require('fs'),http=require('http'),path=require('path');
const {chromium:pw}=require('playwright-core'),ch=require('@sparticuz/chromium');
const before=process.env.BENCH_BEFORE;if(!before)throw Error('Set BENCH_BEFORE to baseline HTML');
const htmls={before:fs.readFileSync(before),after:fs.readFileSync(path.join(__dirname,'../index.html'))};
const samples=[],n=Number(process.env.BENCH_ROWS||20000),width=Number(process.env.BENCH_COLUMNS||32),repeats=Number(process.env.BENCH_REPEATS||2);
function children(pid){try{return fs.readFileSync(`/proc/${pid}/task/${pid}/children`,'utf8').trim().split(/\s+/).filter(Boolean).map(Number)}catch(e){return []}}
function rss(){let bytes=0,count=0;const visit=pid=>{try{const status=fs.readFileSync(`/proc/${pid}/status`,'utf8');const m=status.match(/^VmRSS:\s+(\d+)/m);if(m){bytes+=Number(m[1])*1024;count++}for(const c of children(pid))visit(c)}catch(e){}};for(const pid of children(process.pid))visit(pid);return{bytes,count}}
(async()=>{
 let build='before';const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html;charset=utf-8');res.end(htmls[build])});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{
  for(let repeat=0;repeat<repeats;repeat++)for(const scenario of (process.env.BENCH_SCENARIOS||'xlsx,csv,data-xlsx').split(','))for(const version of (repeat%2?['after','before']:['before','after'])){
   build=version;let browser;
   try{
    browser=await pw.launch({executablePath:await ch.executablePath(),args:[...ch.args,'--enable-precise-memory-info'],headless:true});const page=await browser.newPage();
    await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
    await page.goto('http://127.0.0.1:'+server.address().port+'/#export');await page.waitForFunction(()=>S._bootReady||S._bootError);
    await page.evaluate(({n,width,scenario})=>{
     if(S._bootError)throw Error('boot failed');
     let seed=73;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed.toString(36)};
     S.rows=Array.from({length:n},(_,i)=>{const custom={};for(let j=0;j<width;j++)custom['f'+j]='Текст '+j+' '+i+' '+random()+random()+random();return {id:i+1,article:String(i).padStart(8,'0'),brand:'BRAND',name:'Товар '+i,cost:12.5,price:25,weight:1,length:2,width:3,height:4,custom}});
     S.view=S.rows;S.custom=Array.from({length:width},(_,i)=>({key:'f'+i,name:'Поле '+i,type:'text'}));S.settings.exportExclusions=false;S._econPending=true;
     window._benchCat=[{k:'article',n:'Артикул',txt:true},{k:'price',n:'Цена',f:'0.00'},{k:'cost',n:'Закупка',f:'0.00'},...S.custom.map(c=>({k:'c_'+c.key,custom:c.key,n:c.name,txt:true})),{k:'weight',n:'Вес',f:'0.00'}];
     document.querySelector('#expEnc').value='utf8';document.querySelector('#expDelim').value=';';document.querySelector('#dataExportFormat').value='xlsx';
     Exp.download=b=>{window._benchOutput=b};
     if(scenario==='disk-xlsx'){
      const headers=['Артикул','Бренд',...S.custom.map(c=>c.name)];
      const source=[headers,...S.rows.map(p=>[p.article,p.brand,...S.custom.map(c=>p.custom[c.key])])];
      const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet(source),'Price');
      window._benchInput=new File([XLSX.write(wb,{type:'array',bookType:'xlsx',compression:true})],'price.xlsx');
     }
     const yieldBefore=Exp._yield;window._benchPeakHeap=0;Exp._yield=async()=>{window._benchPeakHeap=Math.max(window._benchPeakHeap,performance.memory.usedJSHeapSize);await yieldBefore()};
    },{n,width,scenario});
    const cdp=await page.context().newCDPSession(page);await cdp.send('HeapProfiler.collectGarbage');const heapStart=(await cdp.send('Runtime.getHeapUsage')).usedSize;
    const rssStart=rss();let peakRss=rssStart.bytes,maxProcesses=rssStart.count;
    const timer=setInterval(()=>{const r=rss();peakRss=Math.max(peakRss,r.bytes);maxProcesses=Math.max(maxProcesses,r.count)},25);
    let operation;try{operation=await page.evaluate(async scenario=>{
     const start=performance.now();let blob;
     if(scenario==='xlsx')blob=await Exp.streamXlsx(window._benchCat,S.rows,null);
     else if(scenario==='csv')blob=await Exp.csvAsync(window._benchCat,S.rows,null);
     else if(scenario==='disk-xlsx'){
      DiskImport._abort=false;const session=await DiskImport._xlsxBegin(window._benchInput);let count=0;
      const total=await session.drain(()=>count++);if(count!==S.rows.length||total!==count)throw Error('disk row count');
      if(DiskImport._sessions.size)throw Error('worker not released');blob=new Blob(['reader benchmark only']);
     }else{await DataOnlyExport.run();blob=window._benchOutput;}
     if(!blob)throw Error('no export produced');window._benchOutput=blob;
     return{ms:performance.now()-start,bytes:blob.size,disk:blob instanceof File,peakHeapAtYields:Math.max(window._benchPeakHeap,performance.memory.usedJSHeapSize)};
    },scenario);}finally{const r=rss();peakRss=Math.max(peakRss,r.bytes);clearInterval(timer)}
    await cdp.send('HeapProfiler.collectGarbage');const heapWithOutput=(await cdp.send('Runtime.getHeapUsage')).usedSize,rssWithOutput=rss().bytes;
    await page.evaluate(()=>{window._benchOutput=null});await cdp.send('HeapProfiler.collectGarbage');const heapAfterRelease=(await cdp.send('Runtime.getHeapUsage')).usedSize,rssAfterRelease=rss().bytes;
    const sample={version,repeat:repeat+1,scenario,rows:n,customColumns:width,...operation,heapStart,heapWithOutput,heapAfterRelease,rssStart:rssStart.bytes,peakRss,rssWithOutput,rssAfterRelease,maxProcesses,rssGrowth:peakRss-rssStart.bytes};samples.push(sample);console.log(JSON.stringify(sample));
   }finally{if(browser)await browser.close()}
  }
 }finally{await new Promise(r=>server.close(r));if(process.env.BENCH_OUT)fs.writeFileSync(process.env.BENCH_OUT,JSON.stringify({samples,n,width,repeats,intervalMs:25},null,2)+'\n')}
})().catch(e=>{console.error(e);process.exitCode=1});
