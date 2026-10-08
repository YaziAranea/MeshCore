'use strict';

// Isolated Chromium tests; no real serial ports, user profile, or network.
// Requires the development dependency `playwright` (also available via NODE_PATH).
// Optional: CHROME_PATH, PYTHON, SMARTUI_UI_OUTPUT. Runtime helper has no dependencies.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { spawnSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const { chromium } = require('playwright');
const {fullSettingsFixture}=require('./test_full_settings_fixture');

const root = path.resolve(__dirname, '../..');
const output = process.env.SMARTUI_UI_OUTPUT
  ? path.resolve(process.env.SMARTUI_UI_OUTPUT)
  : fs.mkdtempSync(path.join(os.tmpdir(), 'smartui-usb-ui-'));
const artifact = path.join(output, 'SmartUI_USB_Helper_2.4.html');
const chromeCandidates = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'
].filter(Boolean);
const executablePath = chromeCandidates.find(candidate => fs.existsSync(candidate));
let browser;

test.before(async () => {
  const packaged = spawnSync(process.env.PYTHON || 'python', [path.join(root, 'tools/package_usb_helper.py'), output], { encoding: 'utf8', windowsHide: true });
  assert.equal(packaged.status, 0, 'Helper packaging failed: ' + packaged.stderr);
  assert.equal(fs.existsSync(artifact), true);
  browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  console.log('Isolated browser: ' + browser.version());
  console.log('Rendered artifacts: ' + output);
});
test.after(async () => { if (browser) await browser.close(); });

function installSerialMock({ supported, readOnly, manualTest, info, replies, localRecovery, settings, settingsCaps, radioFeature, manualAdc, schemas, extendedValues, soundPreview }) {
  if (!supported) {
    Object.defineProperty(Navigator.prototype, 'serial', { configurable: true, get: () => undefined });
    return;
  }
  const mock = window.__serialMock = {
    requests: 0, commands: [], raw: [], mode: localRecovery ? 'USB' : 'BLE', configured: false,
    replies, localRecovery, quickReplies: Array(9).fill(''), settings, settingsReadErrors:{},
    radio:{freq_khz:869525,bw_hz:250000,sf:11,cr:5,path_bytes:3,tx_dbm:20,repeat:0},advert:{interval_min:60},
    settingsCaps:{v:1,adc:1,sound:1,board_led:1,unread_led:1,vibration:0,gps:0,battery_protection:1,display:0,melody_max:30,adc_min:3.675,adc_max:6.125,...settingsCaps},
    settingsState:{battery_mv:3800,adc_multiplier:4.9,adc_default:4.9,sound_quiet:0,volume:10,melody:0,board_led:1,unread_led:1,vibration:0,gps:0,battery_protection:1,shutdown_mv:3200,muted:0},
    adcService:{supported:1,active:0,remaining_ms:0,external:1},identity:'Нода',tx:20,
    settingsRecord(kind,values){return 'OK settings '+kind+' '+Object.entries(values).map(([key,value])=>key+'='+value).join(' ');},
    stage: 'idle', manualTest, readOnly, info, closed: false, ssid: null, password: null,
    emit(text) {
      if (this.closed) return;
      const bytes = new TextEncoder().encode(text + '\r\n');
      for (let i = 0; i < bytes.length; i += 7) {
        try { this.controller.enqueue(bytes.slice(i, i + 7)); } catch (_) { return; }
      }
    },
    complete(passed) {
      this.stage = passed ? 'passed' : 'idle';
      this.emit(passed ? "WiFi test passed. Type 'wifi save' to store it." : 'WiFi test failed; credentials were not saved.');
    },
    command(raw) {
      this.commands.push(raw);
      if (this.stage === 'ssid' || this.stage === 'password') {
        if (raw === 'cancel') { this.stage = 'idle'; this.emit('WiFi setup cancelled.'); return; }
        if (this.stage === 'ssid') {
          this.ssid = raw;
          this.stage = 'password';
          this.emit("Password input is hidden; enter 8..64 bytes, blank for open WiFi, or 'cancel':");
        } else {
          this.password = raw;
          this.stage = 'testing';
          this.emit('Testing WiFi without saving...');
          if (!this.manualTest) this.complete(true);
        }
        return;
      }
      const command = raw.trim().toLowerCase();
      if(radioFeature&&/^settings (radio|advert)( |$)/.test(command)){
        const [,kind,action,...values]=command.split(' ');
        if(action==='set'&&readOnly){this.emit('ERR settings readonly');return;}
        if(action==='set'){const keys=kind==='radio'?['freq_khz','bw_hz','sf','cr','path_bytes']:['interval_min'];keys.forEach((key,i)=>this[kind][key]=Number(values[i]));}
        this.emit('OK settings '+kind+' '+Object.entries(this[kind]).map(([k,v])=>k+'='+v).join(' '));return;
      }
      if ((this.readOnly || this.localRecovery) && command !== 'status' && !(this.settings && ['help','info','settings caps','settings get'].includes(command)) && !(this.localRecovery && command === 'wifi forget')) { this.emit('Connection settings are read-only during storage recovery.'); return; }
      if(this.settings && command.startsWith('settings ')) {
        if(command==='settings caps') this.emit(this.settingsRecord('caps',this.settingsCaps));
        else if(command==='settings get') this.emit(this.settingsRecord('get',Object.fromEntries(['battery_mv','adc_multiplier','adc_default','sound_quiet','volume','melody','board_led','unread_led','vibration','gps','battery_protection','shutdown_mv','muted'].map(key=>[key,this.settingsState[key]]))));
        else if(command==='settings caps schema')this.emit(schemas?'OK settings caps key=schema value=1':'ERR settings unsupported');
        else if(command==='settings caps sound_preview')this.emit(soundPreview?'OK settings caps key=sound_preview value=1':'ERR settings unsupported');
        else if(command==='settings sound preview')this.emit(''+(!soundPreview?'ERR settings unsupported':this.settingsState.muted?'ERR settings muted':'OK settings sound_preview'));
        else if(command.startsWith('settings schema ')){const key=command.slice(16),s=schemas?.[key]||{supported:Number(Object.hasOwn(this.settingsState,key)&&!['vibration','gps'].includes(key)),min:key==='volume'?1:0,max:key==='melody'?30:key==='volume'?10:1,step:1,options:'-'};this.emit('OK settings schema key='+key+' '+Object.entries(s).map(([k,v])=>k+'='+v).join(' '));}
        else if(command.startsWith('settings get ')){const key=command.slice(13);this.emit(this.settingsReadErrors[key]?'ERR settings '+this.settingsReadErrors[key]:'OK settings get key='+key+' value='+(this.settingsState[key]??extendedValues?.[key]));}
        else if(command==='settings identity')this.emit('OK settings identity name_hex='+Array.from(new TextEncoder().encode(this.identity),b=>b.toString(16).padStart(2,'0')).join('')+' max_name_bytes=31');
        else if(command.startsWith('settings name ')){const hex=command.slice(14);this.identity=new TextDecoder().decode(Uint8Array.from(hex.match(/../g),b=>parseInt(b,16)));this.emit('OK settings name name_hex='+hex);}
        else if(command==='settings tx'||command.startsWith('settings tx set ')){if(command.startsWith('settings tx set '))this.tx=Number(command.slice(16));this.emit('OK settings tx value='+this.tx+' min=-9 max=22');}
        else if(command==='settings adc manual')this.emit(manualAdc===undefined?'ERR settings invalid':'OK settings adc_manual supported='+Number(manualAdc));
        else if(this.settingsFailure) this.emit('ERR settings '+this.settingsFailure);
        else if(command.startsWith('settings adc set ')){
          if(!manualAdc){this.emit('ERR settings unsupported');return;}
          this.settingsState.adc_multiplier=Number(command.split(' ').at(-1));this.adcServiceDeadline=0;
          if(!this.dropAdcAck)this.emit('OK settings adc_set');
        }
        else if(command.startsWith('settings adc service')) {
          if(!this.settingsCaps.adc_service){this.emit('ERR settings unsupported');return;}
          if(command.endsWith(' start')){
            if(!this.adcService.external){this.emit('ERR settings usb_required');return;}
            if(!this.adcService.active)this.adcServiceDeadline=Date.now()+120000;
          }
          if(command.endsWith(' stop'))this.adcServiceDeadline=0;
          this.adcService.remaining_ms=Math.max(0,(this.adcServiceDeadline||0)-Date.now());
          this.adcService.active=Number(this.adcService.remaining_ms>0);
          this.emit(this.settingsRecord('adc_service',this.adcService));
        }
        else if(command.startsWith('settings set ')) {
          const [,,key,value]=command.split(' ');this.settingsState[key]=Number(value);
          this.settingsState.shutdown_mv=this.settingsState.battery_protection?3200:2700;
          this.emit('OK settings set key='+key+' value='+value);
        } else if(command.startsWith('settings adc preview ')) {
          const measured=Number(command.split(' ').at(-1));
          this.adcPreview={token:7,sampled_mv:this.settingsState.battery_mv,measured_mv:measured,multiplier:Number((this.settingsState.adc_multiplier*measured/this.settingsState.battery_mv).toFixed(6))};
          this.emit(this.settingsRecord('adc_preview',this.adcPreview));
        } else if(command==='settings adc apply 7' && this.adcPreview) {this.adcServiceDeadline=0;this.settingsState.adc_multiplier=this.adcPreview.multiplier;this.emit('OK settings adc_apply');}
        else if(command==='settings adc reset') {this.adcServiceDeadline=0;this.settingsState.adc_multiplier=this.settingsState.adc_default;this.emit('OK settings adc_reset');}
        else if(command==='settings test') this.emit('OK settings test');
        else this.emit('ERR settings invalid');
        return;
      }
      const getReply = /^reply get ([1-9])$/.exec(command);
      const setReply = /^reply set ([1-9]) (-|[0-9a-f]+)$/.exec(command);
      if (this.replies && getReply) {
        const slot=Number(getReply[1])-1;
        this.emit('Reply='+(slot+1)+' hex='+SmartUiConsole.encodeReply(this.quickReplies[slot])); return;
      }
      if (this.replies && setReply) {
        const slot=Number(setReply[1])-1;
        this.quickReplies[slot]=SmartUiConsole.decodeReply('Reply='+(slot+1)+' hex='+setReply[2],slot).text;
        this.emit('Reply '+(slot+1)+' saved.');return;
      }
      switch (command) {
        case 'help': this.emit('Commands: ' + (this.info ? 'info | ' : '') + 'status | mode ble | mode usb | mode wifi | wifi setup | wifi status | wifi save | wifi cancel | wifi forget | ' + (this.replies ? 'reply get N | reply set N HEX | ' : '') + 'help\r\n'+(this.settings?'Settings protocol: 1\r\n':'')+'Credential input is not echoed. WiFi is saved only after a passed test.'); break;
        case 'info': this.emit(this.info || "Unknown command. Type 'help'."); break;
        case 'status': {
          const online = this.mode === 'WiFi' && this.configured;
          this.emit('Mode=' + this.mode + ' companion=idle via=none USB-service=on WiFi-config=' + (this.configured ? 'yes' : 'no') + ' link=' + (online ? 'associated' : 'down') + ' IP=' + (online ? '192.168.1.77' : 'none') + ' approval=none storage=' + (this.localRecovery ? 'recovery-required' : 'ok'));
          break;
        }
        case 'wifi setup': this.stage = 'ssid'; this.emit('SSID input is hidden; enter SSID, then Enter:'); break;
        case 'wifi cancel': this.stage = 'idle'; this.emit('WiFi setup cancelled.'); break;
        case 'wifi save':
          if (this.stage === 'passed') { this.configured = true; this.stage = 'idle'; this.emit('Tested WiFi saved.'); }
          else this.emit('Nothing saved; pass WiFi test first.');
          break;
        case 'mode wifi': this.mode = 'WiFi'; this.emit('Mode WiFi saved.'); break;
        case 'mode ble': this.mode = 'BLE'; this.emit('Mode BLE saved.'); break;
        case 'mode usb': this.mode = 'USB'; break; // Firmware closes service TX before an ACK.
        case 'wifi forget': this.configured = false; this.mode = 'BLE'; this.localRecovery = false; this.emit('WiFi credentials forgotten.'); break;
        default: this.emit("Unknown command. Type 'help'.");
      }
    },
    async open(options) {
      this.openOptions = options;
      this.closed = false;
      this.input = '';
      this.readable = new ReadableStream({ start: controller => { this.controller = controller; } });
      this.writable = new WritableStream({ write: bytes => {
        const text = new TextDecoder().decode(bytes);
        this.raw.push(text);
        for (const char of text) {
          if (char === '\b' || char === '\x7f') this.input = this.input.slice(0, -1);
          else if (char === '\n' || char === '\r') {
            if (this.input || this.stage === 'password') this.command(this.input);
            this.input = '';
          } else this.input += char;
        }
      } });
    },
    async close() { this.closed = true; },
    unplug() { this.controller.error(new Error('<private> untrusted hardware error')); }
  };
  Object.defineProperty(Navigator.prototype, 'serial', {
    configurable: true,
    get: () => ({ requestPort: async () => { mock.requests++; return mock; } })
  });
}

