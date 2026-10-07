'use strict';
// Browser-only simulation against the packaged offline application.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{chromium}=require('playwright');
const {installApiMock}=require('./test_api_fixture');
const root=path.resolve(__dirname,'../..'),output=process.env.SMARTUI_API_UI_OUTPUT?path.resolve(process.env.SMARTUI_API_UI_OUTPUT):fs.mkdtempSync(path.join(os.tmpdir(),'smartui-api-ui-'));
const artifact=path.join(output,'SmartUI_USB_Helper_1.7.html');let browser;
test.before(async()=>{
  const p=spawnSync(process.env.PYTHON||'python',[path.join(root,'tools/package_usb_helper.py'),output],{encoding:'utf8',windowsHide:true});assert.equal(p.status,0,p.stderr);
  const executablePath=[process.env.CHROME_PATH,'C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','/usr/bin/google-chrome','/usr/bin/chromium'].filter(Boolean).find(p=>fs.existsSync(p));
  browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});console.log('API browser artifacts: '+output);
});
test.after(async()=>{await browser?.close();});
async function fixture(options={}){
  const context=await browser.newContext({viewport:{width:1440,height:1080},locale:'ru-RU'}),page=await context.newPage(),errors=[],network=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))network.push(r.url());});
  if(options.clock)await page.clock.install({time:new Date('2026-01-01T12:00:00Z')});
  await page.addInitScript(installApiMock,options);await page.goto(pathToFileURL(artifact).href);await page.locator('#helper-mode').selectOption('api');
  return {page,async close(){await context.close();assert.deepEqual(errors,[]);assert.deepEqual(network,[]);}};
}
async function connect(page){await page.locator('#connect').click();await page.waitForFunction(()=>document.getElementById('api-settings-status').textContent==='Прочитано с ноды'&&!document.getElementById('api-settings-load').disabled);}

async function ready(page){await page.waitForFunction(()=>!document.getElementById('api-settings-load').disabled);}
async function geometry(page){
  const problems=await page.evaluate(()=>{
    const result=[],visible=e=>e.getClientRects().length&&!e.closest('[hidden]');
    if(document.documentElement.scrollWidth>innerWidth+1)result.push('horizontal overflow');
    for(const e of document.querySelectorAll('.card,.transport-dock,header'))if(visible(e)){const r=e.getBoundingClientRect();if(r.left<0||r.right>innerWidth+1)result.push(e.id+' outside viewport');}
    for(const b of document.querySelectorAll('button'))if(visible(b)&&b.getBoundingClientRect().height<43)result.push(b.id+' small tap target');
    return result;
  });assert.deepEqual(problems,[]);
}

test('ADC service CLI explicit start, source expiry, save and disconnect with one writer',async()=>{
  const f=await fixture({caps:{adc_service:1}});try{const p=f.page;await connect(p);
    await p.locator('#api-adc summary').click();
    assert.equal(await p.locator('#api-adc-service-box').isVisible(),true);
    assert.equal(await p.evaluate(()=>__apiMock.commands.some(c=>c==='ui adc service start')),false);
    await p.locator('#api-adc-service-start').click();await p.locator('#confirm-no').click();
    assert.equal(await p.evaluate(()=>__apiMock.commands.some(c=>c==='ui adc service start')),false);
    await p.locator('#api-adc-service-start').click();await p.locator('#confirm-yes').click();await ready(p);
    assert.match(await p.locator('#api-adc-service-status').textContent(),/Окно активно/);
    await p.evaluate(()=>__apiMock.adcSourceMissing=true);
    await p.locator('#api-adc-measured').fill('3.82');await p.locator('#api-adc-preview').click();await ready(p);
    assert.match(await p.locator('#api-feedback').textContent(),/ProMicro.*2 минут/);
    assert.equal(await p.locator('#api-adc-apply').isDisabled(),true);
    assert.equal(await p.evaluate(()=>__apiMock.commands.some(c=>c.startsWith('ui adc apply'))),false);
    await p.evaluate(()=>{__apiMock.adcSourceMissing=false;__apiMock.adcServiceDeadline=Date.now()+31000;});
    await p.locator('#api-adc-service-refresh').click();await ready(p);
    assert.match(await p.locator('#api-adc-service-status').textContent(),/31 с/);
    await p.locator('#api-adc-preview').click();await ready(p);await p.locator('#api-adc-apply').click();await p.locator('#confirm-yes').click();await ready(p);
    assert.match(await p.locator('#api-adc-service-status').textContent(),/Окно выключено/);
    assert.equal(await p.evaluate(()=>__apiMock.settings.battery_protection),1);
    await p.locator('#api-adc-service-start').click();await p.locator('#confirm-yes').click();await ready(p);
    await geometry(p);await p.locator('#api-adc').screenshot({path:path.join(output,'helper-1.7-cli-adc-desktop.png')});
    await p.setViewportSize({width:390,height:844});await geometry(p);await p.locator('#api-adc').screenshot({path:path.join(output,'helper-1.7-cli-adc-mobile.png')});
    await p.locator('#disconnect').click();await p.waitForFunction(()=>__apiMock.closed);
    assert.equal(await p.evaluate(()=>__apiMock.commands.filter(c=>c==='ui adc service stop').length),1);
    assert.equal(await p.locator('#api-adc-measured').inputValue(),'');
  }finally{await f.close();}
});

