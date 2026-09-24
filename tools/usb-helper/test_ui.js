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
const { chromium } = require('playwright');

const root = path.resolve(__dirname, '../..');
const output = process.env.SMARTUI_UI_OUTPUT
  ? path.resolve(process.env.SMARTUI_UI_OUTPUT)
  : fs.mkdtempSync(path.join(os.tmpdir(), 'smartui-usb-ui-'));
const artifact = path.join(output, 'SmartUI_USB_Helper_1.0.html');
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

function installSerialMock({ supported, readOnly, manualTest }) {
  if (!supported) {
    Object.defineProperty(Navigator.prototype, 'serial', { configurable: true, get: () => undefined });
    return;
  }
  const mock = window.__serialMock = {
    requests: 0, commands: [], raw: [], mode: 'BLE', configured: false,
    stage: 'idle', manualTest, readOnly, closed: false, ssid: null, password: null,
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
      if (this.readOnly && command !== 'status') { this.emit('Connection settings are read-only during storage recovery.'); return; }
      switch (command) {
        case 'help': this.emit('Commands: status | mode ble | mode usb | mode wifi | wifi setup | wifi status | wifi save | wifi cancel | wifi forget | help\r\nCredential input is not echoed. WiFi is saved only after a passed test.'); break;
        case 'status': {
          const online = this.mode === 'WiFi' && this.configured;
          this.emit('Mode=' + this.mode + ' companion=idle via=none USB-service=on WiFi-config=' + (this.configured ? 'yes' : 'no') + ' link=' + (online ? 'associated' : 'down') + ' IP=' + (online ? '192.168.1.77' : 'none') + ' approval=none');
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
        case 'wifi forget': this.configured = false; this.mode = 'BLE'; this.emit('WiFi credentials forgotten.'); break;
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
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/^https?:/i.test(request.url())) network.push(request.url()); });
  await page.addInitScript(installSerialMock, { supported: options.supported !== false, readOnly: Boolean(options.readOnly), manualTest: Boolean(options.manualTest) });
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
}
async function ready(page) { await page.waitForFunction(() => !document.getElementById('test').disabled); }
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

test('offline package loads in Chrome: unsupported Web Serial and responsive layout', async () => {
  const f = await fixture({ supported: false });
  try {
    assert.equal(await f.page.title(), 'SmartUI · USB помощник');
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
    assert.equal(await page.locator('#mode').textContent(), 'Bluetooth');
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

    await confirm(page, '#mode-wifi', false);
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

    await page.locator('#ssid').fill('cancel');
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

    await confirm(page, '#mode-usb', true);
    await page.waitForFunction(() => document.getElementById('connection').textContent === 'Нода не подключена');
    assert.equal(await page.locator('#connect').isEnabled(), true);
    assert.equal(await page.evaluate(() => window.__serialMock.closed), true);
    assert.equal(await page.locator('#mode').textContent(), '—');
    assert.match(await page.locator('#feedback').textContent(), /результат неизвестен/);
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
  } finally { await f.close(); }
});

test('unplug clears secrets/status and ignores hostile serial text', async () => {
  const f = await fixture();
  const page = f.page;
  try {
    await connect(page);
    await ready(page);
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
    await f.page.locator('#disconnect').click();
    await f.page.waitForFunction(() => !document.getElementById('connect').disabled);
  } finally { await f.close(); }
});