async function fixture(options = {}) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 1000 }, locale: 'ru-RU' });
  const page = await context.newPage();
  const errors = [];
  const network = [];
  if(options.clock)await page.clock.install({time:new Date('2026-01-01T12:00:00Z')});
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/^https?:/i.test(request.url())) network.push(request.url()); });
  await page.addInitScript(installSerialMock, { supported: options.supported !== false, readOnly: Boolean(options.readOnly), manualTest: Boolean(options.manualTest), info: options.info || null, replies:Boolean(options.replies),localRecovery:Boolean(options.localRecovery),settings:Boolean(options.settings),settingsCaps:options.settingsCaps||{},radioFeature:Boolean(options.radioFeature),manualAdc:options.manualAdc,schemas:options.schemas,extendedValues:options.extendedValues,soundPreview:Boolean(options.soundPreview) });
  await page.goto(pathToFileURL(artifact).href);
  assert.equal(await page.evaluate(() => window.isSecureContext), true, 'file:// must be a secure context in supported desktop Chromium');
  return {
    page, context, errors, network,
    async close() {
      // Ignore beforeunload only in the isolated test page; never touch user tabs.
      await context.close();
      assert.deepEqual(errors, [], 'Browser runtime errors');
      assert.deepEqual(network, [], 'Offline helper must make no HTTP(S) requests');
    }
  };
}

async function connect(page) {
  assert.equal(await page.locator('#connect').isEnabled(), true);
  assert.equal(await page.evaluate(() => window.__serialMock.requests), 0, 'No port request without a user gesture');
  await page.locator('#connect').click();
  await page.waitForFunction(() => document.getElementById('connection').textContent === 'Консоль SmartUI подключена');
  assert.equal(await page.locator('#disconnect').isEnabled(), true);
  await tab(page, 'device');
}
async function tab(page, name) {
  await page.locator('[data-page-target="' + name + '"]').click();
  assert.equal(await page.locator('[data-page-target="' + name + '"]').getAttribute('aria-selected'), 'true');
}
async function ready(page) { await page.waitForFunction(() => !document.getElementById('test').disabled); }
test('console city presets and auto advert use same controls with confirmation/readback',async()=>{
  const f=await fixture({radioFeature:true,settings:true,info:'SmartUI=0.13 core=1.17.1 build=1234abcd upstream=a27e78e4 capabilities=BLE,USB board=Heltec T114'});
  try{const p=f.page;await connect(p);await tab(p,'radio');await p.waitForFunction(()=>!document.getElementById('radio-refresh').disabled);
    await p.locator('#preset-search').fill('Омск');await p.locator('#preset-city').selectOption({index:1});
    await confirm(p,'#preset-apply',false);assert.equal(await p.evaluate(()=>window.__serialMock.commands.some(c=>c.startsWith('settings radio set'))),false);
    await confirm(p,'#preset-apply',true);await p.waitForFunction(()=>document.getElementById('radio-status').textContent.includes('прочитан обратно'));
    const result=await p.evaluate(()=>({radio:window.__serialMock.radio,city:SmartUiPresets.get(document.getElementById('preset-city').value)}));
    assert.equal(result.radio.freq_khz,result.city.frequencyKHz);assert.equal(result.radio.path_bytes,3);assert.equal(result.radio.tx_dbm,20);
    await p.locator('#advert-interval').selectOption('30');await confirm(p,'#advert-save',true);await p.waitForFunction(()=>document.getElementById('radio-status').textContent.includes('Интервал автоанонса сохранён'));
    assert.equal(await p.evaluate(()=>window.__serialMock.advert.interval_min),30);
    assert.equal(await p.evaluate(()=>window.__serialMock.commands.filter(c=>c==='settings advert set 30').length),1);
  }finally{await f.close();}
});
async function confirm(page, button, accepted) {
  await page.locator(button).click();
  assert.equal(await page.locator('#confirm-dialog').isVisible(), true);
  assert.equal(await page.evaluate(() => document.activeElement.id), 'confirm-no');
  await page.locator(accepted ? '#confirm-yes' : '#confirm-no').click();
  await page.waitForFunction(() => !document.getElementById('confirm-dialog').open);
}
async function noOverlap(page) {
  const problems = await page.evaluate(() => {
    const errors = [];
    const visible = element => element.getClientRects().length && !element.closest('[hidden]');
    const overlap = (a, b) => {
      const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
      return Math.min(ar.right, br.right) - Math.max(ar.left, br.left) > 1 && Math.min(ar.bottom, br.bottom) - Math.max(ar.top, br.top) > 1;
    };
    if (document.documentElement.scrollWidth > innerWidth + 1) errors.push('horizontal page overflow');
    for (const element of document.querySelectorAll('header,.notice,.card,footer,dialog[open]')) {
      if (!visible(element)) continue;
      const rect = element.getBoundingClientRect();
      if (rect.left < -1 || rect.right > innerWidth + 1) errors.push(element.tagName + ' extends beyond viewport');
    }
    const cards = [...document.querySelectorAll('.card')].filter(visible);
    for (let i = 0; i < cards.length; i++) for (let j = i + 1; j < cards.length; j++) if (overlap(cards[i], cards[j])) errors.push('overlapping cards');
    for (const group of document.querySelectorAll('.buttons')) {
      const buttons = [...group.querySelectorAll('button')].filter(visible);
      for (const button of buttons) {
        const rect = button.getBoundingClientRect();
        if (rect.height < 43) errors.push(button.id + ' target too short');
      }
      for (let i = 0; i < buttons.length; i++) for (let j = i + 1; j < buttons.length; j++) if (overlap(buttons[i], buttons[j])) errors.push('overlapping action buttons');
    }
    return errors;
  });
  assert.deepEqual(problems, []);
}

