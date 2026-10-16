'use strict';
// Production offline HTML, isolated browser, synthetic serial streams only.
// No physical device, USB permission or external network is used by this suite.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{chromium}=require('playwright');
const {installApiMock}=require('./test_api_fixture'),{fullSettingsFixture}=require('./test_full_settings_fixture');
const root=path.resolve(__dirname,'../..');
const output=process.env.SMARTUI_SIMPLE_UI_OUTPUT?path.resolve(process.env.SMARTUI_SIMPLE_UI_OUTPUT):fs.mkdtempSync(path.join(os.tmpdir(),'smartui-simple-ui-'));
const artifact=path.join(output,'SmartUI_USB_Helper_2.9.html');
const serviceSource=fs.readFileSync(path.join(__dirname,'test_ui.js'),'utf8');
const serviceStart=serviceSource.indexOf('function installSerialMock('),serviceEnd=serviceSource.indexOf('\nasync function fixture(',serviceStart);
assert.ok(serviceStart>=0&&serviceEnd>serviceStart,'Existing service mock boundary');
const installServiceMock=vm.runInNewContext('('+serviceSource.slice(serviceStart,serviceEnd).trim()+')');
let browser;

test.before(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const rendered=spawnSync(process.env.PYTHON||'python',['-c','from pathlib import Path; from tools.package_usb_helper import render; import sys; Path(sys.argv[1]).write_bytes(render())',artifact],{cwd:root,encoding:'utf8',windowsHide:true});
  assert.equal(rendered.status,0,rendered.stderr);
  const executablePath=[process.env.CHROME_PATH,'C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','/usr/bin/google-chrome','/usr/bin/chromium','/usr/bin/chromium-browser'].filter(Boolean).find(candidate=>fs.existsSync(candidate));
  browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});
  console.log('Simple Helper 2.9 browser artifacts: '+output);
});
test.after(async()=>{await browser?.close();});

async function fixture(transport='api',options={}){
  const context=await browser.newContext({viewport:{width:1440,height:1080},locale:'ru-RU'}),page=await context.newPage(),errors=[],network=[];
  page.setDefaultTimeout(6000);page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(/^https?:/i.test(request.url()))network.push(request.url());});
  const full=fullSettingsFixture(),schemas={...full.schemas,...options.schemas},settings={...full.settings,...options.settings},caps={...full.caps,...options.caps};
  const serviceCaps=Object.fromEntries(Object.entries({...caps,...options.settingsCaps}).filter(([key])=>['adc','sound','board_led','unread_led','vibration','gps','battery_protection','display','melody_max','adc_min','adc_max','adc_service'].includes(key)));
  if(transport==='api')await page.addInitScript(installApiMock,{console:1,control:1,meshcore:1,blePin:1,firmware:'0.20',soundPreview:true,manualAdc:true,...options,schemas,settings,caps});
  else await page.addInitScript(installServiceMock,{supported:true,settings:true,replies:true,radioFeature:true,manualAdc:true,soundPreview:true,
    info:'SmartUI=0.20 core=1.18.0 build=1234abcd upstream=81dbae59 capabilities=BLE,USB ble_pin=1 board=ProMicro DIY',
    ...options,readOnly:false,schemas,extendedValues:settings,settingsCaps:serviceCaps});
  await page.addInitScript(({transport,settings,readOnly})=>{
    const mock=window.__simpleMock=transport==='api'?window.__apiMock:window.__serialMock;
    if(transport!=='api')Object.assign(mock.settingsState,settings);
    // Native Web Serial clears both streams on close. The older shared mocks
    // predate automatic reopen, so supply that native contract in this suite.
    const close=mock.close.bind(mock);mock.close=async()=>{await close();mock.readable=null;mock.writable=null;};
    const method=transport==='api'?'reply':'emit',original=mock[method].bind(mock);
    mock[method]=(...args)=>{
      // Keep schema/get replies readable while reporting storage recovery.
      // The older mock's readOnly guard also rejects these harmless reads.
      if(transport!=='api'&&readOnly&&args[0].startsWith('Mode='))args[0]=args[0].replace('storage=ok','storage=recovery-required');
      if(mock.holdCommand&&mock.commands.at(-1)===mock.holdCommand){mock.holdCommand=null;mock.releaseHeld=()=>{mock.releaseHeld=null;original(...args);};return;}
      original(...args);
    };
  },{transport,settings,readOnly:options.readOnly});
  await page.goto(pathToFileURL(artifact).href);
  return {page,context,transport,async close(){await context.close();assert.deepEqual(errors,[],'Browser runtime errors');assert.deepEqual(network,[],'Offline helper made a network request');}};
}
async function connect(f){
  await f.page.locator('#view-advanced').click();
  await f.page.locator('#helper-mode').selectOption(f.transport==='api'?'api':'console');
  await f.page.locator('#connect').click();
  await f.page.waitForFunction(()=>{const state=SmartUiConsoleBridge.getContext();return state.connected&&!state.busy&&state.settings?.volume!==undefined;});
  await f.page.locator('#view-simple').click();
  await f.page.locator('#simple-fields').waitFor({state:'visible'});
}
const commands=page=>page.evaluate(()=>[...__simpleMock.commands]);
const writes=list=>list.filter(command=>/^set |^settings (?:set |name |tx set |radio set |advert set )|^ui (?:set |name |tx set |radio set |advert set )/.test(command));
const writeCommand=(transport,key,value)=>transport==='api'?'set '+key+' '+value:'settings set '+key+' '+value;
const readCommand=(transport,key)=>transport==='api'?'get '+key:'settings get '+key;
async function rendered(page){await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));}
async function saved(page,key){await page.waitForFunction(key=>!SmartUiConsoleBridge.getContext().busy&&!document.getElementById('simple-setting-'+key).disabled&&document.getElementById('simple-state-'+key).textContent.includes('Сохранено'),key);}
async function setSlider(page,value,event='change'){
  await page.locator('#simple-setting-volume').evaluate((element,{value,event})=>{element.value=String(value);element.dispatchEvent(new Event(event,{bubbles:true}));},{value,event});
}

