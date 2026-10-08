'use strict';
// Browser-only simulation against the packaged offline application.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{chromium}=require('playwright');
const {installApiMock}=require('./test_api_fixture');
const {fullSettingsFixture}=require('./test_full_settings_fixture');
const root=path.resolve(__dirname,'../..'),output=process.env.SMARTUI_API_UI_OUTPUT?path.resolve(process.env.SMARTUI_API_UI_OUTPUT):fs.mkdtempSync(path.join(os.tmpdir(),'smartui-api-ui-'));
const artifact=path.join(output,'SmartUI_USB_Helper_2.2.html');let browser;
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
async function connect(page){await page.locator('#connect').click();await page.waitForFunction(()=>document.getElementById('api-settings-status').textContent==='Прочитано с ноды'&&!document.getElementById('api-settings-load').disabled);await tab(page,'device');}
async function tab(page,name){await page.locator('[data-page-target="'+name+'"]').click();assert.equal(await page.locator('[data-page-target="'+name+'"]').getAttribute('aria-selected'),'true');}

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

test('CLI tabs have visible pins and hash, collapsed phrases, and no navigation side effects',async()=>{
  const f=await fixture({console:1,meshcore:1,firmware:'0.16',soundPreview:true,...fullSettingsFixture()});
  try{const p=f.page;await connect(p);const before=await p.evaluate(()=>__apiMock.commands.length);
    assert.equal(await p.locator('#api-mode-result').textContent(),'Текущий режим: USB-компаньон.');
    assert.doesNotMatch(await p.locator('#api-log').textContent(),/Ответ на чтение не получен/,'Unsupported optional capabilities are not lost responses');
    for(const name of ['connection','radio','sound','device','wifi','phrases','service']){
      await tab(p,name);
      assert.deepEqual(await p.evaluate(selected=>[...document.querySelectorAll('[data-pages]')].filter(el=>!el.dataset.pages.split(/\s+/).includes(selected)&&el.getClientRects().length).map(el=>el.id||el.tagName),name),[]);
      await geometry(p);
    }
    await tab(p,'sound');assert.equal(await p.locator('#api-settings-advanced').isChecked(),false);
    for(const key of ['tone_pin','led_pin','vibe_pin'])assert.equal(await p.locator('#api-setting-'+key).isVisible(),true,key+' is not hidden in advanced settings');
    await tab(p,'radio');assert.equal(await p.locator('#path-bytes').isVisible(),true);
    await tab(p,'phrases');assert.equal(await p.locator('#api-phrases-panel').getAttribute('open'),null);assert.equal(await p.locator('#api-phrase-1').isVisible(),false);
    assert.equal(await p.evaluate(()=>__apiMock.commands.length),before);
    await p.evaluate(()=>{const badge=document.createElement('div');badge.textContent='СИМУЛЯЦИЯ USB · не физическая плата';badge.style.cssText='position:fixed;right:12px;bottom:12px;z-index:1000;background:#1d2d4a;color:#eff4ff;border:1px solid #7192d9;border-radius:7px;padding:7px 10px;font:12px system-ui;';document.body.append(badge);});
    for(const [size,width,height]of [['desktop',1440,1000],['mobile',390,844]]){
      await p.setViewportSize({width,height});
      for(const name of ['connection','radio','sound','device','wifi','phrases','service']){await tab(p,name);await geometry(p);await p.evaluate(()=>scrollTo(0,0));await p.screenshot({path:path.join(output,'helper-2.2-cli-'+name+'-'+size+'.png'),fullPage:true});}
    }
  }finally{await f.close();}
});

test('CLI sound refresh replaces sound drafts only and reads actual pins without writes',async()=>{
  const f=await fixture({console:1,meshcore:1,firmware:'0.16',...fullSettingsFixture()});
  try{const p=f.page;await connect(p);await p.locator('#api-setting-ui_theme').selectOption('2');await tab(p,'sound');await p.locator('#api-setting-volume').selectOption('3');
    await p.evaluate(()=>Object.assign(__apiMock.settings,{volume:8,melody:18,tone_pin:33,sound_quiet:1}));const before=await p.evaluate(()=>__apiMock.commands.length);
    await p.locator('#api-sound-read').click();await p.locator('#confirm-no').click();assert.equal(await p.locator('#api-setting-volume').inputValue(),'3');assert.equal(await p.evaluate(()=>__apiMock.commands.length),before);
    await p.locator('#api-sound-read').click();await p.locator('#confirm-yes').click();await ready(p);
    assert.equal(await p.locator('#api-setting-volume').inputValue(),'8');assert.equal(await p.locator('#api-setting-tone_pin').inputValue(),'33');assert.equal(await p.locator('#api-setting-melody').inputValue(),'18');assert.equal(await p.locator('#api-setting-sound_quiet').inputValue(),'1');
    assert.equal(await p.locator('#api-setting-ui_theme').inputValue(),'2');assert.equal(await p.evaluate(n=>__apiMock.commands.slice(n).some(c=>/^ui (set|sound preview|test)\b/.test(c)),before),false);
  }finally{await f.close();}
});