async function bridgeScreenshots(page,state){
  const viewport=page.viewportSize();
  await page.locator('#device-section').evaluate(section=>{const caption=document.createElement('p');caption.id='bridge-simulation-caption';caption.className='hint';caption.textContent='Симуляция USB · не физическая плата. Мостовой звук: проверка отображения.';section.prepend(caption);});
  for(const [size,width,height]of [['desktop',1440,1000],['mobile',390,844]]){
    await page.setViewportSize({width,height});await noOverlap(page);await page.screenshot({path:path.join(output,'helper-2.3-console-bridge-'+state+'-'+size+'.png'),fullPage:true});
  }
  await page.locator('#bridge-simulation-caption').evaluate(caption=>caption.remove());await page.setViewportSize(viewport);
}

test('console tabs expose sound pins, hash and collapsed phrases without sending commands',async()=>{
  const full=fullSettingsFixture(),f=await fixture({settings:true,replies:true,radioFeature:true,soundPreview:true,info:RELEASE_DEVICE_INFO,schemas:full.schemas,extendedValues:full.settings});
  try{const p=f.page;await connect(p);await p.waitForFunction(()=>!document.getElementById('sound-read').disabled);
    const before=await p.evaluate(()=>__serialMock.commands.length);
    assert.equal(await p.locator('[data-page-target]').count(),7);
    for(const name of ['connection','radio','sound','device','wifi','phrases','service']){
      await tab(p,name);
      assert.deepEqual(await p.evaluate(selected=>[...document.querySelectorAll('[data-pages]')].filter(el=>!el.dataset.pages.split(/\s+/).includes(selected)&&el.getClientRects().length).map(el=>el.id||el.tagName),name),[],'Only active tab panels are visible');
      await noOverlap(p);
    }
    await tab(p,'sound');
    assert.equal(await p.locator('#settings-advanced').isChecked(),false);
    for(const key of ['bridge','tone_pin','led_pin','vibe_pin'])assert.equal(await p.locator('#setting-'+key).isVisible(),true,key+' is a basic sound control');
    assert.equal(await p.evaluate(()=>Math.abs(document.getElementById('sound-panel').getBoundingClientRect().top-document.getElementById('lights-panel').getBoundingClientRect().top)<2),true,'Desktop sound and LED panels share one row even without GPS');
    await tab(p,'radio');assert.equal(await p.locator('#path-bytes').isVisible(),true);
    await tab(p,'phrases');assert.equal(await p.locator('#replies-panel').getAttribute('open'),null);assert.equal(await p.locator('#reply-0').isVisible(),false);
    assert.equal(await p.evaluate(()=>__serialMock.commands.length),before,'Tab changes cannot transmit settings or test commands');
    await p.evaluate(()=>{const badge=document.createElement('div');badge.textContent='СИМУЛЯЦИЯ USB · не физическая плата';badge.style.cssText='position:fixed;right:12px;bottom:12px;z-index:1000;background:#1d2d4a;color:#eff4ff;border:1px solid #7192d9;border-radius:7px;padding:7px 10px;font:12px system-ui;';document.body.append(badge);});
    for(const [size,width,height]of [['desktop',1440,1000],['mobile',390,844]]){
      await p.setViewportSize({width,height});
      for(const name of ['connection','radio','sound','device','wifi','phrases','service']){await tab(p,name);await noOverlap(p);await p.evaluate(()=>scrollTo(0,0));await p.screenshot({path:path.join(output,'helper-2.3-console-'+name+'-'+size+'.png'),fullPage:true});}
    }
  }finally{await f.close();}
});

test('console sound refresh reads bridge 0 to 1 to 0, discards sound drafts and keeps other drafts without writes',async()=>{
  const full=fullSettingsFixture(),f=await fixture({settings:true,radioFeature:true,soundPreview:true,info:RELEASE_DEVICE_INFO,schemas:full.schemas,extendedValues:full.settings,settingsCaps:{display:1}});
  try{const p=f.page;await connect(p);await p.locator('#setting-ui_theme').selectOption('2');await tab(p,'sound');
    assert.equal(await p.locator('#settings-advanced').isChecked(),false);
    assert.equal(await p.locator('#setting-bridge').isVisible(),true);
    assert.equal(await p.locator('#setting-bridge').inputValue(),'0');
    const initial=await p.locator('#sound-output-state').textContent();
    assert.match(initial,/мост[^·.]*выключен/i);assert.match(initial,/31/);assert.match(initial,/10/);
    await p.locator('#setting-volume').selectOption('3');await p.locator('#setting-bridge').selectOption('1');
    assert.equal(await p.locator('#sound-output-state').textContent(),initial,'Drafts must not change the saved output summary');
    await p.evaluate(()=>Object.assign(__serialMock.settingsState,{bridge:1,volume:8,melody:18,tone_pin:33,sound_quiet:1}));
    const before=await p.evaluate(()=>__serialMock.commands.length);
    await p.locator('#sound-read').click();await p.locator('#confirm-no').click();
    assert.equal(await p.locator('#setting-volume').inputValue(),'3');assert.equal(await p.locator('#setting-bridge').inputValue(),'1');assert.equal(await p.evaluate(()=>__serialMock.commands.length),before);
    await p.locator('#sound-read').click();await p.locator('#confirm-yes').click();await p.waitForFunction(()=>!document.getElementById('sound-read').disabled&&document.getElementById('setting-volume').value==='8');
    assert.equal(await p.locator('#setting-tone_pin').inputValue(),'33');assert.equal(await p.locator('#setting-melody').inputValue(),'18');assert.equal(await p.locator('#setting-sound_quiet').inputValue(),'1');
    assert.equal(await p.locator('#setting-bridge').inputValue(),'1');assert.match(await p.locator('#saved-bridge').textContent(),/Прочитано/);
    const enabled=await p.locator('#sound-output-state').textContent();assert.match(enabled,/мост[^·.]*включен|мост[^·.]*включён/i);assert.match(enabled,/33/);assert.match(enabled,/8/);
    await bridgeScreenshots(p,'enabled');
    await p.locator('#setting-bridge').selectOption('0');assert.equal(await p.locator('#sound-output-state').textContent(),enabled);
    await p.locator('#sound-read').click();await p.locator('#confirm-yes').click();await p.waitForFunction(()=>!document.getElementById('sound-read').disabled&&document.getElementById('setting-bridge').value==='1');
    assert.equal(await p.locator('#saved-bridge').getAttribute('data-dirty'),'false','Explicit read discards a bridge draft that differs from the node');
    await p.evaluate(()=>__serialMock.settingsState.bridge=0);await p.locator('#sound-read').click();await p.waitForFunction(()=>!document.getElementById('sound-read').disabled&&document.getElementById('setting-bridge').value==='0');
    assert.match(await p.locator('#sound-output-state').textContent(),/мост[^·.]*выключен/i);
    assert.equal(await p.locator('#setting-ui_theme').inputValue(),'2');
    assert.equal(await p.evaluate(n=>__serialMock.commands.slice(n).some(c=>/settings (set|sound preview|test|adc (set|apply|reset))/.test(c)),before),false,'Refresh must not change or play anything');
  }finally{await f.close();}
});

test('console bridge stays visible and unavailable without schema or with unsupported schema',async()=>{
  for(const schema of [false,true]){
    const full=fullSettingsFixture();full.schemas.bridge.supported=0;
    const f=await fixture({settings:true,radioFeature:true,info:RELEASE_DEVICE_INFO,...(schema?{soundPreview:true,schemas:full.schemas,extendedValues:full.settings}:{})});
    try{const p=f.page;await connect(p);await tab(p,'sound');
      for(let read=0;read<2;read++){
        assert.equal(await p.locator('#setting-bridge').isVisible(),true);assert.equal(await p.locator('#setting-bridge').isDisabled(),true);
        assert.match(await p.locator('#saved-bridge').textContent(),schema?/Недоступно|не поддержива/i:/не прочитан|не подтвержд/i);
        assert.match(await p.locator('#sound-output-state').textContent(),schema?/Мост: недоступен/:/Мост: не прочитан/);
        assert.doesNotMatch(await p.locator('#saved-bridge').textContent(),/На ноде:|Прочитано|null|Выключен/);
        await p.locator('#sound-read').click();await p.waitForFunction(()=>!document.getElementById('sound-read').disabled);
      }
      assert.equal(await p.evaluate(()=>__serialMock.commands.includes('settings get bridge')),false,'Unsupported schema must skip bridge read');
      assert.equal(await p.evaluate(()=>__serialMock.commands.some(c=>c.startsWith('settings set '))),false);
      if(schema)await bridgeScreenshots(p,'unsupported');
    }finally{await f.close();}
  }
});

