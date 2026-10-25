// Presentation regressions: symmetric arcs, stale data and directional badges.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app.js','utf8');
const node=()=>({textContent:'',dataset:{},attrs:{},setAttribute(k,v){this.attrs[k]=v;}});
const gauge=node();gauge.parts=Object.fromEntries(['.spark-arc','.spark-arrow','.spark-percent','.spark-contracts'].map(k=>[k,node()]));gauge.querySelector=k=>gauge.parts[k];
const nodes={gauge,gaugeCaption:node(),focusEntry:node(),focusAbsorption:node()};
const context={$:id=>nodes[id],fmt:n=>String(n)};vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function sparkArcPath('),source.indexOf('function renderCandleFlow(')),context);
for(const side of ['buy','sell'])for(const pct of [1,50,58,63,99]){
 const nums=context.sparkArcPath(pct,side).match(/-?\d+(?:\.\d+)?/g).map(Number);
 assert.ok(Math.abs(nums[0]+nums.at(-2)-120)<1e-8,'endpoints mirror horizontally');
 assert.ok(Math.abs(nums[1]-nums.at(-1))<1e-8,'endpoints have equal heights');
 if(pct===50)assert.ok(side==='buy'?nums[0]>60:nums[0]<60,'buy traverses bottom, sell top');
}
assert.equal(context.sparkArcPath(0,'buy'),'');assert.equal((context.sparkArcPath(100,'buy').match(/ A /g)||[]).length,2);
for(const [buy,sell,available,tone,value] of [[58,42,true,'buy','58%'],[37,63,true,'sell','63%'],[50,50,true,'neutral','50%'],[58,42,false,'neutral','—'],[0,0,true,'neutral','—']]){
 context.updateSparkGauge('gauge',buy,sell,available);assert.equal(gauge.dataset.tone,tone);assert.equal(gauge.parts['.spark-percent'].textContent,value);
 if(tone==='neutral')assert.equal(gauge.parts['.spark-arc'].attrs.d,'');
}
for(const [text,tone] of [['COMPRA CONFIRMADA','buy'],['VENDA CONFIRMADA','sell'],['AGUARDAR','neutral'],['SEM ABSORÇÃO DETECTADA','neutral'],['POSSÍVEL VENDA · AGUARDAR TREASURY','neutral']]){
 nodes.focusEntry.textContent=nodes.focusAbsorption.textContent=text;context.updateSparkStatus();assert.equal(nodes.focusEntry.attrs['data-tone'],tone);assert.equal(nodes.focusAbsorption.attrs['data-tone'],tone);
}
const html=fs.readFileSync('index.html','utf8');const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);assert.equal(ids.length,new Set(ids).size,'data bindings must stay unique');
console.log('Spark UI: symmetric geometry, pressure states, missing data, badges and unique bindings passed.');
