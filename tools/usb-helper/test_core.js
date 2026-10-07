'use strict';

// No dependencies or device required: node tools/usb-helper/test_core.js
const test = require('node:test');
const assert = require('node:assert/strict');
const { ReadableStream, WritableStream } = require('node:stream/web');
const { ConsoleClient, ConsoleError, validateCredentials, parseStatus, parseInfo, encodeReply, decodeReply, parseSettingsCaps, parseDeviceSettings, parseAdcPreview, parseAdcService, parseAdcManual, adcMultiplier, measuredMilliVolts } = require('./core.js');

const STATUS = 'Mode=BLE companion=idle via=none USB-service=on WiFi-config=no link=down IP=none approval=none';
const SSID_PROMPT = 'SSID input is hidden; enter SSID, then Enter:';
const PASSWORD_PROMPT = "Password input is hidden; enter 8..64 bytes, blank for open WiFi, or 'cancel':";
const HELP = 'Commands: status | mode ble | mode usb | mode wifi | wifi setup | wifi status | wifi save | wifi cancel | wifi forget | help\r\nCredential input is not echoed. WiFi is saved only after a passed test.';
const HELP_INFO = HELP.replace('Commands: status', 'Commands: info | status');
const HELP_REPLIES = HELP_INFO.replace('wifi forget | help', 'wifi forget | reply get N | reply set N HEX | help');
const INFO = 'SmartUI=0.06 core=PS22b17 build=1234abcd upstream=5ad64e00 capabilities=BLE,USB,WiFi board=Heltec V3';
const SETTINGS_CAPS = {v:1,adc:1,sound:1,board_led:1,unread_led:1,vibration:0,gps:0,battery_protection:1,display:0,melody_max:30,adc_min:3.675,adc_max:6.125};
const SETTINGS = {battery_mv:3800,adc_multiplier:4.9,adc_default:4.9,sound_quiet:0,volume:10,melody:0,board_led:1,unread_led:1,vibration:0,gps:0,battery_protection:1,shutdown_mv:3200,muted:0};
const wireRecord=(kind,values)=>'OK settings '+kind+' '+Object.entries(values).map(([key,value])=>key+'='+value).join(' ');
const tick = () => new Promise(resolve => setImmediate(resolve));

test('radio/advert records bound every field and reject duplicate or hostile payloads',()=>{
  const {parseNetworkSetting,networkValuesValid,ADVERT_INTERVALS}=require('./core.js');
  const radio='OK settings radio freq_khz=868731 bw_hz=62500 sf=7 cr=7 path_bytes=2 tx_dbm=20 repeat=0';
  const parsed=parseNetworkSetting(radio,'radio');assert.equal(parsed.freq_khz,868731);
  assert.equal(networkValuesValid('radio',parsed),true);
  for(const altered of [radio+' extra=1',radio.replace('sf=7','sf=263'),radio.replace('path_bytes=2','path_bytes=0'),radio.replace('repeat=0','repeat=2'),radio.replace('bw_hz=62500','bw_hz=NaN'),radio.replace('cr=7','cr=7 sf=7'),radio.replace('sf=7','sf=<script>'),radio+'\n'])assert.equal(parseNetworkSetting(altered,'radio'),null);
  assert.deepEqual(ADVERT_INTERVALS,[0,15,30,60,120,180]);
  for(const value of ADVERT_INTERVALS)assert.deepEqual(parseNetworkSetting('OK ui advert interval_min='+value,'advert','ui'),{interval_min:value});
  for(const value of [-1,1,14,16,65536])assert.equal(parseNetworkSetting('OK ui advert interval_min='+value,'advert','ui'),null);
});

test('ADC service strict capability/status records and old caps compatibility',()=>{
  assert.equal(parseSettingsCaps(wireRecord('caps',SETTINGS_CAPS)).adc_service,undefined);
  assert.equal(parseSettingsCaps(wireRecord('caps',{...SETTINGS_CAPS,adc_service:1})).adc_service,1);
  assert.equal(parseSettingsCaps(wireRecord('caps',{...SETTINGS_CAPS,adc_service:2})),null);
  const base={supported:1,active:1,remaining_ms:98765,external:1};
  assert.deepEqual(parseAdcService(wireRecord('adc_service',base)),base);
  assert.deepEqual(parseAdcService('OK ui adc_service supported=1 active=0 remaining_ms=0 external=0','ui'),{supported:1,active:0,remaining_ms:0,external:0});
  for(const patch of [{remaining_ms:120001},{remaining_ms:0},{supported:0},{external:0},{active:0},{external:2},{extra:0}])assert.equal(parseAdcService(wireRecord('adc_service',{...base,...patch})),null);
});

test('manual ADC strict discovery, decimals and board bounds',()=>{
  assert.deepEqual(parseAdcManual('OK settings adc_manual supported=1'),{supported:1});
  assert.deepEqual(parseAdcManual('OK ui adc_manual supported=0','ui'),{supported:0});
  for(const line of ['OK settings adc_manual supported=2','OK settings adc_manual supported=1 supported=0','OK settings adc_manual supported=1 extra=0'])assert.equal(parseAdcManual(line),null);
  const caps={adc_min:1.36125,adc_max:2.26875};
  for(const text of ['1.815','1,815000',' 1.815000 '])assert.equal(adcMultiplier(text,caps),'1.815000');
  for(const text of ['NaN','Infinity','1e0','-1.8','+1.8','1.8150001','1.8.0','1,8,0','1.8\n2','0',''])assert.throws(()=>adcMultiplier(text,caps));
  for(const text of ['1.361249','2.268751'])assert.throws(()=>adcMultiplier(text,caps),code('SETTINGS_RANGE'));
});