test('console bridge read errors clear confirmed output instead of reporting bridge off',async()=>{
  for(const error of ['unsupported','storage']){
    const full=fullSettingsFixture(),f=await fixture({settings:true,info:RELEASE_DEVICE_INFO,schemas:full.schemas,extendedValues:full.settings});
    try{const p=f.page;await p.evaluate(()=>__serialMock.settingsState.bridge=1);await connect(p);await tab(p,'sound');
      await p.evaluate(error=>__serialMock.settingsReadErrors.bridge=error,error);await p.locator('#sound-read').click();
      await p.waitForFunction(()=>!document.getElementById('sound-read').disabled&&SmartUiLegacy.getState().deviceSettings===null);
      assert.match(await p.locator('#sound-output-state').textContent(),/не подтвержд|не прочитан|нет подтвержд/i);
      assert.doesNotMatch(await p.locator('#sound-output-state').textContent(),/мост[^·.]*выключен/i);
      assert.equal(await p.locator('#setting-bridge').isVisible(),true);assert.equal(await p.locator('#setting-bridge').isDisabled(),true);
      assert.equal(await p.evaluate(()=>__serialMock.commands.some(c=>c.startsWith('settings set '))),false);
    }finally{await f.close();}
  }
});

test('console melody preview is distinct from notification test and never changes quiet settings',async()=>{
  const full=fullSettingsFixture(),f=await fixture({settings:true,soundPreview:true,info:RELEASE_DEVICE_INFO,schemas:full.schemas,extendedValues:full.settings});
  try{const p=f.page;await connect(p);await tab(p,'sound');
    await p.evaluate(()=>Object.assign(__serialMock.settingsState,{sound_quiet:1,muted:0,melody:18}));
    await p.locator('#sound-read').click();await p.waitForFunction(()=>!document.getElementById('sound-read').disabled&&document.getElementById('setting-sound_quiet').value==='1');
    const before=await p.evaluate(()=>__serialMock.commands.length);
    await p.locator('#sound-preview').click();await p.waitForFunction(()=>__serialMock.commands.includes('settings sound preview')&&!document.getElementById('sound-preview').disabled);
    assert.equal(await p.evaluate(()=>__serialMock.settingsState.sound_quiet),1);assert.equal(await p.evaluate(()=>__serialMock.settingsState.muted),0);
    assert.equal(await p.evaluate(n=>__serialMock.commands.slice(n).some(c=>c.startsWith('settings set ')),before),false);
    await p.evaluate(()=>__serialMock.settingsState.muted=1);await p.locator('#sound-preview').click();
    await p.waitForFunction(()=>document.getElementById('sound-action-status').textContent.includes('тишина'));
    assert.equal(await p.evaluate(()=>__serialMock.commands.filter(c=>c==='settings sound preview').length),1,'Fresh muted state blocks preview before transmission');
  }finally{await f.close();}
  const old=await fixture({settings:true,info:RELEASE_DEVICE_INFO});try{await connect(old.page);await tab(old.page,'sound');assert.equal(await old.page.locator('#sound-preview').isDisabled(),true);assert.equal(await old.page.evaluate(()=>__serialMock.commands.includes('settings sound preview')),false);}finally{await old.close();}
});

test('offline package loads in Chrome: unsupported Web Serial and responsive layout', async () => {
  const f = await fixture({ supported: false });
  try {
    assert.equal(await f.page.title(), 'SmartUI · Локальный центр управления');
    assert.equal(await f.page.locator('#unsupported').isVisible(), true);
    for (const selector of ['#connect', '#disconnect', '#test', '#save', '#refresh', '#mode-wifi', '#forget']) assert.equal(await f.page.locator(selector).isDisabled(), true);
    for (const width of [320, 390, 730, 731, 1040, 1440]) {
      await f.page.setViewportSize({ width, height: 1000 });
      await noOverlap(f.page);
      if ([320, 390, 1440].includes(width)) await f.page.screenshot({ path: path.join(output, 'unsupported-' + width + '.png'), fullPage: true });
    }
  } finally { await f.close(); }
});

test('real browser mock-serial flow: test, save, confirmation, switch, forget, USB', async () => {
  const f = await fixture({ manualTest: true });
  const page = f.page;
  try {
    assert.equal(await page.locator('#unsupported').isVisible(), false);
    await connect(page);
    await ready(page);
    assert.equal(await page.locator('#info-firmware').textContent(), '—');
    assert.equal(await page.evaluate(() => window.__serialMock.commands.includes('info')), false, 'legacy 0.05 must not receive info');
    assert.equal(await page.locator('#mode').textContent(), 'Bluetooth');
    await tab(page,'wifi');
    await page.locator('#ssid').fill('  Сеть Home  ');
    await page.locator('#password').fill('  private<PW>  ');
    await page.locator('#show-password').check();
    assert.equal(await page.locator('#password').getAttribute('type'), 'text');
    await page.locator('#test').click();
    await page.waitForFunction(() => window.__serialMock.stage === 'testing');
    assert.equal(await page.locator('#password').inputValue(), '');
    assert.equal(await page.locator('#password').getAttribute('type'), 'password');
    assert.equal(await page.locator('#show-password').isChecked(), false);
    assert.equal(await page.locator('#disconnect').isEnabled(), true);
    for (const selector of ['#test', '#save', '#cancel', '#refresh', '#mode-wifi']) assert.equal(await page.locator(selector).isDisabled(), true);
    assert.deepEqual(await page.evaluate(() => [window.__serialMock.ssid, window.__serialMock.password]), ['  Сеть Home  ', '  private<PW>  ']);
    await page.evaluate(() => window.__serialMock.complete(true));
    await page.waitForFunction(() => !document.getElementById('save').disabled);
    assert.equal(await page.locator('#test').isDisabled(), true);
    assert.equal(await page.locator('#refresh').isDisabled(), true);
    assert.equal(await page.evaluate(() => window.__serialMock.commands.includes('wifi save')), false);
    await page.screenshot({ path: path.join(output, 'test-passed-desktop.png'), fullPage: true });
    await page.locator('#save').click();
    await ready(page);
    assert.equal(await page.locator('#configured').textContent(), 'Есть');
    const visibleText = await page.locator('body').innerText();
    assert.equal(visibleText.includes('private<PW>'), false);
    assert.equal(visibleText.includes('Сеть Home'), false);

    await tab(page,'connection');await confirm(page, '#mode-wifi', false);
    assert.equal(await page.evaluate(() => window.__serialMock.commands.includes('mode wifi')), false);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#mode-wifi').click();
    await noOverlap(page);
    await page.screenshot({ path: path.join(output, 'confirm-mobile.png'), fullPage: true });
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#confirm-dialog').isVisible(), false);
    await confirm(page, '#mode-wifi', true);
    await ready(page);
    assert.equal(await page.locator('#mode').textContent(), 'Wi-Fi');
    assert.equal(await page.locator('#ip').textContent(), '192.168.1.77');
    assert.equal(await page.locator('#mode-wifi').getAttribute('aria-pressed'), 'true');
    await page.locator('summary').filter({ hasText: 'Служебные события' }).click();
    await confirm(page, '#forget', false);
    assert.equal(await page.locator('#configured').textContent(), 'Есть');
    await confirm(page, '#forget', true);
    await ready(page);
    assert.equal(await page.locator('#configured').textContent(), 'Не задана');
    assert.equal(await page.locator('#mode').textContent(), 'Bluetooth');
    await page.locator('#clear-events').click();
    assert.equal(await page.locator('#events li').count(), 0);

    await tab(page,'wifi');await page.locator('#ssid').fill('cancel');
    await page.locator('#password').fill('password');
    await page.locator('#test').click();
    await page.waitForFunction(() => document.getElementById('feedback').textContent.includes('зарезервирован'));
    assert.equal(await page.locator('#password').inputValue(), '');
    await ready(page);
    await page.locator('#ssid').fill('Open network');
    await page.locator('#open-network').check();
    assert.equal(await page.locator('#password').isDisabled(), true);
    assert.equal(await page.locator('#open-warning').isVisible(), true);
    await page.evaluate(() => { window.__serialMock.manualTest = false; });
    await page.locator('#test').click();
    await page.waitForFunction(() => !document.getElementById('save').disabled);
    assert.equal(await page.evaluate(() => window.__serialMock.password), '');
    await page.locator('#cancel').click();
    await ready(page);
    assert.equal(await page.locator('#configured').textContent(), 'Не задана');

    await tab(page,'connection');await confirm(page, '#mode-usb', true);
    await page.waitForFunction(() => document.getElementById('connection').textContent === 'Нода не подключена');
    assert.equal(await page.locator('#connect').isEnabled(), true);
    assert.equal(await page.evaluate(() => window.__serialMock.closed), true);
    assert.equal(await page.locator('#mode').textContent(), '—');
    assert.match(await page.locator('#feedback').textContent(), /результат неизвестен/);
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
  } finally { await f.close(); }
});

test('0.06 identity uses text fields, fits narrow screens and gates known non-WiFi boards', async () => {
  for (const wifi of [true, false]) {
    const board = wifi ? 'Heltec V3' : 'Heltec T114 (nRF52840)';
    const f = await fixture({info:'SmartUI=0.06 core=PS22b17 build=0123456789012345678901234567890123456789 upstream=abcdef01 capabilities=BLE,USB' + (wifi ? ',WiFi' : '') + ' board=' + board});
    try {
      await connect(f.page);
      assert.equal(await f.page.locator('#info-firmware').textContent(), '0.06');
      assert.equal(await f.page.locator('#info-core').textContent(), 'PS22b17');
      assert.equal(await f.page.locator('#info-board').textContent(), board);
      assert.equal(await f.page.locator('#info-build').textContent(), '0123456789012345678901234567890123456789');
      assert.equal(await f.page.evaluate(() => window.__serialMock.commands.filter(x => x === 'info').length), 1);
      for (const id of ['ssid','password','show-password','open-network','test','cancel','forget','mode-wifi']) {
        assert.equal(await f.page.locator('#' + id).isEnabled(), wifi, id + ' capability gate');
      }
      for (const id of ['mode-ble','mode-usb','refresh']) assert.equal(await f.page.locator('#' + id).isEnabled(), true);
      for (const width of [320, 390, 1280]) {
        await f.page.setViewportSize({width,height:1000});
        await noOverlap(f.page);
        await f.page.screenshot({path:path.join(output, 'info-' + (wifi ? 'wifi' : 'nrf') + '-' + width + '.png'),fullPage:true});
      }
      await f.page.locator('#disconnect').click();
      await f.page.waitForFunction(() => document.getElementById('connection').textContent === 'Нода не подключена');
      assert.equal(await f.page.locator('#info-board').textContent(), '—');
    } finally {await f.close();}
  }
});

