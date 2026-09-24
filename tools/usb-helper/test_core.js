'use strict';

// No dependencies or device required: node tools/usb-helper/test_core.js
const test = require('node:test');
const assert = require('node:assert/strict');
const { ReadableStream, WritableStream } = require('node:stream/web');
const { ConsoleClient, ConsoleError, validateCredentials, parseStatus } = require('./core.js');

const STATUS = 'Mode=BLE companion=idle via=none USB-service=on WiFi-config=no link=down IP=none approval=none';
const SSID_PROMPT = 'SSID input is hidden; enter SSID, then Enter:';
const PASSWORD_PROMPT = "Password input is hidden; enter 8..64 bytes, blank for open WiFi, or 'cancel':";
const HELP = 'Commands: status | mode ble | mode usb | mode wifi | wifi setup | wifi status | wifi save | wifi cancel | wifi forget | help\r\nCredential input is not echoed. WiFi is saved only after a passed test.';
const tick = () => new Promise(resolve => setImmediate(resolve));

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
        } else if (this.input.length < 96) this.input += char;
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
    if (this.options.readOnly && command !== 'status') { this.reply('Connection settings are read-only during storage recovery.'); return; }
    switch (command) {
      case 'help': this.reply(HELP); break;
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
  for (const bad of ['<script>' + STATUS, STATUS + '<img>', STATUS.replace('IP=none', 'IP=300.1.1.1'), STATUS.replace('IP=none', 'IP=<secret>')]) assert.equal(parseStatus(bad), null);
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
  assert.equal(port.rawWrites.filter(value => value === '\b'.repeat(96) + 'cancel\n').length, 2);
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

test('read-only firmware can be inspected but mutations are blocked', async () => {
  const { instance, port } = await connected({ readOnly: true });
  assert.equal(instance.state.verified, true);
  assert.equal(instance.state.status.readOnly, true);
  await assert.rejects(instance.testWifi('network', 'password'), code('READ_ONLY'));
  await assert.rejects(instance.setMode('wifi'), code('READ_ONLY'));
  await assert.rejects(instance.forgetWifi(), code('READ_ONLY'));
  assert.equal(port.commands.includes('wifi setup'), false);
  await instance.refreshStatus();
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

test('known persistent Forget cleanup failure invalidates old status', async () => {
  const { instance } = await connected({ onCommand: (raw, target) => {
    if (raw === 'wifi forget') { target.reply('WiFi cleared in RAM; persistent cleanup failed.'); return false; }
  } });
  await assert.rejects(instance.forgetWifi(), code('FORGET_FAILED'));
  assert.equal(instance.state.verified, false);
  assert.equal(instance.state.status, null);
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