class FakePort {
  constructor(options = {}) {
    this.options = options;
    this.commands = [];
    this.rawWrites = [];
    this.stage = options.stage || 'idle';
    this.input = options.partial || '';
    this.overflow = Boolean(options.overflow);
    this.mode = 'BLE';
    this.configured = false;
    this.closed = false;
    this.signals = [];
    this.replies = Array(9).fill('');
    this.settingsCaps={...SETTINGS_CAPS,...options.settingsCaps};
    this.settingsState={...SETTINGS,...options.settingsState};
    this.adcService={supported:1,active:0,remaining_ms:0,external:1};
  }
  async open(options) {
    if (this.options.openError) throw this.options.openError;
    this.openOptions = options;
    this.closed = false;
    this.readable = new ReadableStream({ start: controller => { this.controller = controller; } });
    this.writable = new WritableStream({ write: bytes => {
      const text = new TextDecoder().decode(bytes);
      this.rawWrites.push(text);
      for (const char of text) {
        if (char === '\b' || char === '\x7f') this.input = this.input.slice(0, -1);
        else if (char === '\n' || char === '\r') {
          if (this.overflow) this.emit('Input too long; discarded.\r\n');
          else if (this.input || this.stage === 'password') this.command(this.input);
          this.input = '';
          this.overflow = false;
        } else if (this.input.length < (this.options.replies ? 160 : 96)) this.input += char;
        else this.overflow = true;
      }
      if (this.options.hangWrite && this.options.hangWrite(text)) return new Promise(() => {});
    } });
  }
  async setSignals(signals) { this.signals.push(signals); }
  async close() { this.closed = true; }
  emit(text) {
    if (this.closed) return;
    const bytes = new TextEncoder().encode(text);
    const width = this.options.fragment || bytes.length;
    for (let start = 0; start < bytes.length; start += width) {
      try { this.controller.enqueue(bytes.slice(start, start + width)); } catch (_) { return; }
    }
  }
  reply(line) { this.emit(line + '\r\n'); }
  command(raw) {
    this.commands.push(raw);
    if (this.options.onCommand && this.options.onCommand(raw, this) === false) return;
    if (this.stage === 'ssid' || this.stage === 'password') {
      if (raw === 'cancel') { this.stage = 'idle'; this.reply('WiFi setup cancelled.'); return; }
      if (this.stage === 'ssid') {
        this.ssid = raw;
        this.stage = 'password';
        this.reply(PASSWORD_PROMPT);
      } else {
        this.password = raw;
        this.stage = 'testing';
        this.reply('Testing WiFi without saving...');
        if (this.options.testResult === 'wait') return;
        if (this.options.testResult === 'fail') {
          this.stage = 'idle';
          this.reply('WiFi test failed; credentials were not saved.');
        } else {
          this.stage = 'passed';
          this.reply("WiFi test passed. Type 'wifi save' to store it.");
        }
      }
      return;
    }
    const command = raw.trim().toLowerCase();
    if (this.options.settings && command.startsWith('settings ')) {
      if (command==='settings caps') this.reply(wireRecord('caps',this.settingsCaps));
      else if (command==='settings get') this.reply(wireRecord('get',this.settingsState));
      else if (command==='settings adc manual') this.reply(this.options.manualAdc===undefined?'ERR settings invalid':'OK settings adc_manual supported='+Number(this.options.manualAdc));
      else if (command.startsWith('settings adc set ')) {
        if(!this.options.manualAdc){this.reply('ERR settings unsupported');return;}
        this.settingsState.adc_multiplier=Number(command.split(' ').at(-1));Object.assign(this.adcService,{active:0,remaining_ms:0});
        if(!this.options.dropAdcAck)this.reply('OK settings adc_set');
      }
      else if (command.startsWith('settings adc service')) {
        if (!this.settingsCaps.adc_service) { this.reply('ERR settings unsupported'); return; }
        if (command.endsWith(' start')) {
          if (!this.adcService.external) { this.reply('ERR settings usb_required'); return; }
          if (!this.adcService.active) Object.assign(this.adcService,{active:1,remaining_ms:120000});
        }
        if (command.endsWith(' stop')) Object.assign(this.adcService,{active:0,remaining_ms:0});
        this.reply(wireRecord('adc_service',this.adcService));
      }
      else if (command.startsWith('settings set ')) {
        const [, ,key,value]=command.split(' '); this.settingsState[key]=Number(value);
        this.settingsState.shutdown_mv=this.settingsState.battery_protection ? 3200 : 2700;
        this.reply('OK settings set key='+key+' value='+value);
      } else if (command.startsWith('settings adc preview ')) {
        const measured=Number(command.split(' ').at(-1));
        this.adcPreview={token:7,sampled_mv:this.settingsState.battery_mv,measured_mv:measured,multiplier:Number((this.settingsState.adc_multiplier*measured/this.settingsState.battery_mv).toFixed(6))};
        this.reply(wireRecord('adc_preview',this.adcPreview));
      } else if (command==='settings adc apply 7' && this.adcPreview) {
        Object.assign(this.adcService,{active:0,remaining_ms:0});
        this.settingsState.adc_multiplier=this.adcPreview.multiplier;this.reply('OK settings adc_apply');
      } else if (command==='settings adc reset') {
        Object.assign(this.adcService,{active:0,remaining_ms:0});
        this.settingsState.adc_multiplier=this.settingsState.adc_default;this.reply('OK settings adc_reset');
      } else if (command==='settings test') this.reply('OK settings test');
      else this.reply('ERR settings invalid');
      return;
    }
    const getReply = /^reply get ([1-9])$/.exec(command);
    const setReply = /^reply set ([1-9]) (-|[0-9a-f]+)$/.exec(command);
    if (this.options.replies && getReply) {
      const slot = Number(getReply[1]) - 1;
      this.reply('Reply=' + (slot + 1) + ' hex=' + encodeReply(this.replies[slot])); return;
    }
    if (this.options.replies && setReply) {
      const slot = Number(setReply[1]) - 1;
      const value = decodeReply('Reply=' + (slot + 1) + ' hex=' + setReply[2], slot);
      if (value) { this.replies[slot] = value.text; this.reply('Reply ' + (slot + 1) + ' saved.'); }
      else this.reply('Invalid quick reply.');
      return;
    }
    if (this.options.readOnly && command !== 'status') { this.reply('Connection settings are read-only during storage recovery.'); return; }
    switch (command) {
      case 'help': this.reply((this.options.replies ? HELP_REPLIES : this.options.info || this.options.settings ? HELP_INFO : HELP).replace('Credential input',this.options.settings ? 'Settings protocol: 1\r\nCredential input' : 'Credential input')); break;
      case 'info': this.reply(this.options.info || (this.options.settings ? INFO.replace('SmartUI=0.06','SmartUI=0.08') : "Unknown command. Type 'help'.")); break;
      case 'status': this.reply(STATUS.replace('Mode=BLE', 'Mode=' + this.mode).replace('WiFi-config=no', 'WiFi-config=' + (this.configured ? 'yes' : 'no'))); break;
      case 'wifi setup': this.stage = 'ssid'; this.reply(SSID_PROMPT); break;
      case 'wifi cancel': this.stage = 'idle'; this.reply('WiFi setup cancelled.'); break;
      case 'wifi save':
        if (this.stage === 'passed') { this.stage = 'idle'; this.configured = true; this.reply('Tested WiFi saved.'); }
        else this.reply('Nothing saved; pass WiFi test first.');
        break;
      case 'mode ble': this.mode = 'BLE'; this.reply('Mode BLE saved.'); break;
      case 'mode wifi': this.mode = 'WiFi'; this.reply('Mode WiFi saved.'); break;
      case 'mode usb':
        if (this.options.usbFailed) this.reply('USB mode unavailable or save failed.');
        else this.mode = 'USB'; // Successful firmware switch clears queued TX.
        break;
      case 'wifi forget':
        this.configured = false; this.mode = 'BLE';
        this.reply('Forgetting WiFi and falling back to BLE...');
        this.reply('WiFi credentials forgotten.');
        break;
      default: this.reply("Unknown command. Type 'help'.");
    }
  }
  unplug() { this.closed = true; this.controller.error(new Error('untrusted serial error <secret>')); }
}

function client(options = {}) {
  const seen = { states: [], statuses: [], events: [] };
  const instance = new ConsoleClient({
    timeouts: { command: 150, test: 250, usb: 40, close: 30, candidate: 10000, ...options.timeouts },
    onState: value => seen.states.push(value),
    onStatus: value => seen.statuses.push(value),
    onEvent: value => seen.events.push(value),
    ...options.callbacks
  });
  return { instance, seen };
}
async function connected(portOptions, clientOptions) {
  const port = new FakePort(portOptions);
  const result = client(clientOptions);
  await result.instance.connect(port);
  return { ...result, port };
}
const code = expected => error => error instanceof ConsoleError && error.code === expected && error.safe === true;

test('credentials: exact UTF-8 lengths, whitespace, hex PSK, controls, open network', () => {
  assert.deepEqual(validateCredentials(' сеть ', ' password '), { ssidBytes: 10, passwordBytes: 10, openNetwork: false });
  assert.equal(validateCredentials('я'.repeat(16), 'a'.repeat(63)).ssidBytes, 32);
  assert.equal(validateCredentials('x', 'aB09'.repeat(16)).passwordBytes, 64);
  assert.equal(validateCredentials('x', '', { openNetwork: true }).openNetwork, true);
  assert.throws(() => validateCredentials('я'.repeat(17), 'password'), code('INVALID_SSID'));
  assert.throws(() => validateCredentials('cancel', 'password'), code('RESERVED_SSID'));
  assert.throws(() => validateCredentials('x', 'z'.repeat(64)), code('INVALID_PASSWORD'));
  assert.throws(() => validateCredentials('x', '1234567'), code('INVALID_PASSWORD'));
  assert.throws(() => validateCredentials('x', ''), code('OPEN_CONFIRMATION'));
  assert.throws(() => validateCredentials('x', 'password', { openNetwork: true }), code('OPEN_PASSWORD'));
  for (const char of ['\0', '\n', '\r', '\t', '\x7f', '\u0085', '\u2028']) {
    assert.throws(() => validateCredentials('x' + char, 'password'), code('INVALID_SSID'));
    assert.throws(() => validateCredentials('x', 'password' + char), code('INVALID_PASSWORD'));
  }
  assert.throws(() => validateCredentials('\ud800', 'password'), code('INVALID_TEXT'));
  assert.throws(() => validateCredentials('x', '\udc00password'), code('INVALID_TEXT'));
});

