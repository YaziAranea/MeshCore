'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const presets = require('./presets');
const { buildSnapshot, localizedNames, serialize } = require('../update_meshcoretel_presets');
const when = '2026-10-07T06:02:33.000Z';
const region = (code, name = code) => ({ code, name, kind: 'iata', country_code: 'RU' });
const catalog = rows => ({ countries: [{ country: { code: 'RU' }, regions: rows }] });
const radio = (code, patch = {}) => ({ code, settings: { frequency: '868.731018', bandwidth: '62.5', spreadingFactor: '7', codingRate: '7', ...patch } });
const build = (regions = [region('OMS', 'Omsk')], radios = [radio('OMS')], names = { OMS: 'Омск' }) =>
  buildSnapshot(catalog(regions), radios, names, when);

test('bundled snapshot has real source provenance and no invented evidence', () => {
  assert.ok(presets.list().length >= 40);
  assert.equal(presets.metadata.presetCount, presets.list().length);
  assert.equal(presets.metadata.selectionCount, presets.list().length + presets.metadata.excluded.length);
  assert.match(presets.metadata.sourceHashes.catalog, /^[a-f0-9]{64}$/);
  assert.match(presets.metadata.sourceHashes.radio, /^[a-f0-9]{64}$/);
  assert.match(presets.metadata.namesUrl, /^https:\/\/meshcoretel\.ru\/assets\/index-[\w-]+\.js$/);
  assert.equal(presets.metadata.sourceUrl, 'https://meshcoretel.ru/ru/OMS');
  assert.ok(Date.parse(presets.metadata.snapshotAt) > 0);
  for (const row of presets.list()) {
    assert.equal(presets.validateRadio(row), true, row.code);
    assert.equal(row.votes, null);
    assert.equal(row.sourceUpdatedAt, null);
    assert.equal(row.pathHashBytes, null);
    assert.equal(row.frequencyKHz, Math.round(Number(row.sourceRadio.frequency) * 1000));
    assert.equal(row.bandwidthHz, Number(row.sourceRadio.bandwidth) * 1000);
    assert.equal(row.sf, Number(row.sourceRadio.spreadingFactor));
    assert.equal(row.cr, Number(row.sourceRadio.codingRate));
  }
});

test('search by Russian name, English name and IATA; no default city', () => {
  assert.equal(presets.get(' oms ').name, 'Омск');
  assert.equal(presets.list('Омск')[0].id, 'OMS');
  assert.equal(presets.list('Omsk')[0].id, 'OMS');
  assert.equal(presets.list('оРеЛ')[0].id, 'OEL');
  assert.equal(presets.list('САНКТ LED')[0].id, 'LED');
  assert.equal(presets.get('ZZZ'), null);
  assert.equal(presets.get(''), null);
  assert.equal(presets.get(null), null);
  assert.deepEqual(presets.list('нет-такого-города'), []);
  assert.deepEqual(presets.list().map(row => row.id), presets.list().map(row => row.id));
});

test('catalog and rows cannot be silently modified by a caller', () => {
  assert.throws(() => { presets.get('OMS').sf = 12; }, TypeError);
  assert.throws(() => { presets.get('OMS').sourceRadio.frequency = '433'; }, TypeError);
  assert.throws(() => { presets.metadata.sourceHashes.radio = ''; }, TypeError);
  const length = presets.list().length;
  presets.list().pop();
  assert.equal(presets.list().length, length);
});

test('source join is exact and only includes cities from the RU catalog', () => {
  const snapshot = build([region('OMS'), region('LED')], [radio('MOW'), radio('OMS'), radio('AAQ'), radio('LED', { frequency: '868.856018' })]);
  assert.deepEqual(snapshot.presets.map(row => row.code), ['LED', 'OMS']);
  assert.equal(snapshot.presets[0].frequencyMHz, 868.856);
  assert.equal(snapshot.presets[1].frequencyMHz, 868.731);
  const api = presets.createCatalog(snapshot);
  assert.equal(api.get('MOW'), null);
  assert.equal(api.get('AAQ'), null);
});

test('missing or unsupported city is excluded, not filled from Moscow/default', () => {
  const snapshot = build([region('OMS'), region('LED'), region('SVX')], [radio('OMS'), radio('SVX', { spreadingFactor: '263' })]);
  assert.deepEqual(snapshot.presets.map(row => row.code), ['OMS']);
  assert.deepEqual(snapshot.metadata.excluded, [
    { code: 'LED', reason: 'missing-radio-settings' },
    { code: 'SVX', reason: 'unsupported-radio-settings' },
  ]);
  assert.throws(() => build([region('LED')], [radio('MOW')]), /No usable/);
});

