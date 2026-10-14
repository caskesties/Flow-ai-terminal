'use strict';
// Protótipo de interface. Dados 100% artificiais; lógica sem validade operacional.
const $ = id => document.getElementById(id);
const fmt = n => Math.round(n).toLocaleString('pt-BR');
let timer=null, price=145000, history=[], previousState='', alerts=[];
function render(){
  const recent=history.slice(-30);let buys=0,sells=0;
  for(const t of recent){if(t.side==='buy')buys+=t.qty;else sells+=t.qty;}
  const volume=buys+sells,delta=buys-sells;
  const ratio=volume?Math.abs(delta)/volume:0;
  const strength=Math.min(100,Math.round(ratio*110));
  const dir=delta>0?'COMPRA':'VENDA';
  const bias=strength>=45?(delta>0?'Comprador':'Vendedor'):'Neutro';
  $('price').textContent=fmt(price);$('delta').textContent=(delta>0?'+':'')+fmt(delta);$('volume').textContent=fmt(volume);
  $('delta').className=delta>0?'up':delta<0?'down':'';$('bias').textContent=bias;$('strength').textContent=strength+'/100';
  $('fill').style.width=strength+'%';$('fill').style.background=delta>=0?'#25bd8a':'#f57c7c';
  $('evidence').textContent=`Janela fictícia: ${recent.length} eventos; ${fmt(buys)} contratos em compras agressivas e ${fmt(sells)} em vendas agressivas.`;
  // Regras para demonstrar transições de estado, NÃO regras de negociação reais.
  const stage=recent.length<15?'':strength>=70?'confirmado':strength>=45?'antecipado':'';
  const state=stage?`${dir}:${stage}`:'';
  if(state&&state!==previousState){
    const detail=stage==='antecipado'?'Pressão direcional emergente (simulada).':'Sinal confirmado por limiar ilustrativo, não validado.';
    const element=document.createElement('div');element.className='event '+(stage==='confirmado'?'confirmed ':'')+(dir==='VENDA'?'sell':'');
    const bold=document.createElement('strong');bold.textContent=`${stage==='confirmado'?'SINAL':'ATENÇÃO'} • ${dir} • DEMO`;element.appendChild(bold);
    const desc=document.createElement('p');desc.textContent=detail;element.appendChild(desc);
    const time=document.createElement('small');time.textContent=new Date().toLocaleTimeString('pt-BR')+' • preço fictício '+fmt(price);element.appendChild(time);
    if($('events').textContent==='Ainda não há alertas.')$('events').textContent='';
    $('events').prepend(element);alerts.push({stage,dir,price,at:new Date().toISOString()});
  }
  previousState=state;
}
function tick(){
  // tendência alternada apenas para tornar as telas e os dois sentidos observáveis.
  const phase=Math.floor(history.length/55)%4;
  const desired=phase===0||phase===3?'buy':'sell';
  const side=Math.random()<0.74?desired:(desired==='buy'?'sell':'buy');
  const qty=10+Math.floor(Math.random()*75);
  const move=(side==='buy'?1:-1)*(Math.random()<0.66?5:0);
  price+=move;history.push({side,qty,price,t:Date.now()});
  if(history.length>2000)history=history.slice(-500);
  render();
}
$('start').addEventListener('click',()=>{if(timer)return;timer=setInterval(tick,380);$('start').disabled=true;$('stop').disabled=false;$('status').textContent='Simulação ativa';});
$('stop').addEventListener('click',()=>{clearInterval(timer);timer=null;$('start').disabled=false;$('stop').disabled=true;$('status').textContent='Pausado';});
$('reset').addEventListener('click',()=>{clearInterval(timer);timer=null;price=145000;history=[];previousState='';alerts=[];$('events').textContent='Ainda não há alertas.';$('start').disabled=false;$('stop').disabled=true;$('status').textContent='Parado';render();});
if('serviceWorker' in navigator)window.addEventListener('load',()=>navigator.serviceWorker.register('./sw.js').catch(()=>{}));
render();
