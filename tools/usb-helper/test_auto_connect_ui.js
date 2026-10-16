'use strict';
// Production offline HTML, isolated Chromium, synthetic USB streams only.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{chromium}=require('playwright');
const {installApiMock}=require('./test_api_fixture'),{fullSettingsFixture}=require('./test_full_settings_fixture');
const root=path.resolve(__dirname,'../..');
const output=process.env.SMARTUI_AUTO_UI_OUTPUT?path.resolve(process.env.SMARTUI_AUTO_UI_OUTPUT):fs.mkdtempSync(path.join(os.tmpdir(),'smartui-auto-ui-'));
const artifact=path.join(output,'SmartUI_USB_Helper_2.9.html');
const source=fs.readFileSync(path.join(__dirname,'test_ui.js'),'utf8');
const start=source.indexOf('function installSerialMock('),end=source.indexOf('\nasync function fixture(',start);
assert.ok(start>=0&&end>start,'Existing service mock boundary');
const installServiceMock=vm.runInNewContext('('+source.slice(start,end).trim()+')');
let browser;
test.before(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const rendered=spawnSync(process.env.PYTHON||'python',['-c','from pathlib import Path; from tools.package_usb_helper import render; import sys; Path(sys.argv[1]).write_bytes(render())',artifact],{cwd:root,encoding:'utf8',windowsHide:true});
  assert.equal(rendered.status,0,rendered.stderr);
  const executablePath=[process.env.CHROME_PATH,'C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','/usr/bin/google-chrome','/usr/bin/chromium'].filter(Boolean).find(p=>fs.existsSync(p));
  browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});
  console.log('Autoconnect 2.9 browser artifacts: '+output);
});
test.after(async()=>{await browser?.close();});

async function fixture(transport='companion',behavior='normal'){
  const context=await browser.newContext({viewport:{width:1440,height:1080},locale:'ru-RU'}),page=await context.newPage(),errors=[],network=[];
  page.setDefaultTimeout(12000);
  page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(/^https?:/i.test(request.url()))network.push(request.url());});
  const full=fullSettingsFixture();
  if(transport==='companion')await page.addInitScript(installApiMock,{console:1,control:1,meshcore:1,blePin:1,firmware:'0.20',soundPreview:true,manualAdc:true,...full});
  else await page.addInitScript(installServiceMock,{supported:true,settings:true,replies:true,radioFeature:true,manualAdc:true,soundPreview:true,info:'SmartUI=0.20 core=1.18.0 build=1234abcd upstream=81dbae59 capabilities=BLE,USB ble_pin=1 board=FakeTec',schemas:full.schemas,extendedValues:full.settings});
  await page.addInitScript(({transport,behavior,settings})=>{
    const mock=window.__autoMock=transport==='companion'?window.__apiMock:window.__serialMock;
    if(transport==='service')Object.assign(mock.settingsState,settings);
    mock.nativeOpens=0;mock.nativeCloses=0;mock.activeReaders=0;mock.peakReaders=0;mock.allWrites=[];mock.queryCount=0;
    const originalOpen=mock.open.bind(mock),originalClose=mock.close.bind(mock);
    mock.open=async options=>{
      mock.nativeOpens++;
      if(behavior==='open-error')throw new DOMException('PRIVATE_OPEN_TOKEN','NetworkError');
      await originalOpen(options);
      const getReader=mock.readable.getReader.bind(mock.readable);
      mock.readable.getReader=(...args)=>{const r=getReader(...args),release=r.releaseLock.bind(r);let held=true;mock.activeReaders++;mock.peakReaders=Math.max(mock.peakReaders,mock.activeReaders);r.releaseLock=()=>{release();if(held){held=false;mock.activeReaders--;}};return r;};
      const getWriter=mock.writable.getWriter.bind(mock.writable);
      mock.writable.getWriter=(...args)=>{const w=getWriter(...args),write=w.write.bind(w);w.write=bytes=>{mock.allWrites.push(Array.from(bytes));if(behavior==='silent')return Promise.resolve();if(behavior==='unplug'){mock.controller.error(new Error('PRIVATE_UNPLUG_TOKEN'));return Promise.resolve();}return write(bytes);};return w;};
    };
    mock.close=async()=>{mock.nativeCloses++;await originalClose();mock.readable=null;mock.writable=null;};
    if(transport==='companion'){
      const originalEmit=mock.emit.bind(mock);
      mock.emit=packet=>{if(packet[0]===13&&packet.length>=80){packet=packet.slice();new DataView(packet.buffer,packet.byteOffset,packet.byteLength).setUint32(4,654321,true);}originalEmit(packet);};
      const originalHandle=mock.handle.bind(mock);
      mock.handle=request=>{
        if(request[0]===22){mock.queryCount++;if(mock.queryCount===2&&behavior==='hold-handshake'){mock.releaseHandshake=()=>{mock.releaseHandshake=null;originalHandle(request);};return;}if(mock.queryCount===2&&behavior==='bad-handshake'){mock.emit(Uint8Array.of(1,1));return;}}
        originalHandle(request);
      };
    }else if(behavior==='hold-handshake'){
      const originalCommand=mock.command.bind(mock);let cancellations=0;
      mock.command=command=>{if(command==='cancel'&&++cancellations===2){mock.releaseHandshake=()=>{mock.releaseHandshake=null;originalCommand(command);};return;}originalCommand(command);};
    }
    if(behavior==='picker-cancel')Object.defineProperty(navigator,'serial',{configurable:true,value:{requestPort:async()=>{mock.requests++;throw new DOMException('PRIVATE_PICKER_TOKEN','NotFoundError');}}});
  },{transport,behavior,settings:full.settings});
  await page.goto(pathToFileURL(artifact).href);
  return {page,context,async close(){await context.close();assert.deepEqual(errors,[],'Browser runtime errors');assert.deepEqual(network,[],'Offline helper made a network request');}};
}
const snapshot=page=>page.evaluate(()=>({requests:__autoMock.requests,opens:__autoMock.nativeOpens,closes:__autoMock.nativeCloses,peakReaders:__autoMock.peakReaders,readers:__autoMock.activeReaders,commands:[...__autoMock.commands],writes:__autoMock.allWrites.map(bytes=>[...bytes]),queryCount:__autoMock.queryCount,connected:SmartUiConsoleBridge.getContext().connected,busy:SmartUiConsoleBridge.getContext().busy}));
const mutations=list=>list.filter(c=>/^set |^settings (?:set |name |tx set |radio set |advert set |adc (?:set|apply|reset|service start))|^ui (?:set |name |tx set |radio set |advert set |mode (?:ble|usb|wifi))/.test(c));
async function begin(page){assert.equal(await page.locator('#helper-mode').inputValue(),'auto');assert.equal(await page.locator('main').getAttribute('data-view'),'simple');await page.locator('#connect').click();}
async function ready(page){await page.waitForFunction(()=>{const s=SmartUiConsoleBridge.getContext();return s.connected&&!s.busy&&s.schemas.volume?.supported;});}
async function ended(page){await page.waitForFunction(()=>!document.getElementById('connect').disabled&&!SmartUiConsoleBridge.getContext().busy);}
async function noSecrets(page){assert.doesNotMatch(await page.locator('body').textContent(),/654.?321|PRIVATE_[A-Z_]+_TOKEN/);assert.doesNotMatch(await page.evaluate(()=>JSON.stringify(localStorage)),/654.?321|PRIVATE_[A-Z_]+_TOKEN/);}

