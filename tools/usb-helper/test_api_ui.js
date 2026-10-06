'use strict';
// Browser-only simulation against the packaged offline application.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawnSync}=require('node:child_process'),{pathToFileURL}=require('node:url'),{chromium}=require('playwright');
const {installApiMock}=require('./test_api_fixture');
const root=path.resolve(__dirname,'../..'),output=process.env.SMARTUI_API_UI_OUTPUT?path.resolve(process.env.SMARTUI_API_UI_OUTPUT):fs.mkdtempSync(path.join(os.tmpdir(),'smartui-api-ui-'));
const artifact=path.join(output,'SmartUI_USB_Helper_1.4.html');let browser;
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
async function sync(page){await page.locator('#api-sync-enable').click();await page.waitForFunction(()=>!document.getElementById('api-fetch').disabled);}
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
test('exclusive mode, handshake, legacy API capabilities and no automatic read actions',async()=>{
  const f=await fixture();try{const p=f.page;assert.equal(await p.locator('#api-sync-enable').isDisabled(),true);await connect(p);
    assert.equal(await p.locator('#helper-mode').isDisabled(),true);assert.equal(await p.locator('#device-section').isVisible(),false);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.some(c=>/^api (sync enable|inbox)/.test(c))),false);
    assert.equal(await p.evaluate(()=>window.__apiMock.readerCount),1);assert.equal(await p.evaluate(()=>window.__apiMock.maxOpen),1);
    assert.equal(await p.locator('#api-setting-fem_pa').count(),0);assert.equal(await p.locator('#api-setting-agc_reset').isVisible(),true);
    assert.equal(await p.locator('#api-setting-melody option[value="0"]').textContent(),'0 · Пульс');
    await p.locator('#disconnect').click();await p.waitForFunction(()=>!document.getElementById('helper-mode').disabled);assert.equal(await p.evaluate(()=>window.__apiMock.closed),true);
  }finally{await f.close();}
});
test('explicit receipt, read/dismiss/snooze, safe text and responsive screenshots',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);await sync(p);
    assert.equal(await p.locator('#api-unread').textContent(),'1');assert.equal(await p.evaluate(()=>window.__apiMock.commands.some(c=>/inbox (read|received)/.test(c))),false);
    await p.locator('#api-fetch').click();await p.waitForFunction(()=>document.querySelector('.message-text')?.textContent.includes('Тест: встречаемся'));
    await ready(p);assert.equal(await p.evaluate(()=>window.__apiMock.recordState),1,'receipt must not mark read');
    assert.equal(await p.locator('#api-message-list script').count(),0);assert.match(await p.locator('.message-text').textContent(),/Канал связи работает/);
    await p.evaluate(()=>{scrollTo(0,0);const badge=document.createElement('div');badge.id='simulation-caption';badge.textContent='Симуляция USB · тестовые данные';badge.style.cssText='position:fixed;right:12px;bottom:12px;z-index:1000;background:#203744;color:#edf2f7;border:1px solid #91b8c1;border-radius:7px;padding:7px 10px;font:12px system-ui;';document.body.append(badge);});await geometry(p);await p.screenshot({path:path.join(output,'dashboard-desktop.png'),fullPage:false});
    for(const width of [320,390,730,1040]){await p.setViewportSize({width,height:1000});await geometry(p);if(width===390){await p.locator('#api-inbox').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(output,'dashboard-mobile.png'),fullPage:false});}}
    await p.evaluate(()=>document.getElementById('simulation-caption').remove());
    await p.locator('[data-action="snooze"]').click();await ready(p);assert.equal(await p.evaluate(()=>window.__apiMock.recordState&8),8);
    await p.locator('[data-action="dismiss"]').click();await ready(p);assert.equal(await p.evaluate(()=>window.__apiMock.recordState&2),0);
    await p.locator('[data-action="read"]').click();await ready(p);assert.equal(await p.evaluate(()=>window.__apiMock.recordState&2),2);assert.equal(await p.locator('#api-unread').textContent(),'0');
  }finally{await f.close();}
});
test('untrusted message markup renders as plain text only',async()=>{
  const f=await fixture({markup:true});try{await connect(f.page);await sync(f.page);await f.page.locator('#api-fetch').click();await ready(f.page);assert.match(await f.page.locator('.message-text').textContent(),/<script>не HTML/);assert.equal(await f.page.locator('#api-message-list script').count(),0);}finally{await f.close();}
});
test('API settings readback, bridge confirmation and staged Wi-Fi do not leak secrets',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);
    await p.locator('#api-setting-agc_reset').selectOption('1');await p.getByRole('button',{name:'Сохранить API: AGC-сброс · каждые 60 с',exact:true}).click();await ready(p);assert.equal(await p.evaluate(()=>window.__apiMock.settings.agc_reset),1);
    await p.locator('#api-setting-bridge').selectOption('1');await p.getByRole('button',{name:'Сохранить API: Мостовой звук · два вывода',exact:true}).click();assert.equal(await p.locator('#confirm-dialog').isVisible(),true);await p.locator('#confirm-no').click();assert.equal(await p.evaluate(()=>window.__apiMock.settings.bridge),0);
    await p.locator('#api-ssid').fill('Локальная сеть');await p.locator('#api-password').fill('private-password');await p.locator('#api-wifi-test').click();await p.waitForFunction(()=>!document.getElementById('api-wifi-save').disabled);
    assert.equal(await p.locator('#api-password').inputValue(),'');assert.equal(await p.evaluate(()=>window.__apiMock.wifi),'test_ok');
    assert.doesNotMatch(await p.locator('#api-events').textContent(),/private-password|70726976617465/);
    await p.locator('#api-wifi-save').click();await ready(p);assert.equal(await p.evaluate(()=>window.__apiMock.wifi),'saved');
    await p.locator('#api-command').fill('api caps');await p.locator('#api-command-send').click();await ready(p);assert.match(await p.locator('#api-command-result').textContent(),/Значения скрыты/);
    await p.locator('#api-command').fill('api wifi password 736563726574');await p.locator('#api-command-send').click();assert.match(await p.locator('#api-feedback').textContent(),/соответствующие разделы/);
  }finally{await f.close();}
});
test('push event pulls outside reader; gap resync, reconnect and reboot isolate IDs',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);await sync(p);
    await p.evaluate(()=>window.__apiMock.event(7,'00000000'));await p.waitForFunction(()=>document.getElementById('api-events').textContent.includes('Изменились настройки'));
    await ready(p);await p.evaluate(()=>{window.__apiMock.gap=true;window.__apiMock.event(9,'00000000');});await p.waitForFunction(()=>document.getElementById('api-events').textContent.includes('История событий изменилась'));
    await ready(p);await p.locator('#disconnect').click();await p.waitForFunction(()=>!document.getElementById('connect').disabled);
    await p.evaluate(()=>{window.__apiMock.boot='fedcba9876543210';});await connect(p);await sync(p);assert.match(await p.locator('#api-events').textContent(),/старые идентификаторы сброшены/);
    assert.equal(await p.evaluate(()=>window.__apiMock.maxOpen),1);
  }finally{await f.close();}
});
test('0.10 without sync retains API settings; read-only disables mutations',async()=>{
  for(const options of [{legacy:true},{readonly:true}]){const f=await fixture(options);try{await connect(f.page);assert.equal(await f.page.locator('#api-sync-enable').isDisabled(),true);assert.equal(await f.page.locator('#api-settings-load').isEnabled(),true);if(options.readonly)assert.equal(await f.page.locator('#api-setting-volume').isDisabled(),true);}finally{await f.close();}}
});
test('ADC preview is nonmutating, explicit save verifies readback and keeps other drafts',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);await p.locator('#api-setting-volume').selectOption('3');
    await p.locator('#api-setting-agc_reset').selectOption('1');await p.getByRole('button',{name:'Сохранить API: AGC-сброс · каждые 60 с',exact:true}).click();await ready(p);
    assert.equal(await p.locator('#api-setting-volume').inputValue(),'3');assert.equal(await p.evaluate(()=>window.__apiMock.settings.volume),7);
    await p.locator('#api-adc summary').click();await p.locator('#api-adc-measured').fill('3,90');await p.locator('#api-adc-preview').click();await ready(p);
    assert.equal(await p.evaluate(()=>window.__apiMock.settings.adc_multiplier),4.9);await p.locator('#api-adc-apply').click();await p.locator('#confirm-yes').click();await ready(p);
    assert.match(await p.locator('#api-adc-result').textContent(),/прочитана обратно/);assert.equal(await p.evaluate(()=>window.__apiMock.settings.adc_multiplier),5.028947);
    await p.locator('#api-adc-reset').click();await p.locator('#confirm-yes').click();await ready(p);assert.equal(await p.evaluate(()=>window.__apiMock.settings.adc_multiplier),4.9);
  }finally{await f.close();}
});

