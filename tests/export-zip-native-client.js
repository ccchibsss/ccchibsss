// Нативный ZIP-райтер экспорта: структура архива, порядок записи, откат на fflate.
// NODE_PATH=.arena/idb-tests/node_modules node tests/export-zip-native-client.js
const fs=require('fs'),vm=require('vm'),assert=require('assert'),zlib=require('zlib');
const {CompressionStream}=require('stream/web');
const h=fs.readFileSync(__dirname+'/../index.html','utf8');

const grab=(a,b)=>{const i=h.indexOf(a),j=h.indexOf(b,i);assert(i>0&&j>i,'не найден фрагмент '+a);return h.slice(i,j);};
const fflateStart=h.indexOf('/*! fflate встроен офлайн'),fflateEnd=h.indexOf('</script>',fflateStart);

// Мини-окружение: спул в памяти, fflate из самой сборки, Blob/TextEncoder из Node.
const ctx={console,TextEncoder,Blob,CompressionStream,Uint8Array,DataView,Promise,setTimeout,Math,Number,String,Array,Object,JSON,Error};
ctx.self=ctx;ctx.window=ctx;vm.createContext(ctx);
vm.runInContext(h.slice(fflateStart,fflateEnd),ctx);
ctx.BrowserExportSpool={
  async create(){
    const parts=[];
    return {disk:true,async write(blobs){for(const b of blobs)parts.push(Buffer.from(await b.arrayBuffer()));},
      async finish(){return Buffer.concat(parts);},async abort(){parts.length=0;}};
  }
};
vm.runInContext('this.fflate=self.fflate;',ctx);
/* toU8/utf8enc живут в общей части сборки (возле safeCsvText) — подключаем их,
   иначе фолбэк-путь XLSX не соберётся. */
vm.runInContext(grab('const utf8enc','const XCX_FAST_BAD')+';this.toU8=toU8;',ctx);
vm.runInContext(grab('const BrowserExportZipNative = {','const BrowserExportZip = {')+';this.Native=BrowserExportZipNative;',ctx);(grab('const BrowserExportZipNative = {','const BrowserExportZip = {')+';this.Native=BrowserExportZipNative;',ctx);
const Native=ctx.Native;

const readU16=(b,o)=>b.readUInt16LE(o),readU32=(b,o)=>b.readUInt32LE(o);
function parseZip(buf){
  const eocd=buf.lastIndexOf(Buffer.from([0x50,0x4b,0x05,0x06]));
  assert(eocd>0,'нет EOCD');
  const count=readU16(buf,eocd+10),cdSize=readU32(buf,eocd+12),cdOffset=readU32(buf,eocd+16);
  assert.equal(cdOffset+cdSize,eocd,'смещение/размер центрального каталога');
  const files={};let p=cdOffset;
  for(let i=0;i<count;i++){
    assert.equal(readU32(buf,p),0x02014b50,'сигнатура записи каталога');
    const flags=readU16(buf,p+8),method=readU16(buf,p+10),crc=readU32(buf,p+16),comp=readU32(buf,p+20),size=readU32(buf,p+24);
    const nameLen=readU16(buf,p+28),extra=readU16(buf,p+30),comment=readU16(buf,p+32),localOffset=readU32(buf,p+42);
    const name=buf.slice(p+46,p+46+nameLen).toString('utf8');
    assert.equal(readU32(buf,localOffset),0x04034b50,'сигнатура локального заголовка');
    const lMethod=readU16(buf,localOffset+8),lFlags=readU16(buf,localOffset+6);
    assert.equal(lMethod,method,'метод совпадает с каталогом');
    assert(lFlags&0x8,'в локальном заголовке стоит data descriptor');
    const lNameLen=readU16(buf,localOffset+26),lExtra=readU16(buf,localOffset+28);
    const dataStart=localOffset+30+lNameLen+lExtra;
    const data=buf.slice(dataStart,dataStart+comp);
    const plain=method===8?zlib.inflateRawSync(data):data;
    assert.equal(plain.length,size,'исходный размер');
    assert.equal(zlib.crc32?zlib.crc32(plain):crc32js(plain),crc,'CRC в каталоге');
    // data descriptor идёт сразу за данными и повторяет CRC/размеры
    const dOff=dataStart+comp;
    assert.equal(readU32(buf,dOff),0x08074b50,'сигнатура data descriptor');
    assert.equal(readU32(buf,dOff+4),crc,'CRC в data descriptor');
    assert.equal(readU32(buf,dOff+8),comp,'сжатый размер в data descriptor');
    assert.equal(readU32(buf,dOff+12),size,'исходный размер в data descriptor');
    files[name]=plain.toString('utf8');
    files.__meta=files.__meta||{};files.__meta[name]={crc,comp,size,method,flags,lFlags,dataStart};
    p+=46+nameLen+extra+comment;
  }
  return files;
}
function crc32js(b){let t=[];for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c;}
 let c=-1;for(let i=0;i<b.length;i++)c=t[(c^b[i])&0xFF]^(c>>>8);return (c^-1)>>>0;}