test('status parser is anchored and exposes only enumerated values and IPv4', () => {
  assert.equal(parseStatus(STATUS).mode, 'ble');
  assert.equal(parseStatus(STATUS).ip, null);
  assert.equal(parseStatus(STATUS.replace('IP=none', 'IP=192.168.1.2')).ip, '192.168.1.2');
  assert.equal(parseStatus(STATUS + ' storage=ok').readOnly, false);
  assert.equal(parseStatus(STATUS + ' storage=recovery-required').readOnly, true);
  assert.equal(parseStatus(STATUS + ' storage=<private>'), null);
  for (const bad of ['<script>' + STATUS, STATUS + '<img>', STATUS.replace('IP=none', 'IP=300.1.1.1'), STATUS.replace('IP=none', 'IP=<secret>')]) assert.equal(parseStatus(bad), null);
});

test('info parser bounds all fields, rejects markup, controls, duplicate capabilities and damaged records', () => {
  assert.deepEqual(parseInfo(INFO), {firmware:'0.06',core:'PS22b17',build:'1234abcd',upstream:'5ad64e00',capabilities:['BLE','USB','WiFi'],board:'Heltec V3'});
  assert.equal(parseInfo(INFO.replace('Heltec V3', 'x'.repeat(96))).board.length, 96);
  for (const bad of [
    INFO.replace('Heltec V3', 'x'.repeat(97)), INFO.replace('0.06', 'x'.repeat(33)),
    INFO.replace('1234abcd', 'x'.repeat(41)), INFO.replace('5ad64e00', 'x'.repeat(41)),
    INFO.replace('Heltec V3', '<img src=x onerror=alert(1)>'), INFO + '<private>',
    INFO.replace('Heltec V3', 'Private\u202eBoard'), INFO.replace('Heltec V3', 'Board\x1b[31m'),
    INFO.replace('BLE,USB,WiFi', 'BLE,USB,USB'), INFO.replace('BLE,USB,WiFi', 'BLE,USB,Unknown'),
    INFO.replace('Heltec V3', ' trailing '), INFO.replace(' board=', ' password='),
    'x'.repeat(384), null
  ]) assert.equal(parseInfo(bad), null);
});

test('0.06 advertises info before probing it; 0.05 stays unknown and usable without an info command', async () => {
  const modern = await connected({ info: INFO, fragment: 1 });
  assert.deepEqual(modern.port.commands, ['cancel','wifi cancel','help','status','info']);
  assert.equal(modern.instance.state.info.firmware, '0.06');
  modern.instance.state.info.capabilities.pop();
  assert.equal(modern.instance.state.info.capabilities.includes('WiFi'), true, 'state snapshots cannot mutate capabilities');
  await modern.instance.disconnect();
  assert.equal(modern.instance.state.info, null);
  const old = await connected();
  assert.equal(old.instance.state.info, null);
  assert.equal(old.port.commands.includes('info'), false);
  await old.instance.testWifi('legacy network', 'password');
  await old.instance.disconnect();
});

test('known non-WiFi firmware blocks WiFi commands before serial writes; Bluetooth and USB remain available', async () => {
  const { instance, port } = await connected({info:INFO.replace('BLE,USB,WiFi','BLE,USB').replace('Heltec V3','Heltec T114')});
  const count = port.commands.length;
  for (const action of [() => instance.testWifi('private network','private password'), () => instance.saveWifi(),
      () => instance.cancelWifi(), () => instance.forgetWifi(), () => instance.setMode('wifi')]) {
    await assert.rejects(action(), code('WIFI_UNAVAILABLE'));
  }
  assert.equal(port.commands.length, count);
  await instance.setMode('ble');
  assert.equal((await instance.setMode('usb')).requestedMode, 'usb');
});

test('advertised invalid info fails closed without displaying raw text or sending credentials', async () => {
  for (const bad of [INFO.replace('Heltec V3','<private>'), INFO.replace('Heltec V3','x'.repeat(97)),
      INFO.replace('BLE,USB,WiFi','BLE,BLE'), INFO + 'x'.repeat(384)]) {
    const port = new FakePort({info:bad});
    const {instance,seen} = client();
    await assert.rejects(instance.connect(port), error => ['PROTOCOL','TIMEOUT'].includes(error.code));
    assert.equal(instance.state.connected, false);
    assert.equal(instance.state.info, null);
    assert.equal(port.commands.includes('wifi setup'), false);
    assert.equal(JSON.stringify(seen).includes('<private>'), false);
  }
});

test('local storage error without legacy notice warns instead of green success and blocks writes', async () => {
  const { instance, port, seen } = await connected({info:INFO,onCommand(raw,p) {
    if(raw === 'status') {p.reply(STATUS + ' storage=recovery-required'); return false;}
  }});
  assert.equal(instance.state.status.readOnly, true);
  assert.equal(instance.state.status.recoveryRequired, true);
  assert.equal(seen.events.at(-1).kind, 'warning');
  assert.match(seen.events.at(-1).text, /Ошибка хранилища подключения.*storage=recovery-required/);
  assert.match(seen.events.at(-1).text, /Обновите состояние.*версию и build/);
  assert.equal(seen.events.some(e=>e.kind==='success'),false);
  assert.doesNotMatch(seen.events.at(-1).text,/устройство восстанавливает/);
  await instance.refreshStatus();
  assert.equal(seen.events.at(-1).kind,'warning');
  const count = port.commands.length;
  await assert.rejects(instance.setMode('wifi'), code('READ_ONLY'));
  await assert.rejects(instance.testWifi('private network','private password'), code('READ_ONLY'));
  assert.equal(port.commands.length, count);
  await instance.disconnect();
});

test('connect verifies fragmented protocol, sets baud/flow, never toggles DTR/RTS', async () => {
  const { instance, port } = await connected({ fragment: 1 });
  assert.equal(instance.state.verified, true);
  assert.equal(instance.state.busy, false);
  assert.equal(instance.state.status.mode, 'ble');
  assert.deepEqual(port.commands, ['cancel', 'wifi cancel', 'help', 'status']);
  assert.equal(port.openOptions.baudRate, 115200);
  assert.equal(port.openOptions.flowControl, 'none');
  assert.deepEqual(port.signals, []);
  await instance.disconnect();
  assert.equal(port.readable.locked, false);
  assert.equal(port.writable.locked, false);
  assert.equal(instance.state.connected, false);
});

test('test and save are separate, preserve credentials, suppress all secrets', async () => {
  const { instance, port, seen } = await connected({ fragment: 2 });
  const ssid = '  private-сеть  ';
  const password = '  p<secret>  ';
  assert.deepEqual(await instance.testWifi(ssid, password), { testPassed: true });
  assert.equal(port.ssid, ssid);
  assert.equal(port.password, password);
  assert.equal(port.configured, false);
  assert.equal(port.commands.includes('wifi save'), false);
  assert.equal(instance.state.testPassed, true);
  const commandCount = port.commands.length;
  await assert.rejects(instance.refreshStatus(), code('WIFI_PENDING'));
  await assert.rejects(instance.setMode('wifi'), code('WIFI_PENDING'));
  assert.equal(port.commands.length, commandCount);
  const saved = await instance.saveWifi();
  assert.equal(saved.saved, true);
  assert.equal(port.configured, true);
  assert.equal(instance.state.testPassed, false);
  assert.equal(instance.state.status.wifiConfigured, true);
  const publicOutput = JSON.stringify(seen);
  assert.equal(publicOutput.includes(ssid), false);
  assert.equal(publicOutput.includes(password), false);
  assert.equal(publicOutput.includes('SSID input is hidden'), false);
  await instance.disconnect();
});

