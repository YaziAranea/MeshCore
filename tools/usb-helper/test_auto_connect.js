'use strict';
const {describe,it}=require('node:test'),assert=require('node:assert/strict');
const {ReadableStream,WritableStream}=require('node:stream/web');
const {detect,SETTLE_MS}=require('./auto_connect');
const {CliClient}=require('./api');
const {ConsoleClient}=require('./core');
const enc=new TextEncoder();
const OPTIONS={baudRate:115200,dataBits:8,stopBits:1,parity:'none',flowControl:'none'};
const HELP='Commands: info | status | mode ble | mode usb | mode wifi | wifi setup | wifi status | wifi save | wifi cancel | wifi forget | help';
const HELP_END='Credential input is not echoed. WiFi is saved only after a passed test.';
const STATUS='Mode=BLE companion=idle via=none USB-service=on WiFi-config=no link=down IP=none approval=none';
const INFO='SmartUI=0.20 core=1.18 build=b3be1cc0 upstream=1234abcd capabilities=BLE,USB board=FakeTec';
const short={binary:40,service:50,open:60,close:60};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function binaryInfo(){
  const bytes=new Uint8Array(82);bytes[0]=13;bytes[1]=14;bytes[2]=32;bytes[3]=8;
  new DataView(bytes.buffer).setUint32(4,654321,true);
  bytes.set(enc.encode('2026-10-01'),8);bytes.set(enc.encode('FakeTec'),20);bytes.set(enc.encode('v1.18'),60);return bytes;
}
function fixture(mode='service',options={}){
  const f={mode,readable:null,writable:null,opened:0,closed:0,readerCount:0,commands:[],frames:[],writes:[],draft:options.draft||'',overflow:!!options.overflow,stage:options.stage||'idle',binary:[...(options.partialBinary||[])],partialAt:Date.now(),saved:0};
  f.emit=bytes=>{if(!f.readable)return;if(options.fragment===false)f.controller.enqueue(bytes);else for(let n=0;n<bytes.length;n+=7)f.controller.enqueue(bytes.slice(n,n+7));};
  f.text=text=>f.emit(enc.encode(text+'\r\n'));
  f.packet=packet=>f.emit(Uint8Array.from([62,packet.length&255,packet.length>>8,...packet]));
  f.handleFrame=frame=>{
    f.frames.push(Array.from(frame));
    if(options.drop)return;
    if(frame[0]===22)f.packet(options.info||binaryInfo());
    else if(frame[0]===40)f.packet(Uint8Array.from([21,...enc.encode('smartui_cli:1')]));
    else if(frame[0]===66){const raw=new TextDecoder().decode(frame.slice(1));f.commands.push(raw.slice(3));f.packet(Uint8Array.from([29,...enc.encode(raw.slice(0,3)+'OK ui hello version=1 max_command=156 max_reply=156 write=1 sync=0 events=0 control=1 console=1')]));}
  };
  f.handleLine=line=>{
    f.commands.push(line);if(options.drop)return;
    if(options.owned){f.text('WiFi setup is owned by the companion API; use that client to finish or cancel.');return;}
    if(line==='cancel'||line==='wifi cancel'){f.stage='idle';f.text(options.readonly?'Connection settings are read-only during storage recovery.':line==='wifi cancel'?'WiFi setup cancelled.':"Unknown command. Type 'help'.");}
    else if(f.stage!=='idle'){f.saved++;f.text('Testing WiFi without saving...');}
    else if(line==='help'){f.text(HELP);if(!options.incompleteHelp)f.text(HELP_END);}
    else if(line==='status')f.text(STATUS);
    else if(line==='info')f.text(INFO);
    else if(line.startsWith('settings'))throw new Error('Unexpected settings command during detection');
  };
  f.consume=bytes=>{
    if(mode==='silent')return;
    if(mode==='companion'){
      if(f.binary.length&&Date.now()-f.partialAt>=2000)f.binary=[];
      for(const byte of bytes){
        if(!f.binary.length){if(byte===60){f.binary.push(byte);f.partialAt=Date.now();}continue;}
        f.binary.push(byte);
        if(f.binary.length>=3&&f.binary.length===(f.binary[1]|f.binary[2]<<8)+3){const frame=Uint8Array.from(f.binary.slice(3));f.binary=[];f.handleFrame(frame);}
      }
    }else for(const byte of bytes){
      if(byte===10||byte===13){
        if(f.overflow)f.text('Input too long; discarded.');else if(f.draft||f.stage==='password')f.handleLine(f.draft);
        f.draft='';f.overflow=false;
      }else if(byte===8||byte===127)f.draft=f.draft.slice(0,-1);
      else if(byte>=32){if(f.draft.length<160)f.draft+=String.fromCharCode(byte);else f.overflow=true;}
    }
  };
  f.open=async options2=>{
    assert.deepEqual(options2,OPTIONS);if(options.openError)throw new Error('RAW SECRET OPEN ERROR');
    if(options.openWait)await options.openWait;
    assert.equal(f.readable,null);f.opened++;f.openAt=Date.now();
    const readable=new ReadableStream({start(controller){f.controller=controller;}}),getReader=readable.getReader.bind(readable);
    readable.getReader=(...args)=>{assert.equal(readable.locked,false,'parallel readers forbidden');f.readerCount++;return getReader(...args);};
    f.readable=readable;
    f.writable=new WritableStream({write(bytes){f.writes.push(Array.from(bytes));f.firstWriteAt??=Date.now();if(options.writeError)throw new Error('RAW SECRET WRITE ERROR');if(options.onWrite)options.onWrite(f,bytes);else f.consume(bytes);}});
  };
  f.close=async()=>{assert.equal(f.readable?.locked,false);assert.equal(f.writable?.locked,false);f.closed++;try{f.controller?.close();}catch(_){}f.readable=null;f.writable=null;};
  return f;
}
describe('automatic USB detection with simulated ports only',{concurrency:true},()=>{
  it('binary first, correct transport, single native open, same readable adopted by CLI SDK',async()=>{
    const f=fixture('companion'),events=[],r=await detect(f,{timeouts:short,onProgress:e=>events.push(e)});
    assert.equal(r.transport,'companion');assert.equal(r.originalPort,f);assert.equal(r.port.originalPort,f);assert.equal(f.opened,1);assert.equal(f.closed,0);
    assert.deepEqual(f.frames,[[22,3]]);assert.equal(f.firstWriteAt-f.openAt>=2000,true);
    const client=new CliClient({timeout:100,closeTimeout:100});await client.connect(r.port);assert.equal(client.state.phase,'ready');assert.equal(f.opened,1);assert.equal(f.readerCount,2);await client.disconnect();assert.equal(f.closed,1);
    assert.doesNotMatch(JSON.stringify(events),/654321|FakeTec|pin|board/);assert.deepEqual(Object.keys(r).sort(),['originalPort','port','transport']);
  });
  it('service fallback clears the binary prefix and transfers to full ConsoleClient verification',async()=>{
    const f=fixture(),r=await detect(f,{timeouts:short});assert.equal(r.transport,'service');assert.deepEqual(f.writes[0],[60,2,0,22,3]);assert.deepEqual(f.commands,['cancel','help']);
    const client=new ConsoleClient({timeouts:{command:150,close:100}});await client.connect(r.port);assert.equal(client.state.verified,true);assert.equal(f.opened,1);await client.disconnect();assert.equal(f.closed,1);assert.equal(f.saved,0);
  });
  it('waits for stale binary frame expiry instead of completing an earlier command',async()=>{
    const f=fixture('companion',{partialBinary:[60,30,0,5]});const r=await detect(f,{timeouts:short});assert.equal(r.transport,'companion');assert.deepEqual(f.frames,[[22,3]]);await r.port.close();
  });
  for(const stage of ['password','ssid'])it('clears pending '+stage+' draft without submitting credentials',async()=>{
    const f=fixture('service',{stage,draft:'private network secret'}),r=await detect(f,{timeouts:short});assert.equal(r.transport,'service');assert.equal(f.saved,0);assert.deepEqual(f.commands,['cancel','help']);await r.port.close();
  });
  it('overflow discards its first cancel then sends exactly one additional cancel',async()=>{
    const f=fixture('service',{stage:'password',draft:'x'.repeat(160),overflow:true}),r=await detect(f,{timeouts:short});assert.equal(f.saved,0);assert.equal(f.writes.length,4);assert.deepEqual(f.commands,['cancel','help']);await r.port.close();
  });
  it('read-only service remains discoverable without writes to settings',async()=>{
    const f=fixture('service',{readonly:true}),r=await detect(f,{timeouts:short});assert.equal(r.transport,'service');assert.deepEqual(f.commands,['cancel','help']);await r.port.close();
  });
  it('unknown or silent port never becomes a guessed transport',async()=>{
    const f=fixture('silent');await assert.rejects(detect(f,{timeouts:short}),{code:'UNKNOWN'});assert.equal(f.closed,1);assert.equal(f.writes.length,2);
  });
  it('truncated binary DEVICE_INFO is not a valid identification',async()=>{
    const f=fixture('companion',{info:Uint8Array.of(13,14)});await assert.rejects(detect(f,{timeouts:short}),{code:'UNKNOWN'});assert.equal(f.closed,1);
  });
  it('text acknowledgement without both exact help markers is unknown',async()=>{
    const f=fixture('service',{incompleteHelp:true});await assert.rejects(detect(f,{timeouts:short}),{code:'UNKNOWN'});assert.equal(f.closed,1);
  });
  it('busy Wi-Fi owner has a distinct error and receives no further probe',async()=>{
    const f=fixture('service',{owned:true});await assert.rejects(detect(f,{timeouts:short}),{code:'DEVICE_BUSY'});assert.equal(f.closed,1);assert.deepEqual(f.commands,['cancel']);
  });
  it('port-open denial is not a protocol fallback or an OS message leak',async()=>{
    const f=fixture('service',{openError:true});await assert.rejects(detect(f,{timeouts:short}),error=>error.code==='OPEN'&&!error.message.includes('SECRET'));assert.equal(f.writes.length,0);assert.equal(f.closed,0);
  });
  it('already open or detecting port is busy without a second open',async()=>{
    const f=fixture(),controller=new AbortController(),first=detect(f,{timeouts:short,signal:controller.signal});await tick();await assert.rejects(detect(f),{code:'BUSY'});controller.abort();await assert.rejects(first,{code:'CANCELLED'});assert.equal(f.opened,1);assert.equal(f.closed,1);
  });
  it('abort before picking/opening does not touch the device',async()=>{
    const controller=new AbortController();controller.abort();const f=fixture();await assert.rejects(detect(f,{signal:controller.signal}),{code:'CANCELLED'});assert.equal(f.opened,0);
  });
  it('abort at binary probing closes without switching to text',async()=>{
    const controller=new AbortController(),f=fixture('silent');await assert.rejects(detect(f,{timeouts:short,signal:controller.signal,onProgress:e=>{if(e.phase==='probing_companion')controller.abort();}}),{code:'CANCELLED'});assert.equal(f.closed,1);assert.equal(f.writes.length,0);
  });
  it('disconnect while probing is LOST, not fallback',async()=>{
    const f=fixture('companion',{onWrite:p=>p.controller.error(new Error('RAW SECRET DISCONNECT'))});await assert.rejects(detect(f,{timeouts:short}),{code:'LOST'});assert.equal(f.writes.length,1);
  });
  it('write failure stops rather than probing a different protocol',async()=>{
    const f=fixture('companion',{writeError:true});await assert.rejects(detect(f,{timeouts:short}),{code:'LOST'});assert.equal(f.writes.length,1);
  });
  it('late native open after timeout is closed and blocked from concurrent reuse',async()=>{
    let release;const f=fixture('service',{openWait:new Promise(resolve=>{release=resolve;})});await assert.rejects(detect(f,{timeouts:short}),{code:'OPEN_TIMEOUT'});await assert.rejects(detect(f),{code:'BUSY'});release();await tick();await tick();assert.equal(f.opened,1);assert.equal(f.closed,1);assert.equal(f.writes.length,0);
  });
  it('adoption can be claimed only once and never reopens native port',async()=>{
    const f=fixture('companion'),r=await detect(f,{timeouts:short});await r.port.open(OPTIONS);await assert.rejects(r.port.open(OPTIONS),{code:'BUSY'});assert.equal(f.opened,1);await r.port.close();await r.port.close();assert.equal(f.closed,1);
  });
  it('abort from detected callback closes the unclaimed port',async()=>{
    const f=fixture('companion'),controller=new AbortController();await assert.rejects(detect(f,{timeouts:short,signal:controller.signal,onProgress:e=>{if(e.phase==='detected')controller.abort();}}),{code:'CANCELLED'});assert.equal(f.closed,1);
  });
  it('fixed settling delay exceeds firmware binary parser timeout',()=>{assert.equal(SETTLE_MS>2000,true);});
});
