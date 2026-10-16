'use strict';(()=>{
const $=id=>document.getElementById(id),fmt=(n,d=0)=>Number(n).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d}),KEY='flow-ai-v3-alerts';
let history=[];try{history=JSON.parse(localStorage.getItem(KEY)||'[]');if(!Array.isArray(history))history=[]}catch{}
let demoStart=Date.now(),trades=[],play=[],cursor=0,timer=null,ws=null,seed=1217,price=132400,lastStage='',lastAlert=0,breakout=null,running=false,lastIngest=0,buyTrigger=null,sellTrigger=null,zoneRefreshAt=0,diTicks=[],diRate=13.25,lastEarly=0,absZone=null,absLastAlert=0,seenIds=new Set(),rejected=0;
const config={WIN:{tick:5,start:132400},GC:{tick:.1,start:2650},MGC:{tick:.1,start:2650},NQ:{tick:.25,start:20000},MNQ:{tick:.25,start:20000}};

// Filtro macro do ouro: somente observações recebidas do backend autorizado.
// Valores DXY/US02Y/US10Y/TIPS10Y representam índices/yields (não preços de futuros Treasury).
const macroSymbols=['DXY','US02Y','US10Y','TIPS10Y','SI'];
let macroFeeds=Object.fromEntries(macroSymbols.map(k=>[k,[]]));
function macroReset(){macroFeeds=Object.fromEntries(macroSymbols.map(k=>[k,[]]));macroRender(null)}
function ingestMacro(m,source){
 const key=String(m.symbol||'').toUpperCase();if(!macroSymbols.includes(key))return false;
 const value=Number(m.value??m.rate??m.price),raw=m.timestamp;
 let ts=typeof raw==='number'?raw:/^\\d+$/.test(String(raw))?Number(raw):Date.parse(raw);
 if(ts<1e11)ts*=1000;
 if(!Number.isFinite(value)||value<=0||!Number.isFinite(ts))return true;
 if(source==='live'&&(Math.abs(Date.now()-ts)>3000))return true;
 const a=macroFeeds[key];if(a.length&&ts<=a[a.length-1].timestamp)return true;
 a.push({timestamp:ts,value});while(a.length>500||a.length&&a[0].timestamp<ts-900000)a.shift();
 macroRender(ts);return true;
}
function macroEvaluate(now,flowSign){
 const rows=[];let bullish=0,bearish=0,valid=0;
 for(const key of macroSymbols){
  const a=macroFeeds[key],last=a[a.length-1],base=last&&a.find(x=>x.timestamp<=last.timestamp-15000&&x.timestamp>=last.timestamp-120000);
  const fresh=!!last&&Math.abs(now-last.timestamp)<=3000;
  const change=fresh&&base?(last.value-base.value):null;
  // Per-market noise floor; deliberately conservative defaults, not calibrated.
  const threshold={DXY:.03,US02Y:.005,US10Y:.005,TIPS10Y:.005,SI:.03}[key];
  const direction=change===null||Math.abs(change)<threshold?0:Math.sign(change);
  const goldBias=direction*(key==='SI'?1:-1);
  if(fresh&&base&&direction){valid++;if(goldBias>0)bullish++;else bearish++}
  rows.push({key,fresh,change,base:!!base,goldBias});
 }
 const against=flowSign>0?bearish:flowSign<0?bullish:0;
 // Two independent opposing inputs block a new gold confirmation; absent macro data never fabricate consensus.
 return {rows,bullish,bearish,valid,against,blocked:flowSign!==0&&against>=2};
}
function macroRender(now){
 const root=$('macroRows');if(!root)return;
 const ev=macroEvaluate(now??Date.now(),0);
 root.replaceChildren();
 for(const m of ev.rows){
  const item=document.createElement('div');item.className='metric';
  const label=document.createElement('span');label.textContent=m.key;
  const value=document.createElement('strong');value.style.fontSize='13px';
  value.textContent=!m.fresh?'Sem feed recente':!m.base?'Coletando 15s':m.goldBias>0?'Viés favorável à alta':m.goldBias<0?'Viés favorável à baixa':'Sem direção clara';
  value.className=m.goldBias>0?'up':m.goldBias<0?'down':'neutral';
  item.append(label,value);root.append(item);
 }
 $('macroSummary').textContent=ev.valid?'Contexto: '+ev.bullish+' alta / '+ev.bearish+' baixa; correlações condicionais.':'Sem confluência macro verificável. Não simular DXY ou juros.';
}

const isIndexFuture=()=>['NQ','MNQ'].includes(symbol());
const isGold=()=>['GC','MGC'].includes(symbol());
const analysisSymbol=()=>symbol()==='MNQ'?'NQ':symbol()==='MGC'?'GC':symbol();
const microMultiplier=()=>symbol()==='MNQ'?2:symbol()==='MGC'?10:0;
const autoExecutionEnabled=false; // Future only: no broker credentials or order routing in this build.
const nqCorrelates=['ES','US02Y','US10Y','DXY','VIX'];
let nqMacroFeeds=Object.fromEntries(nqCorrelates.map(k=>[k,[]]));
function nqReset(){nqMacroFeeds=Object.fromEntries(nqCorrelates.map(k=>[k,[]]));updateNQPanel(null,0)}
function ingestNQMacro(m,source){const k=String(m.symbol||'').toUpperCase();if(!nqCorrelates.includes(k)||!isIndexFuture())return false;
 const v=Number(m.value??m.rate??m.price);let ts=typeof m.timestamp==='number'?m.timestamp:Date.parse(m.timestamp);if(ts<1e11)ts*=1000;
 if(!Number.isFinite(v)||v<=0||!Number.isFinite(ts)||source==='live'&&Math.abs(Date.now()-ts)>3000)return true;
 const arr=nqMacroFeeds[k];if(arr.length&&ts<=arr[arr.length-1].timestamp)return true;
 arr.push({timestamp:ts,value:v});while(arr.length>200||arr[0].timestamp<ts-600000)arr.shift();return true;
}
function nqEvaluate(now,flowSign){let pro=0,contra=0,observed=0;const rows=[];
 for(const k of nqCorrelates){const a=nqMacroFeeds[k],last=a.at(-1),past=last&&a.find(x=>x.timestamp<=last.timestamp-15000&&x.timestamp>=last.timestamp-120000);
 const fresh=!!last&&Math.abs(now-last.timestamp)<=3000,delta=fresh&&past?last.value-past.value:null;
 const thresholds={ES:1.0,US02Y:.005,US10Y:.005,DXY:.03,VIX:.08};
 const direction=delta===null||Math.abs(delta)<thresholds[k]?0:Math.sign(delta);
 const bias=direction*(k==='ES'?1:-1);if(bias){observed++;if(bias===flowSign)pro++;else if(flowSign!==0)contra++;}
 rows.push({k,fresh,hasPast:!!past,bias});}
 return {rows,pro,contra,observed,blocked:flowSign!==0&&contra>=2};}
