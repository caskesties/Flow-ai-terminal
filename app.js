'use strict';(()=>{
const $=id=>document.getElementById(id),fmt=(n,d=0)=>Number(n).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d}),KEY='flow-ai-v3-alerts';
let reconnectAttempt=0,reconnectTimer=null;
let pushPublicKey='';
let resumeConnection=false;
let gcReference={trades:[],last:0};
let history=[];try{history=JSON.parse(localStorage.getItem(KEY)||'[]');if(!Array.isArray(history))history=[]}catch{}
let fibSnapshot=null;let demoStart=Date.now(),trades=[],play=[],cursor=0,timer=null,ws=null,seed=1217,price=132400,lastStage='',lastAlert=0,breakout=null,running=false,lastIngest=0,buyTrigger=null,sellTrigger=null,zoneRefreshAt=0,diTicks=[],diRate=13.25,treasuryTicks=[],treasuryQuoteTicks=[],treasuryTradeTicks=[],lastEarly=0,absZone=null,absLastAlert=0,seenIds=new Set(),rejected=0;
const config={WIN:{tick:5,start:132400},GC:{tick:.1,start:2650},MGC:{tick:.1,start:2650},NQ:{tick:.25,start:24500},MNQ:{tick:.25,start:24500}};
const symbol=()=>$('instrument').value;function rng(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296}
function log(stage,side,score,why){const a={id:Date.now()+'-'+Math.round(Math.random()*1e6),status:'PENDENTE',after5:null,after30:null,time:new Date().toISOString(),symbol:symbol(),source:$('source').value,stage,side,score,price,why};history.unshift(a);history=history.slice(0,200);try{localStorage.setItem(KEY,JSON.stringify(history))}catch{}renderAlerts()}
function renderAlerts(){const root=$('events');root.replaceChildren();if(!history.length){root.textContent='Nenhum alerta.';return}for(const a of history.slice(0,22)){const el=document.createElement('div');el.className='event '+(/FALSO|INVALIDADO|REVERSÃO/.test(a.stage)?'bad':a.stage==='CONFIRMADO'?'good':'');const title=document.createElement('b');title.textContent=a.stage+' · '+a.side+' · '+a.symbol+' · '+a.source.toUpperCase();const detail=document.createElement('p');detail.className='muted';detail.textContent=new Date(a.time).toLocaleTimeString('pt-BR')+' · '+fmt(a.price,2)+' · '+a.score+'/100 · '+a.why+' · 5s: '+(a.after5===null||a.after5===undefined?'PENDENTE':fmt(a.after5,2))+' · 30s: '+(a.after30===null||a.after30===undefined?'PENDENTE':fmt(a.after30,2))+' · Avaliação servidor: '+(a.outcomes?Object.entries(a.outcomes).map(([k,v])=>k+'s '+fmt(v.move,2)+' (fav '+fmt(v.favorable,2)+' / contr '+fmt(v.adverse,2)+(v.flag==='OBSERVED'?'':'; LACUNA')+')').join(' | '):'pendente');el.append(title,detail);root.append(el)}}
function stop(){if(reconnectTimer){clearTimeout(reconnectTimer);reconnectTimer=null}running=false;if(timer)clearInterval(timer);timer=null;if(ws){ws.onclose=null;ws.close();ws=null}$('start').disabled=false;$('stop').disabled=true;$('status').textContent='Pausado'}
function reset(){gcReference={trades:[],last:0};if($('gcRefInfo'))$('gcRefInfo').textContent='Aguardando negócios '+(symbol()==='MNQ'?'NQ':'GC');for(const id of ['shortDelta','shortAcceleration','shortMove','shortConfluence'])if($(id))$(id).textContent='Aguardando dados';stop();demoStart=Date.now();trades=[];play=[];cursor=0;fibSnapshot=null;breakout=null;buyTrigger=null;sellTrigger=null;zoneRefreshAt=0;diTicks=[];diRate=13.25;treasuryTicks=[];treasuryQuoteTicks=[];treasuryTradeTicks=[];lastEarly=0;seenIds.clear();rejected=0;lastStage='';lastAlert=0;price=config[symbol()].start;$('instrumentLabel').textContent=symbol()+' · '+(symbol()==='WIN'?'Mini índice':symbol()==='NQ'||symbol()==='MNQ'?'Nasdaq futuro':'Ouro futuro');$('level').value=symbol()==='WIN'?'132480':symbol()==='NQ'||symbol()==='MNQ'?'':'';$('level').step=config[symbol()].tick;$('maxStop').value=symbol()==='WIN'?'200':'';$('maxStop').step=config[symbol()].tick;$('maxStop').max=symbol()==='WIN'?'200':'';$('breakLevel').textContent=$('level').value?fmt(Number($('level').value),symbol()==='WIN'?0:2):'Sem nível validado';$('price').textContent=fmt(price,symbol()==='WIN'?0:2);for(const id of ['delta','volume','rate','score','entry','stopPrice','risk','target1','target2'])$(id).textContent='—';$('signal').textContent='AGUARDAR';$('signal').className='signal neutral';$('heroDelta').textContent='—';$('heroDelta').className='neutral';$('heroDeltaTrend').textContent='Aguardando fluxo';$('stage').textContent='OBSERVAÇÃO';$('reason').textContent='Aguardando negócios.';$('confidence').textContent='Força heurística: —';$('timeframes').textContent='Aguardando dados';$('buyBar').style.width='50%';$('sellBar').style.width='50%';$('buyPct').textContent='50%';$('sellPct').textContent='50%';$('feedAge').textContent='Sem dados';$('sourceTag').textContent='DEMO · ARTIFICIAL';$('healthWin').textContent='Desconectado';$('healthDI').textContent='Desconectado';$('healthBook').textContent='Não integrado';$('healthQuality').textContent='Aguardando';$('demoPhase').textContent='Cenário fictício disponível — clique em Iniciar';$('absZone').textContent='Aguardando negócios';$('absStatus').textContent='Sem evidência suficiente.';$('absDirection').textContent='Direção: aguardando confirmação.';$('diStatus').textContent='DI1 aguardando';$('burstStatus').textContent='Aguardando dados';$('confluence').textContent='Sem confirmação';$('buyTrigger').textContent='Aguardando dados';$('sellTrigger').textContent='Aguardando dados';$('buyZoneCard').className='zone';$('sellZoneCard').className='zone';$('triggerInfo').textContent='Coletando histórico para delimitar suporte e resistência; sem gatilhos ativos.';$('heroFibo').textContent='—';$('heroFiboDetail').textContent='30m / 60m · aguardando';$('fibStatus').textContent='Aguardando histórico de preços';$('fibLevels').textContent='—';$('fibDirection').textContent='Sem pivôs identificados';}
function normalize(m,archive=false){if(!m||typeof m!=='object'||String(m.symbol||'').toUpperCase()!==symbol())return null;const price=Number(m.price),size=Number(m.size),side=String(m.side||'').toLowerCase();let timestamp=typeof m.timestamp==='number'?m.timestamp:/^\d+$/.test(String(m.timestamp))?Number(m.timestamp):Date.parse(m.timestamp);if(timestamp<1e11)timestamp*=1000;if(!Number.isFinite(timestamp)||!Number.isFinite(price)||price<=0||!Number.isSafeInteger(size)||size<=0||size>1000000||!['buy','sell'].includes(side))return null;if(!archive&&(timestamp>Date.now()+5000||timestamp<Date.now()-60000))return null;return {timestamp,price,size,side}}
function ingestDI(m,source){if(symbol()!=='WIN'||!m||String(m.symbol||'').toUpperCase().indexOf('DI1')!==0)return;const rate=Number(m.rate),ts=typeof m.timestamp==='number'?m.timestamp:Date.parse(m.timestamp);const timestamp=ts<1e11?ts*1000:ts;if(!Number.isFinite(rate)||rate<0||rate>100||!Number.isFinite(timestamp))return;if(source==='live'&&(Date.now()-timestamp>3000||timestamp>Date.now()+5000))return;if(diTicks.length&&timestamp<diTicks[diTicks.length-1].timestamp)return;diTicks.push({timestamp,rate});diTicks=diTicks.filter(x=>x.timestamp>=timestamp-30000).slice(-1000);diRate=rate;}
// ZN = Treasury Note futures PRICE (inverse of yield); US10Y = yield in percent.
function ingestTreasury(m,source){
 const sym=String(m?.symbol||'').toUpperCase();
 if(!['ZN','US10Y'].includes(sym))return;
 let ts=typeof m.timestamp==='number'?m.timestamp:Date.parse(m.timestamp);
 if(ts<1e11)ts*=1000;
 const value=Number(sym==='ZN'?m.price:m.rate);
 if(!Number.isFinite(value)||value<=0||!Number.isFinite(ts))return;
 if(source==='live'&&(Date.now()-ts>10000||ts>Date.now()+5000))return;
 const prior=treasuryTicks[treasuryTicks.length-1];
 if(prior&&ts<prior.timestamp)return;
 if(prior&&prior.symbol!==sym)treasuryTicks=[];
 const tick={symbol:sym,timestamp:ts,value,source:String(m.source||'unknown')};
 treasuryTicks.push(tick);
 treasuryTicks=treasuryTicks.filter(t=>t.timestamp>=ts-210000).slice(-5000);
 const target=tick.source.toLowerCase().includes('bbo')?treasuryQuoteTicks:treasuryTradeTicks;
 target.push(tick);
 treasuryQuoteTicks=treasuryQuoteTicks.filter(t=>t.timestamp>=ts-60000).slice(-10000);
 treasuryTradeTicks=treasuryTradeTicks.filter(t=>t.timestamp>=ts-60000).slice(-3000);
}
function ingest(m,source){const t=normalize(m,source==='csv');if(!t){rejected++;return;}const id=String(m.trade_id??m.id??'');if(id){if(seenIds.has(id))return;seenIds.add(id);if(seenIds.size>15000)seenIds.clear();}if(trades.length&&t.timestamp<trades[trades.length-1].timestamp-1000)return;trades.push(t);if(trades.length>65000)trades.splice(0,8000);price=t.price;lastIngest=Date.now();render(source);if(source==='live')scheduleFocusRefresh();if(source==='live'&&running&&ws?.readyState===WebSocket.OPEN)$('status').textContent='Recebendo '+symbol()+' · último negócio '+new Date(t.timestamp).toLocaleTimeString('pt-BR')}
function calc(now,windowMs){const arr=trades.filter(t=>t.timestamp>=now-windowMs);let b=0,s=0;for(const t of arr)t.side==='buy'?b+=t.size:s+=t.size;return {arr,b,s,volume:b+s,delta:b-s,span:arr.length>1?now-arr[0].timestamp:0}}
function render(source){if(!trades.length)return;const now=trades[trades.length-1].timestamp,c=config[symbol()],d=symbol()==='WIN'?0:2,w=calc(now,60000),{b,s,volume,delta,span,arr}=w;const percent=volume?Math.round(b/volume*100):50,sign=Math.sign(delta),move=price-arr[0].price,aligned=sign!==0&&Math.sign(move)===sign,rate=arr.length/Math.max(1,span/1000),imbal=volume?Math.abs(delta)/volume:0,level=$('level').value.trim()?Number($('level').value):NaN,broke=Number.isFinite(level)&&(sign>0?price>level:sign<0?price<level:false),hasEnough=arr.length>=24&&span>=5000&&volume>=40,fresh=source!=='live'||Date.now()-now<=3000;
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
// Structural Fibonacci: only 30m/60m swing extrema from historical trade coverage.
// Prior session and additional validated pivots require a complete history service;
// never synthesize previous-session levels from a short mobile buffer.
const fibReference=(minutes)=>{
 const until=now-5000,from=until-minutes*60000;
 const a=trades.filter(t=>t.timestamp>=from&&t.timestamp<=until);
 if(a.length<70||a[a.length-1].timestamp-a[0].timestamp<minutes*60000*.8)return null;
 const bars=new Map();
 for(const t of a){const k=Math.floor(t.timestamp/60000),old=bars.get(k);if(!old)bars.set(k,{time:k,high:t.price,low:t.price});else{old.high=Math.max(old.high,t.price);old.low=Math.min(old.low,t.price);}}
 const v=[...bars.values()].sort((p,q)=>p.time-q.time);
 if(v.length<minutes*.6)return null;
 const pivots=[];
 for(let i=2;i<v.length-2;i++){
   if(v[i].high>Math.max(v[i-2].high,v[i-1].high,v[i+1].high,v[i+2].high))pivots.push({time:v[i].time,price:v[i].high,type:'H'});
   if(v[i].low<Math.min(v[i-2].low,v[i-1].low,v[i+1].low,v[i+2].low))pivots.push({time:v[i].time,price:v[i].low,type:'L'});
 }
 pivots.sort((p,q)=>p.time-q.time);
 // Consider latest completed, meaningful pivot-to-pivot leg (no lookahead beyond available bars).
 let best=null;
 for(let i=0;i<pivots.length;i++)for(let j=i+1;j<pivots.length;j++){
  const p=pivots[i],q=pivots[j],span=Math.abs(q.price-p.price);
  if(p.type===q.type||span<c.tick*20)continue;
  if(!best||q.time>best.to.time||(q.time===best.to.time&&span>best.span))best={from:p,to:q,span};
 }
 if(!best)return null;
 const up=best.from.type==='L',base=best.to.price,dir=up?-1:1;
 return {at:now,period:minutes+'m',up,low:Math.min(best.from.price,best.to.price),high:Math.max(best.from.price,best.to.price),span:best.span,levels:[.382,.5,.618,.786].map(r=>({ratio:r,value:Math.round((base+dir*best.span*r)/c.tick)*c.tick}))};
};
if(!fibSnapshot||now-fibSnapshot.at>=30000){
 const candidates=[fibReference(60),fibReference(30)].filter(Boolean);
 fibSnapshot=candidates[0]||null;
}
let fibNear=null;
if(fibSnapshot){
 fibNear=fibSnapshot.levels.reduce((best,x)=>!best||Math.abs(price-x.value)<Math.abs(price-best.value)?x:best,null);
 const fib50=fibSnapshot.levels.find(x=>x.ratio===.5).value,fib618=fibSnapshot.levels.find(x=>x.ratio===.618).value;
 const inPriority=price>=Math.min(fib50,fib618)-c.tick&&price<=Math.max(fib50,fib618)+c.tick;
 $('heroFibo').textContent=inPriority?'50–61,8%':fmt(fibNear.ratio*100,1)+'%';
 $('heroFiboDetail').textContent=fibSnapshot.period+' · '+(fibSnapshot.up?'alta':'baixa')+(inPriority?' · ZONA PRIORITÁRIA':' · nível próximo');
 $('fibDirection').textContent=fibSnapshot.period+' · '+(fibSnapshot.up?'Impulso de alta':'Impulso de baixa')+' · '+fmt(fibSnapshot.low,d)+' → '+fmt(fibSnapshot.high,d);
 $('fibLevels').textContent=fibSnapshot.levels.map(x=>fmt(x.ratio*100,1)+'% '+fmt(x.value,d)).join(' · ');
 $('fibStatus').textContent=(inPriority?'ZONA PRIORITÁRIA 50–61,8% · ':'Fora da zona prioritária · ')+'nível próximo '+fmt(fibNear.ratio*100,1)+'% em '+fmt(fibNear.value,d)+' · sessão anterior: dados não integrados';
}else{
 $('heroFibo').textContent='—';
 $('heroFiboDetail').textContent='30m / 60m · sem histórico validado';
 $('fibDirection').textContent='Aguardando pivôs estruturais de 30 ou 60 minutos';
 $('fibLevels').textContent='—';
 $('fibStatus').textContent='Sessão anterior e topos/fundos adicionais exigem histórico persistente; níveis indisponíveis até lá';
}
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
$('filterState').textContent='Qualidade: '+(qualityOK?'OK':'BLOQUEADA')+' · '+(symbol()==='NQ'||symbol()==='MNQ'?(treasuryTicks.length&&Math.abs(Date.now()-treasuryTicks[treasuryTicks.length-1].timestamp)<=10000?'Treasury: preço ZN recente; direção não garantida':'Treasury: ausente ou atrasado'):symbol()==='GC'||symbol()==='MGC'?'juros: não aplicável neste filtro':'DI1: '+(diFresh?'sincronizado':'ausente/fora de sincronia'))+' · referência curta: 12s (picos); histórico comparativo: '+(trades.length>1?Math.max(0,Math.round((trades[trades.length-1].timestamp-trades[0].timestamp)/1000)):0)+'s recebidos (mín. 120s válidos); histórico por horário indisponível'+' · rejeitados: '+rejected;
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
const quickRisk=()=>{if(symbol()!=='WIN')return true;const cap=Number($('maxStop').value);if(!Number.isFinite(cap)||cap<=0)return false;const a=trades.filter(t=>t.timestamp>=now-5000),swing=shortSign>0?Math.min(...a.map(t=>t.price)):Math.max(...a.map(t=>t.price));return a.length>1&&Math.abs(price-swing)+2*c.tick<=cap;};
const shortConfluence=hasEnough&&qualityOK&&strongShort&&accelerating&&shortAligned&&diShortOK&&quickRisk();
$('shortDelta').textContent='1s '+(f1.delta>=0?'+':'')+fmt(f1.delta)+' · 3s '+(f3.delta>=0?'+':'')+fmt(f3.delta)+' · 5s '+(f5.delta>=0?'+':'')+fmt(f5.delta);
$('shortAcceleration').textContent=(acceleration>0?'+':'')+fmt(acceleration)+' contratos (3s atual − 3s anterior)';
$('shortMove').textContent=(localMove>0?'+':'')+fmt(localMove,d)+' '+(symbol()==='WIN'||symbol()==='NQ'||symbol()==='MNQ'?'pts':'USD/oz');
$('shortConfluence').textContent=shortConfluence?'CONFLUÊNCIA EXPERIMENTAL '+(shortSign>0?'COMPRADORA':'VENDEDORA'):'AGUARDAR — '+(!qualityOK?'qualidade dos dados':!strongShort?'agressão recente insuficiente':!accelerating?'sem aceleração':!shortAligned?'preço não acompanha':!diShortOK?'DI1 não confirma':'risco acima do limite');
$('shortConfluence').className=shortConfluence?(shortSign>0?'up':'down'):'muted';
// Nasdaq bidirectional rate + aggressive flow filter. This is NOT order execution.
// Compare recent 5s of directional aggressive volume per second with prior 3 min,
// excluding the latest 5s. Only generate signals with synchronized live rate proxy.
const isNasdaq=symbol()==='NQ'||symbol()==='MNQ';
const treasuryLast=treasuryTicks[treasuryTicks.length-1];
const treasuryFresh=!!treasuryLast&&Math.abs(now-treasuryLast.timestamp)<=10000&&(source!=='live'||Date.now()-treasuryLast.timestamp<=10000);
// ZN movement is quantized: many fresh quotes have the same midpoint.
// Require a real, recent change, not simply a fresh repeated quote.
const treasurySeries=treasuryLast?.symbol==='ZN'?(treasuryQuoteTicks.length>=2&&now-treasuryQuoteTicks[treasuryQuoteTicks.length-1].timestamp<=10000?treasuryQuoteTicks:treasuryTradeTicks):treasuryTicks;
const treasurySeriesLast=treasurySeries[treasurySeries.length-1];
const treasurySeriesFresh=!!treasurySeriesLast&&now-treasurySeriesLast.timestamp<=10000;
const treasuryWindows=[2000,5000,10000,20000,30000].map(ms=>{
  const candidates=treasurySeriesLast?treasurySeries.filter(t=>t.timestamp<treasurySeriesLast.timestamp&&treasurySeriesLast.timestamp-t.timestamp>=ms*.75&&treasurySeriesLast.timestamp-t.timestamp<=ms*1.25):[];
  const previous=candidates.reduce((best,t)=>!best||Math.abs(treasurySeriesLast.timestamp-t.timestamp-ms)<Math.abs(treasurySeriesLast.timestamp-best.timestamp-ms)?t:best,null);
  const change=previous?treasurySeriesLast.value-previous.value:NaN;
  const threshold=treasuryLast?.symbol==='ZN'?.015625:.002;
  return {ms,change,valid:!!previous,previous,age:previous?treasurySeriesLast.timestamp-previous.timestamp:NaN,
    direction:Number.isFinite(change)&&Math.abs(change)>=threshold?Math.sign(change):0};
});
const treasuryChanges=treasurySeries.filter((t,i,a)=>i>0&&t.symbol===a[i-1].symbol&&Math.abs(t.value-a[i-1].value)>=.0000001);
const lastEffectiveChange=treasuryChanges[treasuryChanges.length-1];
const changeAge=lastEffectiveChange?now-lastEffectiveChange.timestamp:Infinity;
const directionalWindows=treasuryWindows.filter(w=>w.ms>=5000&&w.direction!==0);
const contradictory=directionalWindows.some(w=>w.direction!==directionalWindows[0]?.direction);
// A directional vote needs agreeing 5/10-second windows OR 20/30-second windows.
// Stale effective changes and contradictory windows never authorize confluence.
const shortVotes=directionalWindows.filter(w=>w.ms<=10000);
const longerVotes=directionalWindows.filter(w=>w.ms>=20000);
const shortConfirmed=shortVotes.length===2&&shortVotes[0].direction===shortVotes[1].direction;
const longerConfirmed=longerVotes.length===2&&longerVotes[0].direction===longerVotes[1].direction;
// Two consistent windows are preferred. A single 20/30s directional window
// is allowed only if an independent most-recent price-change vote agrees,
// the ZN is fresh, and price has not reversed since that effective change.
const previousChange=lastEffectiveChange?treasurySeries.find((t,i,a)=>i>0&&t.timestamp===lastEffectiveChange.timestamp&&Math.abs(t.value-a[i-1].value)>=.0000001):null;
const previousChangeIndex=previousChange?treasurySeries.indexOf(previousChange):-1;
const lastChangeSign=previousChangeIndex>0?Math.sign(treasurySeries[previousChangeIndex].value-treasurySeries[previousChangeIndex-1].value):0;
const sustainedWindow=longerVotes.length===1&&lastChangeSign===longerVotes[0].direction&&changeAge<=30000;
const directionEligible=treasuryFresh&&treasurySeriesFresh&&!contradictory&&
  ((changeAge<=15000&&(shortConfirmed||longerConfirmed))||sustainedWindow);
const treasuryPriceDirection=directionEligible?
  (shortConfirmed?shortVotes[0].direction:longerConfirmed?longerVotes[0].direction:longerVotes[0].direction):0;
const yieldDirection=treasuryLast?.symbol==='ZN'?-treasuryPriceDirection:treasuryPriceDirection;
const treasuryMovementState=!treasuryFresh||!treasurySeriesFresh?'DADOS ATRASADOS':
 !lastEffectiveChange?'SEM ALTERACAO EFETIVA':
 changeAge>30000?'ULTIMA MUDANCA ANTIGA':
 contradictory?'JANELAS CONTRADITORIAS':
 yieldDirection===0?'MOVIMENTO INCONCLUSIVO':'DIRECAO CONFIRMADA';
const treasuryDirectionDiagnostics='fonte '+(treasurySeries===treasuryQuoteTicks?'midpoint':'negocios')+' · ultima mudanca '+(Number.isFinite(changeAge)?fmt(changeAge/1000,1)+'s':'indisponivel')+' · votos '+treasuryWindows.map(w=>w.ms/1000+'s '+(w.direction>0?'alta':w.direction<0?'queda':w.valid?'neutro':'sem base')).join(', ')+' · motivo '+treasuryMovementState;
const recentNasdaq=trades.filter(t=>t.timestamp>now-5000);
const priorNasdaq=trades.filter(t=>t.timestamp<=now-5000&&t.timestamp>now-185000);
const nasdaqBuy=recentNasdaq.reduce((v,t)=>v+(t.side==='buy'?t.size:0),0);
const nasdaqSell=recentNasdaq.reduce((v,t)=>v+(t.side==='sell'?t.size:0),0);
const priorBuy=priorNasdaq.reduce((v,t)=>v+(t.side==='buy'?t.size:0),0);
const priorSell=priorNasdaq.reduce((v,t)=>v+(t.side==='sell'?t.size:0),0);
const priorSpan=priorNasdaq.length>1?priorNasdaq[priorNasdaq.length-1].timestamp-priorNasdaq[0].timestamp:0;
const nasdaqBuyRatio=priorSpan>=120000&&priorBuy>0?(nasdaqBuy/5)/(priorBuy/(priorSpan/1000)):NaN;
const nasdaqSellRatio=priorSpan>=120000&&priorSell>0?(nasdaqSell/5)/(priorSell/(priorSpan/1000)):NaN;
const nasdaqShare=(nasdaqBuy+nasdaqSell)>0?Math.max(nasdaqBuy,nasdaqSell)/(nasdaqBuy+nasdaqSell):0;
const nasdaqDirection=nasdaqBuy>nasdaqSell?1:nasdaqSell>nasdaqBuy?-1:0;
const nasdaqRatio=nasdaqDirection>0?nasdaqBuyRatio:nasdaqSellRatio;
const nasdaqRateOK=!isNasdaq||(yieldDirection!==0&&yieldDirection===-nasdaqDirection);
const nasdaqBurstOK=!isNasdaq||(priorSpan>=120000&&Number.isFinite(nasdaqRatio)&&nasdaqRatio>=1.8&&nasdaqShare>=.60&&nasdaqDirection!==0);
const nasdaqAligned=!isNasdaq||(nasdaqDirection===sign&&nasdaqRateOK&&nasdaqBurstOK);
if(isNasdaq){
 $('diStatus').textContent=!treasuryFresh?'ZN / US10Y ausente ou atrasado':(treasuryLast.symbol==='ZN'?'ZN PREÇO (proxy, não yield)':'US10Y yield')+' · atual '+fmt(treasuryLast.value,5)+' ('+treasuryLast.source+') · amostras '+treasuryTicks.length+' · ZN 60s: book '+treasuryQuoteTicks.length+' updates, '+new Set(treasuryQuoteTicks.map(t=>t.value.toFixed(6))).size+' preços distintos, '+treasuryQuoteTicks.filter((t,i,a)=>i>0&&t.value!==a[i-1].value).length+' mudanças de midpoint; negócios '+treasuryTradeTicks.length+', '+new Set(treasuryTradeTicks.map(t=>t.value.toFixed(6))).size+' preços distintos · '+treasuryWindows.map(w=>(w.ms/1000)+'s '+(w.valid?'anterior '+fmt(w.previous.value,5)+' Δ '+(w.change>=0?'+':'')+fmt(w.change,5)+' ('+fmt(w.age/1000,1)+'s)':'sem amostra')).join(' · ')+' · '+treasuryDirectionDiagnostics+' · '+(yieldDirection<0?'yield proxy em queda':yieldDirection>0?'yield proxy em alta':'sem direcao confirmada');
 const coverageSec=Math.round(priorSpan/1000); const totalSec=trades.length>1?Math.round((trades[trades.length-1].timestamp-trades[0].timestamp)/1000):0;
  $('burstStatus').textContent=Number.isFinite(nasdaqRatio)?fmt(nasdaqRatio,2)+'× média agressora (base '+coverageSec+'s; '+priorNasdaq.length+' negócios)': 'Histórico '+totalSec+'s; base anterior '+coverageSec+'s / 120s mín. ('+priorNasdaq.length+' negócios)'+(priorSpan>=120000?' · volume por lado insuficiente':' · referência insuficiente');
 $('confluence').textContent=nasdaqAligned?'CONFLUÊNCIA NASDAQ + JUROS':!qualityOK?'Bloqueado: qualidade do feed':!treasuryFresh?'Bloqueado: Treasury ausente/atrasado':yieldDirection===0?'Aguardando direção confirmada do Treasury':priorSpan<120000?'Aguardando histórico comparativo ≥120s':!nasdaqBurstOK?'Aguardando agressão anormal ≥1,8× e predomínio ≥60%':nasdaqDirection!==sign?'Aguardando preço acompanhar agressão':'Aguardando confluência juros/agressão';
}
const diConfirmed=symbol()!=='WIN'||diAligned;
const impulse=rate>=2&&imbal>=.2&&aligned&&Math.abs(move)>=c.tick*2;
const early=hasEnough&&qualityOK&&abnormal&&diConfirmed&&burstSide===sign&&sign!==0&&shortConfluence&&nasdaqAligned;
const pre=hasEnough&&qualityOK&&impulse&&score>=52&&diConfirmed&&nasdaqAligned;
const confluenceEarly=shortConfluence&&shortSign===sign&&nasdaqAligned;
const confirmed=pre&&confluenceEarly&&triggerBroke&&score>=73&&nasdaqAligned;
if(!isNasdaq)$('diStatus').textContent=symbol()!=='WIN'?'Não se aplica ao ouro':!diFresh?'DI1 ausente ou atrasado':diDirection<0?'DI1 em queda ('+fmt(diDelta,3)+' p.p.)':diDirection>0?'DI1 em alta ('+fmt(diDelta,3)+' p.p.)':'DI1 sem direção relevante';
if(!isNasdaq)$('burstStatus').textContent=Number.isFinite(spikeRatio)?fmt(spikeRatio,1)+'× do volume normal · '+fmt(burstShare*100,0)+'% desequilíbrio':'Aguardando 8 janelas de referência';
if(!isNasdaq)$('confluence').textContent=source==='demo'?'DI e fluxo inteiramente simulados':symbol()!=='WIN'?'Filtro DI1 apenas no WIN':diAligned&&abnormal?'CONFLUÊNCIA: DI1 + pressão anormal':diFresh?'Sem confluência DI1 + fluxo':'SEM DI1: antecipação bloqueada';
if(early&&riskCheckQuick()&&now-lastEarly>=5000){log('PRÉ-ALERTA 2–3s (ALVO)',sign>0?'COMPRA':'VENDA',score,isNasdaq?'Agressão '+fmt(nasdaqRatio,2)+'× média 3min; juros em direção oposta; antecipação não garantida.':'Pressão '+fmt(spikeRatio,1)+'×; DI1 na direção oposta. Antecipação não garantida.');lastEarly=now;}

function riskCheckQuick(){if(symbol()!=='WIN')return true;const points=Math.ceil((Math.max(...trades.slice(-50).map(x=>x.price))-Math.min(...trades.slice(-50).map(x=>x.price)))/c.tick)*c.tick+2*c.tick;return points<=Math.min(200,Math.max(5,Number($('maxStop').value)||200));}
const last=trades.slice(-50),swing=sign>0?Math.min(...last.map(x=>x.price)):Math.max(...last.map(x=>x.price)),riskTicks=Math.ceil(Math.abs(price-swing)/c.tick)+2,risk=riskTicks*c.tick,limit=Number($('maxStop').value),riskValid=symbol()!=='WIN'||(Number.isFinite(limit)&&limit>0&&risk<=limit),side=sign>0?'COMPRA':sign<0?'VENDA':'NEUTRO';
let stage=confirmed?'CONFIRMADO':confluenceEarly?'CONFLUÊNCIA ANTECIPADA':early?'PRESSÃO ANORMAL':pre?'ANTECIPADO':'OBSERVAÇÃO';if(!riskValid&&stage!=='OBSERVAÇÃO')stage='BLOQUEADO · STOP';if(!qualityOK)stage='BLOQUEADO · QUALIDADE';if(isNasdaq&&!nasdaqAligned)stage='BLOQUEADO · JUROS/FLUXO';
$('price').textContent=fmt(price,d);$('sourceTag').textContent=source==='live'?(Date.now()-now>3000?'DADOS ATRASADOS':!qualityOK?'QUALIDADE BLOQUEADA':'WSS · CONECTADO'):source==='csv'?'REPLAY HISTÓRICO':'DEMO · ARTIFICIAL';$('priceHint').textContent=source==='live'?'Feed externo não auditado':source==='csv'?'Reprodução de CSV':'Preço sintético';$('buyPct').textContent=percent+'%';$('sellPct').textContent=100-percent+'%';$('buyBar').style.width=percent+'%';$('sellBar').style.width=100-percent+'%';$('delta').textContent=(delta>0?'+':'')+fmt(delta);$('heroDelta').textContent=(delta>0?'+':'')+fmt(delta);$('heroDelta').className=delta>0?'up':delta<0?'down':'neutral';$('heroDeltaTrend').textContent=delta>0?'Predomínio comprador':delta<0?'Predomínio vendedor':'Agressões equilibradas';$('delta').className=delta>0?'up':delta<0?'down':'neutral';$('volume').textContent=fmt(volume);$('rate').textContent=fmt(rate,1);$('score').textContent=score+'/100';$('confidence').textContent='Força heurística '+score+'/100 · não é taxa de acerto';$('stage').textContent=stage;
$('signal').textContent=stage==='CONFIRMADO'?'POSSÍVEL '+side:stage==='ANTECIPADO'||stage==='PRESSÃO ANORMAL'||stage==='CONFLUÊNCIA ANTECIPADA'?'ATENÇÃO '+side:stage.startsWith('BLOQUEADO')?'SEM ENTRADA':'AGUARDAR';$('signal').className='signal '+(stage==='CONFIRMADO'||(stage==='ANTECIPADO'||stage==='PRESSÃO ANORMAL'||stage==='CONFLUÊNCIA ANTECIPADA')?(sign>0?'up':'down'):'neutral');
const validEntry=stage==='CONFIRMADO'&&riskValid&&nasdaqAligned;for(const id of ['entry','stopPrice','risk','target1','target2'])$(id).textContent='—';if(validEntry){$('entry').textContent=fmt(price,d);$('stopPrice').textContent=fmt(price-sign*risk,d);$('risk').textContent=fmt(risk,d)+(symbol()==='WIN'||isNasdaq?' pts':' USD/oz');if(symbol()==='WIN'){$('target1').textContent=fmt(price+sign*300);$('target2').textContent=fmt(price+sign*400)}}
$('breakLevel').textContent=Number.isFinite(level)?fmt(level,d):'Sem nível validado';$('flowNarrative').textContent='Agressão '+side.toLowerCase()+' · delta '+fmt(delta)+' · deslocamento '+(aligned?'alinhado':'não confirmado')+' · '+fmt(rate,1)+' negócios/s.';
$('reason').textContent=!fresh?'Feed atrasado: nova entrada bloqueada.':!hasEnough?'Amostra insuficiente de negócios.':!riskValid?'Stop técnico excede o limite configurado ou limite ausente para '+symbol()+'.':stage==='CONFIRMADO'?'Rompimento de '+fmt(sign>0?buyTrigger:sellTrigger,d)+' com pressão e deslocamento alinhados.':stage==='ANTECIPADO'?'Pressão emergente: aguardar rompimento da região de '+(sign>0?(buyTrigger===null?'compra':fmt(buyTrigger,d)):(sellTrigger===null?'venda':fmt(sellTrigger,d)))+'.':'Aguardar Delta recente acelerando, deslocamento do preço, DI1 e risco válido.';
$('intelligence').textContent='Fibonacci: '+(fibNear?fmt(fibNear.ratio*100,1)+'% em '+fmt(fibNear.value,d)+' (contexto, não gatilho)':'indisponível')+'. Leitura local de fluxo: delta '+fmt(delta)+', desequilíbrio '+fmt(imbal*100,1)+'%, velocidade '+fmt(rate,1)+'/s, deslocamento '+fmt(move,d)+', '+(triggerBroke?'rompimento observado':'nível não rompido')+'. Sem identificação de instituições; nenhuma IA treinada conectada.';
$('feedAge').textContent=(source==='live'?'WSS':source==='csv'?'CSV REPLAY':'DEMO')+' · negócio '+new Date(now).toLocaleTimeString('pt-BR')+(source==='live'?' · idade '+fmt((Date.now()-now)/1000,1)+'s':'');
let changed=false;for(const alert of history){if(alert.symbol!==symbol()||alert.source!==$('source').value)continue;const origin=Date.parse(alert.time),age=source==='csv'?now-origin:Date.now()-origin; if(age>=5000&&alert.after5===null&&alert.after5!==undefined){alert.after5=null;} if(source!=='csv'&&age>=5000&&alert.after5===null){alert.after5=Math.round((price-alert.price)*100)/100;changed=true;}if(source!=='csv'&&age>=30000&&alert.after30===null){alert.after30=Math.round((price-alert.price)*100)/100;changed=true;}}if(changed){try{localStorage.setItem(KEY,JSON.stringify(history))}catch{}renderAlerts()}const measured=history.filter(a=>a.symbol===symbol()&&a.after30!==null&&a.after30!==undefined);$('outcomeSummary').textContent=measured.length?'Sinais com 30s observados: '+measured.length+' · movimento bruto posterior, sem custo ou classificação de acerto.':'Sem avaliações de 30 segundos completas. Replay CSV não é avaliação fiel.';
updateHealth(source,now,qualityOK,diFresh);
const tf=$('timeframes');tf.replaceChildren();for(const [name,ms] of [['1m',60000],['5m',300000],['15m',900000],['30m',1800000],['Dia',86400000]]){const t=calc(now,ms),el=document.createElement('div');el.className='tfi';const head=document.createElement('small');head.textContent=name;const bold=document.createElement('b');bold.textContent=t.arr.length?fmt(t.delta):'—';bold.className=t.delta>0?'up':t.delta<0?'down':'neutral';const foot=document.createElement('small');foot.textContent=t.arr.length?(t.span>=ms*.8?'janela ok':'parcial'):'sem dados';el.append(head,bold,foot);tf.append(el)}
if(triggerBroke&&hasEnough&&!breakout)breakout={sign,level:sign>0?buyTrigger:sellTrigger,at:now};if(breakout&&now-breakout.at<30000&&((breakout.sign>0&&price<breakout.level-c.tick)||(breakout.sign<0&&price>breakout.level+c.tick))){if(Date.now()-lastAlert>2500){log('FALSO ROMPIMENTO',breakout.sign>0?'COMPRA':'VENDA',score,'Retorno para dentro do nível');lastAlert=Date.now()}breakout=null}
const sessionParts=new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(now));
const sessionPart=t=>sessionParts.find(p=>p.type===t)?.value;
const day=sessionPart('weekday'),minuteOfDay=Number(sessionPart('hour'))*60+Number(sessionPart('minute'));
const alertsAllowed=source!=='live'||(!['Sat','Sun'].includes(day)&&((minuteOfDay>=389&&minuteOfDay<510)||(minuteOfDay>=990&&minuteOfDay<1200)));
if(alertsAllowed&&lastStage==='CONFIRMADO'&&stage!=='CONFIRMADO'&&Date.now()-lastAlert>2500){log('INVALIDADO',side,score,'Perda das condições de confirmação');lastAlert=Date.now()}if(alertsAllowed&&(stage==='ANTECIPADO'||stage==='CONFIRMADO')&&stage!==lastStage&&Date.now()-lastAlert>2500){log(stage,side,score,stage==='ANTECIPADO'?'Pré-alerta: pressão emergente':'Preço e agressão alinhados após rompimento');lastAlert=Date.now()}lastStage=stage;
}
function updateHealth(source,now,qualityOK,diFresh){const age=Date.now()-now;const live=source==='live',demo=source==='demo';$('healthWin').textContent=live?(age<=3000?'Recebendo · '+Math.round(age)+' ms':'Atrasado'):demo?'DEMO sintética':'CSV histórico';$('healthDI').textContent=symbol()==='NQ'||symbol()==='MNQ'?(treasuryTicks.length&&Math.abs(now-treasuryTicks[treasuryTicks.length-1].timestamp)<=10000?'Treasury sincronizado (preço ZN)':'Treasury ausente'):symbol()!=='WIN'?'Não aplicável':demo?(diFresh?'DI1 fictício':'Aguardando DI1 demo'):source==='csv'?'Não fornecido no CSV':diFresh?'DI1 recente':'Ausente / atrasado';$('healthBook').textContent='Não integrado';$('healthQuality').textContent=qualityOK?'Critérios OK':'Sinais bloqueados';$('healthDetail').textContent='Fonte '+source.toUpperCase()+' · sem book real · DI1 e negócios exigem sincronia. Testes de interface não validam estratégia financeira.';}
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
$('source').onchange=()=>{stop();$('csvWrap').classList.toggle('hidden',$('source').value!=='csv');$('wsWrap').classList.toggle('hidden',$('source').value!=='ws')};$('instrument').onchange=()=>{reset();if($('contract'))$('contract').value=symbol()==='MGC'?'MGCZ6':symbol()==='GC'?'GCZ6':symbol()==='MNQ'?'MNQZ6':symbol()==='NQ'?'NQZ6':'';};$('level').onchange=()=>{breakout=null;$('breakLevel').textContent=$('level').value?fmt(Number($('level').value),symbol()==='WIN'?0:2):'Sem nível validado'};$('reset').onclick=reset;$('stop').onclick=stop;
$('start').onclick=async()=>{if(resumeConnection){resumeConnection=false;stop();$('status').textContent='Restaurando fluxo do servidor';}else reset();const mode=$('source').value;if(mode==='csv'){const file=$('file').files[0];if(!file){$('status').textContent='Selecione o CSV';return}if(file.size>12000000){$('status').textContent='CSV acima de 12 MB';return}try{play=parseCSV(await file.text());if(!play.length)throw Error('Nenhum negócio válido')}catch(e){$('status').textContent=e.message;return}}
if(mode==='ws'){const url=$('endpoint').value.trim();if(!/^wss:\/\//.test(url)){$('status').textContent='Informe wss:// válido';return}try{ws=new WebSocket(url);ws.onopen=()=>{ws.send(JSON.stringify({type:'auth',token:$('bridgeToken').value,symbol:($('contract').value||symbol()).trim().toUpperCase()}));$('status').textContent='Autenticando ponte privada; aguardando feed'};ws.onmessage=e=>{try{let items=JSON.parse(e.data);if(!Array.isArray(items))items=[items];for(const x of items){if(x.type==='replay_batch'){for(const row of x.trades||[]){const t=normalize(row,false);if(!t)continue;if(trades.length&&t.timestamp<trades[trades.length-1].timestamp)continue;trades.push(t);if(trades.length>65000)trades.splice(0,8000);price=t.price;}continue}if(x.type==='replay_complete'){if(trades.length){lastIngest=Date.now();render('live');$('status').textContent='Histórico sincronizado · '+x.count+' negócios recuperados';}else $('status').textContent='Conectado · aguardando histórico recente';continue}if(x.type==='feed_health'){const age=Number(x.age_ms);const ok=x.status==='LIVE'&&Number.isFinite(age)&&age<=3000;$('healthWin').textContent=ok?'Servidor ao vivo · '+age+' ms':'Servidor sem dados atualizados';if(!ok){$('healthQuality').textContent='Sinais bloqueados · feed não sincronizado';$('signal').textContent='SEM ENTRADA';$('stage').textContent='BLOQUEADO · FEED';$('status').textContent=x.provider_connected?'Dados do fornecedor atrasados':'Fornecedor desconectado'}continue}if(x.type==='ready'){pushPublicKey=x.push_public_key||'';reconnectAttempt=0;$('status').textContent='Ponte conectada: '+x.contract+' · agressão estimada';const details=$('advancedDetails');if(details?.open)details.open=false;
 const focused=document.activeElement;if(focused?.blur)focused.blur();
 // iOS Safari sometimes keeps the visual viewport zoom from the password input.
 // Briefly reset viewport scale, then restore user pinch-zoom accessibility.
 const viewport=document.querySelector('meta[name="viewport"]');
 if(viewport){
   const original=viewport.content;
   viewport.content='width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover';
   setTimeout(()=>{viewport.content=original;window.scrollTo(0,0)},300);
 }
 requestAnimationFrame(()=>window.scrollTo(0,0));continue}if(x.type==='server_outcome'){const h=history.find(h=>h.serverTimestamp===x.signal_timestamp&&h.symbol===symbol());if(h){h.outcomes=h.outcomes||{};h.outcomes[String(x.horizon_seconds)]={move:x.signed_move,favorable:x.favorable_excursion,adverse:x.adverse_excursion,flag:x.status};if(x.horizon_seconds===5)h.after5=x.signed_move;if(x.horizon_seconds===30)h.after30=x.signed_move;try{localStorage.setItem(KEY,JSON.stringify(history))}catch{}renderAlerts()}continue}if(x.type==='post_signal_alert'){
  if(String(x.symbol||'').toUpperCase()!==String(($('contract').value||symbol())).toUpperCase())continue;
  const reversal=x.stage==='POSSIBLE_REVERSAL';
  const stage=reversal?'POSSÍVEL REVERSÃO DO FLUXO':'POSSÍVEL ABSORÇÃO';
  const key='post-'+x.stage+'-'+x.symbol+'-'+x.signal_timestamp;
  if(history.some(h=>h.id===key))continue;
  history.unshift({id:key,status:'INFORMATIVO',after5:null,after30:null,
    time:new Date(x.timestamp).toISOString(),serverTimestamp:x.timestamp,
    symbol:symbol(),source:'live',stage,side:x.side==='buy'?'COMPRA':'VENDA',
    score:'—',price:Number(x.price),
    why:(reversal?'Agressão contrária crescente e recuo observado. Avaliar risco e possível encerramento manual.':'Agressão continua com baixo avanço. Avaliar proteção do lucro ou parcial manual.')+
      ' · contra '+Math.round(Number(x.opposing_share)*100)+'% · desde máxima favorável '+x.from_peak_ticks+' ticks. Não há posição confirmada.'});
  history=history.slice(0,200);try{localStorage.setItem(KEY,JSON.stringify(history))}catch{}
  renderAlerts();
  if($('signal')){$('signal').textContent=stage;$('signal').className='signal '+(reversal?'down':'neutral');}
  if($('reason'))$('reason').textContent=x.reason||stage;
  continue;
}
if(x.type==='server_signal'){if(!history.some(h=>h.serverTimestamp===x.timestamp&&h.symbol===symbol()&&h.model===(x.model||'A')&&h.side===(x.side==='buy'?'COMPRA':'VENDA'))){const h={id:'server-'+(x.model||'A')+'-'+x.symbol+'-'+x.timestamp,model:x.model||'A',status:'INFORMATIVO',after5:null,after30:null,time:new Date(x.timestamp).toISOString(),serverTimestamp:x.timestamp,symbol:symbol(),source:'live',stage:x.historical?'MODELO '+(x.model||'A')+' · HISTÓRICO':x.model==='C'?'CONFIRMAÇÃO OPCIONAL · ELEPHANT 2M':x.model==='B'?'MODELO B · ESTRUTURA EXPERIMENTAL':'MODELO A · TREASURY EXPERIMENTAL',side:x.side==='buy'?'COMPRA':'VENDA',score:'—',price:Number(x.price),why:x.model==='C'?'Confirmação complementar, não obrigatória para outros sinais. Elephant 2m com fechamento forte próximo da máxima/mínima dos 3 candles anteriores; '+(x.large_flow_waves||0)+' ondas de agressão estimada, delta alinhado e nível técnico sustentado por 5s. Participantes não identificados; sinal experimental.':x.model==='B'?'Fluxo '+x.ratio+'×; absorção inferida 5m, rompimento 5m, contexto 15m e Fibonacci; SEM Treasury; somente simulação':'Agressão '+x.ratio+'× da referência; '+(x.treasury==='ZN_price_proxy'?'ZN como proxy':'sem filtro de juros')+'; não representa recomendação de entrada'};history.unshift(h);history=history.slice(0,200);try{localStorage.setItem(KEY,JSON.stringify(history))}catch{}renderAlerts()}continue}if(['ZN','US10Y'].includes(String(x.symbol||'').toUpperCase()))ingestTreasury(x,'live');else if(String(x.symbol||'').toUpperCase().startsWith('DI1'))ingestDI(x,'live');else if(x.reference){gcReference.trades.push({t:Number(x.timestamp),side:x.side,size:Number(x.size)||0});gcReference.trades=gcReference.trades.filter(t=>t.t>=Date.now()-60000).slice(-4000);gcReference.last=Number(x.price);const gcBuy=gcReference.trades.filter(t=>t.side==='buy').reduce((v,t)=>v+t.size,0),gcSell=gcReference.trades.filter(t=>t.side==='sell').reduce((v,t)=>v+t.size,0);if($('gcRefInfo'))$('gcRefInfo').textContent=(symbol()==='MNQ'?'NQZ6':'GCZ6')+' · 60s: '+gcReference.trades.length+' negócios classificados · compra '+gcBuy+' · venda '+gcSell+' · delta estimado '+(gcBuy-gcSell)+' · preço '+gcReference.last.toFixed(2)+' · não somado ao micro'}else ingest(x,'live')}}catch{}};ws.onerror=()=>{$('status').textContent='Erro de conexão'};ws.onclose=e=>{const note='WSS encerrado · código '+e.code+(e.reason?' · '+e.reason:' · sem motivo informado');const retry=$('source').value==='ws'&&reconnectAttempt<12;stop();if(retry)resumeConnection=true;$('healthQuality').textContent='Sinais bloqueados · conexão interrompida';if(retry){const delay=Math.min(30000,2000*Math.pow(2,reconnectAttempt++));$('status').textContent=note+' · reconexão em '+Math.round(delay/1000)+'s';reconnectTimer=setTimeout(()=>{reconnectTimer=null;if($('source').value==='ws')$('start').click()},delay)}else $('status').textContent=note}}catch{$('status').textContent='Falha WSS';return}}
running=true;$('start').disabled=true;$('stop').disabled=false;$('status').textContent=mode==='demo'?'Simulando':mode==='csv'?'Reproduzindo CSV':'Conectando WSS';if(mode==='demo')timer=setInterval(demo,140);else if(mode==='csv')timer=setInterval(()=>{if(cursor>=play.length){stop();$('status').textContent='Replay concluído';return}for(let i=0;i<8&&cursor<play.length;i++){const t=play[cursor++];trades.push(t);price=t.price}render('csv')},140);else timer=setInterval(()=>{if(trades.length&&Date.now()-lastIngest>3000){$('healthWin').textContent='Feed atrasado';$('healthQuality').textContent='Sinais bloqueados';$('stage').textContent='BLOQUEADO · FEED';$('signal').textContent='SEM ENTRADA';for(const id of ['entry','stopPrice','risk'])$(id).textContent='—';$('status').textContent='Feed atrasado'}},1000)};
$('clear').onclick=()=>{if(!confirm('Apagar alertas deste navegador?'))return;history=[];try{localStorage.removeItem(KEY)}catch{}renderAlerts()};$('export').onclick=()=>{const rows=[['timestamp','symbol','source','stage','side','price','score','reason','after_5s_price_change','after_30s_price_change'],...history.map(a=>[a.time,a.symbol,a.source,a.stage,a.side,a.price,a.score,a.why,a.after5??'',a.after30??''])],csv=rows.map(r=>r.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv'})),a=document.createElement('a');a.href=url;a.download='flow-ai-v3-alertas.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
$('testPush').onclick=()=>{const status=$('pushStatus');const token=$('bridgeToken').value.trim(),endpoint=$('endpoint').value.trim();if(token.length<24||!endpoint.startsWith('wss://')){status.textContent='Conecte a ponte e configure o token antes do teste';return}const channel=new WebSocket(endpoint);channel.onopen=()=>channel.send(JSON.stringify({type:'push_test',token}));channel.onmessage=e=>{const x=JSON.parse(e.data);status.textContent=x.success?'Teste enviado ao provedor; confirme se apareceu no iPhone':(x.reason||'Teste indisponível');channel.close()};channel.onerror=()=>{status.textContent='Falha ao solicitar push';channel.close()};status.textContent='Solicitando notificação de teste (não é sinal de entrada)';};
$('enablePush').onclick=async()=>{const status=$('pushStatus');try{if(!('serviceWorker' in navigator)||!('PushManager' in window)||!('Notification' in window))throw Error('Push não disponível neste navegador; use Adicionar à Tela de Início no iPhone');if(!pushPublicKey)throw Error('Conecte o Flow ao servidor primeiro');const token=$('bridgeToken').value;if(token.length<24)throw Error('Informe o token de acesso ao servidor');const permission=await Notification.requestPermission();if(permission!=='granted')throw Error('Notificações não autorizadas');const reg=await navigator.serviceWorker.register('./sw.js');await navigator.serviceWorker.ready;const binary=Uint8Array.from(atob(pushPublicKey.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-pushPublicKey.length%4)%4)),c=>c.charCodeAt(0));const subscription=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:binary});const endpoint=$('endpoint').value.trim();if(!endpoint.startsWith('wss://'))throw Error('Endpoint WebSocket inválido');const channel=new WebSocket(endpoint);channel.onopen=()=>channel.send(JSON.stringify({type:'push_subscribe',token,subscription:subscription.toJSON()}));channel.onmessage=e=>{const reply=JSON.parse(e.data);status.textContent=reply.success?'Alertas push cadastrados neste iPhone':'Falha no cadastro: '+(reply.reason||'desconhecida');channel.close()};channel.onerror=()=>{status.textContent='Falha na conexão para cadastro push'};status.textContent='Aguardando cadastro do servidor'}catch(e){status.textContent=e.message||'Falha ao ativar alertas'}};
renderAlerts();reset();$('wsWrap').classList.toggle('hidden',$('source').value!=='ws');$('csvWrap').classList.toggle('hidden',$('source').value!=='csv');
const autoStartFlow=()=>{if(running||reconnectTimer||$('source').value!=='ws')return;const token=$('bridgeToken').value.trim();if(token.length<24){$('status').textContent='Conexão automática pronta · informe o token para iniciar';return}reconnectAttempt=0;$('start').click()};
if($('bridgeToken')){$('bridgeToken').addEventListener('change',autoStartFlow)}
setTimeout(autoStartFlow,600);
// iOS may freeze an OPEN socket while another app is in foreground. On return,
// force a fresh connection if data is stale and let the bridge replay recent prints.
let lastForegroundRecovery=0;
function recoverForegroundFeed(){
 if(document.visibilityState==='hidden'||$('source').value!=='ws')return;
 const token=$('bridgeToken').value.trim();
 if(token.length<24)return;
 const stale=!lastIngest||Date.now()-lastIngest>5000;
 const connected=ws?.readyState===WebSocket.OPEN;
 if(connected&&!stale)return;
 if(Date.now()-lastForegroundRecovery<2500)return;
 lastForegroundRecovery=Date.now();
 if(reconnectTimer){clearTimeout(reconnectTimer);reconnectTimer=null}
 resumeConnection=true;reconnectAttempt=0;
 if(ws){ws.onclose=null;try{ws.close()}catch{}ws=null}
 // Preserve existing market context until the replay replaces stale prices.
 running=false;$('start').disabled=false;$('stop').disabled=true;
 $('healthWin').textContent='Retomando dados recentes';
 $('healthQuality').textContent='Sinais bloqueados · sincronizando';
 $('status').textContent='iPhone retomado · sincronizando histórico recente';
 $('start').click();
}
document.addEventListener('visibilitychange',recoverForegroundFeed);
window.addEventListener('pageshow',recoverForegroundFeed);
window.addEventListener('focus',recoverForegroundFeed);