test('CLI melody preview ignores notification quiet but respects fresh global mute without changing either',async()=>{
  const f=await fixture({soundPreview:true,...fullSettingsFixture()});
  try{const p=f.page;await connect(p);await tab(p,'sound');await p.evaluate(()=>Object.assign(__apiMock.settings,{sound_quiet:1,muted:0,melody:18}));
    await p.locator('#api-sound-read').click();await ready(p);const before=await p.evaluate(()=>__apiMock.commands.length);
    await p.locator('#api-sound-preview').click();await ready(p);
    assert.equal(await p.evaluate(()=>__apiMock.commands.filter(c=>c==='ui sound preview').length),1);assert.equal(await p.evaluate(()=>__apiMock.settings.sound_quiet),1);assert.equal(await p.evaluate(n=>__apiMock.commands.slice(n).some(c=>c.startsWith('ui set ')),before),false);
    await p.evaluate(()=>__apiMock.settings.muted=1);await p.locator('#api-sound-preview').click();await ready(p);
    assert.match(await p.locator('#api-sound-action-status').textContent(),/тишина/);assert.equal(await p.evaluate(()=>__apiMock.commands.filter(c=>c==='ui sound preview').length),1);
  }finally{await f.close();}
  const old=await fixture();try{await connect(old.page);await tab(old.page,'sound');assert.equal(await old.page.locator('#api-sound-preview').isDisabled(),true);assert.equal(await old.page.evaluate(()=>__apiMock.commands.includes('ui sound preview')),false);}finally{await old.close();}
});

test('0.16 full controls use firmware schemas; safe pin consent, drafts, name/TX and phrases work',async()=>{
  const f=await fixture({console:1,meshcore:1,firmware:'0.16',manualAdc:true,...fullSettingsFixture()});
  try{const p=f.page;await connect(p);
    await tab(p,'sound');assert.equal(await p.locator('#api-setting-tone_pin').isVisible(),true);
    await p.locator('#api-settings').evaluate(section=>{const caption=document.createElement('p');caption.id='basic-simulation-caption';caption.className='hint';caption.textContent='Симуляция T096 · SmartUI 0.16. Физическая плата не подключена.';section.prepend(caption);});
    await geometry(p);await p.locator('#api-settings').screenshot({path:path.join(output,'helper-2.1-basic-desktop.png')});
    await p.setViewportSize({width:390,height:844});await geometry(p);await p.locator('#api-settings').screenshot({path:path.join(output,'helper-2.1-basic-mobile.png')});
    await p.setViewportSize({width:1440,height:1080});await p.locator('#basic-simulation-caption').evaluate(el=>el.remove());
    await p.locator('#api-settings-advanced').check();
    assert.deepEqual(await p.locator('#api-setting-tone_pin option').evaluateAll(nodes=>nodes.map(n=>n.value)),['29','31','33','34','35','36','37','39','43']);
    for(const key of ['ui_theme','led_pin'])assert.equal(await p.locator('#api-setting-'+key).isEnabled(),true);
    for(const key of ['profile','melody_dm','melody_mention'])assert.equal(await p.locator('#api-setting-'+key).isDisabled(),true);
    assert.deepEqual(await p.locator('#api-setting-gps_source option').evaluateAll(nodes=>nodes.map(n=>n.value)),['0']);
    assert.equal(await p.locator('#api-setting-vibration').isDisabled(),true);
    await p.locator('#api-settings-filter').fill('tone_pin');
    assert.equal(await p.locator('#api-settings-fields .device-panel:visible').count(),1);
    await p.locator('#api-settings-filter').fill('');
    await tab(p,'device');await p.locator('#api-adc summary').click();assert.equal(await p.locator('#api-adc-manual-value').isEnabled(),true);await tab(p,'sound');
    await p.locator('#api-setting-volume').selectOption('5');await p.locator('#api-setting-tone_pin').selectOption('33');
    await p.getByRole('button',{name:'Сохранить CLI: Вывод звука',exact:true}).click();await p.locator('#confirm-no').click();assert.equal(await p.evaluate(()=>__apiMock.settings.tone_pin),31);
    await p.getByRole('button',{name:'Сохранить CLI: Вывод звука',exact:true}).click();await p.locator('#confirm-yes').click();await ready(p);
    assert.equal(await p.evaluate(()=>__apiMock.settings.tone_pin),33);assert.equal(await p.locator('#api-setting-volume').inputValue(),'5');
    await tab(p,'radio');await p.locator('#node-name').fill('Моя нода');await p.locator('#node-name-save').click();await p.locator('#confirm-yes').click();await ready(p);assert.equal(await p.evaluate(()=>__apiMock.meshcore.name),'Моя нода');
    await p.locator('#node-tx').fill('17');await p.locator('#node-tx-save').click();await p.locator('#confirm-yes').click();await ready(p);assert.equal(await p.evaluate(()=>__apiMock.meshcore.tx),'17');
    await tab(p,'phrases');assert.equal(await p.locator('#api-phrase-1').isVisible(),false);await p.locator('#api-phrases-panel summary').click();
    await p.locator('#api-phrases-load').click();await ready(p);await p.locator('#api-phrase-1').fill('Уже еду');await p.locator('#api-phrase-save-1').click();await ready(p);assert.equal(await p.evaluate(()=>__apiMock.phrases[0]),'Уже еду');
    await tab(p,'sound');await p.locator('#api-settings').evaluate(section=>{const caption=document.createElement('p');caption.className='hint';caption.textContent='Симуляция T096 · SmartUI 0.16. Физическая плата не подключена.';section.prepend(caption);});
    await geometry(p);await p.locator('#api-settings').screenshot({path:path.join(output,'helper-2.1-settings-desktop.png')});
    await p.setViewportSize({width:390,height:844});await geometry(p);await p.locator('#api-settings').screenshot({path:path.join(output,'helper-2.1-settings-mobile.png')});
  }finally{await f.close();}
});