test('open WiFi requires explicit consent and transmits exactly a blank password', async () => {
  const { instance, port } = await connected();
  await assert.rejects(instance.testWifi('OpenNet', ''), code('OPEN_CONFIRMATION'));
  assert.equal(port.commands.includes('wifi setup'), false);
  await instance.testWifi('OpenNet', '', { openNetwork: true });
  assert.equal(port.password, '');
  await instance.cancelWifi();
  assert.equal(instance.state.testPassed, false);
  assert.equal(port.configured, false);
  await instance.disconnect();
});

test('failed WiFi test cancels candidate, never saves, permits another action', async () => {
  const { instance, port } = await connected({ testResult: 'fail' });
  await assert.rejects(instance.testWifi('network', 'password'), code('TEST_FAILED'));
  assert.equal(instance.state.testPassed, false);
  assert.equal(instance.state.verified, true);
  assert.equal(port.stage, 'idle');
  assert.equal(port.commands.includes('wifi save'), false);
  await assert.rejects(instance.saveWifi(), code('NO_TEST'));
  await instance.refreshStatus();
  await instance.disconnect();
});

test('unverified console receives neither credentials nor wizard commands', async () => {
  const { instance, seen } = client();
  const port = new FakePort({ onCommand: () => false });
  await assert.rejects(instance.connect(port), code('TIMEOUT'));
  await assert.rejects(instance.testWifi('network', 'password'), code('NOT_CONNECTED'));
  assert.deepEqual(port.commands, ['cancel']);
  assert.equal(instance.state.connected, false);
  assert.equal(port.closed, true);
  assert.equal(seen.events.some(event => event.text.includes('password')), false);
});

test('missing exact password prompt aborts without sending password', async () => {
  const password = 'must-not-send';
  const { instance, port } = await connected({ onCommand: (raw, target) => {
    if (raw === 'network') { target.stage = 'password'; target.reply('<span>' + PASSWORD_PROMPT + '</span>'); return false; }
  } });
  await assert.rejects(instance.testWifi('network', password), code('TIMEOUT'));
  assert.equal(port.commands.includes(password), false);
  assert.equal(port.stage, 'idle');
  assert.equal(instance.state.verified, true);
  await instance.disconnect();
});

test('busy operations reject, disconnect aborts test and old session cannot change new state', async () => {
  const { instance, port } = await connected({ testResult: 'wait' });
  const pending = instance.testWifi('network', 'password');
  const rejectedPending = assert.rejects(pending, code('DISCONNECTED'));
  await tick();
  await assert.rejects(instance.refreshStatus(), code('BUSY'));
  await assert.rejects(instance.cancelWifi(), code('BUSY'));
  await instance.disconnect();
  await rejectedPending;
  assert.equal(instance.state.busy, false);
  assert.equal(port.readable.locked, false);
  assert.equal(port.writable.locked, false);
  const fresh = new FakePort();
  await instance.connect(fresh);
  port.emit("WiFi test passed. Type 'wifi save' to store it.\r\n");
  await tick();
  assert.equal(instance.state.verified, true);
  assert.equal(instance.state.testPassed, false);
  await instance.disconnect();
});

test('unplug sanitizes exception, clears status/test, releases locks', async () => {
  const { instance, port, seen } = await connected();
  port.unplug();
  await tick();
  await tick();
  assert.equal(instance.state.connected, false);
  assert.equal(instance.state.verified, false);
  assert.equal(instance.state.status, null);
  assert.equal(port.readable.locked, false);
  assert.equal(port.writable.locked, false);
  assert.equal(JSON.stringify(seen).includes('<secret>'), false);
});

for (const stage of ['ssid', 'password', 'testing', 'passed']) {
  test('reconnect safely cancels existing ' + stage + ' stage and partial input', async () => {
    const { instance, port } = await connected({ stage, partial: 'previous-partial-value' });
    assert.equal(port.stage, 'idle');
    assert.equal(port.configured, false);
    assert.deepEqual(port.commands, ['cancel', 'wifi cancel', 'help', 'status']);
    assert.equal(port.ssid, undefined);
    assert.equal(port.password, undefined);
    await instance.disconnect();
  });
}

test('reconnect handles persistent firmware line overflow before issuing commands', async () => {
  const { instance, port } = await connected({ stage: 'ssid', partial: 'x'.repeat(96), overflow: true });
  assert.equal(port.rawWrites.filter(value => value === '\b'.repeat(160) + 'cancel\n').length, 2);
  assert.equal(port.stage, 'idle');
  assert.equal(port.password, undefined);
  await instance.disconnect();
});

test('firmware wizard timeout invalidates successful test and prevents Save', async () => {
  const { instance, port, seen } = await connected();
  await instance.testWifi('network', 'password');
  port.stage = 'idle';
  port.reply('WiFi setup timed out; credentials were not saved.');
  await tick();
  assert.equal(instance.state.testPassed, false);
  await assert.rejects(instance.saveWifi(), code('NO_TEST'));
  assert.equal(port.commands.includes('wifi save'), false);
  assert.equal(seen.events.some(event => event.kind === 'warning'), true);
  await instance.disconnect();
});

test('candidate deadline without firmware response fails closed', async () => {
  const { instance, port } = await connected({}, { timeouts: { candidate: 15 } });
  await instance.testWifi('network', 'password');
  await new Promise(resolve => setTimeout(resolve, 30));
  assert.equal(instance.state.testPassed, false);
  assert.equal(instance.state.verified, false);
  await assert.rejects(instance.saveWifi(), code('NOT_VERIFIED'));
  assert.equal(port.commands.includes('wifi save'), false);
  await instance.disconnect();
});

test('malicious RX and oversized lines never escape into UI callbacks', async () => {
  const { instance, port, seen } = await connected({ onCommand: (raw, target) => {
    target.reply('<img src=x onerror=steal(secret)>');
    target.reply('x'.repeat(20000));
    target.reply(STATUS.replace('IP=none', 'IP=<private-password>'));
  } });
  await instance.refreshStatus();
  const output = JSON.stringify(seen);
  for (const forbidden of ['<img', 'steal', 'secret', 'private-password', 'xxxxx']) assert.equal(output.includes(forbidden), false);
  assert.equal(instance._session.buffer.length <= 256, true);
  await instance.disconnect();
});

test('stale partial prompt cannot satisfy a fresh setup request', async () => {
  const { instance, port } = await connected({ onCommand: (raw, target) => {
    if (raw === 'wifi setup') { target.stage = 'ssid'; target.emit(SSID_PROMPT.slice(15) + '\r\n'); return false; }
  } });
  port.emit(SSID_PROMPT.slice(0, 15));
  await tick();
  await assert.rejects(instance.testWifi('network', 'password'), code('TIMEOUT'));
  assert.equal(port.commands.includes('network'), false);
  assert.equal(port.commands.includes('password'), false);
  await instance.disconnect();
});

test('USB switch is uncertain without ACK and never claims saved USB mode', async () => {
  const { instance, port } = await connected();
  assert.deepEqual(await instance.setMode('usb'), { uncertain: true, requestedMode: 'usb' });
  assert.equal(port.mode, 'USB');
  assert.equal(instance.state.connected, false);
  assert.equal(instance.state.verified, false);
  assert.equal(instance.state.status, null);
  assert.equal(port.closed, true);
  assert.equal(port.readable.locked, false);
  assert.equal(port.writable.locked, false);
  await assert.rejects(instance.refreshStatus(), code('NOT_CONNECTED'));
  await instance.disconnect();
});

test('USB failure ACK remains a failure, not an uncertain success', async () => {
  const { instance } = await connected({ usbFailed: true });
  await assert.rejects(instance.setMode('usb'), code('MODE_FAILED'));
  assert.equal(instance.state.verified, true);
  assert.equal(instance.state.status.mode, 'ble');
  await instance.disconnect();
});

test('USB write timeout cannot leave old mode verified or keep the port locked', async () => {
  const { instance, port } = await connected({ hangWrite: text => text === 'mode usb\n' }, { timeouts: { usb: 25 } });
  assert.deepEqual(await instance.setMode('usb'), { uncertain: true, requestedMode: 'usb' });
  assert.equal(instance.state.connected, false);
  assert.equal(instance.state.verified, false);
  assert.equal(instance.state.status, null);
  assert.equal(port.closed, true);
  assert.equal(port.writable.locked, false);
});

