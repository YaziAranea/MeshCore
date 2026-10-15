'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {Runner}=require('./console_runner');
function fixture(overrides={}){
  const state={session:{},connected:true,busy:false,write:true,transport:'companion',control:true,compact:true,meshcore:true,caps:{sound:1},schemas:{volume:{supported:true,min:1,max:10,step:1,options:null},muted:{supported:true,min:0,max:1,step:1,options:null}}};
  const sent=[],events=[],confirmations=[];let releases=0,acquires=0;
  const bridge={getContext:()=>({...state}),acquire(session){assert.equal(session,state.session);state.busy=true;acquires++;},release(){state.busy=false;releases++;},async confirm(text){confirmations.push(text);return true;},async execute(step){sent.push(step.wire);return {reply:'OK'};},...overrides};
  return {state,sent,events,confirmations,bridge,runner:new Runner(bridge,e=>events.push(e)),get releases(){return releases;},get acquires(){return acquires;}};
}
const macro=commands=>({name:'Проверка',description:'Тестовая последовательность',commands});
test('all lines validate before any acquisition, confirmation or write',async()=>{
  const f=fixture();await assert.rejects(f.runner.run(macro(['set volume 7','get pin'])));assert.deepEqual(f.sent,[]);assert.equal(f.acquires,0);assert.equal(f.confirmations.length,0);assert.equal(f.runner.busy,false);
});
test('readonly rejects a write macro before the first read',async()=>{
  const f=fixture();f.state.write=false;await assert.rejects(f.runner.run(macro(['get volume','set volume 7'])));assert.deepEqual(f.sent,[]);
});
test('read macro executes in order without confirmation and releases once',async()=>{
  const f=fixture();const r=await f.runner.run(macro(['get volume','get battery']));assert.equal(r.status,'complete');assert.deepEqual(f.sent,['get volume','get battery']);assert.equal(f.confirmations.length,0);assert.equal(f.releases,1);assert.equal(f.runner.busy,false);
});
test('one confirmation includes the frozen entire plan; refusal sends nothing',async()=>{
  const f=fixture();f.bridge.confirm=async text=>{f.confirmations.push(text);return false;};const r=await f.runner.run(macro(['set volume 7','get volume']));assert.equal(r.status,'cancelled');assert.match(f.confirmations[0],/set volume 7\nget volume/);assert.deepEqual(f.sent,[]);assert.equal(f.releases,1);
});
test('session changed during confirmation cannot receive a stale plan',async()=>{
  const f=fixture();f.bridge.confirm=async()=>{f.state.session={};return true;};await assert.rejects(f.runner.run(macro(['set volume 7'])));assert.deepEqual(f.sent,[]);assert.equal(f.releases,1);
});
test('timeout of a write stops immediately and never retries',async()=>{
  const f=fixture();f.bridge.execute=async step=>{f.sent.push(step.wire);throw Object.assign(new Error('Нет ответа'),{safe:true});};await assert.rejects(f.runner.run(macro(['set volume 7','get volume'])),/Нет ответа/);assert.deepEqual(f.sent,['set volume 7']);assert.equal(f.events.find(e=>e.type==='error').attemptedWrite,true);assert.equal(f.releases,1);
});
test('stop waits for in-flight response then skips all following steps',async()=>{
  const f=fixture();let resolve;f.bridge.execute=step=>{f.sent.push(step.wire);return new Promise(r=>{resolve=r;});};const pending=f.runner.run(macro(['get volume','get battery']));await new Promise(r=>setImmediate(r));f.runner.stop();assert.equal(f.runner.busy,true);assert.equal(f.releases,0);resolve({reply:'> 7'});assert.equal((await pending).status,'stopped');assert.deepEqual(f.sent,['get volume']);assert.equal(f.releases,1);
});
test('second run cannot interleave with an in-flight request',async()=>{
  const f=fixture();let resolve;f.bridge.execute=()=>new Promise(r=>{resolve=r;});const pending=f.runner.run(macro(['get volume']));await new Promise(r=>setImmediate(r));await assert.rejects(f.runner.run(macro(['set volume 4'])),/уже выполняется/);resolve({reply:'> 7'});await pending;assert.equal(f.acquires,1);
});
test('a reply from a replaced session is not logged as a successful result',async()=>{
  const f=fixture();f.bridge.execute=async()=>{f.state.session={};return {reply:'> 7'};};await assert.rejects(f.runner.run(macro(['get volume','get battery'])));assert.equal(f.events.some(e=>e.type==='reply'),false);assert.equal(f.releases,1);
});
test('changed capabilities are checked before each later write',async()=>{
  const f=fixture();f.bridge.execute=async step=>{f.sent.push(step.wire);f.state.schemas.volume.supported=false;return {reply:'> 7'};};await assert.rejects(f.runner.run(macro(['get volume','set volume 7'])));assert.deepEqual(f.sent,['get volume']);
});
test('service plan translates canonical commands without sending combined lines',async()=>{
  const f=fixture();f.state.transport='service';const r=await f.runner.run(macro(['set volume 7','get volume']));assert.equal(r.status,'complete');assert.deepEqual(f.sent,['settings set volume 7','settings get volume']);
});