test('ADC service CLI firmware timeout never resumes; unsupported capability stays hidden',async()=>{
  const old=await fixture();try{await connect(old.page);assert.equal(await old.page.locator('#api-adc-service-box').isHidden(),true);
    assert.equal(await old.page.evaluate(()=>__apiMock.commands.some(c=>c==='ui adc service')),false);
  }finally{await old.close();}
  const f=await fixture({caps:{adc_service:1},clock:true});try{const p=f.page;await connect(p);await p.locator('#api-adc summary').click();
    await p.locator('#api-adc-service-start').click();await p.locator('#confirm-yes').click();await ready(p);
    await p.locator('#api-adc-measured').fill('3.82');await p.locator('#api-adc-preview').click();await ready(p);
    await p.clock.fastForward(125000);await ready(p);
    await p.waitForFunction(()=>document.getElementById('api-adc-service-status').textContent.includes('Окно выключено'));
    assert.equal(await p.locator('#api-adc-apply').isDisabled(),true);
    assert.equal(await p.evaluate(()=>__apiMock.commands.filter(c=>c==='ui adc service start').length),1);
  }finally{await f.close();}
});

test('ADC preview expiring during confirmation cannot send a stale apply',async()=>{
  const f=await fixture({caps:{adc_service:1},clock:true});try{const p=f.page;await connect(p);await p.locator('#api-adc summary').click();
    await p.locator('#api-adc-service-start').click();await p.locator('#confirm-yes').click();await ready(p);
    await p.locator('#api-adc-measured').fill('3.82');await p.locator('#api-adc-preview').click();await ready(p);
    await p.locator('#api-adc-apply').click();await p.clock.fastForward(125000);await ready(p);
    await p.locator('#confirm-yes').click();
    assert.match(await p.locator('#api-adc-result').textContent(),/Расчёт устарел/);
    assert.equal(await p.evaluate(()=>__apiMock.commands.some(c=>c.startsWith('ui adc apply'))),false);
  }finally{await f.close();}
});

test('CLI settings-only handshake, one reader, hidden unsupported hardware',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);
    assert.equal(await p.locator('#helper-mode').isDisabled(),true);assert.equal(await p.locator('#device-section').isVisible(),false);
    for(const id of ['api-sync-enable','api-inbox','api-events','api-fetch'])assert.equal(await p.locator('#'+id).count(),0);
    assert.equal(await p.evaluate(()=>window.__apiMock.readerCount),1);assert.equal(await p.evaluate(()=>window.__apiMock.maxOpen),1);
    assert.equal(await p.locator('#api-setting-fem_pa').count(),0);assert.equal(await p.locator('#api-setting-agc_reset').isVisible(),true);
    assert.equal(await p.locator('#api-setting-melody option[value="0"]').textContent(),'0 · Пульс');
    await p.locator('#api-notify-test').click();await ready(p);
    assert.match(await p.locator('#api-feedback').textContent(),/Команда теста принята/);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.filter(c=>c==='ui test').length),1);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.every(c=>c.startsWith('ui '))),true);
    assert.equal(await p.evaluate(()=>window.__apiMock.packets.every(p=>[22,40,66].includes(p[0]))),true);
    await p.locator('#disconnect').click();assert.equal(await p.evaluate(()=>window.__apiMock.closed),true);
    await p.locator('#helper-mode').selectOption('console');assert.equal(await p.locator('#device-section').isVisible(),true);
  }finally{await f.close();}
});