function updateNQPanel(now,flowSign){const root=$('nqMacroRows');if(!root)return;const e=nqEvaluate(now??Date.now(),flowSign);root.replaceChildren();for(const r of e.rows){const el=document.createElement('div');el.className='metric';const sp=document.createElement('span');sp.textContent=r.k;const st=document.createElement('strong');st.style.fontSize='13px';st.textContent=!r.fresh?'Sem feed':!r.hasPast?'Coletando histórico':r.bias>0?'Viés alta':r.bias<0?'Viés baixa':'Neutro';st.className=r.bias>0?'up':r.bias<0?'down':'neutral';el.append(sp,st);root.append(el)}$('nqMacroSummary').textContent=e.blocked?'Divergência macro: nova confirmação bloqueada':e.observed?'Confirmações '+e.pro+' · divergências '+e.contra+' (heurísticas)':'Sem confirmação macro ao vivo';return e;}
const symbol=()=>$('instrument').value;function rng(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296}
function log(stage,side,score,why){const a={id:Date.now()+'-'+Math.round(Math.random()*1e6),status:'PENDENTE',after5:null,after30:null,time:new Date().toISOString(),symbol:symbol(),source:$('source').value,stage,side,score,price,why};history.unshift(a);history=history.slice(0,200);try{localStorage.setItem(KEY,JSON.stringify(history))}catch{}renderAlerts()}
function renderAlerts(){const root=$('events');root.replaceChildren();if(!history.length){root.textContent='Nenhum alerta.';return}for(const a of history.slice(0,22)){const el=document.createElement('div');el.className='event '+(/FALSO|INVALIDADO/.test(a.stage)?'bad':a.stage==='CONFIRMADO'?'good':'');const title=document.createElement('b');title.textContent=a.stage+' · '+a.side+' · '+a.symbol+' · '+a.source.toUpperCase();const detail=document.createElement('p');detail.className='muted';detail.textContent=new Date(a.time).toLocaleTimeString('pt-BR')+' · '+fmt(a.price,2)+' · '+a.score+'/100 · '+a.why+' · 5s: '+(a.after5===null||a.after5===undefined?'PENDENTE':fmt(a.after5,2))+' · 30s: '+(a.after30===null||a.after30===undefined?'PENDENTE':fmt(a.after30,2));el.append(title,detail);root.append(el)}}
function stop(){running=false;if(timer)clearInterval(timer);timer=null;if(ws){ws.onclose=null;ws.close();ws=null}$('start').disabled=false;$('stop').disabled=true;$('status').textContent='Pausado'}
function reset(){for(const id of ['shortDelta','shortAcceleration','shortMove','shortConfluence'])if($(id))$(id).textContent='Aguardando dados';stop();demoStart=Date.now();trades=[];play=[];cursor=0;breakout=null;buyTrigger=null;sellTrigger=null;zoneRefreshAt=0;diTicks=[];diRate=13.25;lastEarly=0;seenIds.clear();macroReset();nqReset();rejected=0;lastStage='';lastAlert=0;price=config[symbol()].start;$('instrumentLabel').textContent=symbol()+' · '+(symbol()==='WIN'?'Mini índice':isIndexFuture()?'Nasdaq futuro':'Ouro futuro');$('level').value=symbol()==='WIN'?'132480':isIndexFuture()?'20000.25':'2650.5';$('level').step=config[symbol()].tick;$('breakLevel').textContent=fmt(Number($('level').value),symbol()==='WIN'?0:2);$('price').textContent=fmt(price,symbol()==='WIN'?0:2);for(const id of ['delta','volume','rate','score','entry','stopPrice','risk','target1','target2'])$(id).textContent='—';$('signal').textContent='AGUARDAR';$('signal').className='signal neutral';$('heroDelta').textContent='—';$('heroDelta').className='neutral';$('heroDeltaTrend').textContent='Aguardando fluxo';$('stage').textContent='OBSERVAÇÃO';$('reason').textContent='Aguardando negócios.';$('confidence').textContent='Força heurística: —';$('timeframes').textContent='Aguardando dados';$('buyBar').style.width='50%';$('sellBar').style.width='50%';$('buyPct').textContent='50%';$('sellPct').textContent='50%';$('feedAge').textContent='Sem dados';$('sourceTag').textContent='DEMO · ARTIFICIAL';$('healthWin').textContent='Desconectado';$('healthDI').textContent='Desconectado';$('healthBook').textContent='Não integrado';$('healthQuality').textContent='Aguardando';$('demoPhase').textContent='Cenário fictício disponível — clique em Iniciar';$('absZone').textContent='Aguardando negócios';$('absStatus').textContent='Sem evidência suficiente.';$('absDirection').textContent='Direção: aguardando confirmação.';$('diStatus').textContent='DI1 aguardando';$('burstStatus').textContent='Aguardando dados';$('confluence').textContent='Sem confirmação';$('buyTrigger').textContent='Aguardando dados';$('sellTrigger').textContent='Aguardando dados';$('buyZoneCard').className='zone';$('sellZoneCard').className='zone';$('triggerInfo').textContent='Coletando histórico para delimitar suporte e resistência; sem gatilhos ativos.'}
function normalize(m,archive=false){if(!m||typeof m!=='object'||String(m.symbol||'').toUpperCase()!==symbol())return null;const price=Number(m.price),size=Number(m.size),side=String(m.side||'').toLowerCase();let timestamp=typeof m.timestamp==='number'?m.timestamp:/^\d+$/.test(String(m.timestamp))?Number(m.timestamp):Date.parse(m.timestamp);if(timestamp<1e11)timestamp*=1000;if(!Number.isFinite(timestamp)||!Number.isFinite(price)||price<=0||!Number.isSafeInteger(size)||size<=0||size>1000000||!['buy','sell'].includes(side))return null;if(!archive&&(timestamp>Date.now()+5000||timestamp<Date.now()-60000))return null;return {timestamp,price,size,side}}
function ingestDI(m,source){if(symbol()!=='WIN'||!m||String(m.symbol||'').toUpperCase().indexOf('DI1')!==0)return;const rate=Number(m.rate),ts=typeof m.timestamp==='number'?m.timestamp:Date.parse(m.timestamp);const timestamp=ts<1e11?ts*1000:ts;if(!Number.isFinite(rate)||rate<0||rate>100||!Number.isFinite(timestamp))return;if(source==='live'&&(Date.now()-timestamp>3000||timestamp>Date.now()+5000))return;if(diTicks.length&&timestamp<diTicks[diTicks.length-1].timestamp)return;diTicks.push({timestamp,rate});diTicks=diTicks.filter(x=>x.timestamp>=timestamp-30000).slice(-1000);diRate=rate;}
function ingest(m,source){const normalizedSymbol={...m,symbol:(symbol()==='MNQ'&&String(m.symbol).toUpperCase()==='NQ')?'MNQ':m.symbol}; // only NQ->MNQ analysis proxy; GC and MGC remain distinctconst t=normalize(normalizedSymbol,source==='csv');if(!t){rejected++;return;}const id=String(m.trade_id??m.id??'');if(id){if(seenIds.has(id))return;seenIds.add(id);if(seenIds.size>15000)seenIds.clear();}if(trades.length&&t.timestamp<trades[trades.length-1].timestamp-1000)return;trades.push(t);if(trades.length>65000)trades.splice(0,8000);price=t.price;lastIngest=Date.now();render(source)}
function calc(now,windowMs){const arr=trades.filter(t=>t.timestamp>=now-windowMs);let b=0,s=0;for(const t of arr)t.side==='buy'?b+=t.size:s+=t.size;return {arr,b,s,volume:b+s,delta:b-s,span:arr.length>1?now-arr[0].timestamp:0}}
function render(source){if(!trades.length)return;const now=trades[trades.length-1].timestamp,c=config[symbol()],d=symbol()==='WIN'?0:2,w=calc(now,60000),{b,s,volume,delta,span,arr}=w;const percent=volume?Math.round(b/volume*100):50,sign=Math.sign(delta),move=price-arr[0].price,aligned=sign!==0&&Math.sign(move)===sign,rate=arr.length/Math.max(1,span/1000),imbal=volume?Math.abs(delta)/volume:0,level=Number($('level').value),broke=sign>0?price>level:sign<0?price<level:false,hasEnough=arr.length>=24&&span>=5000&&volume>=40,fresh=source!=='live'||Date.now()-now<=3000;
// Níveis congelados durante a janela de observação, evitando gatilho que persiga cada tick.
// Resistência/suporte calculados SOMENTE com negócios anteriores ao instante atual.
const prior=trades.filter(t=>t.timestamp>=now-90000&&t.timestamp<=now-5000);
if(prior.length>=20&&prior[prior.length-1].timestamp-prior[0].timestamp>=5000&&(!zoneRefreshAt||now-zoneRefreshAt>=60000)){
 const high=Math.max(...prior.map(t=>t.price)),low=Math.min(...prior.map(t=>t.price));
 buyTrigger=Math.round((high+c.tick)/c.tick)*c.tick;
 sellTrigger=Math.round((low-c.tick)/c.tick)*c.tick;
 zoneRefreshAt=now;breakout=null;
}
const buyBreak=buyTrigger!==null&&price>=buyTrigger;
const sellBreak=sellTrigger!==null&&price<=sellTrigger;
const triggerBroke=sign>0?buyBreak:sign<0?sellBreak:false;
const dTrigger=symbol()==='WIN'?0:2;
$('buyTrigger').textContent=buyTrigger===null?'Aguardando histórico':'Acima de '+fmt(buyTrigger,dTrigger);
$('sellTrigger').textContent=sellTrigger===null?'Aguardando histórico':'Abaixo de '+fmt(sellTrigger,dTrigger);
$('buyZoneCard').className='zone'+(buyBreak?' active-buy':'');
$('sellZoneCard').className='zone'+(sellBreak?' active-sell':'');
$('buyZoneText').textContent=buyBreak?'Região rompida; validar delta e continuidade.':'Possível compra somente após rompimento com agressão compradora.';
$('sellZoneText').textContent=sellBreak?'Região perdida; validar delta e continuidade.':'Possível venda somente após rompimento com agressão vendedora.';
$('triggerInfo').textContent=zoneRefreshAt?'Faixas baseadas nas máximas/mínimas observadas antes do gatilho, fixadas por 60 s. '+(source==='demo'?'Preços inteiramente fictícios.':source==='csv'?'Preços históricos em replay.':'Feed externo não auditado.'):'Sem histórico suficiente para calcular zonas.';
// Detecção heurística de absorção: alta agressão sem avanço e repetidos testes.
// NÃO prova presença de player institucional ou de liquidez oculta.
const sample=trades.filter(t=>t.timestamp>=now-12000);
if(sample.length>=25){
 const v=sample.reduce((q,t)=>q+t.size,0),signed=sample.reduce((q,t)=>q+(t.side==='buy'?t.size:-t.size),0);
 const hi=Math.max(...sample.map(t=>t.price)),lo=Math.min(...sample.map(t=>t.price));
 const displacement=price-sample[0].price,pressure=v?Math.abs(signed)/v:0;
 const testedUpper=sample.filter(t=>t.price>=hi-c.tick).length;
 const testedLower=sample.filter(t=>t.price<=lo+c.tick).length;
 const imbalanceSide=Math.sign(signed);
 const stall=pressure>=.48&&Math.abs(displacement)<=c.tick*3&&v>=100;
 const repeated=imbalanceSide>0?testedUpper>=4:testedLower>=4;
 if(stall&&repeated&&(!absZone||now-absZone.formed>25000)){
   const ceiling=imbalanceSide>0,mid=ceiling?hi:lo;
   absZone={low:mid-c.tick,high:mid+c.tick,formed:now,kind:ceiling?'VENDEDORA':'COMPRADORA',absorbed:Math.abs(signed),state:'ATIVA',brokenAt:null};
 }
}
if(absZone){
 const breakUp=price>absZone.high+c.tick,breakDown=price<absZone.low-c.tick;
 if(absZone.state==='ATIVA'&&(breakUp||breakDown)){
   absZone.state=breakUp?'ROMPIDA PARA CIMA':'ROMPIDA PARA BAIXO';absZone.brokenAt=now;
   if(now-absLastAlert>=5000){log('REGIÃO DE ABSORÇÃO ROMPIDA',breakUp?'COMPRA':'VENDA',0,'Região rompida: aguardar confirmação de agressão, DI1 e risco.');absLastAlert=now;}
 }
 if(absZone.state!=='ATIVA'&&now-absZone.brokenAt>15000)absZone=null;
}
$('absZone').textContent=absZone?fmt(absZone.low,d)+' – '+fmt(absZone.high,d):'Ainda não identificada';
$('absStatus').textContent=absZone?absZone.kind+' · '+absZone.state+' · agressão absorvida estimada '+fmt(absZone.absorbed)+' contratos':'Aguardando agressão forte com deslocamento reduzido e testes repetidos.';
$('absDirection').textContent=!absZone?'Direção: sem hipótese':absZone.state==='ATIVA'?(absZone.kind==='VENDEDORA'?'Possível rejeição para baixo; não confirmado.':'Possível rejeição para cima; não confirmado.'):(absZone.state==='ROMPIDA PARA CIMA'?'Rompimento comprador detectado; validar continuidade.':'Rompimento vendedor detectado; validar continuidade.');
const score=Math.min(100,Math.round(imbal*34+Math.min(1,rate/7)*22+(aligned?19:0)+Math.min(1,Math.abs(move)/(c.tick*15))*15+(triggerBroke?10:0)));
// Confirmação DI: inversão de direção observada em janela de até 5 segundos.
// Sem DI recente no feed real, nenhum alerta de antecipação é permitido.
const diLast=diTicks[diTicks.length-1],diPast=diTicks.find(x=>diLast&&x.timestamp>=diLast.timestamp-5000),diDelta=diLast&&diPast?diLast.rate-diPast.rate:NaN;
const syncGap=diLast?Math.abs(now-diLast.timestamp):Infinity;
const diFresh=!!diLast&&syncGap<=1500&&(source==='demo'||source==='csv'||Date.now()-diLast.timestamp<=3000);
const diDirection=Number.isFinite(diDelta)&&Math.abs(diDelta)>=.005?Math.sign(diDelta):0;
const diAligned=symbol()!=='WIN'||(diFresh&&sign!==0&&diDirection===-sign);
const recentSecond=trades.filter(t=>t.timestamp>now-1000),recentVolume=recentSecond.reduce((v,t)=>v+t.size,0);
const buckets=Array.from({length:12},(_,i)=>trades.filter(t=>t.timestamp>now-(i+2)*1000&&t.timestamp<=now-(i+1)*1000).reduce((v,t)=>v+t.size,0));
const baseline=buckets.filter(x=>x>0),baseVolume=baseline.length>=8?baseline.reduce((x,y)=>x+y,0)/baseline.length:NaN;
const spikeRatio=Number.isFinite(baseVolume)&&baseVolume>0?recentVolume/baseVolume:NaN;
const recentBuy=recentSecond.filter(t=>t.side==='buy').reduce((v,t)=>v+t.size,0),recentSell=recentVolume-recentBuy;
const burstSide=Math.sign(recentBuy-recentSell),burstShare=recentVolume?Math.abs(recentBuy-recentSell)/recentVolume:0;
const abnormal=baseline.length>=8&&spikeRatio>=1.8&&burstShare>=.55&&burstSide!==0;
// Sem histórico de várias sessões equivalentes, a referência é curta e rotulada.
const noGap=arr.length>1&&arr.every((t,i)=>i===0||t.timestamp-arr[i-1].timestamp<=2000);
const liquidityOK=volume>=60&&rate>=2;
const qualityOK=fresh&&noGap&&liquidityOK&&(source!=='live'||rejected<10);
$('filterState').textContent='Qualidade: '+(qualityOK?'OK':'BLOQUEADA')+' · DI1: '+(diFresh?'sincronizado':'ausente/fora de sincronia')+' · referência: 12 segundos (histórico por horário ainda não disponível)'+' · rejeitados: '+rejected;
// Confluência de curtíssimo prazo: agressão NOVA, resposta de preço e DI1 sincronizado.
// Janelas de 1/3/5s são independentes do delta acumulado móvel de 60s.
const shortFlow=ms=>{const a=trades.filter(t=>t.timestamp>now-ms&&t.timestamp<=now);return {delta:a.reduce((v,t)=>v+(t.side==='buy'?t.size:-t.size),0),volume:a.reduce((v,t)=>v+t.size,0),arr:a};};
const f1=shortFlow(1000),f3=shortFlow(3000),f5=shortFlow(5000);
const prev3=trades.filter(t=>t.timestamp>now-6000&&t.timestamp<=now-3000);
const previousDelta=prev3.reduce((v,t)=>v+(t.side==='buy'?t.size:-t.size),0);
const acceleration=f3.delta-previousDelta;
const shortSign=Math.sign(f3.delta);
const localMove=f3.arr.length>1?price-f3.arr[0].price:0;
const shortAligned=shortSign!==0&&Math.sign(localMove)===shortSign&&Math.abs(localMove)>=c.tick;
const strongShort=f3.volume>=20&&f3.arr.length>=5&&Math.abs(f3.delta)/f3.volume>=.35;
const accelerating=shortSign!==0&&Math.sign(acceleration)===shortSign&&Math.abs(acceleration)>=Math.max(10,f3.volume*.15);
const diShortOK=symbol()!=='WIN'||(diFresh&&diDirection===-shortSign);
const quickRisk=()=>{const a=trades.filter(t=>t.timestamp>=now-5000),swing=shortSign>0?Math.min(...a.map(t=>t.price)):Math.max(...a.map(t=>t.price));return a.length>1&&(symbol()!=='WIN'||Math.abs(price-swing)+2*c.tick<=Math.min(200,Math.max(5,Number($('maxStop').value)||200)));};
const shortConfluence=hasEnough&&qualityOK&&strongShort&&accelerating&&shortAligned&&diShortOK&&quickRisk();
$('shortDelta').textContent='1s '+(f1.delta>=0?'+':'')+fmt(f1.delta)+' · 3s '+(f3.delta>=0?'+':'')+fmt(f3.delta)+' · 5s '+(f5.delta>=0?'+':'')+fmt(f5.delta);
$('shortAcceleration').textContent=(acceleration>0?'+':'')+fmt(acceleration)+' contratos (3s atual − 3s anterior)';
$('shortMove').textContent=(localMove>0?'+':'')+fmt(localMove,d)+' '+(symbol()==='WIN'?'pts':'USD/oz');
$('shortConfluence').textContent=shortConfluence?'CONFLUÊNCIA EXPERIMENTAL '+(shortSign>0?'COMPRADORA':'VENDEDORA'):'AGUARDAR — '+(!qualityOK?'qualidade dos dados':!strongShort?'agressão recente insuficiente':!accelerating?'sem aceleração':!shortAligned?'preço não acompanha':!diShortOK?'DI1 não confirma':'risco acima do limite');
$('shortConfluence').className=shortConfluence?(shortSign>0?'up':'down'):'muted';
const diConfirmed=symbol()!=='WIN'||diAligned;
const impulse=rate>=2&&imbal>=.2&&aligned&&Math.abs(move)>=c.tick*2;
const early=hasEnough&&qualityOK&&abnormal&&diConfirmed&&burstSide===sign&&sign!==0&&shortConfluence;
const pre=hasEnough&&qualityOK&&impulse&&score>=52&&diConfirmed;
const confluenceEarly=shortConfluence&&shortSign===sign;
const macro=isGold()?macroEvaluate(now,sign):null;
const nqMacro=isIndexFuture()?updateNQPanel(now,sign):null;
const macroBlocked=!!macro&&macro.blocked||!!nqMacro&&nqMacro.blocked;
const confirmed=pre&&confluenceEarly&&triggerBroke&&score>=73&&!macroBlocked;
if(macro){macroRender(now);$('macroSummary').textContent=(macroBlocked?'DIVERGÊNCIA MACRO: confirmação bloqueada · ':'')+macro.bullish+' favoráveis à alta / '+macro.bearish+' favoráveis à baixa · '+macro.valid+' direções observadas. Ausência de feed não é confirmação.';}
$('diStatus').textContent=symbol()!=='WIN'?'Não se aplica ao ouro':!diFresh?'DI1 ausente ou atrasado':diDirection<0?'DI1 em queda ('+fmt(diDelta,3)+' p.p.)':diDirection>0?'DI1 em alta ('+fmt(diDelta,3)+' p.p.)':'DI1 sem direção relevante';
$('burstStatus').textContent=Number.isFinite(spikeRatio)?fmt(spikeRatio,1)+'× do volume normal · '+fmt(burstShare*100,0)+'% desequilíbrio':'Aguardando 8 janelas de referência';
$('confluence').textContent=source==='demo'?'DI e fluxo inteiramente simulados':symbol()!=='WIN'?'Filtro DI1 apenas no WIN':diAligned&&abnormal?'CONFLUÊNCIA: DI1 + pressão anormal':diFresh?'Sem confluência DI1 + fluxo':'SEM DI1: antecipação bloqueada';
if(early&&riskCheckQuick()&&now-lastEarly>=5000){log('PRÉ-ALERTA 2–3s (ALVO)',sign>0?'COMPRA':'VENDA',score,'Pressão '+fmt(spikeRatio,1)+'×; DI1 na direção oposta. Antecipação não garantida.');lastEarly=now;}

function riskCheckQuick(){if(symbol()!=='WIN')return true;const points=Math.ceil((Math.max(...trades.slice(-50).map(x=>x.price))-Math.min(...trades.slice(-50).map(x=>x.price)))/c.tick)*c.tick+2*c.tick;return points<=Math.min(200,Math.max(5,Number($('maxStop').value)||200));}
const last=trades.slice(-50),swing=sign>0?Math.min(...last.map(x=>x.price)):Math.max(...last.map(x=>x.price)),riskTicks=Math.ceil(Math.abs(price-swing)/c.tick)+2,risk=riskTicks*c.tick,limit=Math.min(200,Math.max(5,Number($('maxStop').value)||200)),riskValid=symbol()!=='WIN'||risk<=limit,side=sign>0?'COMPRA':sign<0?'VENDA':'NEUTRO';
let stage=confirmed?'CONFIRMADO':confluenceEarly?'CONFLUÊNCIA ANTECIPADA':early?'PRESSÃO ANORMAL':pre?'ANTECIPADO':'OBSERVAÇÃO';if(!riskValid&&stage!=='OBSERVAÇÃO')stage='BLOQUEADO · STOP';if(!qualityOK)stage='BLOQUEADO · QUALIDADE';if(macroBlocked&&pre&&confluenceEarly&&triggerBroke)stage='BLOQUEADO · MACRO';
$('price').textContent=fmt(price,d);$('sourceTag').textContent=source==='live'?'WSS · NÃO VERIFICADO':source==='csv'?'REPLAY HISTÓRICO':'DEMO · ARTIFICIAL';$('priceHint').textContent=source==='live'?'Feed externo não auditado':source==='csv'?'Reprodução de CSV':'Preço sintético';$('buyPct').textContent=percent+'%';$('sellPct').textContent=100-percent+'%';$('buyBar').style.width=percent+'%';$('sellBar').style.width=100-percent+'%';$('delta').textContent=(delta>0?'+':'')+fmt(delta);$('heroDelta').textContent=(delta>0?'+':'')+fmt(delta);$('heroDelta').className=delta>0?'up':delta<0?'down':'neutral';$('heroDeltaTrend').textContent=delta>0?'Predomínio comprador':delta<0?'Predomínio vendedor':'Agressões equilibradas';$('delta').className=delta>0?'up':delta<0?'down':'neutral';$('volume').textContent=fmt(volume);$('rate').textContent=fmt(rate,1);$('score').textContent=score+'/100';$('confidence').textContent='Força heurística '+score+'/100 · não é taxa de acerto';$('stage').textContent=stage;
$('signal').textContent=stage==='CONFIRMADO'?'POSSÍVEL '+side:stage==='ANTECIPADO'||stage==='PRESSÃO ANORMAL'||stage==='CONFLUÊNCIA ANTECIPADA'?'ATENÇÃO '+side:stage.startsWith('BLOQUEADO')?'SEM ENTRADA':'AGUARDAR';$('signal').className='signal '+(stage==='CONFIRMADO'||(stage==='ANTECIPADO'||stage==='PRESSÃO ANORMAL'||stage==='CONFLUÊNCIA ANTECIPADA')?(sign>0?'up':'down'):'neutral');
const validEntry=stage==='CONFIRMADO'&&riskValid;for(const id of ['entry','stopPrice','risk','target1','target2'])$(id).textContent='—';if(validEntry){$('entry').textContent=fmt(price,d);$('stopPrice').textContent=fmt(price-sign*risk,d);$('risk').textContent=fmt(risk,d)+(symbol()==='WIN'||isIndexFuture()?' pts':' USD/oz');if(isIndexFuture()){const n=Number($('mnqContracts').value)||1;$('mnqRiskDisplay').textContent='Risco técnico estimado: =fmt(price+sign*300);$('target2').textContent=fmt(price+sign*400)}}
$('breakLevel').textContent=fmt(level,d);$('flowNarrative').textContent='Agressão '+side.toLowerCase()+' · delta '+fmt(delta)+' · deslocamento '+(aligned?'alinhado':'não confirmado')+' · '+fmt(rate,1)+' negócios/s.';
$('reason').textContent=!fresh?'Feed atrasado: nova entrada bloqueada.':!hasEnough?'Amostra insuficiente de negócios.':!riskValid?'Risco técnico supera o limite de planejamento configurado (não monitorado na NinjaTrader).':stage==='CONFIRMADO'?'Rompimento de '+fmt(sign>0?buyTrigger:sellTrigger,d)+' com pressão e deslocamento alinhados.':stage==='ANTECIPADO'?'Pressão emergente: aguardar rompimento da região de '+(sign>0?(buyTrigger===null?'compra':fmt(buyTrigger,d)):(sellTrigger===null?'venda':fmt(sellTrigger,d)))+'.':'Aguardar Delta recente acelerando, deslocamento do preço, DI1 e risco válido.';
$('intelligence').textContent='Leitura local de fluxo: delta '+fmt(delta)+', desequilíbrio '+fmt(imbal*100,1)+'%, velocidade '+fmt(rate,1)+'/s, deslocamento '+fmt(move,d)+', '+(triggerBroke?'rompimento observado':'nível não rompido')+'. Sem identificação de instituições; nenhuma IA treinada conectada.';
$('feedAge').textContent=(source==='live'?'WSS':source==='csv'?'CSV REPLAY':'DEMO')+' · negócio '+new Date(now).toLocaleTimeString('pt-BR')+(source==='live'?' · idade '+fmt((Date.now()-now)/1000,1)+'s':'');
let changed=false;for(const alert of history){if(alert.symbol!==symbol()||alert.source!==$('source').value)continue;const origin=Date.parse(alert.time),age=source==='csv'?now-origin:Date.now()-origin; if(age>=5000&&alert.after5===null&&alert.after5!==undefined){alert.after5=null;} if(source!=='csv'&&age>=5000&&alert.after5===null){alert.after5=Math.round((price-alert.price)*100)/100;changed=true;}if(source!=='csv'&&age>=30000&&alert.after30===null){alert.after30=Math.round((price-alert.price)*100)/100;changed=true;}}if(changed){try{localStorage.setItem(KEY,JSON.stringify(history))}catch{}renderAlerts()}const measured=history.filter(a=>a.symbol===symbol()&&a.after30!==null&&a.after30!==undefined);$('outcomeSummary').textContent=measured.length?'Sinais com 30s observados: '+measured.length+' · movimento bruto posterior, sem custo ou classificação de acerto.':'Sem avaliações de 30 segundos completas. Replay CSV não é avaliação fiel.';
updateHealth(source,now,qualityOK,diFresh);
const tf=$('timeframes');tf.replaceChildren();for(const [name,ms] of [['1m',60000],['5m',300000],['15m',900000],['30m',1800000],['Dia',86400000]]){const t=calc(now,ms),el=document.createElement('div');el.className='tfi';const head=document.createElement('small');head.textContent=name;const bold=document.createElement('b');bold.textContent=t.arr.length?fmt(t.delta):'—';bold.className=t.delta>0?'up':t.delta<0?'down':'neutral';const foot=document.createElement('small');foot.textContent=t.arr.length?(t.span>=ms*.8?'janela ok':'parcial'):'sem dados';el.append(head,bold,foot);tf.append(el)}
if(triggerBroke&&hasEnough&&!breakout)breakout={sign,level:sign>0?buyTrigger:sellTrigger,at:now};if(breakout&&now-breakout.at<30000&&((breakout.sign>0&&price<breakout.level-c.tick)||(breakout.sign<0&&price>breakout.level+c.tick))){if(Date.now()-lastAlert>2500){log('FALSO ROMPIMENTO',breakout.sign>0?'COMPRA':'VENDA',score,'Retorno para dentro do nível');lastAlert=Date.now()}breakout=null}
if(lastStage==='CONFIRMADO'&&stage!=='CONFIRMADO'&&Date.now()-lastAlert>2500){log('INVALIDADO',side,score,'Perda das condições de confirmação');lastAlert=Date.now()}if((stage==='ANTECIPADO'||stage==='CONFIRMADO')&&stage!==lastStage&&Date.now()-lastAlert>2500){log(stage,side,score,stage==='ANTECIPADO'?'Pré-alerta: pressão emergente':'Preço e agressão alinhados após rompimento');lastAlert=Date.now()}lastStage=stage;
}
function updateHealth(source,now,qualityOK,diFresh){const age=Date.now()-now;const live=source==='live',demo=source==='demo';$('healthWin').textContent=live?(age<=3000?'Recebendo · '+Math.round(age)+' ms':'Atrasado'):demo?'DEMO sintética':'CSV histórico';$('healthDI').textContent=symbol()!=='WIN'?'Não aplicável':demo?(diFresh?'DI1 fictício':'Aguardando DI1 demo'):source==='csv'?'Não fornecido no CSV':diFresh?'DI1 recente':'Ausente / atrasado';$('healthBook').textContent='Não integrado';$('healthQuality').textContent=qualityOK?'Critérios OK':'Sinais bloqueados';$('healthDetail').textContent='Fonte '+source.toUpperCase()+' · sem book real · DI1 e negócios exigem sincronia. Testes de interface não validam estratégia financeira.';}
function runSelfTest(){const synthetic=[{label:'pressão compradora',buy:850,sell:150,move:20,rateDelta:-.02,expected:1},{label:'pressão vendedora',buy:120,sell:880,move:-20,rateDelta:.02,expected:-1},{label:'absorção possível',buy:850,sell:150,move:0,rateDelta:-.02,expected:0},{label:'DI divergente',buy:800,sell:200,move:15,rateDelta:.02,expected:0}];const outcomes=synthetic.map(x=>{const sign=Math.sign(x.buy-x.sell),aligned=Math.sign(x.move)===sign&&x.move!==0,interest=Math.sign(x.rateDelta)===-sign;return {label:x.label,result:aligned&&interest?sign:0,expected:x.expected}});const passed=outcomes.filter(x=>x.result===x.expected).length;$('selfTestResult').textContent=passed+'/'+outcomes.length+' casos de regra OK (não é backtest)';$('selfTestResult').className=passed===outcomes.length?'up':'down';}
$('selfTest').onclick=runSelfTest;
function demo(){
 const t=Date.now(),elapsed=(t-demoStart)/1000,phase=elapsed%40;
 // 0-13s referência normal; 13-20s pressão compradora; 20-26s estabilização;
 // 26-33s pressão vendedora; 33-40s estabilização.
 const burstBuy=phase>=13&&phase<20,burstSell=phase>=26&&phase<33,burst=burstBuy||burstSell;
 const favored=burstBuy?'buy':burstSell?'sell':'';
 const side=favored?(rng()<.96?favored:(favored==='buy'?'sell':'buy')):(rng()<.5?'buy':'sell');
 const size=burst?70+Math.floor(rng()*95):7+Math.floor(rng()*15);
 const tick=config[symbol()].tick;
 // DI1 fictício: direcionado em sentido inverso apenas durante a pressão;
 // nunca é apresentado como valor observado na B3.
 if(symbol()==='WIN'&&(!diTicks.length||t-diTicks[diTicks.length-1].timestamp>=750)){
  const d=burstBuy?-.012:burstSell?.012:(rng()-.5)*.002;
  diRate=Math.round((diRate+d)*1000)/1000;
  ingestDI({symbol:'DI1-DEMO',rate:diRate,timestamp:t},'demo');
 }
 const step=burst?(side==='buy'?1:-1)*(rng()<.92?2:1)*tick:(rng()<.48?(side==='buy'?1:-1)*tick:0);
 price=Math.round((price+step)/tick)*tick;
 ingest({timestamp:t,price,size,side,symbol:symbol()},'demo');
 $('demoPhase').textContent=burstBuy?'Cenário: agressão compradora extraordinária + DI1 em queda':burstSell?'Cenário: agressão vendedora extraordinária + DI1 em alta':'Cenário: formando volume normal de referência';
}
function parseCSV(text){const lines=text.replace(/^\uFEFF/,'').trim().split(/\r?\n/);if(lines.length<2||lines.length>100001)throw Error('CSV inválido ou limite de 100 mil linhas');const sep=lines[0].includes(';')?';':',';const headers=lines.shift().split(sep).map(x=>x.trim().toLowerCase());for(const h of ['timestamp','price','size','side','symbol'])if(!headers.includes(h))throw Error('Coluna ausente: '+h);const out=[];for(const row of lines){const values=row.split(sep),obj=Object.fromEntries(headers.map((h,i)=>[h,values[i]?.trim()])),t=normalize(obj,true);if(t)out.push(t)}return out.sort((a,b)=>a.timestamp-b.timestamp)}
$('source').onchange=()=>{stop();$('csvWrap').classList.toggle('hidden',$('source').value!=='csv');$('wsWrap').classList.toggle('hidden',$('source').value!=='ws')};$('instrument').onchange=reset;$('level').onchange=()=>{breakout=null;$('breakLevel').textContent=fmt(Number($('level').value),symbol()==='WIN'?0:2)};$('reset').onclick=reset;$('stop').onclick=stop;
$('start').onclick=async()=>{reset();const mode=$('source').value;if(mode==='csv'){const file=$('file').files[0];if(!file){$('status').textContent='Selecione o CSV';return}if(file.size>12000000){$('status').textContent='CSV acima de 12 MB';return}try{play=parseCSV(await file.text());if(!play.length)throw Error('Nenhum negócio válido')}catch(e){$('status').textContent=e.message;return}}
if(mode==='ws'){const url=$('endpoint').value.trim();if(!/^wss:\/\//.test(url)){$('status').textContent='Informe wss:// válido';return}try{ws=new WebSocket(url);ws.onopen=()=>{ws.send(JSON.stringify({type:'subscribe',symbol:analysisSymbol()}));if(symbol()==='WIN')ws.send(JSON.stringify({type:'subscribe',symbol:'DI1'}));else if(isGold())for(const macroSymbol of macroSymbols)ws.send(JSON.stringify({type:'subscribe',symbol:macroSymbol}));else if(isIndexFuture()){if(symbol()==='MNQ')ws.send(JSON.stringify({type:'subscribe',symbol:'NQ'}));for(const k of nqCorrelates)ws.send(JSON.stringify({type:'subscribe',symbol:k}));}$('status').textContent='Conectado; aguardando feed'};ws.onmessage=e=>{try{let items=JSON.parse(e.data);if(!Array.isArray(items))items=[items];for(const x of items){if(ingestNQMacro(x,'live')){updateNQPanel(Date.now(),Math.sign(calc(Date.now(),3000).delta));continue;}if(ingestMacro(x,'live'))continue;if(String(x.symbol||'').toUpperCase().startsWith('DI1'))ingestDI(x,'live');else ingest(x,'live')}}catch{}};ws.onerror=()=>{$('status').textContent='Erro de conexão'};ws.onclose=()=>{if(running)stop()}}catch{$('status').textContent='Falha WSS';return}}
running=true;$('start').disabled=true;$('stop').disabled=false;$('status').textContent=mode==='demo'?'Simulando':mode==='csv'?'Reproduzindo CSV':'Conectando WSS';if(mode==='demo')timer=setInterval(demo,140);else if(mode==='csv')timer=setInterval(()=>{if(cursor>=play.length){stop();$('status').textContent='Replay concluído';return}for(let i=0;i<8&&cursor<play.length;i++){const t=play[cursor++];trades.push(t);price=t.price}render('csv')},140);else timer=setInterval(()=>{if(trades.length&&Date.now()-lastIngest>3000){$('healthWin').textContent='Feed atrasado';$('healthQuality').textContent='Sinais bloqueados';$('stage').textContent='BLOQUEADO · FEED';$('signal').textContent='SEM ENTRADA';for(const id of ['entry','stopPrice','risk'])$(id).textContent='—';$('status').textContent='Feed atrasado'}},1000)};
$('clear').onclick=()=>{if(!confirm('Apagar alertas deste navegador?'))return;history=[];try{localStorage.removeItem(KEY)}catch{}renderAlerts()};$('export').onclick=()=>{const rows=[['timestamp','symbol','source','stage','side','price','score','reason'],...history.map(a=>[a.time,a.symbol,a.source,a.stage,a.side,a.price,a.score,a.why])],csv=rows.map(r=>r.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv'})),a=document.createElement('a');a.href=url;a.download='flow-ai-v3-alertas.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
renderAlerts();reset();
})();+fmt(risk*n*microMultiplier(),2)+' antes de taxas/slippage.';}if(symbol()==='WIN'){$('target1').textContent=fmt(price+sign*300);$('target2').textContent=fmt(price+sign*400)}}
$('breakLevel').textContent=fmt(level,d);$('flowNarrative').textContent='Agressão '+side.toLowerCase()+' · delta '+fmt(delta)+' · deslocamento '+(aligned?'alinhado':'não confirmado')+' · '+fmt(rate,1)+' negócios/s.';
$('reason').textContent=!fresh?'Feed atrasado: nova entrada bloqueada.':!hasEnough?'Amostra insuficiente de negócios.':!riskValid?'Stop técnico supera limite de '+fmt(limit)+' pontos WIN.':stage==='CONFIRMADO'?'Rompimento de '+fmt(sign>0?buyTrigger:sellTrigger,d)+' com pressão e deslocamento alinhados.':stage==='ANTECIPADO'?'Pressão emergente: aguardar rompimento da região de '+(sign>0?(buyTrigger===null?'compra':fmt(buyTrigger,d)):(sellTrigger===null?'venda':fmt(sellTrigger,d)))+'.':'Aguardar Delta recente acelerando, deslocamento do preço, DI1 e risco válido.';
$('intelligence').textContent='Leitura local de fluxo: delta '+fmt(delta)+', desequilíbrio '+fmt(imbal*100,1)+'%, velocidade '+fmt(rate,1)+'/s, deslocamento '+fmt(move,d)+', '+(triggerBroke?'rompimento observado':'nível não rompido')+'. Sem identificação de instituições; nenhuma IA treinada conectada.';
$('feedAge').textContent=(source==='live'?'WSS':source==='csv'?'CSV REPLAY':'DEMO')+' · negócio '+new Date(now).toLocaleTimeString('pt-BR')+(source==='live'?' · idade '+fmt((Date.now()-now)/1000,1)+'s':'');
let changed=false;for(const alert of history){if(alert.symbol!==symbol()||alert.source!==$('source').value)continue;const origin=Date.parse(alert.time),age=source==='csv'?now-origin:Date.now()-origin; if(age>=5000&&alert.after5===null&&alert.after5!==undefined){alert.after5=null;} if(source!=='csv'&&age>=5000&&alert.after5===null){alert.after5=Math.round((price-alert.price)*100)/100;changed=true;}if(source!=='csv'&&age>=30000&&alert.after30===null){alert.after30=Math.round((price-alert.price)*100)/100;changed=true;}}if(changed){try{localStorage.setItem(KEY,JSON.stringify(history))}catch{}renderAlerts()}const measured=history.filter(a=>a.symbol===symbol()&&a.after30!==null&&a.after30!==undefined);$('outcomeSummary').textContent=measured.length?'Sinais com 30s observados: '+measured.length+' · movimento bruto posterior, sem custo ou classificação de acerto.':'Sem avaliações de 30 segundos completas. Replay CSV não é avaliação fiel.';
updateHealth(source,now,qualityOK,diFresh);
const tf=$('timeframes');tf.replaceChildren();for(const [name,ms] of [['1m',60000],['5m',300000],['15m',900000],['30m',1800000],['Dia',86400000]]){const t=calc(now,ms),el=document.createElement('div');el.className='tfi';const head=document.createElement('small');head.textContent=name;const bold=document.createElement('b');bold.textContent=t.arr.length?fmt(t.delta):'—';bold.className=t.delta>0?'up':t.delta<0?'down':'neutral';const foot=document.createElement('small');foot.textContent=t.arr.length?(t.span>=ms*.8?'janela ok':'parcial'):'sem dados';el.append(head,bold,foot);tf.append(el)}
if(triggerBroke&&hasEnough&&!breakout)breakout={sign,level:sign>0?buyTrigger:sellTrigger,at:now};if(breakout&&now-breakout.at<30000&&((breakout.sign>0&&price<breakout.level-c.tick)||(breakout.sign<0&&price>breakout.level+c.tick))){if(Date.now()-lastAlert>2500){log('FALSO ROMPIMENTO',breakout.sign>0?'COMPRA':'VENDA',score,'Retorno para dentro do nível');lastAlert=Date.now()}breakout=null}
if(lastStage==='CONFIRMADO'&&stage!=='CONFIRMADO'&&Date.now()-lastAlert>2500){log('INVALIDADO',side,score,'Perda das condições de confirmação');lastAlert=Date.now()}if((stage==='ANTECIPADO'||stage==='CONFIRMADO')&&stage!==lastStage&&Date.now()-lastAlert>2500){log(stage,side,score,stage==='ANTECIPADO'?'Pré-alerta: pressão emergente':'Preço e agressão alinhados após rompimento');lastAlert=Date.now()}lastStage=stage;
}
function updateHealth(source,now,qualityOK,diFresh){const age=Date.now()-now;const live=source==='live',demo=source==='demo';$('healthWin').textContent=live?(age<=3000?'Recebendo · '+Math.round(age)+' ms':'Atrasado'):demo?'DEMO sintética':'CSV histórico';$('healthDI').textContent=symbol()!=='WIN'?'Não aplicável':demo?(diFresh?'DI1 fictício':'Aguardando DI1 demo'):source==='csv'?'Não fornecido no CSV':diFresh?'DI1 recente':'Ausente / atrasado';$('healthBook').textContent='Não integrado';$('healthQuality').textContent=qualityOK?'Critérios OK':'Sinais bloqueados';$('healthDetail').textContent='Fonte '+source.toUpperCase()+' · sem book real · DI1 e negócios exigem sincronia. Testes de interface não validam estratégia financeira.';}
function runSelfTest(){const synthetic=[{label:'pressão compradora',buy:850,sell:150,move:20,rateDelta:-.02,expected:1},{label:'pressão vendedora',buy:120,sell:880,move:-20,rateDelta:.02,expected:-1},{label:'absorção possível',buy:850,sell:150,move:0,rateDelta:-.02,expected:0},{label:'DI divergente',buy:800,sell:200,move:15,rateDelta:.02,expected:0}];const outcomes=synthetic.map(x=>{const sign=Math.sign(x.buy-x.sell),aligned=Math.sign(x.move)===sign&&x.move!==0,interest=Math.sign(x.rateDelta)===-sign;return {label:x.label,result:aligned&&interest?sign:0,expected:x.expected}});const passed=outcomes.filter(x=>x.result===x.expected).length;$('selfTestResult').textContent=passed+'/'+outcomes.length+' casos de regra OK (não é backtest)';$('selfTestResult').className=passed===outcomes.length?'up':'down';}
$('selfTest').onclick=runSelfTest;
function demo(){
 const t=Date.now(),elapsed=(t-demoStart)/1000,phase=elapsed%40;
 // 0-13s referência normal; 13-20s pressão compradora; 20-26s estabilização;
 // 26-33s pressão vendedora; 33-40s estabilização.
 const burstBuy=phase>=13&&phase<20,burstSell=phase>=26&&phase<33,burst=burstBuy||burstSell;
 const favored=burstBuy?'buy':burstSell?'sell':'';
 const side=favored?(rng()<.96?favored:(favored==='buy'?'sell':'buy')):(rng()<.5?'buy':'sell');
 const size=burst?70+Math.floor(rng()*95):7+Math.floor(rng()*15);
 const tick=config[symbol()].tick;
 // DI1 fictício: direcionado em sentido inverso apenas durante a pressão;
 // nunca é apresentado como valor observado na B3.
 if(symbol()==='WIN'&&(!diTicks.length||t-diTicks[diTicks.length-1].timestamp>=750)){
  const d=burstBuy?-.012:burstSell?.012:(rng()-.5)*.002;
  diRate=Math.round((diRate+d)*1000)/1000;
  ingestDI({symbol:'DI1-DEMO',rate:diRate,timestamp:t},'demo');
 }
 const step=burst?(side==='buy'?1:-1)*(rng()<.92?2:1)*tick:(rng()<.48?(side==='buy'?1:-1)*tick:0);
 price=Math.round((price+step)/tick)*tick;
 ingest({timestamp:t,price,size,side,symbol:symbol()},'demo');
 $('demoPhase').textContent=burstBuy?'Cenário: agressão compradora extraordinária + DI1 em queda':burstSell?'Cenário: agressão vendedora extraordinária + DI1 em alta':'Cenário: formando volume normal de referência';
}
function parseCSV(text){const lines=text.replace(/^\uFEFF/,'').trim().split(/\r?\n/);if(lines.length<2||lines.length>100001)throw Error('CSV inválido ou limite de 100 mil linhas');const sep=lines[0].includes(';')?';':',';const headers=lines.shift().split(sep).map(x=>x.trim().toLowerCase());for(const h of ['timestamp','price','size','side','symbol'])if(!headers.includes(h))throw Error('Coluna ausente: '+h);const out=[];for(const row of lines){const values=row.split(sep),obj=Object.fromEntries(headers.map((h,i)=>[h,values[i]?.trim()])),t=normalize(obj,true);if(t)out.push(t)}return out.sort((a,b)=>a.timestamp-b.timestamp)}
$('source').onchange=()=>{stop();$('csvWrap').classList.toggle('hidden',$('source').value!=='csv');$('wsWrap').classList.toggle('hidden',$('source').value!=='ws')};$('instrument').onchange=reset;$('level').onchange=()=>{breakout=null;$('breakLevel').textContent=fmt(Number($('level').value),symbol()==='WIN'?0:2)};$('reset').onclick=reset;$('stop').onclick=stop;
$('start').onclick=async()=>{reset();const mode=$('source').value;if(mode==='csv'){const file=$('file').files[0];if(!file){$('status').textContent='Selecione o CSV';return}if(file.size>12000000){$('status').textContent='CSV acima de 12 MB';return}try{play=parseCSV(await file.text());if(!play.length)throw Error('Nenhum negócio válido')}catch(e){$('status').textContent=e.message;return}}
if(mode==='ws'){const url=$('endpoint').value.trim();if(!/^wss:\/\//.test(url)){$('status').textContent='Informe wss:// válido';return}try{ws=new WebSocket(url);ws.onopen=()=>{ws.send(JSON.stringify({type:'subscribe',symbol:symbol()}));if(symbol()==='WIN')ws.send(JSON.stringify({type:'subscribe',symbol:'DI1'}));else if(isGold())for(const macroSymbol of macroSymbols)ws.send(JSON.stringify({type:'subscribe',symbol:macroSymbol}));else if(isIndexFuture()){if(symbol()==='MNQ')ws.send(JSON.stringify({type:'subscribe',symbol:'NQ'}));for(const k of nqCorrelates)ws.send(JSON.stringify({type:'subscribe',symbol:k}));}$('status').textContent='Conectado; aguardando feed'};ws.onmessage=e=>{try{let items=JSON.parse(e.data);if(!Array.isArray(items))items=[items];for(const x of items){if(ingestNQMacro(x,'live'))continue;if(ingestMacro(x,'live'))continue;if(String(x.symbol||'').toUpperCase().startsWith('DI1'))ingestDI(x,'live');else ingest(x,'live')}}catch{}};ws.onerror=()=>{$('status').textContent='Erro de conexão'};ws.onclose=()=>{if(running)stop()}}catch{$('status').textContent='Falha WSS';return}}
running=true;$('start').disabled=true;$('stop').disabled=false;$('status').textContent=mode==='demo'?'Simulando':mode==='csv'?'Reproduzindo CSV':'Conectando WSS';if(mode==='demo')timer=setInterval(demo,140);else if(mode==='csv')timer=setInterval(()=>{if(cursor>=play.length){stop();$('status').textContent='Replay concluído';return}for(let i=0;i<8&&cursor<play.length;i++){const t=play[cursor++];trades.push(t);price=t.price}render('csv')},140);else timer=setInterval(()=>{if(trades.length&&Date.now()-lastIngest>3000){$('healthWin').textContent='Feed atrasado';$('healthQuality').textContent='Sinais bloqueados';$('stage').textContent='BLOQUEADO · FEED';$('signal').textContent='SEM ENTRADA';for(const id of ['entry','stopPrice','risk'])$(id).textContent='—';$('status').textContent='Feed atrasado'}},1000)};
$('clear').onclick=()=>{if(!confirm('Apagar alertas deste navegador?'))return;history=[];try{localStorage.removeItem(KEY)}catch{}renderAlerts()};$('export').onclick=()=>{const rows=[['timestamp','symbol','source','stage','side','price','score','reason'],...history.map(a=>[a.time,a.symbol,a.source,a.stage,a.side,a.price,a.score,a.why])],csv=rows.map(r=>r.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv'})),a=document.createElement('a');a.href=url;a.download='flow-ai-v3-alertas.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
renderAlerts();reset();
})();