'use strict';
// Capture the production Helper UI with synthetic serial streams, never hardware.
// Requires Playwright plus a Chromium browser; no production files are modified.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');
const {installApiMock} = require('./usb-helper/test_api_fixture');
const {fullSettingsFixture} = require('./usb-helper/test_full_settings_fixture');

const root = path.resolve(__dirname, '..');
const output = path.resolve(process.argv[2] || path.join(root, 'docs/assets/showcase/readme-helper.png'));
const mobileOutput = path.join(path.dirname(output), path.basename(output, '.png') + '-mobile.png');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'smartui-readme-helper-'));
const html = path.join(temporary, 'SmartUI_USB_Helper_2.9.html');
const rendered = spawnSync(process.env.PYTHON || 'python', ['-B', '-c',
  'from pathlib import Path; from tools.package_usb_helper import render; import sys; Path(sys.argv[1]).write_bytes(render())', html],
  {cwd: root, encoding: 'utf8', windowsHide: true});
assert.equal(rendered.status, 0, rendered.stderr);
fs.mkdirSync(path.dirname(output), {recursive: true});

async function capture() {
  const executablePath = [process.env.CHROME_PATH,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser']
    .filter(Boolean).find(candidate => fs.existsSync(candidate));
  const browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  const errors = [], network = [];
  try {
    const context = await browser.newContext({viewport: {width: 1280, height: 1800}, locale: 'ru-RU', reducedMotion: 'reduce'});
    await context.route(/^https?:\/\//, async route => {
      network.push(route.request().url());
      await route.abort();
    });
    const page = await context.newPage();
    page.setDefaultTimeout(10000);
    page.on('pageerror', error => errors.push(error.message));
    const fixture = fullSettingsFixture();
    // The T096-shaped fixture's older TX-gain capability is not in SmartUI 0.22.
    fixture.caps.fem_pa = 0;
    fixture.settings.fem_pa = 0;
    fixture.schemas.fem_pa = {...fixture.schemas.fem_pa, supported: 0};
    await page.addInitScript(installApiMock, {
      console: 1, control: 1, meshcore: 1, blePin: 1, firmware: '0.22',
      soundPreview: true, manualAdc: true, wifi: false,
      caps: fixture.caps, settings: fixture.settings, schemas: fixture.schemas
    });
    await page.addInitScript(() => {
      const mock = window.__apiMock;
      mock.meshcore.name = 'Демо-нода T096';
      const close = mock.close.bind(mock);
      mock.close = async () => { await close(); mock.readable = null; mock.writable = null; };
    });
    await page.goto(pathToFileURL(html).href);
    assert.equal(await page.evaluate(() => __apiMock.requests), 0, 'No port request on load');
    await page.locator('#connect').click();
    await page.waitForFunction(() => {
      const state = SmartUiConsoleBridge.getContext();
      return state.connected && !state.busy && state.settings?.volume !== undefined;
    });
    assert.equal(await page.locator('#view-simple').getAttribute('aria-pressed'), 'true');
    assert.match(await page.locator('header .tag').textContent(), /2\.9/);
    assert.match(await page.locator('#simple-device').textContent(), /SmartUI 0\.22/);
    assert.equal(await page.locator('#simple-title').textContent(), 'Демо-нода T096');
    assert.equal(await page.locator('#simple-setting-volume').inputValue(), '7');
    assert.equal(await page.evaluate(() => SmartUiConsoleBridge.getContext().firmware), '0.22');

    // Documentary annotation only. The production controls/layout remain intact.
    await page.locator('.simple-intro').evaluate(intro => {
      const caption = document.createElement('p');
      caption.id = 'readme-simulation-caption';
      caption.className = 'hint';
      caption.textContent = 'USB Helper 2.9 · Симуляция USB-ноды · Не физическая плата';
      intro.before(caption);
    });
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const panel = await page.locator('#simple-panel').boundingBox();
    const lastRow = await page.locator('.simple-setting[data-key="melody"]').boundingBox();
    assert.ok(panel && lastRow);
    const clip = {x: Math.floor(panel.x), y: Math.floor(panel.y), width: Math.ceil(panel.width),
      height: Math.ceil(lastRow.y + lastRow.height - panel.y + 8)};
    await page.screenshot({path: output, clip, animations: 'disabled'});

    const commands = await page.evaluate(() => [...__apiMock.commands]);
    assert.equal(await page.evaluate(() => __apiMock.requests), 1, 'Exactly one synthetic port request');
    assert.deepEqual(commands.filter(command => /^(set |ui (set |name |tx set |radio set |advert set ))/.test(command)), [], 'Screenshot capture only reads');
    assert.deepEqual(errors, [], 'Browser runtime errors');
    assert.deepEqual(network, [], 'No external network requests');

    await page.setViewportSize({width: 390, height: 1800});
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'No mobile horizontal overflow');
    const mobilePanel = await page.locator('#simple-panel').boundingBox();
    const mobileLastRow = await page.locator('.simple-setting[data-key="sound_quiet"]').boundingBox();
    assert.ok(mobilePanel && mobileLastRow);
    const mobileClip = {x: Math.floor(mobilePanel.x), y: Math.floor(mobilePanel.y), width: Math.ceil(mobilePanel.width),
      height: Math.ceil(mobileLastRow.y + mobileLastRow.height - mobilePanel.y + 8)};
    await page.screenshot({path: mobileOutput, clip: mobileClip, animations: 'disabled'});
    assert.match(await page.locator('#readme-simulation-caption').textContent(), /Симуляция USB-ноды/);
    assert.equal(await page.evaluate(() => __apiMock.requests), 1, 'Viewport changes never request another port');
    assert.deepEqual(await page.evaluate(() => [...__apiMock.commands]), commands, 'Viewport changes only render existing state');
    assert.deepEqual(errors, [], 'Browser runtime errors after mobile capture');
    assert.deepEqual(network, [], 'No external network requests after mobile capture');
    console.log(JSON.stringify({output, width: clip.width, height: clip.height, helper: '2.9',
      simulatedFirmware: '0.22', physicalDevice: false, externalRequests: network.length,
      mutationCommands: 0, browserErrors: errors.length, mobileOverflow: false,
      mobileOutput, mobileWidth: mobileClip.width, mobileHeight: mobileClip.height,
      sourceHtml: html}, null, 2));
    await context.close();
  } finally {
    await browser.close();
  }
}
capture().catch(error => { console.error(error); process.exitCode = 1; });
