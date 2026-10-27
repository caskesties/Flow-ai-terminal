const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
const recovery=src.slice(src.indexOf('function recoverForegroundFeed(){'),src.indexOf("document.addEventListener('visibilitychange',recoverForegroundFeed)"));
function scenario({paused=false,heartbeat=Date.now(),ready=1}={}){
 let starts=0,closes=0;
 const fields={source:{value:'ws'},bridgeToken:{value:'t'.repeat(24)},start:{click(){starts++}},stop:{},healthWin:{},healthQuality:{},status:{}};
 const ctx={manuallyPaused:paused,lastServerHeartbeat:heartbeat,lastIngest:0,document:{visibilityState:'visible'},$:id=>fields[id],Date,WebSocket:{OPEN:1},ws:{readyState:ready,close(){closes++}},lastForegroundRecovery:0,reconnectTimer:null,resumeConnection:false,reconnectAttempt:5,running:true,clearTimeout};
 vm.createContext(ctx);vm.runInContext(recovery+';recoverForegroundFeed();',ctx);return {starts,closes};
}
assert.deepEqual(scenario(),{starts:0,closes:0},'quiet market with fresh heartbeat must not reconnect');
assert.deepEqual(scenario({paused:true,heartbeat:0}),{starts:0,closes:0},'manual pause must survive focus');
assert.deepEqual(scenario({heartbeat:Date.now()-10000}),{starts:1,closes:1},'frozen socket recovers');
assert.deepEqual(scenario({ready:3}),{starts:1,closes:1},'closed socket recovers');
console.log('4 foreground recovery scenarios passed');

// Resuming must not double count a replayed execution; distinct ids at the same ms survive.
const replayStart=src.indexOf("if(x.type==='replay_batch'){")+"if(x.type==='replay_batch'){".length;
const replayBody=src.slice(replayStart,src.indexOf("continue}if(x.type==='replay_complete')",replayStart));
const now=Date.now();const original={timestamp:now,price:100,size:1,side:'buy',trade_id:'1'};
const replayCtx={x:{trades:[original,{...original,trade_id:'2'}]},trades:[original],seenIds:new Set(['1']),normalize:x=>x,Date,price:100};
vm.createContext(replayCtx);vm.runInContext(replayBody,replayCtx);
assert.equal(replayCtx.trades.length,2);
assert.equal(replayCtx.trades[1].trade_id,'2');
console.log('Replay deduplication passed');