for(const transport of ['companion','service'])test(transport+': default one-button connect detects protocol and loads values with one port picker/open',async()=>{
  const f=await fixture(transport);try{
    const p=f.page;await begin(p);await ready(p);const s=await snapshot(p);
    assert.equal(s.requests,1);assert.equal(s.opens,1);assert.equal(s.closes,0);assert.equal(s.peakReaders,1);assert.equal(s.readers,1);assert.deepEqual(mutations(s.commands),[]);
    assert.equal(await p.evaluate(()=>SmartUiConsoleBridge.getContext().transport),transport);
    assert.equal(s.writes.filter(bytes=>bytes.join(',')==='60,2,0,22,3').length,transport==='companion'?2:1,'Exactly one probe plus the binary SDK verification, no retries');
    await noSecrets(p);await p.locator('#view-advanced').click();await p.locator('#disconnect').click();await ended(p);assert.equal((await snapshot(p)).closes,1);
    await p.locator('#view-simple').click();await begin(p);await ready(p);const reopened=await snapshot(p);assert.equal(reopened.requests,2);assert.equal(reopened.opens,2);assert.equal(reopened.peakReaders,1);assert.deepEqual(mutations(reopened.commands),[]);await noSecrets(p);
  }finally{await f.close();}
});
test('unknown silent device fails closed, sends no mutations, and shows the actual detection error',async()=>{
  const f=await fixture('service','silent');try{
    const p=f.page;await begin(p);await ended(p);const s=await snapshot(p);
    assert.equal(s.connected,false);assert.equal(s.requests,1);assert.equal(s.opens,1);assert.equal(s.closes,1);assert.equal(s.writes.length,2);assert.equal(s.readers,0);assert.deepEqual(s.commands,[]);
    assert.match(await p.locator('#transport-state').textContent(),/Не удалось определить протокол/);await noSecrets(p);
  }finally{await f.close();}
});
test('cancel is visible in simple mode while detecting and does not hand off or retry',async()=>{
  const f=await fixture('companion');try{
    const p=f.page;await begin(p);await p.waitForFunction(()=>__autoMock.nativeOpens===1);assert.equal(await p.locator('#disconnect').isVisible(),true);
    await p.locator('#disconnect').click();await ended(p);const s=await snapshot(p);assert.equal(s.connected,false);assert.equal(s.closes,1);assert.equal(s.requests,1);assert.equal(s.writes.length,0);assert.equal(s.readers,0);await noSecrets(p);
  }finally{await f.close();}
});
test('disconnect during binary SDK handshake does not run initial setting requests or resurrect the session',async()=>{
  const f=await fixture('companion','hold-handshake');try{
    const p=f.page;await begin(p);await p.waitForFunction(()=>Boolean(__autoMock.releaseHandshake));await p.locator('#disconnect').click();await ended(p);
    await p.evaluate(()=>__autoMock.releaseHandshake());const s=await snapshot(p);assert.equal(s.connected,false);assert.equal(s.opens,1);assert.equal(s.closes,1);assert.equal(s.queryCount,2);assert.deepEqual(s.commands,[]);assert.equal(s.readers,0);await noSecrets(p);
  }finally{await f.close();}
});
test('disconnect during service SDK handshake leaves no background reads or resumed initialization',async()=>{
  const f=await fixture('service','hold-handshake');try{
    const p=f.page;await begin(p);await p.waitForFunction(()=>Boolean(__autoMock.releaseHandshake));await p.locator('#disconnect').click();await ended(p);
    const before=await snapshot(p);await p.evaluate(()=>__autoMock.releaseHandshake());const s=await snapshot(p);assert.equal(s.connected,false);assert.equal(s.opens,1);assert.equal(s.closes,1);assert.equal(s.readers,0);assert.deepEqual(s.commands.slice(before.commands.length),['cancel']);assert.equal(s.commands.some(c=>/^settings /.test(c)),false);await noSecrets(p);
  }finally{await f.close();}
});
test('repeated connect handler cannot create competing detection or picker requests',async()=>{
  const f=await fixture('companion');try{
    const p=f.page;await p.locator('#connect').evaluate(button=>{void button.onclick();void button.onclick();});await ready(p);const s=await snapshot(p);assert.equal(s.requests,1);assert.equal(s.opens,1);assert.equal(s.peakReaders,1);assert.equal(s.queryCount,2);assert.deepEqual(mutations(s.commands),[]);await noSecrets(p);
  }finally{await f.close();}
});
test('failed binary SDK verification remains visible after autodetection, with no settings reads/writes',async()=>{
  const f=await fixture('companion','bad-handshake');try{
    const p=f.page;await begin(p);await ended(p);const s=await snapshot(p);assert.equal(s.connected,false);assert.equal(s.closes,1);assert.deepEqual(s.commands,[]);
    assert.match(await p.locator('#transport-state').textContent(),/USB-компаньон|Текстовую консоль|некоррект|отклон|Ошибка|не подтвержд/i,'Initial handshake error must survive connection finalization');await noSecrets(p);
  }finally{await f.close();}
});
for(const behavior of ['open-error','picker-cancel'])test(behavior+': human-readable error, no protocol fallback or port writes',async()=>{
  const f=await fixture('service',behavior);try{
    const p=f.page;await begin(p);await ended(p);const s=await snapshot(p);assert.equal(s.requests,1);assert.equal(s.opens,behavior==='open-error'?1:0);assert.equal(s.writes.length,0);assert.equal(s.connected,false);
    assert.match(await p.locator('#transport-state').textContent(),behavior==='open-error'?/Порт недоступен|Не удалось открыть порт/:/Порт не выбран/);await noSecrets(p);
  }finally{await f.close();}
});
test('USB loss during probing closes and reports loss rather than trying the other protocol',async()=>{
  const f=await fixture('companion','unplug');try{
    const p=f.page;await begin(p);await ended(p);const s=await snapshot(p);assert.equal(s.writes.length,1);assert.equal(s.closes,1);assert.equal(s.connected,false);assert.equal(s.requests,1);assert.match(await p.locator('#transport-state').textContent(),/прервано/);await noSecrets(p);
  }finally{await f.close();}
});
test('beforeunload while probing aborts detection without opening a second session',async()=>{
  const f=await fixture('service');try{
    const p=f.page;await begin(p);await p.waitForFunction(()=>__autoMock.nativeOpens===1);await p.evaluate(()=>window.dispatchEvent(new Event('beforeunload')));await ended(p);const s=await snapshot(p);assert.equal(s.opens,1);assert.equal(s.closes,1);assert.equal(s.writes.length,0);assert.equal(s.connected,false);assert.equal(s.readers,0);
  }finally{await f.close();}
});