test('city preset confirmation, atomic apply and readback preserve power/repeat/path; advert intervals match node',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);
    await p.locator('#preset-search').fill('Омск');
    assert.ok(await p.locator('#preset-city option').count()>=2);
    await p.locator('#preset-city').selectOption({index:1});
    assert.match(await p.locator('#preset-preview').textContent(),/МГц/);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.some(c=>c.startsWith('ui radio set'))),false);
    await p.locator('#preset-apply').click();await p.locator('#confirm-no').click();
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.some(c=>c.startsWith('ui radio set'))),false);
    // Change path length on the node after preview; applying a city must keep it.
    await p.evaluate(()=>window.__apiMock.radio.path_bytes=3);
    await p.locator('#preset-apply').click();await p.locator('#confirm-yes').click();
    await p.waitForFunction(()=>document.getElementById('radio-status').textContent.includes('прочитан обратно'));
    const result=await p.evaluate(()=>({radio:window.__apiMock.radio,city:SmartUiPresets.get(document.getElementById('preset-city').value),commands:window.__apiMock.commands}));
    assert.equal(result.radio.freq_khz,result.city.frequencyKHz);assert.equal(result.radio.bw_hz,result.city.bandwidthHz);
    assert.equal(result.radio.path_bytes,3);assert.equal(result.radio.tx_dbm,20);assert.equal(result.radio.repeat,0);
    assert.equal(result.commands.filter(c=>c.startsWith('ui radio set')).length,1);
    assert.deepEqual(await p.locator('#advert-interval option').evaluateAll(options=>options.map(o=>Number(o.value))),[0,15,30,60,120,180]);
    await p.locator('#advert-interval').selectOption('120');await p.locator('#advert-save').click();await p.locator('#confirm-yes').click();
    await p.waitForFunction(()=>document.getElementById('radio-status').textContent.includes('Интервал автоанонса сохранён'));
    assert.equal(await p.evaluate(()=>window.__apiMock.advert.interval_min),120);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.filter(c=>c==='ui advert set 120').length),1);
    await p.locator('#preset-search').fill('не существующий город');assert.equal(await p.locator('#preset-apply').isDisabled(),true);
  }finally{await f.close();}
});

test('old firmware and readonly retain other controls, preset failures never fake success',async()=>{
  for(const options of [{network:false},{readonly:true},{}]){
    const f=await fixture(options);try{const p=f.page;await connect(p);await p.locator('#preset-city').selectOption({index:1});
      if(options.network===false||options.readonly){assert.equal(await p.locator('#preset-apply').isDisabled(),true);assert.equal(await p.locator('#advert-save').isDisabled(),true);assert.equal(await p.locator('#api-settings-load').isDisabled(),false);}
      else{await p.evaluate(()=>window.__apiMock.networkError='repeat');await p.locator('#preset-apply').click();await p.locator('#confirm-yes').click();await p.waitForFunction(()=>document.getElementById('radio-status').dataset.kind==='error');assert.match(await p.locator('#radio-status').textContent(),/ретрансляция несовместима/);assert.equal(await p.evaluate(()=>window.__apiMock.radio.freq_khz),869525);assert.equal(await p.evaluate(()=>window.__apiMock.commands.filter(c=>c.startsWith('ui radio set')).length),1);}
    }finally{await f.close();}
  }
});

test('radio ACK lost: no automatic retry and writes blocked until reconnect',async()=>{
  const f=await fixture({clock:true});try{const p=f.page;await connect(p);await p.locator('#preset-city').selectOption({index:1});await p.locator('#preset-apply').click();
    await p.evaluate(()=>{const original=window.__apiMock.reply;window.__apiMock.reply=function(tag,text){if(this.commands.at(-1).startsWith('ui radio set'))return;original.call(this,tag,text);};});
    await p.locator('#confirm-yes').click();await p.waitForFunction(()=>window.__apiMock.commands.some(c=>c.startsWith('ui radio set')));await p.clock.runFor(6500);
    assert.equal(await p.locator('#preset-apply').isDisabled(),true);assert.match(await p.locator('#radio-status').textContent(),/неизвестен/);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.filter(c=>c.startsWith('ui radio set')).length),1);
  }finally{await f.close();}
});