test('simple view is the default, hides unread controls and never opens a port on load',async()=>{
  const f=await fixture();try{
    const p=f.page;assert.equal(await p.locator('#view-simple').getAttribute('aria-pressed'),'true');assert.equal(await p.locator('#connect').isVisible(),true);
    assert.equal(await p.locator('#helper-mode').isVisible(),false);assert.equal(await p.locator('#simple-fields').isVisible(),false);
    assert.equal(await p.evaluate(()=>__simpleMock.requests),0);assert.deepEqual(await commands(p),[]);
  }finally{await f.close();}
});

for(const transport of ['api','service']){
  test(transport+': one simple Connect detects the protocol and reads without writing',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await p.locator('#connect').click();
      await p.waitForFunction(()=>{const state=SmartUiConsoleBridge.getContext();return state.connected&&!state.busy&&state.settings?.volume!==undefined;});
      assert.equal(await p.evaluate(()=>SmartUiConsoleBridge.getContext().transport),transport==='api'?'companion':'service');
      assert.equal(await p.locator('#view-simple').getAttribute('aria-pressed'),'true');assert.equal(await p.locator('#simple-setting-volume').inputValue(),'7');
      assert.equal(await p.evaluate(()=>__simpleMock.requests),1);assert.deepEqual(writes(await commands(p)),[]);
    }finally{await f.close();}
  });

  test(transport+': reading and switching views display current values without writing',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);assert.equal(await p.locator('#simple-setting-volume').inputValue(),'7');assert.equal(await p.locator('#simple-setting-melody').inputValue(),'0');
      assert.equal(await p.locator('#simple-setting-sound_quiet').inputValue(),'0');assert.equal(await p.locator('#simple-setting-muted').inputValue(),'0');
      if(transport==='service'){assert.equal(await p.locator('#simple-setting-melody option').count(),31);assert.match(await p.locator('#simple-setting-melody option[value="18"]').textContent(),/Лебеди/);}
      await p.locator('#view-advanced').click();await p.locator('#view-simple').click();await rendered(p);
      assert.deepEqual(writes(await commands(p)),[]);assert.equal(await p.evaluate(()=>__simpleMock.requests),1);
    }finally{await f.close();}
  });

  test(transport+': selecting melody applies once without confirmation and requires readback',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);const before=(await commands(p)).length;
      await p.locator('#simple-setting-melody').selectOption('2');await saved(p,'melody');
      assert.equal(await p.locator('#confirm-yes').isVisible(),false);assert.match(await p.locator('#simple-status').textContent(),/Сохранено.*проверено/i);
      const sent=(await commands(p)).slice(before),mutation=writeCommand(transport,'melody',2);
      assert.deepEqual(writes(sent),[mutation]);assert.ok(sent.indexOf(readCommand(transport,'melody'))>sent.indexOf(mutation));
      assert.equal(Number(await p.evaluate(()=>SmartUiConsoleBridge.getContext().settings.melody)),2);
    }finally{await f.close();}
  });

  test(transport+': slider input previews locally; change commits the final value only',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);const before=(await commands(p)).length;
      await setSlider(p,3,'input');await setSlider(p,4,'input');await setSlider(p,5,'input');await rendered(p);
      assert.deepEqual(writes((await commands(p)).slice(before)),[]);assert.equal(Number(await p.evaluate(()=>SmartUiConsoleBridge.getContext().settings.volume)),7);
      await setSlider(p,5);await saved(p,'volume');assert.deepEqual(writes((await commands(p)).slice(before)),[writeCommand(transport,'volume',5)]);
    }finally{await f.close();}
  });

  test(transport+': simple save replaces its own advanced draft and preserves unrelated drafts',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);const before=(await commands(p)).length,prefix=transport==='api'?'api-':'';
      await p.locator('#view-advanced').click();await p.locator('[data-page-target="sound"]').click();
      await p.locator('#'+prefix+'setting-volume').selectOption('8');await p.locator('#'+prefix+'setting-board_led').selectOption('0');
      assert.deepEqual(writes((await commands(p)).slice(before)),[],'Advanced drafts do not autosave');
      await p.locator('#view-simple').click();assert.equal(await p.locator('#simple-setting-volume').inputValue(),'7');assert.equal(await p.locator('#simple-setting-board_led').inputValue(),'1');
      await setSlider(p,4);await saved(p,'volume');
      await p.locator('#view-advanced').click();await p.locator('[data-page-target="sound"]').click();
      assert.equal(await p.locator('#'+prefix+'setting-volume').inputValue(),'4');assert.equal(await p.locator('#'+prefix+'saved-volume').getAttribute('data-dirty'),'false');
      assert.equal(await p.locator('#'+prefix+'setting-board_led').inputValue(),'0');assert.equal(await p.locator('#'+prefix+'saved-board_led').getAttribute('data-dirty'),'true');
      assert.equal(Number(await p.evaluate(()=>SmartUiConsoleBridge.getContext().settings.board_led)),1);
      assert.deepEqual(writes((await commands(p)).slice(before)),[writeCommand(transport,'volume',4)]);
    }finally{await f.close();}
  });

  test(transport+': pending verification disables all simple controls and competing forms',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);const before=(await commands(p)).length;
      await p.evaluate(command=>__simpleMock.holdCommand=command,readCommand(transport,'volume'));await setSlider(p,4);
      await p.waitForFunction(()=>Boolean(__simpleMock.releaseHeld));
      const enabled=await p.locator('#simple-fields input:visible:not(:disabled),#simple-fields select:visible:not(:disabled),#simple-fields button:visible:not(:disabled)').count();assert.equal(enabled,0);
      assert.match(await p.locator('#simple-status').textContent(),/Применяем|проверяем/i);assert.equal(await p.evaluate(()=>SmartUiConsoleBridge.getContext().busy),true);
      assert.equal(await p.locator(transport==='api'?'#api-setting-volume':'#setting-volume').isDisabled(),true,'Advanced setting shares the same busy lease');
      assert.equal(await p.locator('#command-send').isDisabled(),true,'Console cannot interleave with verification');
      await p.evaluate(()=>__simpleMock.releaseHeld());await saved(p,'volume');assert.deepEqual(writes((await commands(p)).slice(before)),[writeCommand(transport,'volume',4)]);
    }finally{await f.close();}
  });

  test(transport+': read-only connection exposes no enabled write control',async()=>{
    const f=await fixture(transport,transport==='api'?{readonly:true}:{readOnly:true});try{
      const p=f.page;await connect(f);await rendered(p);
      assert.equal(await p.locator('#simple-fields input:visible:not(:disabled),#simple-fields select:visible:not(:disabled)').count(),0);assert.deepEqual(writes(await commands(p)),[]);
      assert.match(await p.locator('#simple-status').textContent(),/чтени/i);
    }finally{await f.close();}
  });

  test(transport+': headless and unsupported capabilities hide unavailable settings',async()=>{
    const full=fullSettingsFixture();
    const f=await fixture(transport,{caps:{display:0,board_led:0,unread_led:0},schemas:{...Object.fromEntries(['ui_theme','ui_font','backlight_timeout','board_led','unread_led'].map(key=>[key,{...full.schemas[key],supported:0}]))}});try{
      const p=f.page;await connect(f);
      for(const key of ['ui_theme','ui_font','backlight_timeout','board_led','unread_led','vibration'])assert.equal(await p.locator('#simple-setting-'+key).isVisible(),false,key+' unavailable');
      assert.equal(await p.locator('#simple-setting-melody').isVisible(),true);assert.deepEqual(writes(await commands(p)),[]);
      const shown=await p.locator('#simple-fields [id^="simple-setting-"]').evaluateAll(elements=>elements.filter(element=>element.getClientRects().length).map(element=>element.id.slice('simple-setting-'.length)));
      assert.ok(shown.every(key=>['muted','sound_quiet','volume','melody','board_led','unread_led','vibration','ui_theme','ui_font','backlight_timeout'].includes(key)));
    }finally{await f.close();}
  });

  test(transport+': wrong readback never reports success, disables further writes and never retries',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);const before=(await commands(p)).length;
      await p.evaluate(transport=>{
        const mock=__simpleMock,method=transport==='api'?'reply':'emit',original=mock[method].bind(mock);let changed=false;
        mock[method]=(...args)=>{
          const command=mock.commands.at(-1);if(command===(transport==='api'?'set volume 4':'settings set volume 4'))changed=true;
          if(changed&&command===(transport==='api'?'get volume':'settings get volume'))args[transport==='api'?1:0]=transport==='api'?'> 6':'OK settings get key=volume value=6';
          original(...args);
        };
      },transport);
      await setSlider(p,4);await p.waitForFunction(()=>!SmartUiConsoleBridge.getContext().busy);await rendered(p);
      assert.match(await p.locator('#simple-status').textContent(),/не подтвержден|переподключ|ошиб/i);assert.doesNotMatch(await p.locator('#simple-status').textContent(),/Сохранено.*проверено/i);
      assert.equal(await p.locator('#simple-fields input:visible:not(:disabled),#simple-fields select:visible:not(:disabled)').count(),0);
      assert.deepEqual(writes((await commands(p)).slice(before)),[writeCommand(transport,'volume',4)]);
    }finally{await f.close();}
  });

  test(transport+': disconnect during verification cannot mark saved or replay on reconnect',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);const before=(await commands(p)).length;
      await p.evaluate(command=>__simpleMock.holdCommand=command,readCommand(transport,'volume'));await setSlider(p,4);await p.waitForFunction(()=>Boolean(__simpleMock.releaseHeld));
      await p.evaluate(()=>__simpleMock.controller.error(new Error('private-serial-token-2749')));
      await p.waitForFunction(()=>!SmartUiConsoleBridge.getContext().busy&&!SmartUiConsoleBridge.getContext().connected);await rendered(p);
      assert.doesNotMatch(await p.locator('#simple-status').textContent(),/Сохранено.*проверено/i);assert.doesNotMatch(await p.locator('body').textContent(),/private-serial-token-2749/);
      assert.deepEqual(writes((await commands(p)).slice(before)),[writeCommand(transport,'volume',4)]);
      await connect(f);await rendered(p);assert.deepEqual(writes((await commands(p)).slice(before)),[writeCommand(transport,'volume',4)],'Reconnect only reads state');
    }finally{await f.close();}
  });

  test(transport+': simple Reconnect recovers an uncertain save without picker, replay or stale error',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);const before=(await commands(p)).length;
      await p.evaluate(transport=>{
        const mock=__simpleMock,method=transport==='api'?'reply':'emit',original=mock[method].bind(mock);let saved=false,badOnce=true;
        mock[method]=(...args)=>{
          const command=mock.commands.at(-1);if(command===(transport==='api'?'set volume 4':'settings set volume 4'))saved=true;
          if(saved&&badOnce&&command===(transport==='api'?'get volume':'settings get volume')){badOnce=false;args[transport==='api'?1:0]=transport==='api'?'> 6':'OK settings get key=volume value=6';}
          original(...args);
        };
      },transport);
      await setSlider(p,4);await p.waitForFunction(()=>!SmartUiConsoleBridge.getContext().busy);
      assert.match(await p.locator('#connect').textContent(),/Переподключить/);
      assert.match(await p.locator('#simple-status').textContent(),/не подтвержден|переподключ|ошиб/i);
      await p.locator('#connect').click();await p.waitForFunction(()=>{const state=SmartUiConsoleBridge.getContext();return state.connected&&!state.busy&&Number(state.settings?.volume)===4;});
      assert.equal(await p.locator('#view-simple').getAttribute('aria-pressed'),'true');assert.equal(await p.locator('#simple-setting-volume').inputValue(),'4');assert.equal(await p.locator('#simple-setting-volume').isEnabled(),true);
      assert.doesNotMatch(await p.locator('#simple-status').textContent(),/не подтвержден|переподключ|ошиб/i);assert.equal(await p.evaluate(()=>__simpleMock.requests),1,'Reuse the same authorized port');
      assert.deepEqual(writes((await commands(p)).slice(before)),[writeCommand(transport,'volume',4)]);
      await setSlider(p,5);await saved(p,'volume');assert.deepEqual(writes((await commands(p)).slice(before)),[writeCommand(transport,'volume',4),writeCommand(transport,'volume',5)]);
    }finally{await f.close();}
  });
}

