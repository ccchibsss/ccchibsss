const fs=require('fs'),http=require('http'),assert=require('assert');
const {chromium:pw}=require('playwright-core'),ch=require('@sparticuz/chromium');
(async()=>{
 const server=http.createServer((q,r)=>{r.setHeader('Content-Type','text/html; charset=utf-8');r.end(fs.readFileSync(__dirname+'/../index.html'))});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await pw.launch({executablePath:await ch.executablePath(),args:ch.args,headless:true});const page=await browser.newPage();
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto('http://127.0.0.1:'+server.address().port);await page.waitForFunction(()=>S._bootReady||S._bootError);
  const result=await page.evaluate(async()=>{
   if(S._bootError||PyEngine.processingMode()!=='browser')throw Error('browser boot failed');
   const NativeWorker=window.Worker,instances=[];let terminated=0;
   window.Worker=class extends NativeWorker{constructor(...args){super(...args);instances.push(this)}terminate(){terminated++;super.terminate()}};
   const realCheck=MemGuard.check;MemGuard.check=()=>0;
   try{
    const rows=Array.from({length:30001},(_,i)=>({article:String(i).padStart(8,'0'),brand:'B',name:'Wide '.repeat(60),visible:true,price:i,excluded:false}));
    S.rows=rows;S.sort={k:'article',dir:1};
    for(let i=0;i<3;i++){
     if(!FWorker.setRowsIfNeeded(rows,i+1))throw Error('worker upload refused');
     const indices=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('worker result timeout')),20000);FWorker.filter({showExcluded:true},{k:'article',dir:1,numeric:false},i+1,idx=>{clearTimeout(timer);resolve(Array.from(idx))});});
     if(indices.length!==rows.length||indices[0]!==0||indices.at(-1)!==30000)throw Error('worker filter parity failed');
     FWorker.release();
    }
    FWorker.setRowsIfNeeded(rows,10);MemGuard.check=()=>2;
    if(FWorker.setRowsIfNeeded(rows,11)!==false)throw Error('pressure not rejected');
    if(terminated!==4||instances.length!==4)throw Error('worker/catalog retained after release');
    return{rows:rows.length,cycles:3,workersCreated:instances.length,workersTerminated:terminated,pressureRelease:true};
   }finally{FWorker.release();MemGuard.check=realCheck;window.Worker=NativeWorker;}
  });assert.equal(result.workersCreated,result.workersTerminated);console.log(JSON.stringify(result));
 }finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1});
