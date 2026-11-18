// Замер упаковки XLSX: встроенный fflate против нативного CompressionStream.
// Не входит в CI (время), запуск вручную: node tests/export-zip-benchmark.js
// Проверяет и корректность: архив, собранный нативно, читается fflate байт-в-байт.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const {CompressionStream}=require('stream/web');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');
const a=h.indexOf('/*! fflate встроен офлайн'),b=h.indexOf('</script>',a);
const ctx={console};ctx.self=ctx;ctx.window=ctx;vm.createContext(ctx);
vm.runInContext(h.slice(a,b),ctx);
const fflate=ctx.fflate;

const ROWS=Number(process.env.BENCH_ROWS||8000),COLS=45;
const COL=i=>{let s='';i++;while(i>0){const m=(i-1)%26;s=String.fromCharCode(65+m)+s;i=Math.floor((i-1)/26);}return s;};
const parts=[];
for(let j=0;j<ROWS;j++){
  const row=[`<row r="${j+2}">`];
  for(let c=0;c<COLS;c++)row.push(`<c r="${COL(c)}${j+2}" s="0" t="inlineStr"><is><t xml:space="preserve">Амортизатор передний ${c} ${j} KYB</t></is></c>`);
  row.push('</row>');parts.push(row.join(''));
}
const xml=parts.join(''),u8=new TextEncoder().encode(xml);
const scale=120000/ROWS;

let crcTable=null;
const crc32=buf=>{
  if(!crcTable){crcTable=new Int32Array(256);for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;crcTable[n]=c;}}
  let c=-1;for(let i=0;i<buf.length;i++)c=crcTable[(c^buf[i])&0xFF]^(c>>>8);return (c^-1)>>>0;
};
async function deflateRaw(bytes){
  const cs=new CompressionStream('deflate-raw');
  const w=cs.writable.getWriter();w.write(bytes);w.close();
  const out=[],r=cs.readable.getReader();
  for(;;){const {done,value}=await r.read();if(done)break;out.push(value);}
  return out;
}
/* ZIP с data descriptor (флаг bit 3): CRC и размеры пишутся после данных,
   поэтому сжатие можно вести потоком, не зная длину заранее. */
async function zipNative(name,bytes){
  const parts=[],central=[];let offset=0;
  const push=b=>{parts.push(Buffer.from(b));offset+=b.length;};
  const nb=new TextEncoder().encode(name),localOffset=offset;
  const head=new Uint8Array(30+nb.length),dv=new DataView(head.buffer);
  dv.setUint32(0,0x04034b50,true);dv.setUint16(4,20,true);dv.setUint16(6,0x0808,true);dv.setUint16(8,8,true);
  dv.setUint16(26,nb.length,true);head.set(nb,30);push(head);
  const chunks=await deflateRaw(bytes);let comp=0;
  for(const c of chunks){push(c);comp+=c.length;}
  const desc=new Uint8Array(16),dd=new DataView(desc.buffer);
  dd.setUint32(0,0x08074b50,true);dd.setUint32(4,crc32(bytes),true);dd.setUint32(8,comp,true);dd.setUint32(12,bytes.length,true);push(desc);
  central.push({name:nb,crc:crc32(bytes),comp,size:bytes.length,offset:localOffset});
  const cdStart=offset;
  for(const c of central){
    const z=new Uint8Array(46+c.name.length),dz=new DataView(z.buffer);
    dz.setUint32(0,0x02014b50,true);dz.setUint16(4,20,true);dz.setUint16(6,20,true);dz.setUint16(8,0x0808,true);dz.setUint16(10,8,true);
    dz.setUint32(16,c.crc,true);dz.setUint32(20,c.comp,true);dz.setUint32(24,c.size,true);
    dz.setUint16(28,c.name.length,true);dz.setUint32(42,c.offset,true);z.set(c.name,46);push(z);
  }
  const end=new Uint8Array(22),de=new DataView(end.buffer);
  de.setUint32(0,0x06054b50,true);de.setUint16(8,central.length,true);de.setUint16(10,central.length,true);
  de.setUint32(12,offset-cdStart,true);de.setUint32(16,cdStart,true);push(end);
  return Buffer.concat(parts);
}

(async()=>{
  console.log('вход: '+ROWS+' строк × '+COLS+' колонок · '+(u8.length/1048576).toFixed(1)+' МБ XML · масштаб к 120 000 строк ×'+Math.round(scale));
  let t=Date.now(),total=0,afterZip=0;
  const zip=new fflate.Zip((e,d)=>{if(e)throw e;total+=d.length;});
  const file=new fflate.ZipDeflate('xl/worksheets/sheet1.xml',{level:6});zip.add(file);
  for(let off=0;off<u8.length;off+=262144)file.push(u8.subarray(off,Math.min(off+262144,u8.length)),false);
  file.push(new Uint8Array(0),true);zip.end();afterZip=Date.now()-t;
  console.log('fflate ZipDeflate level 6 : '+afterZip+' мс · '+(total/1048576).toFixed(2)+' МБ (≈'+Math.round(afterZip*scale/1000)+' с на 120k)');

  t=Date.now();
  const nativeZip=await zipNative('xl/worksheets/sheet1.xml',u8);
  const afterNative=Date.now()-t;
  console.log('нативный deflate-raw+ZIP : '+afterNative+' мс · '+(nativeZip.length/1048576).toFixed(2)+' МБ (≈'+Math.round(afterNative*scale/1000)+' с на 120k)');

  t=Date.now();
  const zipped=fflate.deflateSync(u8,{level:6});
  const afterSync=Date.now()-t;
  console.log('fflate deflateSync level 6: '+afterSync+' мс · '+(zipped.length/1048576).toFixed(2)+' МБ');
  console.log('ускорение упаковки: ×'+(afterZip/afterNative).toFixed(1)+' · объём '+(100-100*nativeZip.length/total).toFixed(1)+'% меньше');

  const back=fflate.unzipSync(new Uint8Array(nativeZip));
  assert.strictEqual(new TextDecoder().decode(back['xl/worksheets/sheet1.xml']),xml,'нативный ZIP распаковывается байт-в-байт');
  console.log('нативный архив прочитан fflate: содержимое совпадает байт-в-байт');

  t=Date.now();const te=new TextEncoder().encode(xml);
  const tTe=Date.now()-t;t=Date.now();const s8=fflate.strToU8(xml);
  console.log('кодирование '+(xml.length/1048576).toFixed(0)+' МБ в UTF-8: TextEncoder '+tTe+' мс · fflate.strToU8 '+(Date.now()-t)+' мс');
})();