test('successful radio ACK followed by readback error is uncertain and blocks writes',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);await p.locator('#preset-city').selectOption('OMS');
    await p.evaluate(()=>{const original=window.__apiMock.reply;window.__apiMock.reply=function(tag,text){if(this.commands.at(-1).startsWith('ui radio set'))this.afterRadioSave=true;else if(this.afterRadioSave&&this.commands.at(-1)==='ui radio')text='ERR ui busy';original.call(this,tag,text);};});
    await p.locator('#preset-apply').click();await p.locator('#confirm-yes').click();await p.waitForFunction(()=>document.getElementById('transport-state').textContent.includes('Результат неизвестен'));
    assert.equal(await p.locator('#preset-apply').isDisabled(),true);assert.equal(await p.locator('#api-settings-load').isDisabled(),true);assert.match(await p.locator('#radio-status').textContent(),/не подтверждена/);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.filter(c=>c.startsWith('ui radio set')).length),1);
  }finally{await f.close();}
});
test('desktop/mobile geometry and simulated screenshots',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);
    await p.evaluate(()=>{scrollTo(0,0);const badge=document.createElement('div');badge.id='simulation-watermark';badge.textContent='Симуляция USB · тестовые данные';badge.style.cssText='position:fixed;right:12px;bottom:12px;z-index:1000;background:#203744;color:#edf2f7;border:1px solid #91b8c1;border-radius:7px;padding:7px 10px;font:12px system-ui;';document.body.append(badge);});
    const cityScreenshot=async name=>{
      await p.evaluate(()=>{document.getElementById('simulation-watermark').hidden=true;const badge=document.createElement('p');badge.id='city-simulation-watermark';badge.textContent='Симуляция USB · тестовые данные';badge.style.cssText='display:block;margin:18px 0 0;padding:9px 12px;border:1px solid #627779;border-radius:9px;color:#b0c3c5;font:12px/1.5 system-ui;text-align:center;';document.getElementById('radio-section').append(badge);});
      await p.locator('#radio-section').screenshot({path:path.join(output,name)});
      await p.evaluate(()=>{document.getElementById('city-simulation-watermark').remove();document.getElementById('simulation-watermark').hidden=false;});
    };
    await p.locator('#preset-city').selectOption('OMS');
    await geometry(p);await p.screenshot({path:path.join(output,'dashboard-desktop.png'),fullPage:false});
    await cityScreenshot('radio-desktop.png');
    for(const width of [320,390,730,1040]){await p.setViewportSize({width,height:1000});await geometry(p);if(width===390){await cityScreenshot('radio-mobile.png');await p.locator('#api-settings').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(output,'dashboard-mobile.png'),fullPage:false});}}
    await p.locator('#preset-search').focus();await p.keyboard.press('Tab');assert.equal(await p.evaluate(()=>document.activeElement.id),'preset-city');
  }finally{await f.close();}
});
test('per-field save/readback keeps another unsaved field',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);
    await p.locator('#api-setting-volume').selectOption('3');
    await p.locator('#api-setting-agc_reset').selectOption('1');await p.getByRole('button',{name:'Сохранить CLI: AGC-сброс · каждые 60 с',exact:true}).click();await ready(p);
    assert.equal(await p.evaluate(()=>window.__apiMock.settings.agc_reset),1);assert.equal(await p.locator('#api-setting-volume').inputValue(),'3');
    assert.equal(await p.evaluate(()=>window.__apiMock.settings.volume),7);
  }finally{await f.close();}
});
test('bridge/protection confirmations can decline; no accidental writes',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);
    for(const [key,value,label]of [['bridge','1','Мостовой звук · два вывода'],['battery_protection','0','Защита АКБ 3,2 В']]){
      await p.locator('#api-setting-'+key).selectOption(value);await p.getByRole('button',{name:'Сохранить CLI: '+label,exact:true}).click();assert.equal(await p.locator('#confirm-dialog').isVisible(),true);await p.locator('#confirm-no').click();
    }
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.some(c=>c.startsWith('ui set '))),false);
  }finally{await f.close();}
});
test('staged Wi-Fi explicit save, redacted developer view and secrets',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);
    await p.locator('#api-ssid').fill('Локальная сеть');await p.locator('#api-password').fill('private-password');await p.locator('#api-wifi-test').click();await p.waitForFunction(()=>!document.getElementById('api-wifi-save').disabled);
    assert.equal(await p.locator('#api-password').inputValue(),'');assert.equal(await p.evaluate(()=>window.__apiMock.wifi),'test_ok');
    assert.doesNotMatch(await p.locator('#api-log').textContent(),/private-password|70726976617465|Локальная сеть/);
    await p.locator('#api-wifi-save').click();await ready(p);assert.equal(await p.evaluate(()=>window.__apiMock.wifi),'saved');
    await p.locator('#api-command').fill('ui get volume');await p.locator('#api-command-send').click();await ready(p);assert.match(await p.locator('#api-command-result').textContent(),/Значения скрыты/);
    await p.locator('#api-command').fill('ui wifi password 736563726574');await p.locator('#api-command-send').click();assert.match(await p.locator('#api-feedback').textContent(),/специальные формы/);
  }finally{await f.close();}
});
test('ADC battery reference preview is nonmutating; source error explained',async()=>{
  const f=await fixture({adcMin:1.36125,adcMax:2.26875,adcReference:3100,settings:{battery_mv:4100,adc_multiplier:1.97,adc_default:1.815}});try{const p=f.page;await connect(p);await p.locator('#api-adc summary').click();
    await p.locator('#api-adc-measured').fill('3,30');await p.locator('#api-adc-preview').click();await ready(p);
    assert.match(await p.locator('#api-adc-result').textContent(),/3100 мВ/);assert.equal(await p.evaluate(()=>window.__apiMock.settings.adc_multiplier),1.97);
    await p.locator('#api-adc-apply').click();await p.locator('#confirm-yes').click();await ready(p);
    assert.ok(Math.abs(await p.evaluate(()=>window.__apiMock.settings.adc_multiplier)-2.097097)<0.000002);
    await p.evaluate(()=>window.__apiMock.adcSourceMissing=true);await p.locator('#api-adc-preview').click();await ready(p);assert.match(await p.locator('#api-feedback').textContent(),/без перезапуска.*2 минут/);
    assert.equal(await p.locator('#api-adc-apply').isDisabled(),true);
  }finally{await f.close();}
});