test('strict numeric and SX1262 range validation rejects truncation/injection', () => {
  for (const patch of [
    { frequency: 'NaN' }, { frequency: 'Infinity' }, { frequency: '868;reboot' },
    { frequency: '868.731garbage' }, { frequency: '149' }, { frequency: '961' },
    { frequency: 868.731 }, { bandwidth: '126' }, { bandwidth: '0' },
    { spreadingFactor: '7e0' }, { spreadingFactor: '7.5' }, { spreadingFactor: '263' },
    { spreadingFactor: '-1' }, { spreadingFactor: '' }, { codingRate: '9' },
  ]) assert.throws(() => build([region('OMS')], [radio('OMS', patch)]), /No usable/, JSON.stringify(patch));
  for (const bandwidth of ['7.8', '10.4', '15.6', '20.8', '31.25', '41.7', '62.5', '125', '250', '500']) {
    assert.equal(build([region('OMS')], [radio('OMS', { bandwidth })]).presets.length, 1);
  }
});

test('duplicate, wrong-country and malformed catalog fail closed', () => {
  assert.throws(() => build([region('OMS'), region('OMS')]), /duplicate/);
  assert.throws(() => build(undefined, [radio('OMS'), radio('OMS')]), /duplicate/);
  assert.throws(() => build([{ ...region('OMS'), country_code: 'BY' }]), /Invalid/);
  assert.throws(() => build([{ ...region('OMS'), kind: 'country' }]), /Invalid/);
  assert.throws(() => build([{ ...region('OMS'), code: '<x>' }]), /Invalid/);
  assert.throws(() => buildSnapshot({ countries: [] }, [], {}, when), /Missing RU/);
  assert.throws(() => buildSnapshot({ countries: [{ country: { code: 'RU' }, regions: [] }] }, [], {}, when), /region count/);
});

test('Russian names extracted as data without evaluating site JavaScript', () => {
  assert.deepEqual(localizedNames('const Q={OMS:"Омск",MOW:"Москва",OEL:"Орёл"};'), { OMS: 'Омск', MOW: 'Москва', OEL: 'Орёл' });
  assert.throws(() => localizedNames('const Q={OMS:"Омск",MOW:"Москва",EGO:runCode()};'), /Unrecognized/);
  assert.throws(() => localizedNames('const Q={OMS:"Омск",MOW:"Москва",OMS:"Подмена"};'), /Duplicate/);
  assert.throws(() => localizedNames(''), /not found/);
});

test('untrusted names and malformed embedded rows rejected', () => {
  for (const name of ['<img src=x>', 'x\ny', '', 'x'.repeat(101)]) {
    assert.throws(() => build([region('OMS')], [radio('OMS')], { OMS: name }), /Invalid city/);
  }
  for (const change of [row => row.frequencyMHz = 915, row => row.id = 'MOW', row => row.pathHashBytes = 4,
    row => row.votes = 0, row => row.sourceUrl = 'https://example.org/OMS']) {
    const data = build();
    change(data.presets[0]);
    assert.throws(() => presets.createCatalog(data), /Invalid city/);
  }
  const data = build();
  data.presets.push(data.presets[0]);
  assert.throws(() => presets.createCatalog(data), /Invalid city/);
  data.presets.pop();
  data.metadata.snapshotAt = 'yesterday';
  assert.throws(() => presets.createCatalog(data), /snapshot/);
});

test('embedded JSON never terminates its HTML script block', () => {
  const output = serialize({ name: '</script><img>&\u2028\u2029' });
  assert.equal(output.includes('</script'), false);
  assert.equal(output.includes('<'), false);
  assert.deepEqual(JSON.parse(output), { name: '</script><img>&\u2028\u2029' });
});

test('browser module works offline and never reaches network or storage', () => {
  const text = fs.readFileSync(require.resolve('./presets'), 'utf8');
  const context = vm.createContext({
    fetch() { throw new Error('Unexpected network access'); },
    localStorage: { getItem() { throw new Error('Unexpected storage access'); } },
  });
  vm.runInContext(text, context);
  assert.equal(context.SmartUiPresets.get('OMS').id, 'OMS');
  assert.ok(context.SmartUiPresets.list('Омск').some(row => row.id === 'OMS'));
});