test('invalid advertised info never renders device markup or enables credentials', async () => {
  const f = await fixture({info:'SmartUI=0.06 core=PS22b17 build=123abc upstream=abc123 capabilities=BLE,USB board=<img src=x onerror=alert(1)>'});
  try {
    await f.page.locator('#connect').click();
    await f.page.waitForFunction(() => document.getElementById('feedback').textContent.includes('Ответ не соответствует'));
    assert.equal(await f.page.locator('#test').isDisabled(), true);
    assert.equal(await f.page.locator('#info-board').textContent(), '—');
    assert.equal(await f.page.locator('img').count(), 0);
    assert.equal((await f.page.locator('body').textContent()).includes('<img'), false);
    assert.equal(await f.page.evaluate(() => window.__serialMock.commands.includes('wifi setup')), false);
  } finally {await f.close();}
});

test('unplug clears secrets/status and ignores hostile serial text', async () => {
  const f = await fixture();
  const page = f.page;
  try {
    await connect(page);
    await ready(page);
    await tab(page,'wifi');
    await page.locator('#password').fill('must-clear-on-disconnect');
    await page.evaluate(() => {
      window.__serialMock.emit('<img src="https://example.invalid/steal" onerror="alert(1)">password-from-rx');
      window.__serialMock.emit('Mode=BLE companion=idle via=none USB-service=on WiFi-config=no link=down IP=<private> approval=none');
      window.__serialMock.unplug();
    });
    await page.waitForFunction(() => document.getElementById('connection').textContent === 'Нода не подключена');
    assert.equal(await page.locator('#password').inputValue(), '');
    assert.equal(await page.locator('#mode').textContent(), '—');
    assert.equal(await page.locator('#connect').isEnabled(), true);
    assert.equal(await page.locator('img').count(), 0);
    const text = await page.locator('body').innerText();
    assert.equal(text.includes('<private>'), false);
    assert.equal(text.includes('password-from-rx'), false);
  } finally { await f.close(); }
});

test('read-only console blocks settings and remains disconnectable', async () => {
  const f = await fixture({ readOnly: true });
  try {
    await connect(f.page);
    for (const selector of ['#test', '#save', '#cancel', '#mode-wifi', '#forget']) assert.equal(await f.page.locator(selector).isDisabled(), true);
    assert.match(await f.page.locator('#feedback').textContent(), /только для чтения/);
    assert.equal(await f.page.locator('#feedback').getAttribute('data-kind'),'warning');
    assert.match(await f.page.locator('#feedback').textContent(),/запись заблокирована.*версию и build/);
    assert.doesNotMatch(await f.page.locator('#feedback').textContent(),/устройство восстанавливает|хранилища подключения/);
    assert.equal(await f.page.evaluate(()=>window.__serialMock.commands.includes('wifi forget')),false);
    await f.page.locator('#disconnect').click();
    await f.page.waitForFunction(() => !document.getElementById('connect').disabled);
  } finally { await f.close(); }
});

test('custom phrases require explicit capability, save UTF8 with readback, and clear back to default',async()=>{
  const f=await fixture({replies:true,info:'SmartUI=0.07 core=1.17.1 build=12345678 upstream=abcdef01 capabilities=BLE,USB board=Heltec T114'});
  try {
    await connect(f.page);
    await tab(f.page,'phrases');
    assert.equal(await f.page.locator('#reply-0').isDisabled(),true);
    assert.equal(await f.page.locator('#reply-0').isVisible(),false);await f.page.locator('#replies-panel summary').click();
    await f.page.locator('#replies-load').click();
    await f.page.waitForFunction(()=>!document.getElementById('reply-0').disabled);
    const phrase='Я на месте';
    await f.page.locator('#reply-0').fill(phrase);
    await f.page.locator('#reply-save-0').click();
    await f.page.waitForFunction(()=>document.getElementById('feedback').textContent.includes('прочитана обратно'));
    assert.equal(await f.page.evaluate(()=>window.__serialMock.quickReplies[0]),phrase);
    assert.equal(await f.page.locator('#reply-0').inputValue(),phrase);
    await f.page.locator('#reply-8').fill('я'.repeat(33));
    await f.page.locator('#reply-save-8').click();
    await f.page.waitForFunction(()=>document.getElementById('feedback').textContent.includes('не более 64'));
    assert.equal(await f.page.evaluate(()=>window.__serialMock.quickReplies[8]),'');
    await confirm(f.page,'#reply-clear-0',true);
    await f.page.waitForFunction(()=>document.getElementById('reply-0').value==='');
    assert.equal(await f.page.evaluate(()=>window.__serialMock.quickReplies[0]),'');
    for(const width of [320,390,1280]) {await f.page.setViewportSize({width,height:1000});await noOverlap(f.page);}
    await f.page.screenshot({path:path.join(output,'custom-replies-1280.png'),fullPage:true});
  } finally {await f.close();}
});

test('local USB recovery leaves status and safe cleanup action accessible',async()=>{
  const f=await fixture({localRecovery:true});
  try {
    await connect(f.page);
    assert.equal(await f.page.locator('#refresh').isEnabled(),true);
    assert.equal(await f.page.locator('#mode-ble').isDisabled(),true);
    assert.equal(await f.page.locator('#feedback').getAttribute('data-kind'),'warning');
    assert.match(await f.page.locator('#feedback').textContent(),/Ошибка хранилища подключения.*storage=recovery-required/);
    assert.equal(await f.page.evaluate(()=>window.__serialMock.commands.includes('wifi forget')),false);
    await tab(f.page,'connection');await f.page.locator('summary').filter({hasText:'Служебные события'}).click();
    assert.equal(await f.page.locator('#forget').isEnabled(),true);
    await confirm(f.page,'#forget',true);
    await f.page.waitForFunction(()=>document.getElementById('mode').textContent==='Bluetooth');
    assert.equal(await f.page.locator('#mode-ble').isEnabled(),true);
  } finally {await f.close();}
});