test('sound labels match firmware and tests explain mute, disabled sound and unsaved edits',async()=>{
  for(const schema of [false,true]){
    const full=schema?fullSettingsFixture():{};
    const f=await fixture({...full,settings:{...full.settings,muted:0,sound_quiet:1}});
    try{const p=f.page;await connect(p);
      await tab(p,'sound');
      assert.equal(await p.locator('#api-setting-sound_quiet option:checked').textContent(),'Выключен');
      assert.match(await p.locator('#api-notify-state').textContent(),/Звук выключен на ноде/);
      const save=p.getByRole('button',{name:'Сохранить CLI: Звук уведомлений ЛС',exact:true});assert.equal(await save.isDisabled(),true);
      await p.locator('#api-setting-sound_quiet').selectOption({label:'Включён'});await save.click();await ready(p);
      assert.equal(await p.evaluate(()=>__apiMock.settings.sound_quiet),0);assert.match(await p.locator('#api-notify-state').textContent(),/Звук включён на ноде/);
      await p.locator('#api-setting-muted').selectOption('1');await p.getByRole('button',{name:'Сохранить CLI: Общая тишина',exact:true}).click();await ready(p);
      await p.locator('#api-notify-test').click();await ready(p);assert.match(await p.locator('#api-sound-action-status').textContent(),/Общая тишина включена/);
      await p.locator('#api-setting-muted').selectOption('0');
      const before=await p.evaluate(()=>__apiMock.commands.filter(c=>c==='ui test').length);
      await p.locator('#api-notify-test').click();assert.match(await p.locator('#confirm-text').textContent(),/несохранённые/);await p.locator('#confirm-no').click();
      assert.equal(await p.evaluate(()=>__apiMock.commands.filter(c=>c==='ui test').length),before);
      await p.locator('#api-notify-test').click();await p.locator('#confirm-yes').click();await ready(p);
      assert.equal(await p.evaluate(()=>__apiMock.settings.muted),1);assert.match(await p.locator('#api-sound-action-status').textContent(),/Общая тишина включена/);
      assert.equal(await p.evaluate(()=>__apiMock.commands.filter(c=>c==='ui test').length),before,'Muted notification is blocked without silently changing settings');
    }finally{await f.close();}
  }
});