test('BLE/WiFi mode and Forget require exact ACK followed by fresh status', async () => {
  const { instance, port } = await connected();
  assert.equal((await instance.setMode('wifi')).saved, true);
  assert.equal(instance.state.status.mode, 'wifi');
  port.configured = true;
  assert.equal((await instance.forgetWifi()).forgotten, true);
  assert.equal(instance.state.status.mode, 'ble');
  assert.equal(instance.state.status.wifiConfigured, false);
  await instance.disconnect();
});

test('global read-only quarantine warns without claiming local cleanup and forbids every mutation', async () => {
  const { instance, port, seen } = await connected({ readOnly: true });
  assert.equal(instance.state.verified, true);
  assert.equal(instance.state.status.readOnly, true);
  assert.equal(instance.state.status.recoveryRequired,false);
  assert.equal(seen.events.at(-1).kind,'warning');
  assert.match(seen.events.at(-1).text,/запись заблокирована из-за состояния хранилища/);
  assert.doesNotMatch(seen.events.at(-1).text,/хранилища подключения|устройство восстанавливает/);
  assert.equal(seen.events.some(e=>e.kind==='success'),false);
  const before=port.commands.length;
  await assert.rejects(instance.testWifi('network', 'password'), code('READ_ONLY'));
  await assert.rejects(instance.setMode('wifi'), code('READ_ONLY'));
  await assert.rejects(instance.forgetWifi(), code('READ_ONLY'));
  assert.equal(port.commands.length,before);
  assert.equal(port.commands.includes('wifi setup'), false);
  await instance.refreshStatus();
  assert.equal(seen.events.at(-1).kind,'warning');
  await instance.disconnect();
});

test('global quarantine still rejects explicit local cleanup when both storage error signals exist',async()=>{
  const {instance,port,seen}=await connected({onCommand(raw,p){
    if(raw==='status'){p.reply(STATUS+' storage=recovery-required');return false;}
    if(['cancel','wifi cancel','wifi forget'].includes(raw)){p.reply('Connection settings are read-only during storage recovery.');return false;}
  }});
  assert.equal(instance.state.status.readOnly,true);
  assert.equal(instance.state.status.recoveryRequired,true);
  assert.equal(port.commands.includes('wifi forget'),false,'connection must not attempt repair');
  await assert.rejects(instance.forgetWifi(),code('READ_ONLY'));
  assert.equal(port.commands.filter(c=>c==='wifi forget').length,1,'only the explicit requested action is sent');
  assert.equal(instance.state.status.readOnly,true);
  assert.equal(seen.events.some(e=>e.kind==='success'),false);
  await instance.disconnect();
});

test('an early response cannot remove the deadline for a stuck serial write', async () => {
  const { instance } = client();
  const port = new FakePort({ hangWrite: text => text === 'help\n' });
  await assert.rejects(instance.connect(port), code('TIMEOUT'));
  assert.equal(instance.state.connected, false);
  assert.equal(instance.state.busy, false);
  assert.equal(port.readable.locked, false);
  assert.equal(port.writable.locked, false);
});

test('external error text and callback exceptions never leak or disrupt cleanup', async () => {
  const { instance, seen } = client();
  const port = new FakePort({ openError: new Error('<private-password>') });
  await assert.rejects(instance.connect(port), error => code('OPEN_FAILED')(error) && !error.message.includes('private-password'));
  assert.equal(JSON.stringify(seen).includes('private-password'), false);
  const other = await connected({}, { callbacks: { onState: () => { throw new Error('UI failure'); } } });
  await other.instance.disconnect();
  assert.equal(other.port.readable.locked, false);
  assert.equal(other.port.writable.locked, false);
});

test('hung open times out; late completion closes only its own port', async () => {
  const { instance } = client({ timeouts: { command: 25, close: 10 } });
  let finishOpen;
  const gate = new Promise(resolve => { finishOpen = resolve; });
  class DelayedPort extends FakePort {
    async open(options) { await gate; await super.open(options); }
  }
  const late = new DelayedPort();
  await assert.rejects(instance.connect(late), code('TIMEOUT'));
  assert.equal(instance.state.busy, false);
  await assert.rejects(instance.connect(late), code('BUSY'));
  const fresh = new FakePort();
  await instance.connect(fresh);
  finishOpen();
  await tick();
  await tick();
  assert.equal(late.closed, true);
  assert.equal(fresh.closed, false);
  assert.equal(instance.state.verified, true);
  await instance.disconnect();
});

test('disconnect interrupts pending open without awaiting the command deadline', async () => {
  const { instance } = client({ timeouts: { command: 500, close: 10 } });
  let finishOpen;
  const gate = new Promise(resolve => { finishOpen = resolve; });
  class DelayedPort extends FakePort {
    async open(options) { await gate; await super.open(options); }
  }
  const port = new DelayedPort();
  const opening = assert.rejects(instance.connect(port), code('DISCONNECTED'));
  await tick();
  await instance.disconnect();
  await opening;
  assert.equal(instance.state.connected, false);
  assert.equal(instance.state.busy, false);
  finishOpen();
  await tick();
  await tick();
  assert.equal(port.closed, true);
  assert.equal(port.readable.locked, false);
  assert.equal(port.writable.locked, false);
});

for (const [command, operation, errorCode] of [
  ['mode wifi', instance => instance.setMode('wifi'), 'MODE_UNCERTAIN'],
  ['wifi forget', instance => instance.forgetWifi(), 'FORGET_UNCERTAIN']
]) {
  test(command + ': lost mutation ACK invalidates stale status', async () => {
    const { instance } = await connected({ onCommand: raw => raw === command ? false : undefined }, { timeouts: { command: 25 } });
    await assert.rejects(operation(instance), code(errorCode));
    assert.equal(instance.state.verified, false);
    assert.equal(instance.state.status, null);
    await instance.disconnect();
  });
}

test('lost Save ACK is explicitly uncertain, even if resync succeeds', async () => {
  const { instance, port, seen } = await connected({ onCommand: (raw, target) => {
    if (raw === 'wifi save') { target.configured = true; target.stage = 'idle'; return false; }
  } }, { timeouts: { command: 25 } });
  await instance.testWifi('network', 'password');
  const beforeSave = seen.events.length;
  await assert.rejects(instance.saveWifi(), code('SAVE_UNCERTAIN'));
  assert.equal(port.configured, true);
  assert.equal(instance.state.verified, false);
  assert.equal(instance.state.status, null);
  assert.equal(instance.state.testPassed, false);
  assert.equal(seen.events.slice(beforeSave).some(event => event.text.includes('не сохранены')), false);
  await instance.disconnect();
});

test('known persistent Forget cleanup failure refreshes status and keeps retry possible', async () => {
  const { instance } = await connected({ onCommand: (raw, target) => {
    if (raw === 'wifi forget') { target.reply('WiFi cleared in RAM; persistent cleanup failed.'); return false; }
  } });
  await assert.rejects(instance.forgetWifi(), code('FORGET_FAILED'));
  assert.equal(instance.state.verified, true);
  assert.equal(instance.state.status.mode, 'ble');
  await instance.disconnect();
});

test('new cleanup failure is recognized and local recovery permits retry while USB framed transport is disabled', async () => {
  let recovery = true, attempts = 0;
  const {instance,port} = await connected({onCommand(raw,p) {
    if (['cancel','wifi cancel'].includes(raw) && recovery) { p.reply('Connection settings are read-only during storage recovery.'); return false; }
    if (raw === 'status') { p.reply(STATUS.replace('Mode=BLE', recovery ? 'Mode=USB' : 'Mode=BLE') + ' storage=' + (recovery ? 'recovery-required' : 'ok')); return false; }
    if (raw === 'wifi forget') {
      if (++attempts === 1) p.reply("WiFi cleared in RAM; persistent cleanup failed. Do not assume credentials were erased. Retry 'wifi forget'.");
      else {recovery = false; p.reply('WiFi credentials forgotten.');}
      return false;
    }
  }});
  assert.equal(instance.state.status.recoveryRequired,true);
  await assert.rejects(instance.setMode('ble'),code('READ_ONLY'));
  await assert.rejects(instance.forgetWifi(),code('FORGET_FAILED'));
  assert.equal(instance.state.verified,true);
  assert.equal((await instance.forgetWifi()).forgotten,true);
  assert.equal(instance.state.status.readOnly,false);
  assert.equal(port.commands.filter(line => line === 'wifi forget').length,2);
  await instance.disconnect();
});

