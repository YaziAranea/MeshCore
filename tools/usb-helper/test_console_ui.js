'use strict';
// Production offline HTML in isolated Chromium, synthetic serial streams only.
// Optional NODE_PATH (Playwright), PYTHON, CHROME_PATH, SMARTUI_CONSOLE_UI_OUTPUT.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{chromium}=require('playwright');
const {installApiMock}=require('./test_api_fixture'),{fullSettingsFixture}=require('./test_full_settings_fixture');
const root=path.resolve(__dirname,'../..');
const output=process.env.SMARTUI_CONSOLE_UI_OUTPUT?path.resolve(process.env.SMARTUI_CONSOLE_UI_OUTPUT):fs.mkdtempSync(path.join(os.tmpdir(),'smartui-console-ui-'));
const artifact=path.join(output,'SmartUI_USB_Helper_2.9.html');
// Reuse the existing service wire fixture without registering its browser tests.
const serviceFixtureSource=fs.readFileSync(path.join(__dirname,'test_ui.js'),'utf8');
const serviceStart=serviceFixtureSource.indexOf('function installSerialMock('),serviceEnd=serviceFixtureSource.indexOf('\nasync function fixture(',serviceStart);
assert.ok(serviceStart>=0&&serviceEnd>serviceStart,'Existing service mock boundary');
const installServiceMock=vm.runInNewContext('('+serviceFixtureSource.slice(serviceStart,serviceEnd).trim()+')');
let browser;
test.before(async()=>{
  fs.mkdirSync(output,{recursive:true});
  // Same render() used by package(); documentation/screenshots are tested by
  // package tests separately and are not dependencies of browser behavior.
  const rendered=spawnSync(process.env.PYTHON||'python',['-c',
    'from pathlib import Path; from tools.package_usb_helper import render; import sys; Path(sys.argv[1]).write_bytes(render())',artifact],
    {cwd:root,encoding:'utf8',windowsHide:true});
  assert.equal(rendered.status,0,rendered.stderr);
  const executablePath=[process.env.CHROME_PATH,'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','/usr/bin/google-chrome','/usr/bin/chromium','/usr/bin/chromium-browser'].filter(Boolean).find(p=>fs.existsSync(p));
  browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});
  console.log('Console 2.8 browser artifacts: '+output);
});
test.after(async()=>{await browser?.close();});

async function fixture(transport='api',options={}){
  const context=await browser.newContext({viewport:{width:1440,height:1080},locale:'ru-RU',acceptDownloads:true});
  const page=await context.newPage(),errors=[],network=[];
  page.setDefaultTimeout(5000);
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(/^https?:/i.test(request.url()))network.push(request.url());});
  const full=fullSettingsFixture();
  if(transport==='api')await page.addInitScript(installApiMock,{console:1,control:1,meshcore:1,blePin:1,firmware:'0.20',soundPreview:true,manualAdc:true,...full,...options});
  else await page.addInitScript(installServiceMock,{supported:true,settings:true,replies:true,radioFeature:true,manualAdc:true,soundPreview:true,
    info:'SmartUI=0.20 core=1.18.0 build=1234abcd upstream=81dbae59 capabilities=BLE,USB ble_pin=1 board=ProMicro DIY',
    settingsCaps:{display:1,gps:1,adc_service:1},schemas:full.schemas,extendedValues:full.settings,...options});
  await page.addInitScript(({transport,settings})=>{
    const mock=window.__consoleMock=transport==='api'?window.__apiMock:window.__serialMock;
    if(transport!=='api')Object.assign(mock.settingsState,settings);
    const method=transport==='api'?'reply':'emit',original=mock[method].bind(mock);
    mock[method]=(...args)=>{
      if(mock.holdCommand&&mock.commands.at(-1)===mock.holdCommand){
        mock.holdCommand=null;mock.releaseHeld=()=>{mock.releaseHeld=null;original(...args);};return;
      }
      original(...args);
    };
  },{transport,settings:full.settings});
  await page.goto(pathToFileURL(artifact).href);
  await page.locator('#view-advanced').click();
  await page.locator('#helper-mode').selectOption(transport==='api'?'api':'console');
  return {page,context,transport,async close(){await context.close();assert.deepEqual(errors,[],'Browser runtime errors');assert.deepEqual(network,[],'Offline helper made a network request');}};
}
async function connect(f){
  await f.page.locator('#connect').click();
  await f.page.waitForFunction(()=>{const c=SmartUiConsoleBridge.getContext();return c.connected&&!c.busy&&c.schemas.volume?.supported;});
  await f.page.locator('[data-page-target="console"]').click();
  await f.page.locator('#command-input').waitFor({state:'visible'});
}
const commands=page=>page.evaluate(()=>[...__consoleMock.commands]);
async function idle(page){await page.waitForFunction(()=>document.getElementById('command-stop').disabled&&!SmartUiConsoleBridge.getContext().busy);}
async function send(page,text){await page.locator('#command-input').fill(text);await page.locator('#command-send').click();}
async function confirm(page,yes=true){await page.locator(yes?'#confirm-yes':'#confirm-no').click();}
async function downloadText(page,selector){
  const pending=page.waitForEvent('download');await page.locator(selector).click();const download=await pending;
  return fs.readFileSync(await download.path(),'utf8');
}
const writes=list=>list.filter(command=>/^set |^settings (?:set |name |tx set |radio set |advert set )|^ui (?:set |name |tx set |radio set |advert set )/.test(command));