test('path selector changes only hash bytes using fresh radio state, consent and readback',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);await tab(p,'radio');
    assert.equal(await p.locator('#path-bytes').inputValue(),'2');await p.locator('#path-bytes').selectOption('1');
    await p.locator('#path-save').click();await p.locator('#confirm-no').click();assert.equal(await p.evaluate(()=>__apiMock.commands.some(c=>c.startsWith('ui radio set'))),false);
    await p.evaluate(()=>Object.assign(__apiMock.radio,{freq_khz:868731,bw_hz:62500,sf:7,cr:7,tx_dbm:17,repeat:1}));
    await p.locator('#path-save').click();await p.locator('#confirm-yes').click();await p.waitForFunction(()=>document.getElementById('radio-status').textContent.includes('Хеш маршрута сохранён'));
    assert.deepEqual(await p.evaluate(()=>__apiMock.radio),{freq_khz:868731,bw_hz:62500,sf:7,cr:7,path_bytes:1,tx_dbm:17,repeat:1});
    assert.equal(await p.locator('#path-save').isDisabled(),true);assert.equal(await p.evaluate(()=>__apiMock.commands.filter(c=>c.startsWith('ui radio set')).length),1);
    await geometry(p);await p.locator('#radio-section').screenshot({path:path.join(output,'helper-2.1-path-desktop.png')});
    await p.setViewportSize({width:390,height:844});await geometry(p);await p.locator('#radio-section').screenshot({path:path.join(output,'helper-2.1-path-mobile.png')});
  }finally{await f.close();}
  const read=await fixture({readonly:true});try{await connect(read.page);assert.equal(await read.page.locator('#path-bytes').isDisabled(),true);}finally{await read.close();}
});

test('companion mode change needs consent and is confirmed only through mode status and readback',async()=>{
  const f=await fixture({wifi:false});try{const p=f.page;await connect(p);await tab(p,'connection');assert.equal(await p.locator('#api-mode-wifi').isDisabled(),true);
    await p.locator('#api-mode-ble').click();await p.locator('#confirm-no').click();assert.equal(await p.evaluate(()=>__apiMock.mode),'usb');
    await p.locator('#api-mode-ble').click();await p.locator('#confirm-yes').click();await ready(p);
    assert.equal(await p.evaluate(()=>__apiMock.mode),'ble');assert.match(await p.locator('#api-mode-result').textContent(),/подтверждён нодой/);
  }finally{await f.close();}
});

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

test('manual ADC CLI uses explicit input/readback without battery reference and reports source locally',async()=>{
  const f=await fixture({manualAdc:true,caps:{adc_service:1},adcMin:1.36125,adcMax:2.26875,settings:{adc_multiplier:1.97,adc_default:1.815,battery_mv:2770}});
  try{const p=f.page;await connect(p);await p.locator('#api-adc summary').click();
    await p.evaluate(()=>__apiMock.adcSourceMissing=true);
    await p.locator('#api-adc-measured').fill('3.32');await p.locator('#api-adc-preview').click();await ready(p);
    assert.match(await p.locator('#api-adc-result').textContent(),/ProMicro/);assert.equal(await p.locator('#api-adc-result').getAttribute('data-kind'),'error');
    await p.locator('#api-adc-manual-value').fill('2,109806');
    await p.locator('#api-adc-manual-save').click();assert.match(await p.locator('#confirm-text').textContent(),/2\.109806/);await p.locator('#confirm-no').click();
    assert.equal(await p.evaluate(()=>__apiMock.commands.some(c=>c.startsWith('ui adc set '))),false);
    await p.locator('#api-adc-manual-save').click();await p.locator('#confirm-yes').click();await ready(p);
    assert.match(await p.locator('#api-adc-manual-result').textContent(),/Сохранено на ноде и проверено: 2\.109806/);
    assert.equal(await p.locator('#api-adc-result').getAttribute('data-kind'),'info');
    assert.match(await p.locator('#api-adc-result').textContent(),/Коэффициент сохранён вручную/);
    assert.match(await p.locator('#api-adc-value').textContent(),/Сохранённый ADC-множитель: 2\.109806/);
    assert.equal(await p.evaluate(()=>__apiMock.commands.filter(c=>c==='ui adc set 2.109806').length),1);
    await geometry(p);await p.locator('#api-adc').screenshot({path:path.join(output,'helper-1.8-cli-adc-desktop.png')});
    await p.setViewportSize({width:390,height:844});await geometry(p);await p.locator('#api-adc').screenshot({path:path.join(output,'helper-1.8-cli-adc-mobile.png')});
  }finally{await f.close();}
});

