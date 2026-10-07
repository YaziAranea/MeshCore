#!/usr/bin/env node
'use strict';
// Maintainer-only snapshot generation. Never imported by the offline helper.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const presets = require('./usb-helper/presets');
const origin = 'https://meshcoretel.ru';
const sourceUrl = origin + '/ru/OMS';
const catalogUrl = origin + '/api/regions/catalog';
const radioUrl = origin + '/api/regions/radio-settings?all_regions=true';
const target = path.join(__dirname, 'usb-helper', 'presets.js');
const maxBody = 8 * 1024 * 1024;

function numeric(text) {
  if (typeof text !== 'string' || !/^(?:0|[1-9]\d*)(?:\.\d{1,9})?$/.test(text)) return NaN;
  return Number(text);
}

function localizedNames(script) {
  // Extract a string-only dictionary; never evaluate downloaded JavaScript.
  const anchor = script.indexOf('OMS:"Омск"');
  if (anchor < 0) throw new Error('Russian city dictionary not found');
  const start = script.lastIndexOf('{', anchor);
  const end = script.indexOf('}', anchor);
  if (start < 0 || end <= start || end - start > 50000) throw new Error('Invalid city dictionary');
  const dictionary = script.slice(start + 1, end);
  const names = {};
  const grammar = /(?:^|,)([A-Z0-9]{3,5}):("(?:[^"\\\x00-\x1f]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*")/gy;
  let match;
  let consumed = 0;
  while ((match = grammar.exec(dictionary))) {
    if (Object.hasOwn(names, match[1])) throw new Error('Duplicate city name');
    names[match[1]] = JSON.parse(match[2]);
    consumed = grammar.lastIndex;
  }
  if (consumed !== dictionary.length || names.OMS !== 'Омск' || names.MOW !== 'Москва') {
    throw new Error('Unrecognized city dictionary; inspect upstream changes');
  }
  return names;
}

function buildSnapshot(catalog, radio, names, snapshotAt, provenance = {}) {
  const countries = catalog?.countries;
  if (!Array.isArray(countries) || !Array.isArray(radio) || radio.length > 1024) throw new Error('Invalid source catalog');
  const matches = countries.filter(country => country.country?.code === 'RU');
  if (matches.length !== 1 || !Array.isArray(matches[0].regions)) throw new Error('Missing RU region list');
  const selected = matches[0].regions;
  if (!selected.length || selected.length > 512) throw new Error('Invalid RU region count');
  const byCode = new Map();
  for (const row of radio) {
    if (!row || !/^[A-Z0-9-]{2,32}$/.test(row.code) || byCode.has(row.code)) throw new Error('Invalid/duplicate radio code');
    byCode.set(row.code, row.settings);
  }
  const rows = [], excluded = [], seen = new Set();
  for (const region of selected) {
    const code = region?.code;
    if (!/^[A-Z0-9]{3}$/.test(code) || seen.has(code) || region.kind !== 'iata' || region.country_code !== 'RU') {
      throw new Error('Invalid/duplicate selected region');
    }
    seen.add(code);
    const source = byCode.get(code);
    if (!source) { excluded.push({ code, reason: 'missing-radio-settings' }); continue; }
    const frequencyMHz = numeric(source.frequency);
    const bandwidthKHz = numeric(source.bandwidth);
    const frequencyKHz = Math.round(frequencyMHz * 1000);
    const bandwidthHz = bandwidthKHz * 1000;
    const row = {
      id: code, code,
      name: Object.hasOwn(names, code) ? names[code] : region.name,
      nameEn: region.name,
      frequencyKHz, frequencyMHz: frequencyKHz / 1000,
      bandwidthHz, bandwidthKHz, sf: numeric(source.spreadingFactor), cr: numeric(source.codingRate),
      pathHashBytes: null, votes: null, sourceUpdatedAt: null,
      sourceUrl: origin + '/ru/' + code,
      sourceRadio: { frequency: source.frequency, bandwidth: source.bandwidth,
        spreadingFactor: source.spreadingFactor, codingRate: source.codingRate },
    };
    if (!presets.validateRadio(row)) { excluded.push({ code, reason: 'unsupported-radio-settings' }); continue; }
    rows.push(row);
  }
  if (!rows.length) throw new Error('No usable city presets; keeping previous snapshot');
  rows.sort((a, b) => a.code.localeCompare(b.code));
  const result = {
    metadata: {
      schema: 1, snapshotAt, sourceUrl, sourceName: 'MeshCoreTel', countrySelection: 'RU',
      selectionCount: selected.length, presetCount: rows.length, excluded,
      catalogUrl, radioUrl, ...provenance,
      selectionPolicy: 'Only RU iata regions listed in the source catalog; exact radio code match. No client default.',
      unknownFields: ['votes', 'sourceUpdatedAt', 'pathHashBytes'],
    },
    presets: rows,
  };
  presets.createCatalog(result);
  return result;
}