test('quick replies validate UTF8 and require an explicit new help capability', async () => {
  assert.equal(encodeReply(''),'-');
  assert.equal(encodeReply('я'.repeat(32)).length,128);
  for (const text of ['x'.repeat(65),'я'.repeat(33),'bad\n','\ud800']) assert.throws(() => encodeReply(text),code('INVALID_REPLY'));
  for (const value of ['00','c080','eda080','f4908080','0a']) assert.equal(decodeReply('Reply=1 hex='+value,0),null);
  const {instance,port} = await connected({info:INFO});
  const before = port.commands.length;
  await assert.rejects(instance.loadQuickReplies(),code('REPLIES_UNAVAILABLE'));
  await assert.rejects(instance.saveQuickReply(0,'hello'),code('REPLIES_UNAVAILABLE'));
  assert.equal(port.commands.length,before);
  await instance.disconnect();
});

test('quick replies nine slots read, save max UTF8, clear default and verify readback', async () => {
  const {instance,port,seen} = await connected({info:INFO,replies:true});
  assert.equal(instance.state.quickRepliesSupported,true);
  assert.deepEqual(await instance.loadQuickReplies(),Array(9).fill(''));
  const phrase = 'я'.repeat(32);
  assert.equal((await instance.saveQuickReply(8,phrase)).text,phrase);
  assert.equal(port.replies[8],phrase);
  assert.equal(instance.state.replies[8],phrase);
  assert.equal(JSON.stringify(seen.events).includes(phrase),false);
  instance.state.replies[8] = 'cannot modify';
  assert.equal(instance.state.replies[8],phrase);
  await instance.saveQuickReply(8,'');
  assert.equal(port.replies[8],'');
  assert.equal(port.commands.includes('reply set 9 -'),true);
  await instance.disconnect();
  assert.equal(instance.state.quickRepliesSupported,false);
});

test('quick reply save failure preserves previous value; mismatched readback fails closed', async () => {
  let fail = true;
  const {instance,port} = await connected({info:INFO,replies:true,onCommand(raw,p) {
    if(raw.startsWith('reply set')) {p.reply(fail ? 'Quick reply save failed.' : 'Reply 1 saved.'); return false;}
  }});
  await instance.loadQuickReplies();
  await assert.rejects(instance.saveQuickReply(0,'replacement'),code('REPLY_FAILED'));
  assert.equal(instance.state.replies[0],'');
  assert.equal(instance.state.verified,true);
  fail = false;
  await assert.rejects(instance.saveQuickReply(0,'replacement'),code('REPLY_UNCERTAIN'));
  assert.equal(instance.state.verified,false);
  assert.equal(port.replies[0],'');
  await instance.disconnect();
});

test('confirmed Save remains saved if its following status refresh times out', async () => {
  let saved = false;
  const { instance, seen } = await connected({ onCommand: raw => {
    if (raw === 'wifi save') saved = true;
    if (raw === 'status' && saved) return false;
  } }, { timeouts: { command: 25 } });
  await instance.testWifi('network', 'password');
  assert.deepEqual(await instance.saveWifi(), { saved: true, status: null });
  assert.equal(instance.state.verified, false);
  assert.equal(seen.events.some(event => event.text.startsWith('Операция подтверждена')), true);
  await instance.disconnect();
});

test('disconnect aborts a stuck write even after its response already matched', async () => {
  const { instance, port } = await connected({ hangWrite: text => text === 'password\n' }, { timeouts: { test: 2000 } });
  const pending = assert.rejects(instance.testWifi('network', 'password'), code('DISCONNECTED'));
  await tick();
  assert.equal(port.stage, 'passed');
  assert.equal(instance._session.waiter, null);
  const started = Date.now();
  await instance.disconnect();
  await pending;
  assert.equal(Date.now() - started < 1000, true);
  assert.equal(instance.state.busy, false);
  await instance.connect(new FakePort());
  assert.equal(instance.state.verified, true);
  await instance.disconnect();
});

test('settings parsers reject unknown, duplicated, inconsistent and hostile fields',()=>{
  const capsLine=wireRecord('caps',SETTINGS_CAPS),caps=parseSettingsCaps(capsLine);
  assert.deepEqual(caps,SETTINGS_CAPS);
  assert.deepEqual(parseDeviceSettings(wireRecord('get',SETTINGS),caps),SETTINGS);
  for (const line of [capsLine+' x=1',capsLine.replace('sound=1','sound=2'),capsLine.replace('v=1','v=2'),capsLine.replace('sound=1','adc=1'),capsLine.replace('adc_min=3.675','adc_min=NaN'),capsLine.replace('adc_max=6.125','adc_max=2'),'<img>',capsLine+'\n']) assert.equal(parseSettingsCaps(line),null);
  for (const changed of [{volume:11},{melody:31},{gps:2},{shutdown_mv:2700},{adc_multiplier:100},{battery_mv:65536}]) assert.equal(parseDeviceSettings(wireRecord('get',{...SETTINGS,...changed}),caps),null);
  assert.equal(parseAdcPreview(wireRecord('adc_preview',{token:0,sampled_mv:3800,measured_mv:3800,multiplier:4.9}),caps,3800),null);
  assert.equal(parseAdcPreview(wireRecord('adc_preview',{token:1,sampled_mv:3800,measured_mv:3900,multiplier:4.9}),caps,3800),null);
  assert.equal(measuredMilliVolts(' 3,825 '),3825);
  assert.equal(measuredMilliVolts('4.5'),4500);
  for (const value of ['2.499','4,501','3e0','3800','3.8000','3,8\nsettings set muted 1','NaN',3.8]) assert.throws(()=>measuredMilliVolts(value),code('ADC_INPUT'));
});

test('settings are explicitly advertised, automatically read and never probed on old help',async()=>{
  const legacy=await connected({info:INFO});
  assert.equal(legacy.instance.state.settingsSupported,false);
  assert.equal(legacy.port.commands.some(c=>c.startsWith('settings')),false);
  await assert.rejects(legacy.instance.loadDeviceSettings(),code('SETTINGS_UNAVAILABLE'));
  await legacy.instance.disconnect();
  const f=await connected({settings:true,fragment:1});
  assert.deepEqual(f.port.commands.slice(-3),['settings caps','settings get','settings adc manual']);
  assert.deepEqual(f.instance.state.deviceSettings,SETTINGS);
  const copy=f.instance.state;copy.settingsCaps.adc=0;copy.deviceSettings.volume=1;
  assert.equal(f.instance.state.settingsCaps.adc,1);assert.equal(f.instance.state.deviceSettings.volume,10);
  await f.instance.disconnect();
});

test('every supported setting requires matched ACK then current readback',async()=>{
  const f=await connected({settings:true,settingsCaps:{gps:1,vibration:1}});
  for (const [key,value] of Object.entries({sound_quiet:1,volume:4,melody:8,board_led:0,unread_led:0,vibration:1,gps:1,battery_protection:0,muted:1})) {
    const result=await f.instance.saveDeviceSetting(key,value);
    assert.equal(result[key],value);
    assert.deepEqual(f.port.commands.slice(-2),['settings set '+key+' '+value,'settings get']);
  }
  assert.equal(f.instance.state.deviceSettings.shutdown_mv,2700);
  await f.instance.testDeviceNotification();assert.equal(f.port.commands.at(-1),'settings test');
  await f.instance.disconnect();
});