test('manual ADC CLI old firmware, readonly, changed input and unsupported probe remain safe',async()=>{
  for(const options of [{},{readonly:true,manualAdc:true}]){const f=await fixture(options);try{const p=f.page;await connect(p);await p.locator('#api-adc summary').click();assert.equal(await p.locator('#api-adc-manual-value').isDisabled(),true);assert.equal(await p.locator('#api-settings-load').isEnabled(),true);}finally{await f.close();}}
  const f=await fixture({manualAdc:true});try{const p=f.page;await connect(p);await p.locator('#api-adc summary').click();
    await p.locator('#api-adc-manual-value').fill('4.8');await p.locator('#api-adc-manual-save').click();
    await p.evaluate(()=>{const x=document.getElementById('api-adc-manual-value');x.value='4.7';x.dispatchEvent(new Event('input'));});await p.locator('#confirm-yes').click();
    assert.match(await p.locator('#api-adc-manual-result').textContent(),/значение изменилось/);
    assert.equal(await p.evaluate(()=>__apiMock.commands.some(c=>c.startsWith('ui adc set '))),false);
  }finally{await f.close();}
});

test('manual ADC CLI lost acknowledgement or lost USB stays local and never retries',async()=>{
  for(const unplug of [false,true]){const f=await fixture({manualAdc:true,clock:true});try{const p=f.page;await connect(p);await p.locator('#api-adc summary').click();
    await p.evaluate(()=>__apiMock.dropAdcAck=true);await p.locator('#api-adc-manual-value').fill('4.8');await p.locator('#api-adc-manual-save').click();await p.locator('#confirm-yes').click();
    await p.waitForFunction(()=>__apiMock.commands.includes('ui adc set 4.800000'));
    if(unplug)await p.evaluate(()=>__apiMock.controller.error(new Error('USB lost')));else await p.clock.fastForward(6100);
    await p.waitForFunction(()=>document.getElementById('api-adc-manual-result').dataset.kind==='error');
    assert.match(await p.locator('#api-adc-manual-result').textContent(),/неизвестен|не подтверждено|недоступна/);
    assert.equal(await p.locator('#api-adc-manual-save').isDisabled(),true);
    assert.equal(await p.evaluate(()=>__apiMock.commands.filter(c=>c.startsWith('ui adc set ')).length),1);
  }finally{await f.close();}}
});

test('manual ADC CLI readback mismatch becomes local uncertainty, never false success',async()=>{
  const f=await fixture({manualAdc:true});try{const p=f.page;await connect(p);await p.locator('#api-adc summary').click();
    await p.evaluate(()=>{const m=__apiMock,original=m.handle;m.handle=function(packet){original.call(this,packet);if(this.commands.at(-1)==='ui adc set 4.800000')this.settings.adc_multiplier=4.81;};});
    await p.locator('#api-adc-manual-value').fill('4.8');await p.locator('#api-adc-manual-save').click();await p.locator('#confirm-yes').click();
    await p.waitForFunction(()=>document.getElementById('api-adc-manual-result').dataset.kind==='error');
    assert.match(await p.locator('#api-adc-manual-result').textContent(),/операция не подтверждена/);
    assert.equal(await p.locator('#api-adc-manual-save').isDisabled(),true);
    assert.equal(await p.evaluate(()=>__apiMock.commands.filter(c=>c.startsWith('ui adc set ')).length),1);
  }finally{await f.close();}
});

test('protocol14 meshcore hello preserves CLI settings-only handshake, one reader and hardware gates',async()=>{
  const f=await fixture({meshcore:1});try{const p=f.page;await connect(p);
    assert.equal(await p.locator('#helper-mode').isDisabled(),true);assert.equal(await p.locator('#device-section').isVisible(),false);
    for(const id of ['api-sync-enable','api-inbox','api-events','api-fetch'])assert.equal(await p.locator('#'+id).count(),0);
    assert.equal(await p.evaluate(()=>window.__apiMock.readerCount),1);assert.equal(await p.evaluate(()=>window.__apiMock.maxOpen),1);
    assert.equal(await p.locator('#api-setting-fem_pa').count(),0);assert.equal(await p.locator('#api-setting-agc_reset').isVisible(),true);
    assert.equal(await p.locator('#api-setting-melody option[value="0"]').textContent(),'0 · Пульс');
    await tab(p,'sound');
    await p.locator('#api-notify-test').click();await ready(p);
    assert.match(await p.locator('#api-sound-action-status').textContent(),/Запрос уведомления принят/);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.filter(c=>c==='ui test').length),1);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.every(c=>c.startsWith('ui '))),true);
    assert.equal(await p.evaluate(()=>window.__apiMock.packets.every(p=>[22,40,66].includes(p[0]))),true);
    await p.locator('#disconnect').click();assert.equal(await p.evaluate(()=>window.__apiMock.closed),true);
    await p.locator('#helper-mode').selectOption('console');assert.equal(await p.locator('#device-section').isVisible(),true);
  }finally{await f.close();}
});

