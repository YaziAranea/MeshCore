'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const api=require('./api'),{installApiMock}=require('./test_api_fixture');
async function connected(options={}){
  const port=installApiMock(options),events=[],client=new api.CliClient({timeout:40,closeTimeout:40,onEvent:e=>events.push(e)});
  await client.connect(port);return {port,client,events};
}
test('CMD66/RESP29 exact tagged wire and max length; no C9',()=>{
  const frame=api.encodeCommand('a9','ui get volume');assert.deepEqual(Array.from(frame.slice(0,4)),[66,97,57,124]);
  assert.equal(frame.length,17);assert.equal(api.decodeReply(Uint8Array.from([29,...new TextEncoder().encode('a9|OK ui get key=volume value=7')]),'a9'),'OK ui get key=volume value=7');
  assert.equal(api.encodeCommand('00','ui '+ 'x'.repeat(153)).length,160);
  for(const command of ['ui '+ 'x'.repeat(154),'ui get\nvolume','ui имя','reboot','api hello'])assert.throws(()=>api.encodeCommand('00',command),{code:'INPUT'});
  assert.throws(()=>api.encodeCommand('x|','ui hello'),{code:'INPUT'});
  assert.equal(api.matches(frame,Uint8Array.of(1,6)),true);
  assert.throws(()=>api.decodeReply(Uint8Array.of(1,6),'a9'),{code:'FAILED'});
});
test('strict discovery including absent, old protocol and duplicate marker',()=>{
  const p=s=>Uint8Array.from([21,...new TextEncoder().encode(s)]);
  api.discover(p('foo:2,smartui_cli:1'));
  for(const s of ['smartui_api:1','smartui_cli:2','smartui_cli:1,smartui_cli:1','smartui_cli:1,smartui_cli:2'])assert.throws(()=>api.discover(p(s)),{code:'UNSUPPORTED'});
});
test('old 0.11 never receives CMD66/C9 and closes with archive guidance',async()=>{
  const port=installApiMock({oldFirmware:true}),client=new api.CliClient({timeout:40});
  await assert.rejects(client.connect(port),{code:'UNSUPPORTED'});assert.equal(port.closed,true);assert.deepEqual(port.packets.map(p=>p[0]),[22,40]);
});
test('fragmented stream, standard pushes and matching prefix; one reader',async()=>{
  const f=await connected();try{
    f.port.emit(Uint8Array.of(0x83));f.port.reply('ZZ','OK ui get key=volume value=99');
    assert.equal(await f.client.execute('ui get volume'),'OK ui get key=volume value=7');
    assert.equal(f.port.readerCount,1);assert.equal(f.port.maxOpen,1);assert.ok(f.port.packets.every(p=>[22,40,66].includes(p[0])));
  }finally{await f.client.disconnect();}
});
test('known errors do not poison or retry; unsupported field stays readable',async()=>{
  const f=await connected();try{
    for(const reason of ['unsupported','readonly','storage','source','range','stale','invalid']){
      f.port.errorNext='ERR ui '+reason;const before=f.port.commands.length;
      await assert.rejects(f.client.execute('ui get volume'),e=>e.reason===reason);
      assert.equal(f.port.commands.length,before+1);assert.equal(f.client.state.uncertain,false);
    }
    await f.client.execute('ui get volume');
  }finally{await f.client.disconnect();}
});
test('timeout poisons writes; no automatic retry or write after disconnect',async()=>{
  const f=await connected();f.port.drop=true;
  await assert.rejects(f.client.execute('ui set volume 4',{mutate:true}),{code:'TIMEOUT'});
  const count=f.port.packets.length;await assert.rejects(f.client.execute('ui get volume'),{code:'UNCERTAIN'});
  assert.equal(f.port.packets.length,count);await f.client.disconnect();const reads=f.port.readCalls;
  await assert.rejects(f.client.execute('ui get volume'),{code:'CLOSED'});await new Promise(r=>setTimeout(r,5));
  assert.equal(f.port.packets.length,count);assert.equal(f.port.readCalls,reads);
});
test('wrong prefix cannot resolve request',async()=>{
  const f=await connected();try{f.port.wrong=true;await assert.rejects(f.client.execute('ui get volume'),{code:'TIMEOUT'});assert.equal(f.client.state.uncertain,true);}
  finally{await f.client.disconnect();}
});
test('busy guard prevents competing operations and read-only denies mutation',async()=>{
  const f=await connected();try{f.port.drop=true;const pending=f.client.execute('ui get volume');await assert.rejects(f.client.execute('ui get volume'),{code:'BUSY'});await assert.rejects(pending,{code:'TIMEOUT'});}
  finally{await f.client.disconnect();}
  const r=await connected({readonly:true});try{const before=r.port.commands.length;await assert.rejects(r.client.execute('ui set volume 1',{mutate:true}),{code:'DENIED'});assert.equal(r.port.commands.length,before);}
  finally{await r.client.disconnect();}
});
test('ADC service start is inferred mutation; stop remains allowed during read-only',async()=>{
  const f=await connected({readonly:true,caps:{adc_service:1}});
  try{
    const before=f.port.commands.length;
    await assert.rejects(f.client.execute('ui adc service start'),{code:'DENIED'});
    await assert.rejects(f.client.execute('ui adc set 1.815000'),{code:'DENIED'});
    assert.equal(f.port.commands.length,before);
    assert.match(await f.client.execute('ui adc service stop'),/^OK ui adc_service supported=1 active=0/);
  }finally{await f.client.disconnect();}
});

