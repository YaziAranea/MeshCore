'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const api=require('./api'),{installApiMock}=require('./test_api_fixture');
async function connected(options={}){
  const port=installApiMock(options),events=[],client=new api.CliClient({timeout:40,closeTimeout:40,onEvent:e=>events.push(e)});
  await client.connect(port);return {port,client,events};
}
const upstreamWrites=['set name Дача','set pin 654321','set tx 20','set af 2.5','set dutycycle 10',
  'set rxdelay 1.5','set multi.acks 2','set path.hash.mode 1','set radio.rxgain on',
  'set tz.offset 5.5','set radio 869.618,62.5,8,8'];
const upstreamReads=['get freq','get tx','get af','get dutycycle','get rxdelay','get multi.acks',
  'get path.hash.mode','get radio.rxgain','get tz.offset','get wifi.status','get wifi.ip'];
const friendlyReads=['get volume','get vibration','get melody','get sound_quiet','get muted','get board_led',
  'get unread_led','get gps','get battery_protection','get agc_reset','get fem.lna','get fem.pa','get sound.bridge',
  'get adc','get adc.multiplier','get adc.default','get battery','get battery_mv','get shutdown_mv','get advert',
  'caps adc','get caps fem.lna','help','help sound 2','help adc 3','help radio 2','help connection 2',
  'help system','help advert','help led','help gps','help fem','melody 1','melodies','adc manual','adc service','adc service stop'];
const friendlyWrites=['set volume 5','set vibration on','set vibration off','set vibration 1','set vibration 0',
  'set melody 1','set sound_quiet 1','set muted on','set board_led off','set unread_led 1','set gps 0',
  'set battery_protection on','set agc_reset 1','set fem.lna on','set fem.pa off','set sound.bridge on',
  'set adc 4.9','set adc.multiplier 4.900000','set advert 120','test notification','adc preview 3800',
  'adc apply 7','adc reset','adc service start'];

test('friendly console marker is independent and preserves original ui commands',async()=>{
  const f=await connected({console:1,manualAdc:true,caps:{adc_service:1}});try{
    assert.equal(f.client.state.hello.console,'1');
    for(const command of friendlyReads)assert.match(await f.client.execute(command),/^(?:> |OK adc_)/,command);
    for(const command of friendlyWrites)assert.match(await f.client.execute(command),/^(?:OK|> interval_min=)/,command);
    assert.equal(await f.client.execute('get volume'),'> 5');
    assert.equal(await f.client.execute('get fem.lna'),'> 1');
    assert.equal(await f.client.execute('get advert'),'> interval_min=120');
    assert.equal(await f.client.execute('melody 1'),'> 1: Трель');
    assert.equal(api.record(await f.client.execute('ui get volume'),'OK ui get').value,'5');
    await assert.rejects(f.client.execute('get tx'),{code:'MESHCORE_UNSUPPORTED'});
  }finally{await f.client.disconnect();}
});

test('0.14 or malformed console marker never receives new commands; upstream still works',async()=>{
  for(const console of [undefined,0,2]){
    const f=await connected({console,meshcore:1});try{const before=f.port.commands.length;
      for(const command of [...friendlyReads,...friendlyWrites])await assert.rejects(f.client.execute(command),{code:'CONSOLE_UNSUPPORTED'});
      assert.equal(f.port.commands.length,before);assert.equal(f.client.state.uncertain,false);
      assert.equal(await f.client.execute('get tx'),'> 20');
      assert.equal(await f.client.execute('ui get volume'),'OK ui get key=volume value=7');
    }finally{await f.client.disconnect();}
  }
});

test('friendly readonly protects all setters, ADC tokens and tests but allows safe stop',async()=>{
  const f=await connected({console:1,readonly:true,manualAdc:true,caps:{adc_service:1}});try{
    const before=f.port.commands.length;
    for(const command of [...friendlyWrites,'ui adc preview 3800'])await assert.rejects(f.client.execute(command,{mutate:false}),{code:'DENIED'});
    assert.equal(f.port.commands.length,before);
    for(const command of friendlyReads)assert.match(await f.client.execute(command),/^(?:> |OK adc_)/,command);
    assert.equal(f.client.state.uncertain,false);
  }finally{await f.client.disconnect();}
});

test('friendly failures are redacted and no write is ever repeated after missing ACK',async()=>{
  const f=await connected({console:1});try{
    for(const reason of ['range','readonly','unsupported','source','stale','storage']){
      f.port.errorNext='Error: '+reason;const before=f.port.commands.length;
      await assert.rejects(f.client.execute('set volume 5'),e=>e.reason===reason);
      assert.equal(f.port.commands.length,before+1);assert.equal(f.client.state.uncertain,false);
    }
    f.port.drop=true;await assert.rejects(f.client.execute('set volume 5'),{code:'TIMEOUT'});
    const before=f.port.commands.length;await assert.rejects(f.client.execute('set volume 5'),{code:'UNCERTAIN'});
    assert.equal(f.port.commands.length,before);
    assert.doesNotMatch(JSON.stringify(f.events),/set volume|Error:|source/);
  }finally{await f.client.disconnect();}
});