test('unsupported hardware, injection and invalid integers cannot write',async()=>{
  const f=await connected({settings:true,settingsCaps:{sound:0,gps:0,vibration:0}});
  const before=f.port.commands.length;
  for (const [key,value,error] of [['gps',1,'SETTINGS_UNSUPPORTED'],['vibration',1,'SETTINGS_UNSUPPORTED'],['volume',2,'SETTINGS_UNSUPPORTED'],['muted\nmode usb',1,'SETTINGS_INVALID'],['board_led',1.5,'SETTINGS_INVALID'],['board_led',2,'SETTINGS_INVALID']]) await assert.rejects(f.instance.saveDeviceSetting(key,value),code(error));
  assert.equal(f.port.commands.length,before);
  await f.instance.disconnect();
});

test('ADC preview is nonmutating; apply/reset need confirmation and matching readback',async()=>{
  const f=await connected({settings:true});
  const original=f.port.settingsState.adc_multiplier;
  const preview=await f.instance.previewAdc('3,82');
  assert.equal(f.port.commands.at(-1),'settings adc preview 3820');
  assert.equal(f.port.settingsState.adc_multiplier,original);
  assert.equal(f.instance.state.deviceSettings.adc_multiplier,original);
  await assert.rejects(f.instance.applyAdc(),code('ADC_CONFIRM'));
  const saved=await f.instance.applyAdc({confirmed:true});
  assert.equal(saved.adc_multiplier,preview.multiplier);assert.equal(f.instance.state.adcPreview,null);
  await assert.rejects(f.instance.resetAdc(),code('ADC_CONFIRM'));
  await f.instance.resetAdc({confirmed:true});
  assert.equal(f.port.settingsState.adc_multiplier,original);
  assert.equal(f.port.settingsState.board_led,1);
  await f.instance.disconnect();
});

test('ADC preview expires, is invalidated by another save and cleared on disconnect',async()=>{
  const f=await connected({settings:true},{timeouts:{adcPreview:20}});
  await f.instance.previewAdc('3.8');
  await new Promise(resolve=>setTimeout(resolve,30));
  assert.equal(f.instance.state.adcPreview,null);
  await assert.rejects(f.instance.applyAdc({confirmed:true}),code('ADC_CONFIRM'));
  await f.instance.previewAdc('3.8');await f.instance.saveDeviceSetting('muted',1);
  assert.equal(f.instance.state.adcPreview,null);
  await f.instance.previewAdc('3.8');await f.instance.disconnect();
  assert.equal(f.instance.state.adcPreview,null);assert.equal(f.instance.state.deviceSettings,null);
});

test('ADC cached source stays exact within board caps; source error cancels prior preview without saving',async()=>{
  let sourceMissing=false;
  const f=await connected({settings:true,settingsCaps:{adc_min:1.36125,adc_max:2.26875},
    settingsState:{battery_mv:4100,adc_multiplier:1.97,adc_default:1.815},
    onCommand(command,port){if(command.startsWith('settings adc preview ')){
      if(sourceMissing)port.reply('ERR settings source');
      else {port.adcPreview={token:7,sampled_mv:3100,measured_mv:3320,multiplier:2.109806};port.reply(wireRecord('adc_preview',port.adcPreview));}
      return false;
    }}});
  const preview=await f.instance.previewAdc('3,32');
  assert.equal(preview.sampled_mv,3100);assert.equal(preview.multiplier,2.109806);
  assert.equal(f.instance.state.deviceSettings.battery_mv,4100);
  assert.equal(f.port.settingsState.adc_multiplier,1.97);
  sourceMissing=true;
  await assert.rejects(f.instance.previewAdc('3.32'),error=>error.code==='SETTINGS_SOURCE'&&/от АКБ/.test(error.message)&&/без перезапуска/.test(error.message)&&/2 минут/.test(error.message));
  assert.equal(f.instance.state.adcPreview,null);
  await assert.rejects(f.instance.applyAdc({confirmed:true}),code('ADC_CONFIRM'));
  assert.equal(f.port.commands.some(c=>c.startsWith('settings adc apply')),false);
  assert.equal(f.port.settingsState.adc_multiplier,1.97);
  sourceMissing=false;
  await f.instance.previewAdc('3.32');await f.instance.applyAdc({confirmed:true});
  assert.equal(f.port.settingsState.adc_multiplier,2.109806);
  assert.equal(parseAdcPreview('OK settings adc_preview token=1 sampled_mv=3100 measured_mv=3320 multiplier=2.300000',f.instance.state.settingsCaps,3320),null);
  await f.instance.disconnect();
});

test('failed save does not show success; timeout and mismatched readback become uncertain',async()=>{
  for (const scenario of ['storage','timeout','mismatch','wrongack','unplug']) {
    let writes=0;
    const f=await connected({settings:true,onCommand(command,port){
      if (command==='settings set volume 5') {
        writes++;
        if(scenario==='storage') port.reply('ERR settings storage');
        else if(scenario==='mismatch') port.reply('OK settings set key=volume value=5');
        else if(scenario==='wrongack') port.reply('OK settings set key=board_led value=1');
        else if(scenario==='unplug') port.unplug();
        return false;
      }
    }});
    await assert.rejects(f.instance.saveDeviceSetting('volume',5),code(scenario==='storage'?'SETTINGS_STORAGE':'SETTINGS_UNCERTAIN'));
    assert.equal(writes,1);
    assert.equal(f.seen.events.some(e=>e.text.includes('Настройка сохранена')),false);
    if (scenario!=='storage') assert.equal(f.instance.state.verified,false);
    else assert.equal(f.instance.state.deviceSettings.volume,10);
    await f.instance.disconnect();
  }
});

test('settings protocol errors are sanitized, ADC stale/storage errors do not claim success',async()=>{
  for (const [wire,expected] of [['ERR settings stale','SETTINGS_STALE'],['ERR settings storage','SETTINGS_STORAGE'],['ERR settings range','SETTINGS_RANGE'],['ERR settings measurement','SETTINGS_MEASUREMENT'],['ERR settings source','SETTINGS_SOURCE'],['ERR settings busy','BUSY'],['ERR settings readonly','READ_ONLY'],['ERR settings <secret>','PROTOCOL']]) {
    const f=await connected({settings:true,onCommand(command,port){if(command.startsWith('settings adc preview ')){port.reply(wire);return false;}}});
    await assert.rejects(f.instance.previewAdc('3.8'),code(expected));
    assert.equal(f.instance.state.adcPreview,null);
    assert.equal(JSON.stringify(f.seen).includes('<secret>'),false);
    await f.instance.disconnect();
  }
});

test('storage recovery blocks device mutation and a pending WiFi test blocks settings commands',async()=>{
  const f=await connected({settings:true});
  f.instance._setStatus({...f.instance.state.status,readOnly:true});
  const before=f.port.commands.length;
  await assert.rejects(f.instance.saveDeviceSetting('muted',1),code('READ_ONLY'));
  assert.equal(f.port.commands.length,before);
  f.instance._setStatus({...f.instance.state.status,readOnly:false});
  await f.instance.testWifi('network','password');
  await assert.rejects(f.instance.loadDeviceSettings(),code('WIFI_PENDING'));
  await f.instance.cancelWifi();await f.instance.disconnect();
});

test('a readback error after acknowledged save is uncertain, not a claimed rollback',async()=>{
  let acknowledged=false;
  const f=await connected({settings:true,onCommand(command,port){
    if(command==='settings set volume 5'){acknowledged=true;port.settingsState.volume=5;port.reply('OK settings set key=volume value=5');return false;}
    if(command==='settings get' && acknowledged){port.reply('ERR settings unavailable');return false;}
  }});
  await assert.rejects(f.instance.saveDeviceSetting('volume',5),code('SETTINGS_UNCERTAIN'));
  assert.equal(f.port.settingsState.volume,5);
  assert.equal(f.instance.state.deviceSettings,null);
  assert.equal(f.instance.state.verified,false);
  await f.instance.disconnect();
});

