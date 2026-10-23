// Dependency-free UI state regressions for the actual candle panel functions.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{
 constructor(){this.textContent='';this.children=[];this.style={};this.className='';}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(){this.children=[];this.textContent='';}
 setAttribute(){}
}
let now=1800000;
const nodes=Object.fromEntries(['contract','source','candleFlowBars','candleFlowSetup','focusEntry','focusAbsorption'].map(k=>[k,new Element()]));
nodes.contract.value='MNQZ6';nodes.source.value='ws';
const context={Date:class extends Date{static now(){return now;}},
 $:id=>nodes[id],symbol:()=> 'MNQ',fmt:(n)=>String(n),config:{MNQ:{tick:.25}},
 document:{createElement:()=>new Element(),createElementNS:()=>new Element()},
 running:true,ws:{readyState:1},WebSocket:{OPEN:1},
 history:[],KEY:'test',localStorage:{setItem(){}},renderAlerts(){},
 candleFlowState:null,candleFlowEvents:[]};
vm.createContext(context);
const source=fs.readFileSync('app.js','utf8');
vm.runInContext(source.slice(source.indexOf('function receiveCandleFlow('),source.indexOf("setInterval(()=>{if($('source')?.value==='ws')renderCandleFlow()")),context);
const candle={timeframe_seconds:120,open:100,high:102,low:99,close:101,delta:40,
 volume:100,classified_fraction:.9,bbo_fraction:.8,warming_up:false};
const state={type:'candle_state',symbol:'MNQZ6',timestamp:now,candles:[candle],setups:[]};
context.receiveCandleFlow(state);
assert.match(nodes.candleFlowSetup.textContent,/sem padrão/);
const signal={type:'candle_signal',symbol:'MNQZ6',timestamp:now,side:'buy',stage:'GATILHO_CONFIRMADO',
 timeframe_seconds:120,model:'ABSORCAO',setup_id:'x',trigger:101,invalidation:99,price:101,delta_5s:30,reason:'teste'};
context.receiveCandleFlow(signal);
assert.match(nodes.focusEntry.textContent,/GATILHO COMPRA/);
assert.equal(context.history.length,1);
context.receiveCandleFlow(signal);assert.equal(context.history.length,1);
context.receiveCandleFlow({...signal,symbol:'NQZ6',setup_id:'other',side:'sell'});
assert.equal(context.history.length,1);
now+=4000;context.renderCandleFlow();
assert.match(nodes.focusEntry.textContent,/bloqueados/);
assert.equal(nodes.focusEntry.className,'neutral');
context.receiveCandleFlow({...state,timestamp:now});
context.receiveCandleFlow({...signal,timestamp:now,stage:'INVALIDADO'});
assert.match(nodes.focusEntry.textContent,/invalidado/);
assert.equal(context.history.length,2);
now+=11000;context.receiveCandleFlow({...state,timestamp:now});
context.receiveCandleFlow({...signal,setup_id:'new',timestamp:now-11000});
assert.match(nodes.focusEntry.textContent,/já ocorrido/);
console.log('Candle panel: stages, contract isolation, deduplication, stale feed and expired trigger passed.');