test('PIN and advanced navigation open the dedicated forms without issuing writes',async()=>{
  const f=await fixture();try{
    const p=f.page;await connect(f);const before=(await commands(p)).length;
    await p.locator('#simple-pin').click();assert.equal(await p.locator('#view-advanced').getAttribute('aria-pressed'),'true');assert.equal(await p.locator('#node-pin-show').isVisible(),true);
    await p.locator('#view-simple').click();await p.locator('#simple-advanced').click();assert.equal(await p.locator('#view-advanced').getAttribute('aria-pressed'),'true');
    assert.deepEqual(writes((await commands(p)).slice(before)),[]);
  }finally{await f.close();}
});

test('simple view stays within 390/1440 viewports with usable controls and exports screenshots',async()=>{
  const f=await fixture();try{
    const p=f.page;await connect(f);
    await p.locator('#simple-fields').evaluate(fields=>{const caption=document.createElement('p');caption.className='hint';caption.textContent='Симуляция USB · не физическая плата';fields.before(caption);});
    const problems=[];
    for(const width of [390,1440]){
      await p.setViewportSize({width,height:width===1440?1000:844});await rendered(p);
      problems.push(...(await p.evaluate(()=>{
        const result=[];if(document.documentElement.scrollWidth>innerWidth+1)result.push('horizontal overflow');
        for(const element of document.querySelectorAll('#simple-fields,#simple-fields input,#simple-fields select,#simple-fields button,#simple-status,#connect,#simple-pin,#simple-advanced,#view-simple,#view-advanced')){
          if(!element.getClientRects().length||element.closest('[hidden]'))continue;
          const bounds=element.getBoundingClientRect();if(bounds.left< -1||bounds.right>innerWidth+1)result.push((element.id||element.tagName)+' outside viewport');
          if(['BUTTON','SELECT'].includes(element.tagName)&&bounds.height<43)result.push((element.id||element.tagName)+' tap target '+bounds.height);
        }
        return result;
      })).map(problem=>width+': '+problem));
      await p.screenshot({path:path.join(output,'helper-2.9-simple-'+(width===1440?'desktop':'mobile')+'.png'),fullPage:true});
    }
    assert.deepEqual(problems,[]);
  }finally{await f.close();}
});