for(const transport of ['api','service']){
  test(transport+': built-in read macro and input use current port, read-only commands and history',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);
      const before=(await commands(p)).length;
      await p.locator('[data-command-group="power"]').click();await p.locator('[data-action-id="battery"]').click();await p.locator('#command-run').click();await idle(p);
      assert.match(await p.locator('#command-status').textContent(),/Готово: 2 шагов/);
      assert.deepEqual((await commands(p)).slice(before),transport==='api'?['get battery','get shutdown_mv']:['settings get battery_mv','settings get shutdown_mv']);
      await send(p,'get volume');await idle(p);assert.match(await p.locator('#command-journal').textContent(),/get volume/);
      await p.locator('#command-input').press('ArrowUp');assert.equal(await p.locator('#command-input').inputValue(),'get volume');
      assert.equal(writes((await commands(p)).slice(before)).length,0);
      assert.equal(await p.evaluate(()=>__consoleMock.requests),1);
    }finally{await f.close();}
  });

  test(transport+': scalar write needs confirmation, matched readback and updates settings form',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);const before=(await commands(p)).length;
      await send(p,'set volume 3\nget volume');
      assert.deepEqual((await commands(p)).slice(before),[],'Confirmation must precede every serial request');
      await confirm(p);await idle(p);
      assert.match(await p.locator('#command-status').textContent(),/Готово: 2 шагов/);
      assert.match(await p.locator('#command-journal').textContent(),/Сохранение проверено чтением обратно/);
      const sent=(await commands(p)).slice(before),mutation=transport==='api'?'set volume 3':'settings set volume 3';
      assert.deepEqual(writes(sent),[mutation]);
      assert.ok(sent.indexOf(transport==='api'?'get volume':'settings get volume')>sent.indexOf(mutation));
      assert.equal(await p.evaluate(()=>SmartUiConsoleBridge.getContext().settings.volume),transport==='api'?'3':3);
      await p.locator('[data-page-target="sound"]').click();
      assert.equal(await p.locator(transport==='api'?'#api-setting-volume':'#setting-volume').inputValue(),'3');
    }finally{await f.close();}
  });

  test(transport+': cancelled writes and invalid late commands send nothing',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);const before=(await commands(p)).length;
      await send(p,'set volume 3\nget volume');await confirm(p,false);await idle(p);
      assert.match(await p.locator('#command-status').textContent(),/отменено/);
      assert.deepEqual((await commands(p)).slice(before),[]);
      await send(p,'set volume 3\nunknown late command');
      assert.equal(await p.locator('#command-status').getAttribute('data-kind'),'error');
      assert.deepEqual((await commands(p)).slice(before),[]);
      assert.doesNotMatch(await p.locator('#command-journal').textContent(),/set volume 3|unknown late command/);
    }finally{await f.close();}
  });

  test(transport+': contradictory write readback stops macro, invalidates session and never retries',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);const before=(await commands(p)).length;
      await p.evaluate(transport=>{
        const mock=__consoleMock,method=transport==='api'?'reply':'emit',original=mock[method].bind(mock);let saved=false;
        mock[method]=(...args)=>{
          const command=mock.commands.at(-1);
          if(command===(transport==='api'?'set volume 3':'settings set volume 3'))saved=true;
          if(saved&&command===(transport==='api'?'get volume':'settings get volume'))args[transport==='api'?1:0]=transport==='api'?'> 4':'OK settings get key=volume value=4';
          original(...args);
        };
      },transport);
      await send(p,'set volume 3\nget battery');await confirm(p);
      await p.waitForFunction(()=>document.getElementById('command-stop').disabled);
      assert.equal(await p.locator('#command-status').getAttribute('data-kind'),'error');
      assert.equal(await p.locator('#command-send').isDisabled(),true);
      const sent=(await commands(p)).slice(before);
      assert.deepEqual(writes(sent),[transport==='api'?'set volume 3':'settings set volume 3']);
      assert.equal(sent.includes(transport==='api'?'get battery':'settings get battery_mv'),false,'No following macro step after uncertain save');
      assert.doesNotMatch(await p.locator('#command-journal').textContent(),/Сохранение проверено чтением обратно/);
    }finally{await f.close();}
  });

  test(transport+': Stop waits for current reply and suppresses following commands',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);const before=(await commands(p)).length;
      await p.evaluate(command=>__consoleMock.holdCommand=command,transport==='api'?'get battery':'settings get battery_mv');
      await send(p,'get battery\nget volume');await p.waitForFunction(()=>Boolean(__consoleMock.releaseHeld));
      await p.locator('#command-stop').click();assert.match(await p.locator('#command-status').textContent(),/Остановка запрошена/);
      await p.evaluate(()=>__consoleMock.releaseHeld());await idle(p);
      assert.match(await p.locator('#command-status').textContent(),/Остановлено/);
      assert.deepEqual((await commands(p)).slice(before),[transport==='api'?'get battery':'settings get battery_mv']);
    }finally{await f.close();}
  });

  test(transport+': unplug stops macro, blocks commands and does not leak transport exception',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);const before=(await commands(p)).length;
      await p.evaluate(command=>__consoleMock.holdCommand=command,transport==='api'?'get battery':'settings get battery_mv');
      await send(p,'get battery\nset volume 3');await confirm(p);await p.waitForFunction(()=>Boolean(__consoleMock.releaseHeld));
      await p.evaluate(()=>__consoleMock.controller.error(new Error('private-usb-token-9387')));
      await p.waitForFunction(()=>document.getElementById('command-stop').disabled);
      assert.equal(await p.locator('#command-send').isDisabled(),true);
      assert.equal(writes((await commands(p)).slice(before)).length,0);
      assert.doesNotMatch(await p.locator('body').textContent(),/private-usb-token-9387/);
      assert.match(await p.locator('#command-journal').textContent(),/остановлено|закрыто|прервано/i);
    }finally{await f.close();}
  });

  test(transport+': PIN stays in dedicated form, rejected secret commands never enter journal/history/storage',async()=>{
    const f=await fixture(transport);try{
      const p=f.page;await connect(f);
      await p.locator('[data-page-target="connection"]').click();await p.locator('#node-pin-show').click();
      await p.waitForFunction(()=>document.getElementById('node-pin-value').textContent==='654 321');
      await p.locator('[data-page-target="console"]').click();assert.equal(await p.locator('#node-pin-value').textContent(),'••• •••');
      const before=(await commands(p)).length;
      for(const text of ['get pin','set pin 654321','wifi password secret-pass-934','set volume 3\nget ble.pin']){
        await send(p,text);assert.equal(await p.locator('#command-status').getAttribute('data-kind'),'error');
      }
      assert.deepEqual((await commands(p)).slice(before),[]);
      await p.locator('#command-input').fill('');await p.locator('#command-input').press('ArrowUp');assert.equal(await p.locator('#command-input').inputValue(),'');
      const journal=await downloadText(p,'#command-log-save');assert.doesNotMatch(journal,/654.?321|secret-pass-934|get pin|get ble\.pin/);
      assert.doesNotMatch(await p.evaluate(()=>JSON.stringify(localStorage)),/654.?321|secret-pass-934/);
      assert.doesNotMatch(await p.locator('#command-journal').textContent(),/654.?321|secret-pass-934/);
    }finally{await f.close();}
  });
}

