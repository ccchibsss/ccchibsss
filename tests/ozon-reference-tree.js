const fs=require('fs'),vm=require('vm'),h=fs.readFileSync(__dirname+'/../index.html','utf8');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const code=h.match(/const OzonReference = \{[\s\S]*?\n\};\n/)[0];
const context={S:{settings:{ozonReferenceScope:input.scope}},OzonCat:{TYPES:[]}};
vm.createContext(context);vm.runInContext(code+';this.R=OzonReference;',context);
context.R._ref=input.tree;
process.stdout.write(JSON.stringify(input.queries.map(q=>context.R.findPair(q.category,q.type,q.ids))));