test('ProMicro API reference sample is not live USB voltage; source rejection disables stale save',async()=>{
  const f=await fixture({adcMin:'1.361250',adcMax:'2.268750',adcReference:3100,
    settings:{battery_mv:4100,adc_multiplier:1.97,adc_default:1.815}});
  try{const p=f.page;await connect(p);await p.locator('#api-adc summary').click();
    assert.match(await p.locator('#api-adc-source-warning').textContent(),/ProMicro.*USB.*без перезапуска.*2 минут/);
    await p.locator('#api-adc-measured').fill('3,32');await p.locator('#api-adc-preview').click();await ready(p);
    assert.match(await p.locator('#api-adc-result').textContent(),/2\.109806.*Опорный замер: 3100/);
    assert.equal(await p.evaluate(()=>window.__apiMock.settings.adc_multiplier),1.97);
    assert.equal(await p.locator('#api-adc-apply').isEnabled(),true);
    await p.evaluate(()=>{window.__apiMock.adcSourceMissing=true;});
    await p.locator('#api-adc-preview').click();await ready(p);
    assert.match(await p.locator('#api-feedback').textContent(),/Запустите ProMicro от АКБ.*без перезапуска.*2 минут/);
    assert.equal(await p.locator('#api-adc-apply').isDisabled(),true);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.some(c=>c.startsWith('api adc apply'))),false);
    assert.equal(await p.evaluate(()=>window.__apiMock.settings.adc_multiplier),1.97);
    await p.evaluate(()=>{window.__apiMock.adcSourceMissing=false;});
    await p.locator('#api-adc-preview').click();await ready(p);
    await p.locator('#api-adc-apply').click();await p.locator('#confirm-yes').click();await ready(p);
    assert.equal(await p.evaluate(()=>window.__apiMock.settings.adc_multiplier),2.109806);
    assert.match(await p.locator('#api-adc-result').textContent(),/прочитана обратно/);
  }finally{await f.close();}
});
test('unknown write outcome blocks subsequent commands and requires explicit reconnect',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);await p.evaluate(()=>{window.__apiMock.drop=true;});
    await p.locator('#api-setting-agc_reset').selectOption('1');await p.getByRole('button',{name:'Сохранить API: AGC-сброс · каждые 60 с',exact:true}).click();
    await p.waitForFunction(()=>document.getElementById('transport-state').textContent.includes('Результат неизвестен'));
    assert.equal(await p.locator('#api-settings-load').isDisabled(),true);assert.equal(await p.locator('#helper-mode').isDisabled(),true);
    assert.equal(await p.evaluate(()=>window.__apiMock.packets.filter(p=>p[0]===201&&p[7]===1&&new TextDecoder().decode(Uint8Array.from(p.slice(8)))==='api set agc_reset 1').length),1);
    await p.locator('#disconnect').click();await p.waitForFunction(()=>!document.getElementById('connect').disabled);await p.evaluate(()=>{window.__apiMock.drop=false;});await connect(p);
    assert.equal(await p.locator('#api-setting-agc_reset').inputValue(),'0');assert.equal(await p.evaluate(()=>window.__apiMock.maxOpen),1);
  }finally{await f.close();}
});
test('negotiation rejection re-enables the explicit synchronization action',async()=>{
  const f=await fixture();try{const p=f.page;await connect(p);await sync(p);
    await p.evaluate(()=>{const mock=window.__apiMock,original=mock.command;mock.command=function(request){if(request[7]===1&&new TextDecoder().decode(request.slice(8))==='api inbox next'){this.command=original;this.respond(request,'ERR api negotiate',7);return;}original.call(this,request);};});
    await p.locator('#api-fetch').click();await p.waitForFunction(()=>!document.getElementById('api-sync-enable').disabled);
    assert.match(await p.locator('#api-feedback').textContent(),/Включить синхронизацию/);assert.equal(await p.locator('#api-fetch').isDisabled(),true);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.some(c=>/^api inbox (read|dismiss)/.test(c))),false);
    await sync(p);assert.equal(await p.locator('#api-fetch').isEnabled(),true);
  }finally{await f.close();}
});
test('periodic fallback recovers a lost hint, never marks read, and stops on disconnect',async()=>{
  const f=await fixture({clock:true});try{const p=f.page;await connect(p);
    await p.clock.fastForward(16000);assert.equal(await p.evaluate(()=>window.__apiMock.commands.some(c=>c.startsWith('api events next'))),false,'no polling without opt-in');
    await sync(p);await p.evaluate(()=>{const m=window.__apiMock;m.recordState=2;m.event(3,'00000001',0,{hint:false});});
    assert.equal(await p.locator('#api-unread').textContent(),'1');await p.clock.fastForward(8000);
    await p.waitForFunction(()=>document.getElementById('api-unread').textContent==='0');await ready(p);
    assert.match(await p.locator('#api-events').textContent(),/Отмечено прочитанным/);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.some(c=>/^api inbox (read|received|dismiss|snooze|next)(?: |$)/.test(c))),false,'fallback only reads events and metadata');
    await p.locator('#disconnect').click();await p.waitForFunction(()=>!document.getElementById('connect').disabled);
    const count=await p.evaluate(()=>({writes:window.__apiMock.packets.length,reads:window.__apiMock.readCalls}));await p.clock.fastForward(60000);
    assert.deepEqual(await p.evaluate(()=>({writes:window.__apiMock.packets.length,reads:window.__apiMock.readCalls})),count,'no writes or reads after disconnect');
    await connect(p);const eventCount=await p.evaluate(()=>window.__apiMock.commands.filter(c=>c.startsWith('api events next')).length);await p.clock.fastForward(16000);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.filter(c=>c.startsWith('api events next')).length),eventCount,'reconnect requires fresh opt-in');
  }finally{await f.close();}
});
test('nonconsecutive event sequence causes metadata resync rather than accepting the event',async()=>{
  const f=await fixture({clock:true});try{const p=f.page;await connect(p);await sync(p);
    await p.evaluate(()=>{const m=window.__apiMock;m.recordState=2;m.seq+=2;m.event(3,'00000001',0,{hint:false});});
    await p.clock.fastForward(8000);await p.waitForFunction(()=>document.getElementById('api-events').textContent.includes('История событий изменилась'));await ready(p);
    assert.equal(await p.locator('#api-unread').textContent(),'0');assert.doesNotMatch(await p.locator('#api-events').textContent(),/Отмечено прочитанным/,'untrusted skipped-sequence event is not applied');
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.filter(c=>c==='api inbox snapshot').length),2);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.some(c=>/^api inbox (read|received|dismiss|snooze|next)(?: |$)/.test(c))),false);
  }finally{await f.close();}
});
test('fallback skips an active command and resumes on a later bounded tick',async()=>{
  const f=await fixture({clock:true});try{const p=f.page;await connect(p);await sync(p);
    await p.clock.fastForward(5000);
    await p.evaluate(()=>{const m=window.__apiMock,original=m.command;m.command=function(request){if(request[7]===1&&new TextDecoder().decode(request.slice(8))==='api test'){this.pendingTest=request.slice();return;}original.call(this,request);};});
    const before=await p.evaluate(()=>window.__apiMock.commands.filter(c=>c.startsWith('api events next')).length);
    await p.locator('#api-notify-test').click();await p.clock.fastForward(3000);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.filter(c=>c.startsWith('api events next')).length),before,'busy command owns transport');
    await p.evaluate(()=>{const m=window.__apiMock;m.respond(m.pendingTest,'OK api test');m.pendingTest=null;m.recordState=2;m.event(3,'00000001',0,{hint:false});});await ready(p);
    await p.clock.fastForward(8000);await p.waitForFunction(()=>document.getElementById('api-unread').textContent==='0');
    assert.equal(await p.evaluate(()=>window.__apiMock.readerCount),1);
  }finally{await f.close();}
});
test('fallback detects reboot, drops prior message identities and requires fresh opt-in',async()=>{
  const f=await fixture({clock:true});try{const p=f.page;await connect(p);await sync(p);await p.locator('#api-fetch').click();await ready(p);
    assert.match(await p.locator('.message-text').textContent(),/Канал связи работает/);
    const actions=await p.evaluate(()=>window.__apiMock.commands.filter(c=>/^api inbox (read|received|dismiss|snooze|next)(?: |$)/.test(c)).length);
    await p.evaluate(()=>{const m=window.__apiMock;m.boot='fedcba9876543210';m.seq=1;m.events=[];m.recordState=0;m.explicit=false;m.received=false;});
    await p.clock.fastForward(8000);await p.waitForFunction(()=>!document.getElementById('api-sync-enable').disabled);
    assert.match(await p.locator('#api-feedback').textContent(),/Нода перезапустилась/);assert.doesNotMatch(await p.locator('.message-text').textContent(),/Канал связи работает/);
    assert.equal(await p.evaluate(()=>window.__apiMock.commands.filter(c=>/^api inbox (read|received|dismiss|snooze|next)(?: |$)/.test(c)).length),actions);
    const count=await p.evaluate(()=>window.__apiMock.packets.length);await p.clock.fastForward(20000);assert.equal(await p.evaluate(()=>window.__apiMock.packets.length),count,'reboot ends periodic subscription');
    await sync(p);assert.match(await p.locator('#api-boot').textContent(),/76543210/);
  }finally{await f.close();}
});