test('city preset confirmation, atomic apply and readback preserve power/repeat/path; advert intervals match node',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);
    await tab(p,'radio');
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
    const f=await fixture(options);try{const p=f.page;await connect(p);await tab(p,'radio');await p.locator('#preset-city').selectOption({index:1});
      if(options.network===false||options.readonly){assert.equal(await p.locator('#preset-apply').isDisabled(),true);assert.equal(await p.locator('#advert-save').isDisabled(),true);assert.equal(await p.locator('#api-settings-load').isDisabled(),false);}
      else{await p.evaluate(()=>window.__apiMock.networkError='repeat');await p.locator('#preset-apply').click();await p.locator('#confirm-yes').click();await p.waitForFunction(()=>document.getElementById('radio-status').dataset.kind==='error');assert.match(await p.locator('#radio-status').textContent(),/ретрансляция несовместима/);assert.equal(await p.evaluate(()=>window.__apiMock.radio.freq_khz),869525);assert.equal(await p.evaluate(()=>window.__apiMock.commands.filter(c=>c.startsWith('ui radio set')).length),1);}
    }finally{await f.close();}
  }
});

test('radio ACK lost: no automatic retry and writes blocked until reconnect',async()=>{
  const f=await fixture({clock:true});try{const p=f.page;await connect(p);await tab(p,'radio');await p.locator('#preset-city').selectOption({index:1});await p.locator('#preset-apply').click();
    await p.evaluate(()=>{const original=window.__apiMock.reply;window.__apiMock.reply=function(tag,text){if(this.commands.at(-1).startsWith('ui radio set'))return;original.call(this,tag,text);};});
    await p.locator('#confirm-yes').click();await p.waitForFunction(()=>window.__apiMock.commands.some(c=>c.startsWith('ui radio set')));await p.clock.runFor(6500);
    assert.equal(await p.locator('#preset-apply').isDisabled(),true);assert.match(await p.locator('#radio-status').textContent(),/неизвестен/);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.filter(c=>c.startsWith('ui radio set')).length),1);
  }finally{await f.close();}
});

