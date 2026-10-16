'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {Coordinator,keys}=require('./autosave');
const {Runner}=require('./console_runner');

const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
function fixture(){
  const state={session:{},connected:true,busy:false,write:true,transport:'companion',control:true,compact:true,meshcore:true,
    caps:{sound:1,display:1,board_led:1,unread_led:1,vibration:1},schemas:{}};
  for(const key of keys)state.schemas[key]={supported:true,min:0,max:1,step:1,options:null};
  Object.assign(state.schemas,{volume:{supported:true,min:1,max:10,step:1},melody:{supported:true,min:0,max:30,step:1},ui_theme:{supported:true,min:0,max:3,step:1},ui_font:{supported:true,min:0,max:2,step:1},backlight_timeout:{supported:true,min:0,max:2,step:1}});
  const sent=[],events=[];let acquires=0,releases=0;
  const bridge={getContext:()=>({...state}),acquire(session){assert.equal(session,state.session);if(state.busy)throw new Error('BUSY');state.busy=true;acquires++;},release(){state.busy=false;releases++;},async execute(step){sent.push(step.wire);return {reply:'OK',verified:true};},async confirm(){return true;}};
  return {state,bridge,sent,events,coordinator:new Coordinator(bridge,event=>events.push(event)),get acquires(){return acquires;},get releases(){return releases;}};
}
async function settle(f){await tick();assert.equal(f.coordinator.busy,false);assert.equal(f.state.busy,false);}