test('ADC acknowledgement followed by delayed USB write cannot restore closed-session state',async()=>{
  const f=await connected({caps:{adc_service:1},delayWriteCommand:'ui adc service start'});
  const pending=f.client.execute('ui adc service start');
  const rejected=assert.rejects(pending,{code:'CLOSED'});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(typeof f.port.releaseWrite,'function');
  const closing=f.client.disconnect();f.port.releaseWrite();await closing;await rejected;
  assert.equal(f.client.state.connected,false);assert.equal(f.client.state.phase,'disconnected');
});

test('tags unique until exhaustion; no wrap in one session',()=>{
  const tags=new Set();for(let i=0;i<3844;i++)tags.add(api.tagFor(i));assert.equal(tags.size,3844);assert.throws(()=>api.tagFor(3844),{code:'EXHAUSTED'});
});
test('record, UTF8 standard replies and malformed replies',()=>{
  const reply=s=>Uint8Array.from([29,...new TextEncoder().encode('ab|'+s)]);
  assert.equal(api.decodeReply(reply('Тестовая нода'),'ab',false),'Тестовая нода');
  assert.throws(()=>api.decodeReply(reply('Тестовая нода'),'ab'),{code:'PROTOCOL'});
  assert.throws(()=>api.decodeReply(reply('OK ui get x=1'),'zz'),{code:'PROTOCOL'});
  assert.throws(()=>api.decodeReply(reply('OK ui x='+'x'.repeat(157)),'ab'),{code:'PROTOCOL'});
  assert.throws(()=>api.record('OK ui get key=x key=y','OK ui get'),{code:'PROTOCOL'});
  assert.throws(()=>api.decodeReply(reply('Unknown command'),'ab'),e=>e.reason==='unsupported');
  assert.throws(()=>api.decodeReply(reply('Error: secret command rejected'),'ab'),e=>e.code==='FAILED'&&!e.message.includes('secret'));
});

test('notification test uses exact ui test and read-only inference',async()=>{
  const f=await connected();try{assert.equal(await f.client.execute('ui test'),'OK ui test');}finally{await f.client.disconnect();}
  const r=await connected({readonly:true});try{await assert.rejects(r.client.execute('ui test'),{code:'DENIED'});await assert.rejects(r.client.execute('ui set volume 4'),{code:'DENIED'});}finally{await r.client.disconnect();}
});

test('radio and advert writes infer mutation without a caller hint',async()=>{
  const r=await connected({readonly:true});try{
    const count=r.port.commands.length;
    await assert.rejects(r.client.execute('ui radio set 868731 62500 7 7 2'),{code:'DENIED'});
    await assert.rejects(r.client.execute('ui advert set 30'),{code:'DENIED'});
    assert.equal(r.port.commands.length,count);
    assert.match(await r.client.execute('ui radio'),/^OK ui radio /);
    assert.match(await r.client.execute('ui advert'),/^OK ui advert /);
  }finally{await r.client.disconnect();}
});
test('reconnect renegotiates and credentials never enter diagnostic events',async()=>{
  const f=await connected();await f.client.execute('ui wifi password 736563726574',{mutate:true});await f.client.disconnect();await f.client.connect(f.port);
  assert.equal(f.client.state.uncertain,false);assert.equal(f.port.commands.filter(c=>c==='ui hello').length,2);
  assert.doesNotMatch(JSON.stringify(f.events),/736563726574|password|secret|PIN/);await f.client.disconnect();
});
test('raw text and oversized stream frames rejected',()=>{
  assert.throws(()=>new api.FrameDecoder().feed(new TextEncoder().encode('help\r\n')),{code:'MODE'});
  assert.throws(()=>new api.FrameDecoder().feed(Uint8Array.of(62,177,0)),{code:'PROTOCOL'});
});