async function download(url) {
  const parsed = new URL(url);
  if (parsed.origin !== origin) throw new Error('Unexpected source origin');
  const response = await fetch(url, { signal: AbortSignal.timeout(20000), redirect: 'error',
    headers: { Accept: 'application/json, text/html, text/javascript', 'User-Agent': 'MeshCore-SmartUI-Preset-Snapshot/1' } });
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
  if (Number(response.headers.get('content-length')) > maxBody) throw new Error('Source exceeds size limit');
  const reader = response.body.getReader();
  let length = 0;
  const chunks = [];
  try {
    while (true) {
      const result = await reader.read();
      if (result.done) break;
      length += result.value.length;
      if (length > maxBody) throw new Error('Source exceeds size limit');
      chunks.push(Buffer.from(result.value));
    }
  } finally { await reader.cancel().catch(() => {}); }
  return Buffer.concat(chunks).toString('utf8');
}

function serialize(data) {
  return JSON.stringify(data, null, 2).replace(/[<>&\u2028\u2029]/g, char =>
    '\\u' + char.charCodeAt(0).toString(16).padStart(4, '0'));
}

async function main() {
  if (process.argv.slice(2).join(' ') !== '--refresh') {
    throw new Error('Explicit refresh required: node tools/update_meshcoretel_presets.js --refresh');
  }
  const [catalog, radio, page] = await Promise.all([download(catalogUrl), download(radioUrl), download(sourceUrl)]);
  const match = page.match(/<script\b[^>]*\bsrc="(\/assets\/index-[A-Za-z0-9_-]+\.js)"/);
  if (!match) throw new Error('Site entry script missing; inspect upstream changes');
  const namesUrl = origin + match[1];
  const names = await download(namesUrl);
  const sha = value => crypto.createHash('sha256').update(value, 'utf8').digest('hex');
  const snapshot = buildSnapshot(JSON.parse(catalog), JSON.parse(radio), localizedNames(names), new Date().toISOString(), {
    namesUrl, sourceHashes: { catalog: sha(catalog), radio: sha(radio), names: sha(names) },
  });
  const current = fs.readFileSync(target, 'utf8');
  const marker = /\/\* SMARTUI_PRESETS_DATA_BEGIN \*\/[\s\S]*?\/\* SMARTUI_PRESETS_DATA_END \*\//g;
  if (Array.from(current.matchAll(marker)).length !== 1) throw new Error('Snapshot marker missing or duplicated');
  const next = current.replace(marker, '/* SMARTUI_PRESETS_DATA_BEGIN */\n' + serialize(snapshot) + '\n  /* SMARTUI_PRESETS_DATA_END */');
  fs.writeFileSync(target, next, 'utf8');
  process.stdout.write(`Snapshot ${snapshot.metadata.snapshotAt}: ${snapshot.presets.length} presets from ${snapshot.metadata.selectionCount} source regions; ${snapshot.metadata.excluded.length} excluded.\n`);
}

module.exports = { buildSnapshot, localizedNames, serialize };
if (require.main === module) main().catch(error => { console.error(error.message); process.exitCode = 1; });