test('construction and reading state never send a command',()=>{
  const f=fixture();assert.equal(f.coordinator.busy,false);assert.deepEqual(f.coordinator.pendingKeys,[]);assert.equal(f.coordinator.activeKey,null);assert.deepEqual(f.sent,[]);assert.equal(f.acquires,0);
});
test('one explicit ordinary change acquires, verifies and releases without confirmation',async()=>{
  const f=fixture();f.bridge.confirm=()=>assert.fail('No confirmation for ordinary preferences');
  assert.equal((await f.coordinator.set('volume',7)).status,'saved');await settle(f);
  assert.deepEqual(f.sent,['set volume 7']);assert.equal(f.acquires,1);assert.equal(f.releases,1);assert.deepEqual(f.events.map(event=>event.type),['queued','applying','saved','idle']);
});
test('service protocol uses the same verified executor with translated wire command',async()=>{
  const f=fixture();f.state.transport='service';await f.coordinator.set('sound_quiet',0);await settle(f);assert.deepEqual(f.sent,['settings set sound_quiet 0']);
});
test('sensitive keys, arbitrary commands and invalid values cannot enter the queue',async()=>{
  const f=fixture();
  for(const key of ['gps','tx','fem_pa','battery_protection','adc_multiplier','tone_pin','profile','connection','pin','night_quiet','high_drive','bridge','name','volume\nset pin 123456','__proto__'])await assert.rejects(f.coordinator.set(key,1));
  for(const value of [NaN,Infinity,7.1,'7',true,null,undefined,-1,11])await assert.rejects(f.coordinator.set('volume',value));
  assert.deepEqual(f.sent,[]);assert.equal(f.acquires,0);
});
test('read-only, unsupported and out-of-schema choices do not acquire the port',async()=>{
  const f=fixture();f.state.write=false;await assert.rejects(f.coordinator.set('volume',4),/чтение/);f.state.write=true;
  f.state.schemas.volume.supported=false;await assert.rejects(f.coordinator.set('volume',4),/недоступна/);
  f.state.schemas.volume.supported=true;f.state.schemas.volume.max=5;await assert.rejects(f.coordinator.set('volume',7),/диапазон/);
  assert.deepEqual(f.sent,[]);assert.equal(f.acquires,0);
});
test('rapid slider changes conflate pending values, never overlap in-flight writes',async()=>{
  const f=fixture(),first=deferred(),last=deferred();let running=0,maximum=0;
  f.bridge.execute=async step=>{f.sent.push(step.wire);maximum=Math.max(maximum,++running);const response=await (f.sent.length===1?first.promise:last.promise);running--;return response;};
  const p1=f.coordinator.set('volume',2);const p2=f.coordinator.set('volume',3);const p3=f.coordinator.set('volume',4);const p4=f.coordinator.set('volume',5);
  assert.equal((await p2).status,'superseded');assert.equal((await p3).status,'superseded');assert.deepEqual(f.coordinator.pendingKeys,['volume']);
  assert.deepEqual(f.sent,['set volume 2']);assert.equal(f.coordinator.activeKey,'volume');
  first.resolve({verified:true});assert.equal((await p1).status,'saved');await tick();assert.deepEqual(f.sent,['set volume 2','set volume 5']);
  last.resolve({verified:true});assert.equal((await p4).status,'saved');await settle(f);assert.equal(maximum,1);assert.equal(f.acquires,1);assert.equal(f.releases,1);
});
test('different keys remain ordered, replacing a pending key preserves its place',async()=>{
  const f=fixture(),first=deferred();f.bridge.execute=async step=>{f.sent.push(step.wire);return f.sent.length===1?first.promise:{verified:true};};
  const pending=[f.coordinator.set('volume',3),f.coordinator.set('melody',4),f.coordinator.set('board_led',0),f.coordinator.set('melody',5)];
  first.resolve({verified:true});const results=await Promise.all(pending);await settle(f);
  assert.deepEqual(f.sent,['set volume 3','set melody 5','set board_led 0']);assert.equal(results[1].status,'superseded');
});
test('another form or macro lease rejects immediately, never waits to write later',async()=>{
  const f=fixture();f.state.busy=true;await assert.rejects(f.coordinator.set('volume',4),/завершения/);assert.equal(f.acquires,0);f.state.busy=false;await settle(f);assert.deepEqual(f.sent,[]);
});
test('macro execution cannot interleave with an autosave batch',async()=>{
  const f=fixture(),first=deferred();f.bridge.execute=step=>{f.sent.push(step.wire);return first.promise;};
  const save=f.coordinator.set('volume',4),runner=new Runner(f.bridge);
  await assert.rejects(runner.run({name:'Чтение',commands:['get volume']}),/текущей операции/);
  first.resolve({verified:true});await save;await settle(f);assert.deepEqual(f.sent,['set volume 4']);assert.equal(f.acquires,1);
});
for(const code of ['TIMEOUT','PROTOCOL','PARTIAL_WRITE'])test(code+' drops pending writes, never retries and blocks the failed session',async()=>{
  const f=fixture(),first=deferred();f.bridge.execute=step=>{f.sent.push(step.wire);return first.promise;};
  const p1=f.coordinator.set('volume',4),p2=f.coordinator.set('melody',8),done=Promise.allSettled([p1,p2]);
  first.reject(Object.assign(new Error('Device raw reply contains sensitive text'),{code}));const results=await done;await settle(f);
  assert.equal(results[0].status,'rejected');assert.equal(results[1].status,'rejected');assert.deepEqual(f.sent,['set volume 4']);assert.equal(f.releases,1);
  assert.equal(f.events.some(event=>JSON.stringify(event).includes('sensitive')),false);await assert.rejects(f.coordinator.set('volume',4),/Переподключитесь/);
  assert.deepEqual(f.sent,['set volume 4']);
});
test('a resolved ACK without explicit verification is not reported as saved',async()=>{
  const f=fixture();f.bridge.execute=async step=>{f.sent.push(step.wire);return {reply:'OK',verified:false};};
  await assert.rejects(f.coordinator.set('volume',7),/не подтверждено/);await settle(f);assert.equal(f.events.some(event=>event.type==='saved'),false);assert.deepEqual(f.sent,['set volume 7']);
});
test('reconnecting permits a fresh explicit choice but never replays a failed choice',async()=>{
  const f=fixture();f.bridge.execute=async step=>{f.sent.push(step.wire);throw new Error('timeout');};
  await assert.rejects(f.coordinator.set('volume',4));await settle(f);f.state.session={};await tick();assert.deepEqual(f.sent,['set volume 4']);
  f.bridge.execute=async step=>{f.sent.push(step.wire);return {verified:true};};await f.coordinator.set('volume',5);await settle(f);assert.deepEqual(f.sent,['set volume 4','set volume 5']);
});
for(const change of ['disconnect','session','transport','uncertain'])test(change+' while awaiting readback cannot produce success or leak queued writes',async()=>{
  const f=fixture(),first=deferred();f.bridge.execute=step=>{f.sent.push(step.wire);return first.promise;};
  const done=Promise.allSettled([f.coordinator.set('volume',4),f.coordinator.set('melody',8)]);
  if(change==='disconnect')f.state.connected=false;else if(change==='session')f.state.session={};else if(change==='transport')f.state.transport='service';else f.state.uncertain=true;
  first.resolve({verified:true});const results=await done;await tick();assert.equal(f.coordinator.busy,false);
  assert.ok(results.every(result=>result.status==='rejected'));assert.equal(f.events.some(event=>event.type==='saved'),false);assert.deepEqual(f.sent,['set volume 4']);assert.equal(f.releases,1);
});
test('queued write rechecks read-only access immediately before execution',async()=>{
  const f=fixture(),first=deferred();f.bridge.execute=step=>{f.sent.push(step.wire);return first.promise;};
  const done=Promise.allSettled([f.coordinator.set('volume',4),f.coordinator.set('melody',8)]);f.state.write=false;first.resolve({verified:true});
  const results=await done;await settle(f);assert.equal(results[0].status,'fulfilled');assert.equal(results[1].status,'rejected');assert.deepEqual(f.sent,['set volume 4']);
});
test('queued write rechecks schema support immediately before execution',async()=>{
  const f=fixture(),first=deferred();f.bridge.execute=step=>{f.sent.push(step.wire);return first.promise;};
  const done=Promise.allSettled([f.coordinator.set('volume',4),f.coordinator.set('melody',8)]);f.state.schemas.melody.supported=false;first.resolve({verified:true});
  const results=await done;await settle(f);assert.equal(results[0].status,'fulfilled');assert.equal(results[1].status,'rejected');assert.deepEqual(f.sent,['set volume 4']);
});
test('cancel drops pending choices while current verified write finishes',async()=>{
  const f=fixture(),first=deferred();f.bridge.execute=step=>{f.sent.push(step.wire);return first.promise;};
  const active=f.coordinator.set('volume',4),queued=f.coordinator.set('melody',8);f.coordinator.cancel();assert.equal((await queued).status,'cancelled');assert.equal(f.coordinator.busy,true);
  first.resolve({verified:true});assert.equal((await active).status,'saved');await settle(f);assert.deepEqual(f.sent,['set volume 4']);
});
test('a rejected new choice also drops older queued changes without interrupting verification',async()=>{
  const f=fixture(),first=deferred();f.bridge.execute=step=>{f.sent.push(step.wire);return first.promise;};
  const active=f.coordinator.set('volume',4),queued=f.coordinator.set('melody',8);
  await assert.rejects(f.coordinator.set('volume',11));assert.equal((await queued).status,'cancelled');first.resolve({verified:true});
  assert.equal((await active).status,'saved');await settle(f);assert.deepEqual(f.sent,['set volume 4']);
});
test('observer exceptions do not skip verification or strand the shared lease',async()=>{
  const f=fixture();f.coordinator=new Coordinator(f.bridge,()=>{throw new Error('broken view');});assert.equal((await f.coordinator.set('volume',4)).status,'saved');await settle(f);assert.equal(f.releases,1);
});
test('a reentrant queued observer cannot acquire a second lease or strand a choice',async()=>{
  const f=fixture();let second;
  f.coordinator=new Coordinator(f.bridge,event=>{if(event.type==='queued'&&event.key==='volume')second=f.coordinator.set('melody',8);});
  assert.equal((await f.coordinator.set('volume',4)).status,'saved');assert.equal((await second).status,'saved');await settle(f);assert.deepEqual(f.sent,['set volume 4','set melody 8']);assert.equal(f.acquires,1);assert.equal(f.releases,1);
});
test('state changed by applying observer is rechecked before sending the write',async()=>{
  const f=fixture();f.coordinator=new Coordinator(f.bridge,event=>{if(event.type==='applying')f.state.write=false;});await assert.rejects(f.coordinator.set('volume',4),/чтение/);await settle(f);assert.deepEqual(f.sent,[]);
});
test('new changes during asynchronous lease release are rejected instead of stranded',async()=>{
  const f=fixture(),release=deferred();f.bridge.release=()=>release.promise.then(()=>{f.state.busy=false;});
  await f.coordinator.set('volume',4);await assert.rejects(f.coordinator.set('melody',8),/завершения/);assert.equal(f.coordinator.busy,true);release.resolve();await settle(f);assert.deepEqual(f.sent,['set volume 4']);
});