test('readonly Companion refuses macros before requests; readonly service permits safe reads',async()=>{
  const api=await fixture('api',{readonly:true});try{
    const p=api.page;await connect(api);const before=(await commands(p)).length;
    await send(p,'set volume 3');assert.equal(await p.locator('#command-status').getAttribute('data-kind'),'error');
    assert.deepEqual((await commands(p)).slice(before),[]);await send(p,'get volume');await idle(p);
    assert.match(await p.locator('#command-status').textContent(),/Готово/);
  }finally{await api.close();}
  const service=await fixture('service');try{
    const p=service.page;await connect(service);
    await p.evaluate(()=>{const emit=__consoleMock.emit.bind(__consoleMock);__consoleMock.emit=text=>emit(text.startsWith('Mode=')?text.replace('storage=ok','storage=recovery-required'):text);});
    await send(p,'connection status');await idle(p);const before=(await commands(p)).length;
    await send(p,'set volume 3');assert.equal(await p.locator('#command-status').getAttribute('data-kind'),'error');
    assert.deepEqual((await commands(p)).slice(before),[]);await send(p,'get volume');await idle(p);
    assert.match(await p.locator('#command-status').textContent(),/Готово/);
  }finally{await service.close();}
});

test('custom macros save/reload/export/import safely, with no execution or secret persistence',async()=>{
  const f=await fixture('api');try{
    const p=f.page;await connect(f);const before=(await commands(p)).length;
    await p.locator('#command-editor summary').click();
    await p.locator('#macro-name').fill('Мой звук');await p.locator('#macro-description').fill('Читать громкость');await p.locator('#macro-commands').fill('get volume');await p.locator('#macro-save').click();
    assert.match(await p.locator('#macro-status').textContent(),/сохранён/);
    await p.locator('#command-favorite').click();
    const exported=JSON.parse(await downloadText(p,'#macro-export'));
    assert.equal(exported.version,1);assert.equal(exported.macros[0].name,'Мой звук');assert.deepEqual(exported.macros[0].commands,['get volume']);
    assert.deepEqual(exported.favorites,[exported.macros[0].id]);
    assert.equal(Object.hasOwn(exported,'history'),false);assert.equal(Object.hasOwn(exported,'logs'),false);
    await p.locator('#macro-new').click();await p.locator('#macro-name').fill('PIN');await p.locator('#macro-commands').fill('get pin');await p.locator('#macro-save').click();
    assert.equal(await p.locator('#macro-status').getAttribute('data-kind'),'error');
    const importFile=async library=>p.locator('#macro-import').setInputFiles({name:'macros.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(library))});
    const malicious={version:1,macros:[{id:'user:notimported',name:'Earlier valid macro',commands:['get volume']},{id:'user:bad1',name:'Secret',commands:['set pin 654321']}],favorites:[]};
    await importFile(malicious);await p.waitForFunction(()=>document.getElementById('macro-status').dataset.kind==='error');
    assert.doesNotMatch(await p.evaluate(()=>localStorage.getItem('smartui.helper.macros.v1')),/654321|Secret|notimported/,'Import is all-or-nothing');
    await importFile({version:1,macros:[{id:'user:good1',name:'Импорт',description:'Только чтение',commands:['get battery']}],favorites:[]});
    await p.waitForFunction(()=>document.getElementById('macro-status').textContent.includes('Добавлено макросов: 1'));
    assert.deepEqual((await commands(p)).slice(before),[],'Save/import/export do not execute commands');
    await p.reload();await p.locator('#view-advanced').click();await p.locator('[data-page-target="console"]').click();await p.locator('[data-command-group="custom"]').click();
    assert.equal(await p.locator('[data-action-id="user:good1"]').count(),1);
    assert.match(await p.locator('#command-leaves').textContent(),/Мой звук/);
    assert.doesNotMatch(await p.locator('#command-journal').textContent(),/654321|Secret/);
    assert.equal(await p.evaluate(()=>__consoleMock.requests),0,'Reload never reconnects automatically');
  }finally{await f.close();}
});

test('console remains inside 320/390/1440 viewports and exports diagnostic screenshots',async()=>{
  const f=await fixture('api');try{
    const p=f.page;await connect(f);await send(p,'get battery');await idle(p);
    await p.locator('#command-console .command-head').evaluate(header=>{
      const caption=document.createElement('p');caption.className='hint';caption.textContent='Симуляция USB · не физическая плата';header.firstElementChild.append(caption);
    });
    const allProblems=[];
    for(const width of [320,390,1440]){
      await p.setViewportSize({width,height:width===1440?1000:844});
      const problems=await p.evaluate(()=>{
        const result=[];
        if(document.documentElement.scrollWidth>innerWidth+1)result.push('horizontal overflow');
        for(const element of document.querySelectorAll('#command-console,#command-console button,#command-input,#command-search')){
          if(!element.getClientRects().length||element.closest('[hidden]'))continue;
          const r=element.getBoundingClientRect();if(r.left< -1||r.right>innerWidth+1)result.push((element.id||element.textContent)+' outside viewport');
          if(element.tagName==='BUTTON'&&r.height<43)result.push((element.id||element.textContent)+' tap target '+r.height);
        }
        const label=document.createRange();label.selectNodeContents(document.getElementById('command-send'));
        if(label.getClientRects().length!==1)result.push('Execute button label wraps');
        return result;
      });
      await p.screenshot({path:path.join(output,'helper-2.8-console-'+width+'.png'),fullPage:true});
      await p.locator('#command-console').screenshot({path:path.join(output,'helper-2.8-command-tree-'+(width===1440?'desktop':width===390?'mobile':'narrow')+'.png')});
      allProblems.push(...problems.map(problem=>width+': '+problem));
    }
    assert.deepEqual(allProblems,[]);
  }finally{await f.close();}
});