test('successful radio ACK followed by readback error is uncertain and blocks writes',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);await tab(p,'radio');await p.locator('#preset-city').selectOption('OMS');
    await p.evaluate(()=>{const original=window.__apiMock.reply;window.__apiMock.reply=function(tag,text){if(this.commands.at(-1).startsWith('ui radio set'))this.afterRadioSave=true;else if(this.afterRadioSave&&this.commands.at(-1)==='ui radio')text='ERR ui busy';original.call(this,tag,text);};});
    await p.locator('#preset-apply').click();await p.locator('#confirm-yes').click();await p.waitForFunction(()=>document.getElementById('transport-state').textContent.includes('Результат неизвестен'));
    assert.equal(await p.locator('#preset-apply').isDisabled(),true);assert.equal(await p.locator('#api-settings-load').isDisabled(),true);assert.match(await p.locator('#radio-status').textContent(),/не подтверждена/);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.filter(c=>c.startsWith('ui radio set')).length),1);
  }finally{await f.close();}
});
test('desktop/mobile geometry and simulated screenshots',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);
    await tab(p,'radio');
    await p.evaluate(()=>{scrollTo(0,0);const badge=document.createElement('div');badge.id='simulation-watermark';badge.textContent='Симуляция USB · тестовые данные';badge.style.cssText='position:fixed;right:12px;bottom:12px;z-index:1000;background:#203744;color:#edf2f7;border:1px solid #91b8c1;border-radius:7px;padding:7px 10px;font:12px system-ui;';document.body.append(badge);});
    const cityScreenshot=async name=>{
      await p.evaluate(()=>{document.getElementById('simulation-watermark').hidden=true;const badge=document.createElement('p');badge.id='city-simulation-watermark';badge.textContent='Симуляция USB · тестовые данные';badge.style.cssText='display:block;margin:18px 0 0;padding:9px 12px;border:1px solid #627779;border-radius:9px;color:#b0c3c5;font:12px/1.5 system-ui;text-align:center;';document.getElementById('radio-section').append(badge);});
      await p.locator('#radio-section').screenshot({path:path.join(output,name)});
      await p.evaluate(()=>{document.getElementById('city-simulation-watermark').remove();document.getElementById('simulation-watermark').hidden=false;});
    };
    await p.locator('#preset-city').selectOption('OMS');
    await geometry(p);await p.screenshot({path:path.join(output,'dashboard-desktop.png'),fullPage:false});
    await cityScreenshot('radio-desktop.png');
    for(const width of [320,390,730,1040]){await p.setViewportSize({width,height:1000});await geometry(p);if(width===390){await cityScreenshot('radio-mobile.png');await tab(p,'sound');await p.locator('#api-settings').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(output,'dashboard-mobile.png'),fullPage:false});await tab(p,'radio');}}
    await p.locator('#preset-search').focus();await p.keyboard.press('Tab');assert.equal(await p.evaluate(()=>document.activeElement.id),'preset-city');
  }finally{await f.close();}
});
test('per-field save/readback keeps another unsaved field',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);
    await tab(p,'sound');
    await p.locator('#api-setting-volume').selectOption('3');
    await tab(p,'device');
    await p.locator('#api-setting-agc_reset').selectOption('1');await p.getByRole('button',{name:'Сохранить CLI: AGC-сброс · каждые 60 с',exact:true}).click();await ready(p);
    assert.equal(await p.evaluate(()=>window.__apiMock.settings.agc_reset),1);assert.equal(await p.locator('#api-setting-volume').inputValue(),'3');
    assert.equal(await p.evaluate(()=>window.__apiMock.settings.volume),7);
  }finally{await f.close();}
});
test('bridge/protection confirmations can decline; no accidental writes',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);
    await p.locator('#api-settings-advanced').check();
    for(const [key,value,label]of [['bridge','1','Мостовой звук · два вывода'],['battery_protection','0','Защита АКБ 3,2 В']]){
      await tab(p,key==='bridge'?'sound':'device');
      await p.locator('#api-setting-'+key).selectOption(value);await p.getByRole('button',{name:'Сохранить CLI: '+label,exact:true}).click();assert.equal(await p.locator('#confirm-dialog').isVisible(),true);await p.locator('#confirm-no').click();
    }
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.some(c=>c.startsWith('ui set '))),false);
  }finally{await f.close();}
});
test('staged Wi-Fi explicit save, safe developer values and secret isolation',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);
    await tab(p,'wifi');
    await p.locator('#api-ssid').fill('Локальная сеть');await p.locator('#api-password').fill('private-password');await p.locator('#api-wifi-test').click();await p.waitForFunction(()=>!document.getElementById('api-wifi-save').disabled);
    assert.equal(await p.locator('#api-password').inputValue(),'');assert.equal(await p.evaluate(()=>window.__apiMock.wifi),'test_ok');
    assert.doesNotMatch(await p.locator('#api-log').textContent(),/private-password|70726976617465|Локальная сеть/);
    await p.locator('#api-wifi-save').click();await ready(p);assert.equal(await p.evaluate(()=>window.__apiMock.wifi),'saved');
    await tab(p,'service');await p.locator('#api-command').fill('ui get volume');await p.locator('#api-command-send').click();await ready(p);assert.match(await p.locator('#api-command-result').textContent(),/key=volume value=7/);
    await p.locator('#api-command').fill('ui wifi password 736563726574');await p.locator('#api-command-send').click();assert.match(await p.locator('#api-feedback').textContent(),/специальные формы/);
  }finally{await f.close();}
});
test('0.15 console help presets never send themselves and TX setter confirms with readback',async()=>{
  const f=await fixture({console:1,meshcore:1});try{const p=f.page;await connect(p);
    await tab(p,'service');
    const before=await p.evaluate(()=>__apiMock.commands.length);
    await p.locator('#api-command-presets [data-command="help"]').click();
    assert.equal(await p.locator('#api-command').inputValue(),'help');
    assert.equal(await p.evaluate(()=>__apiMock.commands.length),before);
    await p.locator('#api-command-send').click();await ready(p);
    assert.match(await p.locator('#api-command-result').textContent(),/help sound 2/);
    await p.locator('#api-command-presets [data-command="get tx"]').click();await p.locator('#api-command-send').click();await ready(p);
    assert.match(await p.locator('#api-command-result').textContent(),/> 20/);
    await p.locator('#api-command').fill('set tx 18');await p.locator('#api-command-send').click();await p.locator('#confirm-no').click();
    assert.equal(await p.evaluate(()=>__apiMock.commands.includes('set tx 18')),false);
    await p.locator('#api-command-send').click();await p.locator('#confirm-yes').click();await ready(p);
    assert.match(await p.locator('#api-command-result').textContent(),/Прочитано после изменения: > 18/);
    assert.equal(await p.evaluate(()=>__apiMock.commands.filter(c=>c==='set tx 18').length),1);
    await p.locator('#api-command').fill('melody 1');await p.locator('#api-command-send').click();await ready(p);
    assert.match(await p.locator('#api-command-result').textContent(),/1: Трель/);
    assert.doesNotMatch(await p.locator('#api-log').textContent(),/set tx|Трель|help sound/);
    await geometry(p);await p.locator('#api-developer').screenshot({path:path.join(output,'helper-2.1-console-desktop.png')});
    await p.setViewportSize({width:390,height:844});await geometry(p);await p.locator('#api-developer').screenshot({path:path.join(output,'helper-2.1-console-mobile.png')});
  }finally{await f.close();}
});