function updateFocusDashboard(){
 const put=(id,value)=>{const e=$(id);if(e)e.textContent=value};
 const value=id=>$(id)?.textContent?.trim()||'—';
 put('focusInstrument',$('instrument')?.selectedOptions?.[0]?.textContent||'MNQ');
 put('focusPrice',value('price'));
 put('focusFeed',value('healthWin'));
 const badge=$('sourceTag');
 if(badge&&$('source')?.value==='ws'){
   const fresh=ws?.readyState===WebSocket.OPEN&&lastIngest>0&&Date.now()-lastIngest<=3000;
   const quality=value('healthQuality');
   const blocked=/bloquead/i.test(quality);
   badge.textContent=!fresh?'DADOS ATRASADOS':blocked?'QUALIDADE BLOQUEADA':'WSS · CONECTADO';
   badge.style.background=!fresh||blocked?'#fff1d9':'#dff7ed';
   badge.style.color=!fresh||blocked?'#805522':'#096c50';
 }

 put('focusBuy',value('buyPct'));put('focusSell',value('sellPct'));
 if($('focusBuyBar'))$('focusBuyBar').style.width=$('buyBar')?.style.width||'50%';
 if($('focusSellBar'))$('focusSellBar').style.width=$('sellBar')?.style.width||'50%';
 put('focusDelta',value('delta'));
 // The compact card intentionally never shows free-form diagnostic text.
 // Numeric 1-minute volume from classified trades; never display diagnostic prose.
 const latestTrade=trades.length?trades[trades.length-1].timestamp:0;
 const volumeTrades=latestTrade?trades.filter(t=>t.timestamp>=latestTrade-60000):[];
 const minuteVolume=volumeTrades.reduce((total,t)=>total+(Number(t.size)||0),0);
 put('focusVolume',volumeTrades.length?fmt(minuteVolume):'—');
 // Radar uses classified trade volume only; it does not infer actual institution identities.
 const last=trades.length?trades[trades.length-1].timestamp:0;
 const windowTrades=last?trades.filter(t=>t.timestamp>=last-120000&&t.timestamp<=last&&(t.side==='buy'||t.side==='sell')):[];
 const recentVolume=windowTrades.reduce((a,t)=>a+(Number(t.size)||0),0);
 const buyVolume=windowTrades.reduce((a,t)=>a+(t.side==='buy'?(Number(t.size)||0):0),0);
 const sellVolume=recentVolume-buyVolume;
 const pct=recentVolume?Math.round(100*buyVolume/recentVolume):null;
 const putNum=(id,x)=>put(id,x==null?'—':x+'%');
 putNum('radarBuy',pct);putNum('radarSell',pct==null?null:100-pct);
 if($('radarBuyBar'))$('radarBuyBar').style.width=(pct??50)+'%';
 if($('radarSellBar'))$('radarSellBar').style.width=(pct==null?50:100-pct)+'%';
 const signed=(arr)=>arr.reduce((n,t)=>n+(t.side==='buy'?1:-1)*(Number(t.size)||0),0);
 const delta120=signed(windowTrades);
 put('focusDelta',windowTrades.length?((delta120>0?'+':'')+fmt(delta120)):'—');
 const waveStats=(from,to)=>{
   const a=last?trades.filter(t=>t.timestamp>=last-to&&t.timestamp<last-from&&(t.side==='buy'||t.side==='sell')):[];
   const total=a.reduce((n,t)=>n+(Number(t.size)||0),0);
   const delta=signed(a),dominant=Math.abs(delta),side=delta>0?'buy':delta<0?'sell':null;
   const share=total?(Math.max(0,(total+dominant)/2)/total):0;
   return {total,delta,side,share,count:a.length};
 };
 const first=waveStats(3000,6000),second=waveStats(0,3000);
 const fmtWave=w=>w.count>=3&&w.total>=8?(w.side==='buy'?'↑ ':w.side==='sell'?'↓ ':'↔ ')+Math.round(w.share*100)+'%':'—';
 put('radarWave1',fmtWave(first));put('radarWave2',fmtWave(second));
 const priceMove=windowTrades.length>=2?windowTrades[windowTrades.length-1].price-windowTrades[0].price:null;
 put('radarPriceMove',priceMove==null?'—':(priceMove>0?'+':'')+fmt(priceMove,2)+' pt');
 const recent30=windowTrades.filter(t=>t.timestamp>=last-30000);
 const recentBuy=recent30.reduce((n,t)=>n+(t.side==='buy'?(Number(t.size)||0):0),0);
 const recentTotal=recent30.reduce((n,t)=>n+(Number(t.size)||0),0);
 const recentShare=recentTotal?Math.round(100*recentBuy/recentTotal):null;
 const early=recent30.filter(t=>t.timestamp<last-15000),late=recent30.filter(t=>t.timestamp>=last-15000);
 const earlySec=early.length>=2?Math.max(1,(early[early.length-1].timestamp-early[0].timestamp)/1000):0;
 const lateSec=late.length>=2?Math.max(1,(late[late.length-1].timestamp-late[0].timestamp)/1000):0;
 const accel=early.length>=5&&late.length>=5&&earlySec>=5&&lateSec>=5?((signed(late)/lateSec)-(signed(early)/earlySec)):null;
 put('radarAcceleration',recentShare===null||recent30.length<5?'SEM BASE':(recentShare>=57?'↑ ':recentShare<=43?'↓ ':'↔ ')+recentShare+'%');
 const qualified=first.count>=3&&second.count>=3&&first.total>=8&&second.total>=8&&first.side&&first.side===second.side&&first.share>=.57&&second.share>=.57;
 const recentMove=recent30.length>=2?recent30[recent30.length-1].price-recent30[0].price:null;
 const stall=recent30.length>=12&&recentTotal>=40&&recentMove!==null&&Math.abs(recentMove)<=config[symbol()].tick*3&&Math.abs(signed(recent30))/Math.max(1,recentTotal)>=.57;
 let explanation='Coletando fluxo suficiente para análise';
 if(qualified)explanation='Duas ondas de agressão '+(first.side==='buy'?'compradora':'vendedora')+' detectadas · pesquisa';
 else if(stall)explanation='Possível absorção: agressão sem deslocamento · não confirmada';
 else if(windowTrades.length>=12)explanation='Contexto de 2 min · ondas recentes sem confirmação';
 put('radarInterpretation',explanation);
 const status=value('signal'),up=/COMPRA|ALTA/i.test(status),down=/VENDA|BAIXA/i.test(status);
 const blocked=/BLOQUEAD|SEM ENTRADA|AGUARD|PARADO/i.test(status)||!/Recebendo|DEMO|CSV/i.test(value('healthWin'));
 const active=!blocked&&(up||down);
 put('focusDirection',active?(up?'↑':'↓'):'↔');
 put('focusDirectionText',active?(up?'COMPRA':'VENDA'):'AGUARDAR');
 put('focusDirectionNote',active?'Viés experimental':'Sem confirmação de entrada');
 put('focusBias',recentVolume<40||windowTrades.length<12?'AMOSTRA INSUFICIENTE':pct>=57?'COMPRADORES':pct<=43?'VENDEDORES':'EQUILÍBRIO');
 const treasury=value('diStatus');
 const treasuryReady=!/ausente|atrasad|inconclus|aguard|antiga|sem direcao|nao confirmad|CONTRADITOR/i.test(treasury)&&/yield proxy em|DIRECAO CONFIRMADA/i.test(treasury);
 put('focusTreasury',treasuryReady?'DIREÇÃO OBSERVADA':'NÃO CONFIRMADO');
 put('focusTreasuryNote',treasuryReady?'ZN: movimento registrado':'ZN: aguardar direção válida');
 const breakoutOK=/CONFIRMADO|ROMPIMENTO/i.test(value('stage'))&&active;
 put('focusBreak',breakoutOK?'✓':'—');
 put('focusAbs',/poss[ií]vel|absor[cç][aã]o/i.test(value('absStatus'))?'ATENÇÃO':'—');
 // Criteria are indicators, not a numerical probability estimate.
 const confirmations=[active,treasuryReady,breakoutOK,/OK/i.test(value('healthQuality')),value('delta')!=='—'];
 put('focusConfluence',confirmations.filter(Boolean).length+' / 5');
 put('focusConfluenceNote',active?'Condições em observação':'Entrada ainda bloqueada');
 put('focusEntry',active?status:'AGUARDAR');
 put('focusRisk',value('stopPrice')+' / '+value('target1'));
 const card=$('focusEntry');if(card)card.style.color=active?(up?'#078e65':'#ca3854'):'#193148';
}
let focusRenderPending=false;
function scheduleFocusRefresh(){
 if(focusRenderPending)return;
 focusRenderPending=true;
 setTimeout(()=>{focusRenderPending=false;updateFocusDashboard()},120);
}
setInterval(updateFocusDashboard,1000);updateFocusDashboard();
})();