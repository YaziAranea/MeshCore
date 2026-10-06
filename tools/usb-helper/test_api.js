'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {ApiClient,ApiError,FrameDecoder,encode,decodePage,record,parsePush,decodeMessage}=require('./api');
const {installApiMock}=require('./test_api_fixture');
const enc=new TextEncoder();
test('strict fragmented framing, limits and mixed console rejection',()=>{
  for(let split=1;split<7;split++){const decoder=new FrameDecoder(),frame=Uint8Array.of(62,3,0,201,1,2,62,1,0,7);let packets=[];for(let i=0;i<frame.length;i+=split)packets.push(...decoder.feed(frame.slice(i,i+split)));assert.deepEqual(packets.map(p=>[...p]),[[201,1,2],[7]]);}
  for(const bytes of [[65],[62,0,0],[62,177,0]])assert.throws(()=>new FrameDecoder().feed(Uint8Array.from(bytes)),ApiError);
  assert.throws(()=>encode(0,1,enc.encode('api get')),ApiError);assert.throws(()=>encode(1,1,enc.encode('api get\n')),ApiError);
  assert.throws(()=>decodePage(new Uint8Array(13)),ApiError);assert.throws(()=>record('OK api get a=1 a=2','OK api get'),ApiError);
});
test('real wire handshake, pagination and one binary reader; no inbox side effects',async()=>{
  const port=installApiMock(),events=[],client=new ApiClient({onEvent:e=>events.push(e),timeout:200});
  await client.connect(port);assert.equal(client.state.hello.sync,'1');assert.equal(port.readerCount,1);
  assert.equal(client.state.hello.firmware,'0.11');assert.equal(client.state.hello.stage,'release');
  const caps=record(await client.execute('api caps'),'OK api caps');assert.equal(caps.bridge,'1');
  assert.ok(port.packets.some(p=>p[7]===2),'multi-page reply exercised');
  assert.equal(port.commands.some(c=>/inbox|sync enable/.test(c)),false);
  assert.ok(events.every(e=>!JSON.stringify(e).includes('api caps')),'audit has operation category only');
  await client.disconnect();assert.equal(port.closed,true);assert.equal(port.maxOpen,1);
});