test('Settings 1 can expose current values in recovery without allowing writes',async()=>{
  const f=await connected({settings:true,onCommand(command,port){
    if(['cancel','wifi cancel'].includes(command)){port.reply('Connection settings are read-only during storage recovery.');return false;}
  }});
  assert.equal(f.instance.state.settingsSupported,true);
  assert.equal(f.instance.state.status.readOnly,true);
  assert.equal(f.instance.state.deviceSettings.volume,10);
  const before=f.port.commands.length;
  await assert.rejects(f.instance.saveDeviceSetting('volume',5),code('READ_ONLY'));
  assert.equal(f.port.commands.length,before);
  await f.instance.loadDeviceSettings();
  await f.instance.disconnect();
});

test('ADC service is discovered, explicit, fixed snapshot, and stopped on disconnect',async()=>{
  const old=await connected({settings:true});
  assert.equal(old.instance.state.adcService,null);
  assert.equal(old.port.commands.some(c=>c.startsWith('settings adc service')),false);
  await old.instance.disconnect();
  const f=await connected({settings:true,settingsCaps:{adc_service:1}});
  assert.equal(f.instance.state.adcService.active,0);
  await assert.rejects(f.instance.startAdcService(),code('ADC_SERVICE_CONFIRM'));
  assert.equal(f.port.commands.some(c=>c.endsWith('service start')),false);
  await f.instance.startAdcService({confirmed:true});
  f.port.adcService.remaining_ms=93210;await f.instance.loadAdcService();
  assert.equal(f.instance.state.adcService.remaining_ms,93210);
  assert.equal(f.port.commands.filter(c=>c.endsWith('service start')).length,1);
  await f.instance.previewAdc('3.82');assert.ok(f.instance.state.adcPreview);
  await f.instance.disconnect();
  assert.equal(f.port.commands.filter(c=>c.endsWith('service stop')).length,1);
  assert.equal(f.instance.state.adcService,null);assert.equal(f.instance.state.adcPreview,null);
});

test('manual ADC probe is compatible; direct save needs confirmation and verifies readback without sampling',async()=>{
  const old=await connected({settings:true});assert.equal(old.instance.state.adcManualSupported,false);assert.equal(old.instance.state.verified,true);await old.instance.disconnect();
  const f=await connected({settings:true,manualAdc:true,settingsCaps:{adc_min:1.36125,adc_max:2.26875,adc_service:1},settingsState:{adc_multiplier:1.97,adc_default:1.815,battery_mv:2770}});
  assert.equal(f.instance.state.adcManualSupported,true);
  await assert.rejects(f.instance.setAdcMultiplier('1.815'),code('ADC_CONFIRM'));
  await f.instance.startAdcService({confirmed:true});
  const saved=await f.instance.setAdcMultiplier('1,815000',{confirmed:true});
  assert.equal(saved.adc_multiplier,1.815);assert.equal(saved.battery_protection,1);assert.equal(f.instance.state.adcService.active,0);
  assert.equal(f.port.commands.filter(c=>c==='settings adc set 1.815000').length,1);
  assert.equal(f.port.commands.some(c=>c.startsWith('settings adc preview')),false);
  await f.instance.disconnect();
});

test('manual ADC lost ACK or mismatched readback blocks new writes and never repeats set',async()=>{
  for(const mismatch of [false,true]){
    let set=false;
    const f=await connected({settings:true,manualAdc:true,dropAdcAck:!mismatch,onCommand(command,port){
      if(command.startsWith('settings adc set '))set=true;
      if(mismatch&&set&&command==='settings get'){port.reply(wireRecord('get',{...port.settingsState,adc_multiplier:4.99}));return false;}
    }});
    await assert.rejects(f.instance.setAdcMultiplier('4.8',{confirmed:true}),code('SETTINGS_UNCERTAIN'));
    assert.equal(f.instance.state.verified,false);assert.equal(f.instance.state.deviceSettings,null);
    await assert.rejects(f.instance.setAdcMultiplier('4.7',{confirmed:true}),code('NOT_VERIFIED'));
    assert.equal(f.port.commands.filter(c=>c.startsWith('settings adc set ')).length,1);await f.instance.disconnect();
  }
});

test('ADC service save and expiration clear preview; USB denial does not retry',async()=>{
  const f=await connected({settings:true,settingsCaps:{adc_service:1}});
  f.port.adcService.external=0;
  await assert.rejects(f.instance.startAdcService({confirmed:true}),code('ADC_USB_REQUIRED'));
  assert.equal(f.instance.state.adcService,null);
  f.port.adcService.external=1;await f.instance.startAdcService({confirmed:true});
  await f.instance.previewAdc('3.82');await f.instance.applyAdc({confirmed:true});
  assert.equal(f.instance.state.adcService.active,0);
  assert.equal(f.instance.state.deviceSettings.battery_protection,1);
  await f.instance.startAdcService({confirmed:true});await f.instance.previewAdc('3.82');
  Object.assign(f.port.adcService,{active:0,remaining_ms:0});await f.instance.loadAdcService();
  assert.equal(f.instance.state.adcPreview,null);await f.instance.disconnect();
});

test('lost ADC service start acknowledgement never retries or reports an invented timer',async()=>{
  const f=await connected({settings:true,settingsCaps:{adc_service:1},onCommand(command,port){
    if(command==='settings adc service start'){Object.assign(port.adcService,{active:1,remaining_ms:120000});return false;}
  }});
  await assert.rejects(f.instance.startAdcService({confirmed:true}),code('TIMEOUT'));
  assert.equal(f.instance.state.adcService,null);
  assert.equal(f.port.commands.filter(c=>c.endsWith('service start')).length,1);
  assert.equal(f.instance.state.verified,false);
  await assert.rejects(f.instance.loadAdcService(),code('NOT_VERIFIED'));
  await f.instance.disconnect();
});

test('ADC service stop remains available under storage read-only',async()=>{
  const f=await connected({settings:true,settingsCaps:{adc_service:1}});
  await f.instance.startAdcService({confirmed:true});
  f.instance._setStatus({...f.instance.state.status,readOnly:true});
  await assert.rejects(f.instance.startAdcService({confirmed:true}),code('READ_ONLY'));
  await f.instance.stopAdcService();assert.equal(f.instance.state.adcService.active,0);
  await f.instance.disconnect();
});

test('network feature read timeout invalidates untagged console; unknown feature does not',async()=>{
  const old=await connected();await assert.rejects(old.instance.loadNetworkSetting('radio'),code('SETTINGS_UNSUPPORTED'));assert.equal(old.instance.state.verified,true);await old.instance.disconnect();
  const f=await connected({onCommand(command){if(command==='settings radio')return false;}});
  await assert.rejects(f.instance.loadNetworkSetting('radio'),code('TIMEOUT'));assert.equal(f.instance.state.verified,false);
  const count=f.port.commands.length;await assert.rejects(f.instance.loadNetworkSetting('radio'),code('NOT_VERIFIED'));assert.equal(f.port.commands.length,count);await f.instance.disconnect();
});

test('network settings persist once, preserve current path, and fail closed after lost readback',async()=>{
  let state={freq_khz:869525,bw_hz:250000,sf:11,cr:5,path_bytes:3,tx_dbm:20,repeat:0},saved=false;
  const f=await connected({onCommand(command,port){
    if(command.startsWith('settings radio set ')){['freq_khz','bw_hz','sf','cr','path_bytes'].forEach((k,i)=>state[k]=Number(command.split(' ')[i+3]));saved=true;port.reply(wireRecord('radio',state));return false;}
    if(command==='settings radio'){port.reply(saved?'ERR settings busy':wireRecord('radio',state));return false;}
  }});
  await assert.rejects(f.instance.saveNetworkSetting('radio',{freq_khz:868731,bw_hz:62500,sf:7,cr:7,path_bytes:1}),code('SETTINGS_UNCERTAIN'));
  assert.equal(state.path_bytes,3);assert.equal(state.tx_dbm,20);assert.equal(state.freq_khz,868731);assert.equal(f.instance.state.verified,false);
  assert.equal(f.port.commands.filter(c=>c.startsWith('settings radio set')).length,1);await f.instance.disconnect();
});