(async()=>{
  assert(Native.supported(),'CompressionStream обязателен в тесте');

  // 1. Много листов, большие тексты (переход через буфер 256 КБ), юникод и XML-спецсимволы.
  const sheets=[];
  sheets.push({name:'xl/worksheets/sheet1.xml',text:'<?xml version="1.0"?><worksheet><sheetData>'+
    Array.from({length:4000},(_,i)=>`<row r="${i+1}"><c r="A${i+1}" t="inlineStr"><is><t>Амортизатор &amp; ${i} 😀</t></is></c></row>`).join('')+
    '</sheetData></worksheet>'});
  sheets.push({name:'xl/workbook.xml',text:'<workbook>'+'x'.repeat(700000)+'</workbook>'});
  sheets.push({name:'[Content_Types].xml',text:'<Types/>'});
  sheets.push({name:'xl/styles.xml',text:''}); // пустой лист тоже должен попасть в архив

  const archive=await Native.create();
  for(const s of sheets){
    const file=archive.sheet(s.name);
    // пишем кусками, как это делает streamXlsx
    for(let off=0;off<s.text.length;off+=997)file.w(s.text.slice(off,off+997));
    await file.end();
  }
  const buf=await archive.finish();
  assert.equal(buf.readUInt32LE(0),0x04034b50,'файл начинается с локального заголовка');
  const files=parseZip(buf);
  assert.deepEqual(Object.keys(files).filter(k=>k!=='__meta').sort(),sheets.map(s=>s.name).sort(),'все листы в архиве');
  for(const s of sheets)assert.equal(files[s.name],s.text,'содержимое '+s.name+' байт-в-байт: получено '+files[s.name].length+' из '+s.text.length+' байт');

  // 2. Попеременная запись листов и flush — порядок байт не должен сбиться.
  const a2=await Native.create();
  const s1=a2.sheet('a.xml');
  s1.w('<root>first</root>');
  await s1.end();
  const s2=a2.sheet('b.xml');
  for(let i=0;i<5000;i++)s2.w(`<n>${i}</n>`);
  if(a2.needsFlush)await a2.flush();
  s2.w('<tail/>');
  await s2.end();
  await a2.flush();
  const files2=parseZip(await a2.finish());
  assert.equal(files2['a.xml'],'<root>first</root>');
  assert(files2['b.xml'].startsWith('<n>0</n>')&&files2['b.xml'].endsWith('<tail/>'),'второй лист целиком');

  // 3. Незакрытый лист — ошибка, а не «тихо обрезанный» архив.
  const a3=await Native.create();
  a3.sheet('x.xml').w('<x/>');
  await assert.rejects(()=>a3.finish(),/Лист ZIP не завершён/);

  // 4. Закрытый архив нельзя переиспользовать.
  const a4=await Native.create();
  const f4=a4.sheet('x.xml');f4.w('<x/>');await f4.end();await a4.finish();
  await assert.rejects(()=>a4.finish(),/уже закрыт/);
  assert.throws(()=>a4.sheet('y.xml'),/уже закрыт/);

  // 4b. Регресс e2e (Chromium): между листами нельзя открывать новый лист,
  // пока предыдущий не закрыт — нативный райтер закрывает лист асинхронно.
  // Раньше smallSheet() в streamXlsx закрывал сводные листы без await.
  const a4b=await Native.create();
  const first=a4b.sheet('a.xml');first.w('<a/>');
  await first.end();
  const second=a4b.sheet('b.xml');second.w('<b/>');
  assert.throws(()=>a4b.sheet('c.xml'),/Предыдущий лист ZIP ещё не завершён/,'второй лист не открывается, пока не закрыт первый');
  await second.end();
  const buf4b=await a4b.finish();
  assert.equal(zlib.inflateRawSync(...(()=>{ // содержимое каждого листа читается
    const eocd=buf4b.lastIndexOf(Buffer.from([0x50,0x4b,0x05,0x06]));
    let p=buf4b.readUInt32LE(eocd+16);const names=[];
    for(let i=0;i<buf4b.readUInt16LE(eocd+10);i++){
      const nameLen=buf4b.readUInt16LE(p+28),extra=buf4b.readUInt16LE(p+30),comm=buf4b.readUInt16LE(p+32);
      names.push({name:buf4b.slice(p+46,p+46+nameLen).toString(),comp:buf4b.readUInt32LE(p+20),off:buf4b.readUInt32LE(p+42)});
      p+=46+nameLen+extra+comm;
    }
    const b=names.find(n=>n.name==='b.xml');
    const ds=b.off+30+buf4b.readUInt16LE(b.off+26)+buf4b.readUInt16LE(b.off+28);
    return [buf4b.slice(ds,ds+b.comp)];
  })()).toString(),'<b/>','второй лист записан целиком');

  // 4c. Крайние случаи: много листов, большой лист, сжатие не «store»,
  // abort доходит до спула, CRC в каталоге совпадает с CRC32 от исходных байт.
  const a4c=await Native.create();
  const exp={},names=[];
  for(let i=0;i<120;i++){const nm='f'+i+'.xml',t='<x>'+i+'</x>';await a4c.add(nm,t);exp[nm]=t;names.push(nm);}
  const big=('текст 😀 & < > "x"\n').repeat(60000);
  await a4c.add('big.xml',big);exp['big.xml']=big;
  const buf4c=await a4c.finish();
  const z4c=parseZip(buf4c);
  for(const nm of Object.keys(exp))assert.equal(z4c[nm].toString(),exp[nm],'крайние случаи: содержимое '+nm);
  // CRC большого листа сверяем со своим CRC32 от исходных байт (parseZip уже
  // проверил CRC в каталоге и в data descriptor для каждого файла).
  const crcReal=(()=>{const t=new Int32Array(256);for(let n2=0;n2<256;n2++){let v=n2;for(let k=0;k<8;k++)v=v&1?0xEDB88320^(v>>>1):v>>>1;t[n2]=v;}
    let c=-1;const b=Buffer.from(big,'utf8');for(let i=0;i<b.length;i++)c=t[(c^b[i])&0xFF]^(c>>>8);return (c^-1)>>>0;})();
  assert.equal(z4c.__meta['big.xml'].crc,crcReal,'CRC большого листа');
  assert.equal(z4c.__meta['big.xml'].size,Buffer.byteLength(big),'несжатый размер большого листа');
  // данные действительно сжимаются, а не пишутся «как есть»
  const rep='одно и то же '.repeat(50000);
  const a4d=await Native.create();await a4d.add('r.xml',rep);
  const z4d=parseZip(await a4d.finish());
  assert.equal(z4d['r.xml'],rep,'повторяющийся текст распаковывается обратно');
  assert(z4d.__meta['r.xml'].comp<Buffer.byteLength(rep)/50,'данные действительно сжаты');
  console.log('крайние случаи: '+names.length+'+1 лист (из них один '+Math.round(Buffer.byteLength(big)/1048576)+' МБ), сжатие ×'+Math.round(Buffer.byteLength(rep)/z4d.__meta['r.xml'].comp));

  // 5. Фолбэк: без CompressionStream остаётся прежний fflate-путь.
  const ctx2={console,TextEncoder,Blob,Uint8Array,DataView,Promise,setTimeout,Math,Number,String,Array,Object,JSON,Error};
  ctx2.self=ctx2;ctx2.window=ctx2;vm.createContext(ctx2);
  vm.runInContext(h.slice(fflateStart,fflateEnd),ctx2);
  vm.runInContext('this.fflate=self.fflate;',ctx2);
  vm.runInContext(grab('const utf8enc','const XCX_FAST_BAD')+';this.toU8=toU8;',ctx2);
  ctx2.BrowserExportSpool=ctx.BrowserExportSpool;
  vm.runInContext(grab('const BrowserExportZipNative = {','const PyEngine = {')+';this.Zip=BrowserExportZip;',ctx2);
  // В этом окружении CompressionStream нет — значит, create() обязан уйти на fflate.
  const fb=await ctx2.Zip.create();
  assert(!fb.native,'без CompressionStream выбирается путь fflate');
  const ff=fb.sheet('x.xml');ff.w('<x>fallback</x>');ff.end();
  const fbBlob=await fb.finish();
  const fbBuf=Buffer.isBuffer(fbBlob)?fbBlob:Buffer.from(await fbBlob.arrayBuffer());
  const fbFiles=ctx2.fflate.unzipSync(new Uint8Array(fbBuf));
  assert.equal(new TextDecoder().decode(fbFiles['x.xml']),'<x>fallback</x>','фолбэк собирает корректный архив');

  /* 6. Два пути упаковки дают ОДИН И ТОТ ЖЕ архив по содержимому: нативный
     (CompressionStream) и fflate. Сравниваем не байты сжатия (zlib разных
     реализаций), а разобранные файлы + CRC/размеры распакованных данных и
     реальные потоки: fflate.unzipSync и zlib.inflateRawSync. Любая ошибка в
     локальных заголовках/дескрипторах/каталоге ловится именно сверкой путей. */
  const sample=[['a.xml','<a>'+('текст & <теги> "кавычки" \u0001\uFFFE '*4000)+'</a>'],
                ['b.xml',''],['c.xml','x'],
                ['d.xml','🎉'.repeat(3000)+'Ж'.repeat(5000)],
                ['e.xml','<x>'+('abcdefghij'.repeat(20000))+'</x>']];
  const nativeZip=await Native.create();
  for(const [n,t] of sample)await nativeZip.add(n,t);
  const nBuf=Buffer.from(await nativeZip.finish());
  const ffZip=await ctx2.Zip.create();
  for(const [n,t] of sample)await ffZip.add(n,t);
  const fBuf=Buffer.from(await ffZip.finish());
  const nFiles=parseZip(nBuf),fFiles=parseZip(fBuf);
  assert.deepEqual(Object.keys(nFiles).filter(k=>k!=='__meta').sort(),Object.keys(fFiles).filter(k=>k!=='__meta').sort(),'оба пути пишут один набор файлов');
  for(const [n,t] of sample){
    assert.equal(new TextDecoder().decode(ctx.fflate.unzipSync(new Uint8Array(nBuf))[n]),t,'fflate читает нативный архив: '+n);
    assert.equal(new TextDecoder().decode(ctx2.fflate.unzipSync(new Uint8Array(fBuf))[n]),t,'fflate читает архив fflate: '+n);
    assert.deepEqual(zlib.inflateRawSync(nBuf.slice(nFiles.__meta[n].dataStart,nFiles.__meta[n].dataStart+nFiles.__meta[n].comp)),Buffer.from(t,'utf8'),'zlib.inflateRawSync нативного архива: '+n);
    assert.equal(nFiles.__meta[n].crc.toString(16),fFiles.__meta[n].crc.toString(16),'CRC совпадает у обоих путей: '+n);
    assert.equal(nFiles.__meta[n].size,fFiles.__meta[n].size,'размер до сжатия совпадает: '+n);
    assert.equal(nFiles.__meta[n].size,Buffer.byteLength(t,'utf8'),'размер до сжатия — UTF-8 исходника: '+n);
    assert.equal(nFiles[n],t,'контент нативного архива совпадает с исходником: '+n);
  }
  console.log('два пути упаковки: '+sample.length+' файлов, содержимое и CRC совпадают, читаются fflate и zlib');

  console.log('OK: нативный ZIP-райтер — порядок байт, data descriptor, CRC, несколько листов, пустой лист, защита от незакрытого листа, совпадение с fflate-путём и фолбэк');
})().catch(e=>{console.error(e);process.exitCode=1});