test('0.10 release remains usable without ecosystem synchronization',async()=>{
  const port=installApiMock({legacy:true}),client=new ApiClient({timeout:200});
  await client.connect(port);
  assert.equal(client.state.hello.firmware,'0.10');assert.equal(client.state.hello.stage,'release');
  assert.equal(client.state.hello.sync,'0');assert.equal(client.state.hello.events,'0');
  assert.equal(record(await client.execute('api caps'),'OK api caps').bridge,'1');
  assert.equal(port.commands.some(c=>/inbox|sync enable/.test(c)),false);
  await client.disconnect();
});
test('discovery absent: no C9 extension probe sent',async()=>{
  const port=installApiMock({unsupported:true}),client=new ApiClient({timeout:100});
  await assert.rejects(client.connect(port),e=>e.code==='UNSUPPORTED');assert.equal(port.packets.some(p=>p[0]===201),false);assert.equal(port.closed,true);
});
test('timeout becomes uncertain, never repeats write; requires reconnect',async()=>{
  const port=installApiMock(),client=new ApiClient({timeout:25});await client.connect(port);port.drop=true;
  await assert.rejects(client.execute('api set agc_reset 1',{mutate:true}),e=>e.code==='TIMEOUT');
  assert.equal(client.state.uncertain,true);const n=port.packets.length;
  await assert.rejects(client.execute('api get'),e=>e.code==='UNCERTAIN');assert.equal(port.packets.length,n);
  await client.disconnect();port.drop=false;await client.connect(port);assert.equal(client.state.uncertain,false);await client.disconnect();
});
test('read-only permissions, concurrent requests and sanitised backend errors',async()=>{
  const port=installApiMock({readonly:true}),client=new ApiClient({timeout:50});await client.connect(port);
  await assert.rejects(client.execute('api set volume 1',{mutate:true}),e=>e.code==='DENIED');
  await assert.rejects(client.execute('api unknown'),e=>e.code==='FAILED'&&!e.message.includes('unsupported'));
  const p=client.execute('api get');await assert.rejects(client.execute('api get'),e=>e.code==='BUSY');await p;await client.disconnect();
});
test('push hints distinguished from replies and only bounded metadata exposed',async()=>{
  const port=installApiMock(),pushes=[],client=new ApiClient({onPush:p=>pushes.push(p),timeout:100});await client.connect(port);
  port.event(7,'00000000');await new Promise(r=>setTimeout(r,0));const hint=parsePush(pushes[0]);assert.equal(hint.boot,port.boot);assert.equal(hint.mask,'15');
  const malformed=pushes[0].slice();malformed[5]=1;assert.equal(parsePush(malformed),null);await client.disconnect();
});
test('message parser preserves text as data and suppresses CLI/data payload',()=>{
  const frame=Uint8Array.from([16,0,0,0,1,2,3,4,5,6,255,0,0,0,0,0,...enc.encode('<img src=x>Привет')]);
  const hex=p=>Array.from(p,b=>b.toString(16).padStart(2,'0')).join('');assert.equal(decodeMessage(hex(frame)).text,'<img src=x>Привет');
  frame[11]=1;assert.equal(decodeMessage(hex(frame)).text,'Служебное сообщение. Текст скрыт.');
  assert.throws(()=>decodeMessage('10'),ApiError);assert.throws(()=>decodeMessage('zz'),ApiError);
});
test('disconnect cancels pending waiter, clears session and closes reader',async()=>{
  const port=installApiMock(),client=new ApiClient({timeout:200});await client.connect(port);port.drop=true;
  const pending=client.execute('api get');const rejected=assert.rejects(pending,e=>e.code==='CLOSED');await client.disconnect();await rejected;assert.equal(client.state.connected,false);assert.equal(port.closed,true);
});
test('wrong console, malformed pagination and serial loss fail closed',async()=>{
  const port=installApiMock(),client=new ApiClient({timeout:30});await client.connect(port);
  const original=port.respond;port.respond=function(request,text,status){if(request[7]===2){this.emit(Uint8Array.from([201,83,85,73,1,request[5],request[6],2,0,request[8],request[9],255,1,...new Uint8Array(2)]));return;}original.call(this,request,text,status);};
  await assert.rejects(client.execute('api caps'),e=>e.code==='PROTOCOL');assert.equal(client.state.uncertain,true);await client.disconnect();
  port.respond=original;await client.connect(port);port.controller.enqueue(enc.encode('Commands: help\r\n'));await new Promise(r=>setTimeout(r,10));assert.equal(client.state.connected,false);
});
test('open failures and dropped device information never leak raw errors',async()=>{
  const client=new ApiClient({timeout:20});await assert.rejects(client.connect({open:async()=>{throw new Error('SECRET');}}),e=>e.safe&&!e.message.includes('SECRET'));assert.equal(client.state.connected,false);
  const port=installApiMock();port.drop=true;await assert.rejects(client.connect(port),e=>e.code==='TIMEOUT');assert.equal(port.closed,true);
});
test('known backend reasons give precise safe guidance without exposing device text',async()=>{
  const port=installApiMock(),client=new ApiClient({timeout:100});await client.connect(port);
  const cases=[['gone',/больше не хранится/],['unsupported',/отсрочка напоминания недоступна/],['negotiate',/Включить синхронизацию/],['unavailable',/временно недоступен/],['source',/Запустите ProMicro от АКБ.*без перезапуска.*2 минут/]];
  for(const [reason,expected]of cases){
    port.command=request=>port.respond(request,'ERR api '+reason+' secret=PRIVATE_DEVICE_TEXT',7);
    await assert.rejects(client.execute('api inbox snooze 0123456789abcdef 00000001 600',{mutate:true}),error=>error.reason===reason&&expected.test(error.message)&&!error.message.includes('PRIVATE_DEVICE_TEXT')&&error.safe);
    assert.equal(client.state.uncertain,false,'known rejection is not a lost acknowledgement');
  }
  port.command=request=>port.respond(request,'ERR api future_secret PRIVATE_DEVICE_TEXT',7);
  await assert.rejects(client.execute('api get'),error=>error.code==='FAILED'&&!error.reason&&!error.message.includes('PRIVATE_DEVICE_TEXT'));
  await client.disconnect();
});
test('signed plain direct messages skip exactly four sender-prefix bytes in v2 and v3 frames',()=>{
  const hex=p=>Array.from(p,b=>b.toString(16).padStart(2,'0')).join('');
  for(const header of [[7],[16,0,0,0]]){
    const frame=Uint8Array.from([...header,1,2,3,4,5,6,255,2,0,0,0,0,0xde,0xad,0xbe,0xef,...enc.encode('Подписанный текст')]);
    assert.equal(decodeMessage(hex(frame)).text,'Подписанный текст');
    assert.throws(()=>decodeMessage(hex(frame.slice(0,header.length+6+2+4+3))),ApiError);
  }
});