test('firmware preflight stays offline without serial access and displays merged loss warning',async()=>{
  const f=await fixture({supported:false});
  try {
    await tab(f.page,'service');
    const commit='12345678'+'a'.repeat(32),version='0.07';
    const payload=Buffer.from('V3 SmartUI '+version+'\0SmartUI-source:12345678\0');
    const end=Math.floor((32+payload.length+16)/16)*16;
    const raw=Buffer.alloc(0x10000+end+256,0xff),app=Buffer.alloc(end);
    app[0]=0xe9;app[1]=1;app.writeUInt32LE(payload.length,28);payload.copy(app,32);
    let checksum=0xef;for(const byte of payload)checksum^=byte;app[end-1]=checksum;
    raw[0]=0xe9;app.copy(raw,0x10000);
    const name='V3-test-merged.bin';
    const manifest={schema_version:2,commit,version,firmware:[{name,bytes:raw.length,sha256:createHash('sha256').update(raw).digest('hex'),board:'Heltec V3 OLED',environment:'Heltec_v3_companion_radio_ble_smartui',source_commit:commit,image_kind:'esp32-fresh-install-merged',flash_offset:'0x00000'}]};
    await f.page.locator('#firmware-file').setInputFiles({name,mimeType:'application/octet-stream',buffer:raw});
    await f.page.locator('#firmware-manifest').setInputFiles({name:'RELEASE-MANIFEST.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(manifest))});
    await f.page.locator('#firmware-board').selectOption('v3');
    await f.page.locator('#firmware-check').click();
    await f.page.waitForFunction(()=>document.getElementById('firmware-result').textContent.includes('Проверка файла пройдена'));
    const result=await f.page.locator('#firmware-result').textContent();
    assert.match(result,/даже без Erase/);assert.match(result,/не подлинность|а не подлинность/);assert.match(result,/вручную/);
    await f.page.locator('#firmware-board').selectOption('t114');await f.page.locator('#firmware-check').click();
    await f.page.waitForFunction(()=>document.getElementById('firmware-result').textContent.includes('другой платы'));
    assert.equal(await f.page.evaluate(()=>Boolean(window.__serialMock)),false);
  } finally {await f.close();}
});

const DEVICE_INFO='SmartUI=0.08 core=1.17.1 build=12345678 upstream=a27e78e4 capabilities=BLE,USB board=ProMicro RA62';
const RELEASE_DEVICE_INFO=DEVICE_INFO.replace('SmartUI=0.08','SmartUI=0.15');
test('0.08 through 0.17 retain verified melody names; unknown firmware or changed catalogs stay numeric',async()=>{
  for (const {version,maximum,named} of [
    {version:'0.08',maximum:30,named:true},
    {version:'0.09',maximum:30,named:true},
    {version:'0.10',maximum:30,named:true},
    {version:'0.11',maximum:30,named:true},
    {version:'0.12',maximum:30,named:true},
    {version:'0.13',maximum:30,named:true},
    {version:'0.14',maximum:30,named:true},
    {version:'0.15',maximum:30,named:true},
    {version:'0.16',maximum:30,named:true},
    {version:'0.17',maximum:30,named:true},
    {version:'0.18',maximum:30,named:false},
    {version:'0.09',maximum:29,named:false},
    {version:'0.10',maximum:29,named:false},
    {version:'0.11',maximum:29,named:false},
  ]) {
    const info=DEVICE_INFO.replace('SmartUI=0.08','SmartUI='+version);
    const f=await fixture({settings:true,info,settingsCaps:{melody_max:maximum}});
    try {
      await connect(f.page);
      await tab(f.page,'sound');
      assert.equal(await f.page.locator('#info-firmware').textContent(),version);
      assert.equal(await f.page.locator('#setting-melody option').count(),maximum+1);
      assert.equal(await f.page.locator('#setting-melody option[value="0"]').textContent(),named?'0 · Пульс':'Мелодия 0');
      assert.equal(await f.page.locator('#setting-melody option[value="4"]').textContent(),named?'4 · Канон':'Мелодия 4');
      await f.page.locator('#setting-melody').selectOption('4');
      await f.page.locator('#save-melody').click();
      await f.page.waitForFunction(()=>window.__serialMock.commands.at(-1)==='settings get' && !document.getElementById('setting-melody').disabled);
      assert.equal(await f.page.evaluate(()=>__serialMock.settingsState.melody),4);
      assert.match(await f.page.locator('#saved-melody').textContent(),named?/4 · Канон · Прочитано/:/Мелодия 4 · Прочитано/);
    } finally {await f.close();}
  }
});

test('0.16 service mode exposes board pin schemas, filters and preserves other drafts',async()=>{
  const full=fullSettingsFixture();
  const f=await fixture({settings:true,radioFeature:true,manualAdc:true,info:RELEASE_DEVICE_INFO.replace('0.15','0.16').replace('ProMicro RA62','Heltec T096'),schemas:full.schemas,extendedValues:full.settings,settingsCaps:{display:1,gps:1,adc_service:1}});
  try{const p=f.page;await connect(p);
    await tab(p,'sound');
    await p.waitForFunction(()=>!document.getElementById('setting-tone_pin').disabled);
    assert.equal(await p.locator('#setting-tone_pin').isVisible(),true);
    await p.locator('#device-section').evaluate(section=>{const caption=document.createElement('p');caption.id='basic-simulation-caption';caption.className='hint';caption.textContent='Симуляция T096 · SmartUI 0.16. Физическая плата не подключена.';section.prepend(caption);});
    await noOverlap(p);await p.locator('#device-section').screenshot({path:path.join(output,'helper-2.1-basic-desktop.png')});
    await p.setViewportSize({width:390,height:844});await noOverlap(p);await p.locator('#device-section').screenshot({path:path.join(output,'helper-2.1-basic-mobile.png')});
    await p.setViewportSize({width:1440,height:1080});await p.locator('#basic-simulation-caption').evaluate(el=>el.remove());
    await p.locator('#settings-advanced').check();
    assert.deepEqual(await p.locator('#setting-tone_pin option').evaluateAll(o=>o.map(i=>i.value)),['29','31','33','34','35','36','37','39','43']);
    for(const key of ['ui_theme','led_pin'])assert.equal(await p.locator('#setting-'+key).isEnabled(),true);
    for(const key of ['profile','melody_dm','melody_mention'])assert.equal(await p.locator('#setting-'+key).isDisabled(),true);
    assert.deepEqual(await p.locator('#setting-gps_source option').evaluateAll(nodes=>nodes.map(n=>n.value)),['0']);
    assert.equal(await p.locator('#adc-manual-value').isEnabled(),true);
    assert.doesNotMatch(await p.locator('#adc-manual-hint').textContent(),/не поддерживается/);
    await p.locator('#setting-volume').selectOption('4');await p.locator('#setting-tone_pin').selectOption('33');
    await p.locator('#save-tone_pin').click();await p.locator('#confirm-yes').click();await p.waitForFunction(()=>__serialMock.settingsState.tone_pin===33&&!document.getElementById('setting-tone_pin').disabled);
    assert.equal(await p.locator('#setting-volume').inputValue(),'4');
    await p.locator('#settings-filter').fill('tone_pin');assert.equal(await p.locator('#row-tone_pin').isVisible(),true);assert.equal(await p.locator('#row-volume').isVisible(),false);
    assert.equal(await p.locator('#device-fields .device-panel:visible').count(),1);
    await p.locator('#settings-filter').fill('нет такого параметра');assert.equal(await p.locator('#device-fields .device-panel:visible').count(),0);
    await p.locator('#settings-filter').fill('vibration');assert.equal(await p.locator('#lights-panel').isVisible(),false);
    await p.locator('#settings-unavailable').check();assert.equal(await p.locator('#lights-panel').isVisible(),true);assert.equal(await p.locator('#setting-vibration').isDisabled(),true);
    await p.locator('#settings-unavailable').uncheck();await p.locator('#settings-filter').fill('');
    await tab(p,'radio');await p.locator('#node-tx').fill('16');await p.locator('#node-tx-save').click();await p.locator('#confirm-yes').click();await p.waitForFunction(()=>__serialMock.tx===16&&!document.getElementById('node-tx').disabled);
    await tab(p,'sound');
    await p.locator('#device-section').evaluate(section=>{const caption=document.createElement('p');caption.className='hint';caption.textContent='Симуляция T096 · SmartUI 0.16. Физическая плата не подключена.';section.prepend(caption);});
    await p.locator('#device-section').screenshot({path:path.join(output,'helper-2.1-service-desktop.png')});
    await p.setViewportSize({width:390,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);await p.locator('#device-section').screenshot({path:path.join(output,'helper-2.1-service-mobile.png')});
  }finally{await f.close();}
});

test('console sound labels preserve quiet inversion and test warns about unsaved values',async()=>{
  const full=fullSettingsFixture(),f=await fixture({settings:true,info:RELEASE_DEVICE_INFO,schemas:full.schemas,extendedValues:full.settings});
  try{const p=f.page;await connect(p);
    await tab(p,'sound');
    assert.equal(await p.locator('#setting-sound_quiet option:checked').textContent(),'Включён');
    await p.locator('#setting-sound_quiet').selectOption({label:'Выключен'});await p.locator('#save-sound_quiet').click();await p.waitForFunction(()=>!document.getElementById('setting-sound_quiet').disabled);
    assert.equal(await p.evaluate(()=>__serialMock.settingsState.sound_quiet),1);assert.match(await p.locator('#settings-notify-state').textContent(),/Звук выключен на ноде/);
    await p.locator('#setting-sound_quiet').selectOption({label:'Включён'});await p.locator('#settings-test').click();await p.locator('#confirm-no').click();
    assert.equal(await p.evaluate(()=>__serialMock.commands.includes('settings test')),false);
    await p.locator('#settings-test').click();await p.locator('#confirm-yes').click();await p.waitForFunction(()=>__serialMock.commands.includes('settings test'));
    assert.equal(await p.evaluate(()=>__serialMock.settingsState.sound_quiet),1);
  }finally{await f.close();}
});

test('console path selector preserves fresh radio parameters and requires explicit save',async()=>{
  const f=await fixture({settings:true,radioFeature:true,info:RELEASE_DEVICE_INFO});
  try{const p=f.page;await connect(p);await tab(p,'radio');await p.waitForFunction(()=>!document.getElementById('path-bytes').disabled);
    await p.locator('#path-bytes').selectOption('1');await p.locator('#path-save').click();await p.locator('#confirm-no').click();
    assert.equal(await p.evaluate(()=>__serialMock.commands.some(c=>c.startsWith('settings radio set'))),false);
    await p.evaluate(()=>Object.assign(__serialMock.radio,{freq_khz:868731,bw_hz:62500,sf:7,cr:7,tx_dbm:18,repeat:1}));
    await p.locator('#path-save').click();await p.locator('#confirm-yes').click();await p.waitForFunction(()=>document.getElementById('radio-status').textContent.includes('Хеш маршрута сохранён'));
    assert.deepEqual(await p.evaluate(()=>__serialMock.radio),{freq_khz:868731,bw_hz:62500,sf:7,cr:7,path_bytes:1,tx_dbm:18,repeat:1});
    assert.equal(await p.evaluate(()=>__serialMock.commands.filter(c=>c.startsWith('settings radio set')).length),1);
  }finally{await f.close();}
});

test('headless settings save explicit fields with readback; ADC calculation and reset require confirmation',async()=>{
  const f=await fixture({settings:true,info:RELEASE_DEVICE_INFO,replies:true});
  try {
    await connect(f.page);
    assert.equal(await f.page.locator('#device-fields').isVisible(),true);
    assert.match(await f.page.locator('#settings-capabilities').textContent(),/без дисплея/);
    assert.equal(await f.page.locator('#row-gps').isVisible(),false);
    assert.equal(await f.page.locator('#row-vibration').isVisible(),false);
    assert.equal(await f.page.locator('#setting-melody option[value="0"]').textContent(),'0 · Пульс');
    assert.equal(await f.page.locator('#setting-melody option[value="30"]').textContent(),'30 · Alert');
    assert.equal(await f.page.evaluate(()=>__serialMock.commands.some(c=>c.startsWith('settings set'))),false);
    await tab(f.page,'sound');
    await f.page.locator('#setting-volume').selectOption('4');
    assert.match(await f.page.locator('#saved-volume').textContent(),/ещё не сохранено/);
    await f.page.locator('#save-volume').click();
    await f.page.waitForFunction(()=>document.getElementById('saved-volume').textContent.includes('4 / 10 · Прочитано'));
    assert.deepEqual(await f.page.evaluate(()=>__serialMock.commands.slice(-2)),['settings set volume 4','settings get']);
    await tab(f.page,'device');
    await f.page.locator('#adc-measured').fill('3,82');await f.page.locator('#adc-preview').click();
    await f.page.locator('#adc-preview-box').waitFor({state:'visible'});
    assert.match(await f.page.locator('#adc-preview-result').textContent(),/ещё не сохранён/);
    assert.equal(await f.page.evaluate(()=>__serialMock.settingsState.adc_multiplier),4.9);
    await noOverlap(f.page);
    await f.page.locator('#device-section').evaluate(section=>{const caption=document.createElement('p');caption.id='simulation-caption';caption.className='hint';caption.textContent='Симуляция USB · тестовые данные. Физическая плата не подключена.';section.prepend(caption);});
    await f.page.locator('#device-section').screenshot({path:path.join(output,'helper-1.5-settings-desktop.png')});
    await f.page.locator('#simulation-caption').evaluate(caption=>caption.remove());
    await confirm(f.page,'#adc-apply',false);
    assert.equal(await f.page.evaluate(()=>__serialMock.commands.some(c=>c.startsWith('settings adc apply'))),false);
    await confirm(f.page,'#adc-apply',true);
    await f.page.waitForFunction(()=>document.getElementById('adc-current').textContent==='4.925789');
    await confirm(f.page,'#adc-reset',false);
    assert.equal(await f.page.evaluate(()=>__serialMock.settingsState.adc_multiplier),4.925789);
    await confirm(f.page,'#adc-reset',true);
    await f.page.waitForFunction(()=>document.getElementById('adc-current').textContent==='4.900000');
    assert.equal(await f.page.evaluate(()=>__serialMock.settingsState.volume),4);
    await tab(f.page,'sound');await f.page.locator('#settings-test').click();
    await f.page.waitForFunction(()=>document.getElementById('feedback').textContent.includes('Команда теста принята'));
  } finally {await f.close();}
});

test('mobile settings have accessible controls, separate LEDs and battery warning before save',async()=>{
  const f=await fixture({settings:true,info:RELEASE_DEVICE_INFO,settingsCaps:{vibration:1,gps:1,display:1}});
  try {
    await f.page.setViewportSize({width:390,height:844});await connect(f.page);
    await tab(f.page,'sound');
    assert.equal(await f.page.getByLabel('LED платы',{exact:true}).isEnabled(),true);
    assert.equal(await f.page.getByLabel('LED уведомлений',{exact:true}).isEnabled(),true);
    await f.page.locator('#setting-board_led').selectOption('0');await f.page.locator('#save-board_led').click();
    await f.page.waitForFunction(()=>document.getElementById('saved-board_led').textContent.includes('Выключен · Прочитано'));
    assert.equal(await f.page.evaluate(()=>__serialMock.settingsState.unread_led),1);
    await tab(f.page,'device');
    await f.page.locator('#setting-battery_protection').selectOption('0');
    await f.page.locator('#save-battery_protection').click();
    assert.match(await f.page.locator('#confirm-text').textContent(),/2,7 В/);
    assert.match(await f.page.locator('#confirm-text').textContent(),/не безопасная цель/);
    assert.equal(await f.page.evaluate(()=>document.activeElement.id),'confirm-no');
    await f.page.locator('#confirm-no').click();
    assert.equal(await f.page.evaluate(()=>__serialMock.settingsState.battery_protection),1);
    await confirm(f.page,'#save-battery_protection',true);
    await f.page.waitForFunction(()=>document.getElementById('saved-battery_protection').textContent.includes('2,7 В · Прочитано'));
    await tab(f.page,'sound');await f.page.locator('#setting-volume').focus();await f.page.keyboard.press('Tab');
    assert.equal(await f.page.evaluate(()=>document.activeElement.id),'setting-melody'); // unchanged save buttons are disabled
    await noOverlap(f.page);
    await f.page.locator('#device-section').evaluate(section=>{const caption=document.createElement('p');caption.id='simulation-caption';caption.className='hint';caption.textContent='Симуляция USB · тестовые данные. Физическая плата не подключена.';section.prepend(caption);});
    await f.page.locator('#device-section').screenshot({path:path.join(output,'helper-1.5-settings-mobile.png')});
    await f.page.locator('#simulation-caption').evaluate(caption=>caption.remove());
  } finally {await f.close();}
});

test('ProMicro console shows cached reference and actionable source error without retaining a save token',async()=>{
  const f=await fixture({settings:true,info:RELEASE_DEVICE_INFO,settingsCaps:{adc_min:1.36125,adc_max:2.26875}});
  try{const p=f.page;
    await p.evaluate(()=>{const m=window.__serialMock,original=m.command;
      Object.assign(m.settingsState,{battery_mv:4100,adc_multiplier:1.97,adc_default:1.815});
      m.command=function(raw){if(raw.startsWith('settings adc preview ')){
        this.commands.push(raw);
        if(this.adcSourceMissing)this.emit('ERR settings source');
        else {this.adcPreview={token:7,sampled_mv:3100,measured_mv:3320,multiplier:2.109806};this.emit(this.settingsRecord('adc_preview',this.adcPreview));}
        return;
      }original.call(this,raw);};
    });
    await connect(p);
    assert.match(await p.locator('#adc-source-warning').textContent(),/ProMicro.*USB.*без перезапуска.*2 минут/);
    await p.locator('#adc-measured').fill('3,32');await p.locator('#adc-preview').click();
    await p.locator('#adc-preview-box').waitFor({state:'visible'});
    assert.match(await p.locator('#adc-preview-result').textContent(),/2\.109806.*Опорный замер: 3\.100/);
    assert.equal(await p.evaluate(()=>window.__serialMock.settingsState.adc_multiplier),1.97);
    await p.evaluate(()=>{window.__serialMock.adcSourceMissing=true;});
    await p.locator('#adc-preview').click();
    await p.waitForFunction(()=>document.getElementById('feedback').textContent.includes('Запустите ProMicro от АКБ'));
    assert.match(await p.locator('#feedback').textContent(),/без перезапуска.*2 минут/);
    assert.equal(await p.locator('#adc-apply').isDisabled(),true);
    assert.equal(await p.locator('#adc-preview-box').isHidden(),true);
    assert.equal(await p.evaluate(()=>window.__serialMock.commands.some(c=>c.startsWith('settings adc apply'))),false);
    assert.equal(await p.evaluate(()=>window.__serialMock.settingsState.adc_multiplier),1.97);
  }finally{await f.close();}
});

test('unsupported hardware is hidden and storage failure remains unsaved in the form',async()=>{
  const f=await fixture({settings:true,info:DEVICE_INFO,settingsCaps:{sound:0,unread_led:0,vibration:0,gps:0}});
  try {
    await connect(f.page);
    for(const id of ['row-volume','row-melody','row-sound_quiet','row-unread_led','row-vibration','gps-panel']) assert.equal(await f.page.locator('#'+id).isVisible(),false,id);
    assert.equal(await f.page.locator('#settings-test').isEnabled(),false);
    await f.page.evaluate(()=>{__serialMock.settingsFailure='storage';});
    await tab(f.page,'sound');
    await f.page.locator('#setting-board_led').selectOption('0');await f.page.locator('#save-board_led').click();
    await f.page.waitForFunction(()=>document.getElementById('feedback').textContent.includes('ошибка хранилища'));
    assert.match(await f.page.locator('#saved-board_led').textContent(),/ещё не сохранено/);
    assert.equal(await f.page.evaluate(()=>__serialMock.settingsState.board_led),1);
    await tab(f.page,'device');
    await f.page.locator('#adc-measured').fill('99');await f.page.locator('#adc-preview').click();
    await f.page.waitForFunction(()=>document.getElementById('feedback').textContent.includes('2,500'));
    assert.equal(await f.page.evaluate(()=>__serialMock.commands.some(c=>c.startsWith('settings adc preview'))),false);
    await f.page.evaluate(()=>__serialMock.unplug());
    await f.page.waitForFunction(()=>document.getElementById('device-fields').hidden);
  } finally {await f.close();}
});

test('ADC service console requires confirmation, shows firmware time, cancels on save and disconnect',async()=>{
  const f=await fixture({settings:true,info:RELEASE_DEVICE_INFO,settingsCaps:{adc_service:1}});
  try{const p=f.page;await connect(p);
    assert.equal(await p.locator('#adc-service-box').isVisible(),true);
    assert.equal(await p.evaluate(()=>__serialMock.commands.some(c=>c==='settings adc service start')),false);
    await confirm(p,'#adc-service-start',false);
    assert.equal(await p.evaluate(()=>__serialMock.commands.some(c=>c==='settings adc service start')),false);
    await confirm(p,'#adc-service-start',true);
    await p.waitForFunction(()=>document.getElementById('adc-service-status').textContent.includes('Окно активно'));
    assert.equal(await p.locator('#adc-service-start').isDisabled(),true);
    await p.evaluate(()=>__serialMock.adcServiceDeadline=Date.now()+44000);
    await p.locator('#adc-service-refresh').click();
    await p.waitForFunction(()=>document.getElementById('adc-service-status').textContent.includes('44 с'));
    assert.equal(await p.evaluate(()=>__serialMock.commands.filter(c=>c==='settings adc service start').length),1);
    await p.locator('#adc-measured').fill('3.82');await p.locator('#adc-preview').click();
    await p.locator('#adc-preview-box').waitFor({state:'visible'});await confirm(p,'#adc-apply',true);
    await p.waitForFunction(()=>document.getElementById('adc-service-status').textContent.includes('Окно выключено'));
    assert.equal(await p.evaluate(()=>__serialMock.settingsState.battery_protection),1);
    await confirm(p,'#adc-service-start',true);
    await p.waitForFunction(()=>document.getElementById('adc-service-status').textContent.includes('Окно активно'));
    await noOverlap(p);
    await p.locator('#adc-service-box').screenshot({path:path.join(output,'helper-1.7-adc-service-desktop.png')});
    await p.setViewportSize({width:390,height:844});await noOverlap(p);
    await p.locator('#adc-service-box').screenshot({path:path.join(output,'helper-1.7-adc-service-mobile.png')});
    await p.locator('#disconnect').click();await p.waitForFunction(()=>!SmartUiLegacy.getState().connected);
    assert.equal(await p.evaluate(()=>__serialMock.commands.filter(c=>c==='settings adc service stop').length),1);
    assert.equal(await p.locator('#adc-measured').inputValue(),'');
    assert.equal(await p.evaluate(()=>SmartUiLegacy.getState().adcService),null);
  }finally{await f.close();}
});

test('ADC console old firmware hides service; expiration clears unsaved preview without restart',async()=>{
  const old=await fixture({settings:true,info:RELEASE_DEVICE_INFO});
  try{await connect(old.page);assert.equal(await old.page.locator('#adc-service-box').isHidden(),true);
    assert.equal(await old.page.evaluate(()=>__serialMock.commands.some(c=>c.startsWith('settings adc service'))),false);
  }finally{await old.close();}
  const f=await fixture({settings:true,info:RELEASE_DEVICE_INFO,settingsCaps:{adc_service:1}});
  try{const p=f.page;await connect(p);await confirm(p,'#adc-service-start',true);
    await p.waitForFunction(()=>document.getElementById('adc-service-status').textContent.includes('Окно активно'));
    await p.locator('#adc-measured').fill('3.82');await p.locator('#adc-preview').click();await p.locator('#adc-preview-box').waitFor({state:'visible'});
    await p.evaluate(()=>__serialMock.adcServiceDeadline=0);await p.locator('#adc-service-refresh').click();
    await p.waitForFunction(()=>document.getElementById('adc-service-status').textContent.includes('Окно выключено'));
    assert.equal(await p.locator('#adc-preview-box').isHidden(),true);
    assert.equal(await p.evaluate(()=>__serialMock.commands.filter(c=>c==='settings adc service start').length),1);
  }finally{await f.close();}
});

test('ADC start consent cannot outlive its console session',async()=>{
  const f=await fixture({settings:true,info:RELEASE_DEVICE_INFO,settingsCaps:{adc_service:1}});
  try{const p=f.page;await connect(p);await p.locator('#adc-service-start').click();
    await p.evaluate(()=>__serialMock.unplug());await p.waitForFunction(()=>!SmartUiLegacy.getState().connected);
    await p.locator('#confirm-yes').click();
    assert.equal(await p.evaluate(()=>__serialMock.commands.some(c=>c==='settings adc service start')),false);
  }finally{await f.close();}
});

test('manual ADC console: comma input, confirmation, saved readback and desktop/mobile layout',async()=>{
  const f=await fixture({settings:true,manualAdc:true,info:RELEASE_DEVICE_INFO,settingsCaps:{adc_min:1.36125,adc_max:2.26875,adc_service:1}});
  try{const p=f.page;await p.evaluate(()=>Object.assign(__serialMock.settingsState,{adc_multiplier:1.97,adc_default:1.815,battery_mv:2770}));await connect(p);
    assert.equal(await p.locator('#adc-current').textContent(),'1.970000');
    await p.locator('#adc-manual-value').fill('2,109806');
    assert.equal(await p.evaluate(()=>__serialMock.commands.some(c=>c.startsWith('settings adc set'))),false);
    await confirm(p,'#adc-manual-save',false);assert.equal(await p.locator('#adc-current').textContent(),'1.970000');
    await p.locator('#adc-manual-save').click();assert.match(await p.locator('#confirm-text').textContent(),/2\.109806/);await p.locator('#confirm-yes').click();
    await p.waitForFunction(()=>document.getElementById('adc-manual-result').textContent.includes('Сохранено на ноде и проверено'));
    assert.equal(await p.locator('#adc-current').textContent(),'2.109806');
    assert.equal(await p.evaluate(()=>__serialMock.commands.filter(c=>c==='settings adc set 2.109806').length),1);
    assert.equal(await p.evaluate(()=>__serialMock.commands.some(c=>c.startsWith('settings adc preview'))),false);
    await p.locator('#adc-manual-value').fill('1,815000');await p.locator('#adc-service-refresh').click();
    await p.waitForFunction(()=>!document.getElementById('adc-manual-save').disabled);
    assert.equal(await p.locator('#adc-manual-value').inputValue(),'1,815000');
    await noOverlap(p);await p.locator('#adc-fields').screenshot({path:path.join(output,'helper-1.8-adc-desktop.png')});
    await p.setViewportSize({width:390,height:844});await noOverlap(p);await p.locator('#adc-fields').screenshot({path:path.join(output,'helper-1.8-adc-mobile.png')});
  }finally{await f.close();}
});

test('manual ADC console rejects changed consent, bad range and old firmware without hiding connection',async()=>{
  const old=await fixture({settings:true,info:RELEASE_DEVICE_INFO});try{await connect(old.page);assert.equal(await old.page.locator('#adc-manual-value').isDisabled(),true);assert.match(await old.page.locator('#adc-manual-hint').textContent(),/не поддерживается/);}finally{await old.close();}
  const f=await fixture({settings:true,manualAdc:true,info:RELEASE_DEVICE_INFO});try{const p=f.page;await connect(p);
    await p.locator('#adc-manual-value').fill('999');await p.locator('#adc-manual-save').click();assert.match(await p.locator('#adc-manual-result').textContent(),/диапазона/);
    await p.locator('#adc-manual-value').fill('4.8');await p.locator('#adc-manual-save').click();
    await p.evaluate(()=>{const x=document.getElementById('adc-manual-value');x.value='4.7';x.dispatchEvent(new Event('input'));});await p.locator('#confirm-yes').click();
    assert.match(await p.locator('#adc-manual-result').textContent(),/значение изменилось/);
    assert.equal(await p.evaluate(()=>__serialMock.commands.some(c=>c.startsWith('settings adc set'))),false);
    await p.evaluate(()=>__serialMock.settingsFailure='source');await p.locator('#adc-measured').fill('3.82');await p.locator('#adc-preview').click();
    await p.waitForFunction(()=>document.getElementById('adc-result').textContent.includes('ProMicro'));
    assert.equal(await p.locator('#adc-result').getAttribute('data-kind'),'error');
    assert.equal(await p.locator('#adc-apply').isDisabled(),true);
  }finally{await f.close();}
});

test('manual ADC console lost ACK and unplug show local uncertainty without automatic retry',async()=>{
  for(const unplug of [false,true]){const f=await fixture({settings:true,manualAdc:true,info:RELEASE_DEVICE_INFO,clock:true});try{const p=f.page;await connect(p);
    await p.evaluate(()=>__serialMock.dropAdcAck=true);await p.locator('#adc-manual-value').fill('4.8');await confirm(p,'#adc-manual-save',true);
    await p.waitForFunction(()=>__serialMock.commands.includes('settings adc set 4.800000'));
    if(unplug)await p.evaluate(()=>__serialMock.unplug());else await p.clock.fastForward(6100);
    await p.waitForFunction(()=>document.getElementById('adc-manual-result').dataset.kind==='error');
    assert.match(await p.locator('#adc-manual-result').textContent(),/неизвестен|не подтверждено/);
    assert.equal(await p.locator('#adc-manual-save').isDisabled(),true);
    assert.equal(await p.evaluate(()=>__serialMock.commands.filter(c=>c.startsWith('settings adc set')).length),1);
  }finally{await f.close();}}
});

test('read-only Settings 1 shows current values but disables every mutation',async()=>{
  const f=await fixture({settings:true,info:DEVICE_INFO,readOnly:true});
  try {
    await connect(f.page);
    assert.equal(await f.page.locator('#device-fields').isVisible(),true);
    assert.equal(await f.page.locator('#settings-status').textContent(),'Только чтение');
    assert.equal(await f.page.locator('#settings-load').isEnabled(),true);
    for(const id of ['setting-volume','save-volume','adc-measured','adc-preview','adc-reset','settings-test','adc-manual-value','adc-manual-save']) assert.equal(await f.page.locator('#'+id).isEnabled(),false,id);
    assert.match(await f.page.locator('#battery-voltage').textContent(),/3,800/);
    assert.equal(await f.page.evaluate(()=>__serialMock.commands.some(c=>c.startsWith('settings set'))),false);
  } finally {await f.close();}
});