test('friendly console setters preserve second safety confirmations and never bypass forms',async()=>{
  const f=await fixture({console:1,meshcore:1});try{const p=f.page;await connect(p);
    await tab(p,'service');
    for(const [command,warning] of [['set battery_protection off',/3,2 В/],['set sound.bridge on',/пьезоизлучателя/]]){
      await p.locator('#api-command').fill(command);await p.locator('#api-command-send').click();await p.locator('#confirm-yes').click();
      await p.waitForFunction(()=>document.getElementById('confirm-dialog').open);
      assert.match(await p.locator('#confirm-text').textContent(),warning);await p.locator('#confirm-no').click();
      assert.equal(await p.evaluate(c=>__apiMock.commands.includes(c),command),false);
    }
    for(const command of ['set pin 654321','set adc 4.9','adc preview 3800','adc service start','ui wifi password 736563726574','reboot']){
      const before=await p.evaluate(()=>__apiMock.commands.length);
      await p.locator('#api-command').fill(command);await p.locator('#api-command-send').click();
      assert.match(await p.locator('#api-feedback').textContent(),/специальные формы/);
      assert.equal(await p.evaluate(()=>__apiMock.commands.length),before);
    }
    assert.doesNotMatch(await p.locator('#api-log').textContent(),/654321|736563726574/);
  }finally{await f.close();}
});

test('0.14 console gives explicit upgrade guidance; existing ui and upstream TX remain usable',async()=>{
  const f=await fixture({meshcore:1});try{const p=f.page;await connect(p);
    await tab(p,'service');
    const before=await p.evaluate(()=>__apiMock.commands.length);
    await p.locator('#api-command').fill('get volume');await p.locator('#api-command-send').click();await ready(p);
    assert.match(await p.locator('#api-command-result').textContent(),/console=1.*0\.15/);
    assert.equal(await p.evaluate(()=>__apiMock.commands.length),before);
    await p.locator('#api-command').fill('ui get volume');await p.locator('#api-command-send').click();await ready(p);
    assert.match(await p.locator('#api-command-result').textContent(),/value=7/);
    await p.locator('#api-command').fill('get tx');await p.locator('#api-command-send').click();await ready(p);
    assert.match(await p.locator('#api-command-result').textContent(),/> 20/);
  }finally{await f.close();}
});

test('developer replies are inert text, never markup, and readonly refuses console writes',async()=>{
  const f=await fixture({console:1,readonly:true});try{const p=f.page;await connect(p);
    await tab(p,'service');
    await p.locator('#api-command').fill('get volume');await p.evaluate(()=>__apiMock.errorNext='> <img src=x onerror="globalThis.injected=true">');
    await p.locator('#api-command-send').click();await ready(p);
    assert.match(await p.locator('#api-command-result').textContent(),/<img/);
    assert.equal(await p.locator('#api-command-result img').count(),0);assert.equal(await p.evaluate(()=>Boolean(globalThis.injected)),false);
    const before=await p.evaluate(()=>__apiMock.commands.length);
    await p.locator('#api-command').fill('set volume 5');await p.locator('#api-command-send').click();await p.locator('#confirm-yes').click();await ready(p);
    assert.match(await p.locator('#api-command-result').textContent(),/только чтение/);
    assert.equal(await p.evaluate(()=>__apiMock.commands.length),before);
    await tab(p,'device');await p.locator('#api-adc summary').click();assert.equal(await p.locator('#api-adc-preview').isDisabled(),true);
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
    await tab(p,'wifi');
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