test('wrong Wi-Fi acknowledgment stops staging and blocks further commands',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);
    await p.evaluate(()=>window.__apiMock.errorNext='OK ui test');
    await p.locator('#api-ssid').fill('Test network');await p.locator('#api-password').fill('private-password');await p.locator('#api-wifi-test').click();
    await p.waitForFunction(()=>document.getElementById('transport-state').textContent.includes('Результат неизвестен'));
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.some(c=>c.startsWith('ui wifi ssid '))),false);
    assert.equal(await p.locator('#api-settings-load').isDisabled(),true);assert.equal(await p.locator('#api-password').inputValue(),'');
    assert.doesNotMatch(await p.locator('#api-log').textContent(),/private-password/);
  }finally{await f.close();}
});
test('read-only permits reading, hides Wi-Fi on unsupported board',async()=>{
  const f=await fixture({readonly:true,wifi:false});try{await connect(f.page);assert.equal(await f.page.locator('#api-setting-volume').isDisabled(),true);assert.equal(await f.page.locator('#api-settings-load').isDisabled(),false);assert.equal(await f.page.locator('#api-wifi').isVisible(),false);}finally{await f.close();}
});
test('0.11 archive guidance; no guessing support and no CMD66',async()=>{
  const f=await fixture({oldFirmware:true});try{await f.page.locator('#connect').click();await f.page.waitForFunction(()=>document.getElementById('api-feedback').textContent.includes('архивный Helper 1.4'));
    assert.deepEqual(await f.page.evaluate(()=>window.__apiMock.packets.map(p=>p[0])),[22,40]);assert.equal(await f.page.evaluate(()=>window.__apiMock.closed),true);
  }finally{await f.close();}
});
test('disconnect stops all reads/writes and releases mode selector',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);await p.locator('#disconnect').click();await p.waitForFunction(()=>!document.getElementById('helper-mode').disabled);
    const before=await p.evaluate(()=>[window.__apiMock.readCalls,window.__apiMock.packets.length]);await p.waitForTimeout(100);
    assert.deepEqual(await p.evaluate(()=>[window.__apiMock.readCalls,window.__apiMock.packets.length]),before);
    assert.equal(await p.locator('#api-settings-load').isDisabled(),true);
  }finally{await f.close();}
});