test('friendly command grammar rejects secrets, unknown verbs, controls and non-ASCII digits',()=>{
  for(const command of [...friendlyReads,...friendlyWrites])assert.ok(api.encodeCommand('00',command));
  for(const command of ['set volume ５','set vibration yes','set fem 1','set adc NaN','set adc Infinity',
    'set adc 1e2','help reboot','get wifi.password','get pin','set battery_mv 4000','adc service erase',
    'help sound\nreboot','melody -1','get volume extra'])assert.throws(()=>api.encodeCommand('00',command),{code:'INPUT'},command);
});

test('helper allowlist exposes TX, help and readings without accepting credentials or ADC writes',()=>{
  for(const command of [...friendlyReads,...upstreamReads,'ui get volume','ui caps adc','ui radio','ui advert'])assert.equal(api.developerCommand(command).write,false,command);
  for(const command of ['set tx 20','set name Дача','set volume 5','set fem.lna on','set vibration 1','test notification'])assert.equal(api.developerCommand(command).write,true,command);
  for(const command of ['set battery_protection off','set battery_protection 0','ui set battery_protection 0'])assert.equal(api.developerCommand(command).warning,'battery');
  for(const command of ['set sound.bridge on','set sound.bridge 1','ui set bridge 1'])assert.equal(api.developerCommand(command).warning,'bridge');
  for(const command of ['set pin 654321','ui wifi password 736563726574','ui get password','ui get wifi_password',
    'set adc 4.9','set adc.multiplier 4.9','adc preview 3800','adc apply 7','adc reset','adc service start',
    'reboot','poweroff','shutdown'])assert.throws(()=>api.developerCommand(command),{code:'INPUT'},command);
});

test('protocol 14 and additive meshcore hello preserve ui and enable explicit upstream commands',async()=>{
  const f=await connected({meshcore:1});try{
    assert.equal(f.client.state.hello.meshcore,'1');
    assert.equal(await f.client.execute('ui set volume 6'),'OK ui set key=volume value=6');
    assert.equal(api.record(await f.client.execute('ui get volume'),'OK ui get').value,'6');
    for(const command of upstreamReads)assert.match(await f.client.execute(command),/^> /);
    for(const command of upstreamWrites)assert.match(await f.client.execute(command),/^(?:OK|> pin is now)/);
    assert.equal(await f.client.execute('get name'),'> Дача');assert.equal(await f.client.execute('get tx'),'> 20');
    assert.doesNotMatch(JSON.stringify(f.events),/654321|Дача|pin is now/);
  }finally{await f.client.disconnect();}
});

test('new upstream commands require capability; readonly blocks every setter before I/O',async()=>{
  for(const meshcore of [undefined,0,2]){
    const f=await connected({meshcore});try{const before=f.port.commands.length;
      for(const command of [...upstreamReads,...upstreamWrites])await assert.rejects(f.client.execute(command),{code:'MESHCORE_UNSUPPORTED'});
      assert.equal(f.port.commands.length,before);assert.equal(f.client.state.uncertain,false);
      assert.equal(await f.client.execute('ui get volume'),'OK ui get key=volume value=7');
    }finally{await f.client.disconnect();}
  }
  const f=await connected({meshcore:1,readonly:true});try{
    const before=f.port.commands.length;
    for(const command of upstreamWrites)await assert.rejects(f.client.execute(command,{mutate:false}),{code:'DENIED'});
    assert.equal(f.port.commands.length,before);
    for(const command of upstreamReads)assert.match(await f.client.execute(command),/^> /);
  }finally{await f.client.disconnect();}
});

test('upstream codec allows only explicit verbs; UTF8 names use byte budget without replacement',()=>{
  assert.equal(new TextDecoder().decode(api.encodeCommand('ab','set name Дача').slice(4)),'set name Дача');
  const exact='set name '+'я'.repeat(73)+'a';assert.equal(api.encodeCommand('ab',exact).length,160);
  for(const command of [exact+'a','set name \ud800','set name X\nreboot','ui имя','set tx ２０',
    'set wifi.pwd secret','get wifi.pwd','set unknown 1','get unknown','reboot','poweroff','shutdown','erase','rm /prefs.json'])
    assert.throws(()=>api.encodeCommand('00',command),{code:'INPUT'});
});

test('upstream error variants are failures, redacted and not automatically retried',async()=>{
  const f=await connected({meshcore:1});try{
    for(const reply of ['Error, secret invalid value','ERROR: secret invalid value','Error: secret storage']){
      f.port.errorNext=reply;const before=f.port.commands.length;
      await assert.rejects(f.client.execute('set tx 23'),e=>e.code==='FAILED'&&!e.message.includes('secret'));
      assert.equal(f.port.commands.length,before+1);assert.equal(f.client.state.uncertain,false);
    }
    f.port.drop=true;await assert.rejects(f.client.execute('set tx 20'),{code:'TIMEOUT'});
    const before=f.port.commands.length;await assert.rejects(f.client.execute('get tx'),{code:'UNCERTAIN'});
    assert.equal(f.port.commands.length,before);
  }finally{await f.client.disconnect();}
});

test('terminal power commands are deliberately unavailable, never confused with confirmed writes',async()=>{
  const f=await connected({meshcore:1});try{const before=f.port.commands.length;
    for(const command of ['reboot','poweroff','shutdown'])await assert.rejects(f.client.execute(command),{code:'INPUT'});
    assert.equal(f.port.commands.length,before);assert.equal(f.client.state.uncertain,false);
  }finally{await f.client.disconnect();}
});
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
