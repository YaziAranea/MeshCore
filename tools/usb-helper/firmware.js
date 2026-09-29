(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SmartUiFirmware = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const MAX_BYTES = 32 * 1024 * 1024;
  const PROFILES = Object.freeze([
    {id:'t096', label:'T096 FEM ON', environment:'Heltec_t096_companion_radio_ble_femon', reported:'Heltec T096', marker:'T096', format:'uf2'},
    {id:'t114', label:'T114', environment:'Heltec_t114_companion_radio_ble', reported:'Heltec T114', marker:'T114', format:'uf2'},
    {id:'promicro', label:'ProMicro RA62', environment:'ProMicro_ra62_companion_radio_ble', reported:'ProMicro DIY', marker:'ProMicro', format:'uf2'},
    {id:'v3', label:'Heltec V3 OLED', environment:'Heltec_v3_companion_radio_ble_smartui', reported:'Heltec V3', marker:'V3', format:'bin'},
    {id:'v43', label:'Heltec V4.3 OLED FEM ON', environment:'heltec_v4_3_companion_radio_ble_femon_smartui', reported:'Heltec V4.3 OLED', marker:'V4.3', format:'bin'},
    {id:'paper', label:'Wireless Paper FULL', environment:'Heltec_Wireless_Paper_companion_radio_ble_smartui_full', reported:'Heltec Wireless Paper', marker:'Paper', format:'bin'}
  ].map(Object.freeze));
  function fail(message) { const error = new Error(message); error.safe = true; throw error; }
  function requireThat(value, message) { if (!value) fail(message); }
  function reportedProfile(info) { return info && PROFILES.find(profile => profile.reported === info.board) || null; }
  const hex = bytes => Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  async function digest(bytes, cryptoProvider) {
    requireThat(cryptoProvider && cryptoProvider.subtle, 'В браузере недоступен локальный SHA-256. Откройте файл в Chrome или Edge.');
    return hex(new Uint8Array(await cryptoProvider.subtle.digest('SHA-256', bytes)));
  }
  function decodeUf2(raw) {
    requireThat(raw.length > 0 && raw.length % 512 === 0, 'Некорректный размер UF2.');
    const count = raw.length / 512;
    requireThat(count * 256 <= 0xd4000 - 0x26000, 'UF2 выходит за границы области приложения.');
    const image = new Uint8Array(count * 256);
    for (let index = 0; index < count; ++index) {
      const block = new DataView(raw.buffer, raw.byteOffset + index * 512, 512);
      requireThat(block.getUint32(0,true) === 0x0a324655 && block.getUint32(4,true) === 0x9e5d5157 && block.getUint32(508,true) === 0x0ab16f30, 'Повреждён заголовок UF2.');
      requireThat(block.getUint32(8,true) === 0x2000 && block.getUint32(28,true) === 0xada52840, 'UF2 не соответствует nRF52840.');
      requireThat(block.getUint32(16,true) === 256 && block.getUint32(20,true) === index && block.getUint32(24,true) === count && block.getUint32(12,true) === 0x26000 + index * 256, 'Неверные адреса, порядок или размеры блоков UF2.');
      image.set(raw.subarray(index * 512 + 32, index * 512 + 288), index * 256);
    }
    return image;
  }
  async function decodeEspApplication(raw, offset, exact, cryptoProvider) {
    requireThat(raw.length >= offset + 24 && raw[offset] === 0xe9 && raw[offset+1] >= 1 && raw[offset+1] <= 16, 'Не найден корректный заголовок приложения ESP32.');
    const image = raw.subarray(offset);
    const view = new DataView(image.buffer, image.byteOffset, image.byteLength);
    let position = 24, checksum = 0xef;
    for (let segment = 0; segment < image[1]; ++segment) {
      requireThat(position + 8 <= image.length, 'Обрезан заголовок сегмента ESP32.');
      const size = view.getUint32(position+4,true); position += 8;
      requireThat(size <= image.length - position, 'Обрезаны данные сегмента ESP32.');
      for (let end = position + size; position < end; ++position) checksum ^= image[position];
    }
    const end = Math.floor((position + 16) / 16) * 16;
    requireThat(end <= image.length && image[end-1] === checksum, 'Не совпала контрольная сумма приложения ESP32.');
    for (let i = position; i < end-1; ++i) requireThat(image[i] === 0, 'Некорректное выравнивание приложения ESP32.');
    requireThat(image[23] === 0 || image[23] === 1, 'Неизвестный формат SHA приложения ESP32.');
    const total = end + (image[23] ? 32 : 0);
    requireThat(total <= image.length && (!exact || total === image.length), 'BIN update содержит лишние данные или обрезан; возможна путаница с merged.');
    if (image[23]) requireThat(await digest(image.subarray(0,end),cryptoProvider) === hex(image.subarray(end,total)), 'Не совпал встроенный SHA-256 приложения ESP32.');
    return image.subarray(0,total);
  }
  async function verify({name, bytes, manifestText, target, info = null, cryptoProvider = globalThis.crypto}) {
    requireThat(bytes instanceof Uint8Array && bytes.length > 0 && bytes.length <= MAX_BYTES, 'Выберите непустой BIN/UF2 не больше 32 МиБ.');
    requireThat(typeof name === 'string' && /^[A-Za-z0-9._+-]+\.(bin|uf2)$/.test(name), 'Имя файла должно точно совпадать с записью манифеста релиза.');
    requireThat(typeof manifestText === 'string' && manifestText.length <= 2 * 1024 * 1024, 'Выберите RELEASE-MANIFEST.json не больше 2 МиБ.');
    let manifest;
    try { manifest = JSON.parse(manifestText); } catch (_) { fail('Манифест не является корректным JSON.'); }
    requireThat(manifest && manifest.schema_version === 2 && typeof manifest.commit === 'string' && /^[a-f0-9]{40}$/.test(manifest.commit) && typeof manifest.version === 'string' && /^[A-Za-z0-9][A-Za-z0-9._+-]{0,31}$/.test(manifest.version) && Array.isArray(manifest.firmware) && manifest.firmware.length <= 32, 'Неизвестный или некорректный формат манифеста SmartUI.');
    const records = manifest.firmware.filter(item => item && item.name === name);
    requireThat(records.length === 1, 'Файл отсутствует в манифесте либо указан несколько раз.');
    const record = records[0];
    const profile = PROFILES.find(item => item.environment === record.environment);
    requireThat(profile && record.board === profile.label && record.source_commit === manifest.commit && Number.isSafeInteger(record.bytes) && record.bytes === bytes.length && typeof record.sha256 === 'string' && /^[a-fA-F0-9]{64}$/.test(record.sha256), 'Плата, исходный commit или размер файла не соответствуют манифесту.');
    const reported = reportedProfile(info);
    const selected = PROFILES.find(item => item.id === target);
    requireThat(reported || selected, 'Плата ноды неизвестна. Укажите точную модель вручную.');
    requireThat((!reported || reported.id === profile.id) && (!selected || selected.id === profile.id), 'Файл предназначен для другой платы.');
    requireThat(name.endsWith('.' + profile.format), 'Формат BIN/UF2 не соответствует плате.');
    const sha256 = await digest(bytes,cryptoProvider);
    requireThat(sha256 === record.sha256.toLowerCase(), 'SHA-256 не совпал с манифестом: файл повреждён или выбран другой релиз.');
    let image, destructive = false, offset = null;
    if (profile.format === 'uf2') {
      requireThat(record.image_kind === 'nrf52840-uf2-bootloader' && record.flash_offset === null, 'Манифест неправильно описывает UF2.');
      image = decodeUf2(bytes);
    } else {
      destructive = record.image_kind === 'esp32-fresh-install-merged';
      requireThat(destructive || record.image_kind === 'esp32-application-update', 'Неизвестный тип BIN.');
      offset = destructive ? '0x00000' : '0x10000';
      requireThat(record.flash_offset === offset && name.endsWith(destructive ? '-merged.bin' : '-update.bin'), 'Тип update/merged, имя и адрес прошивки противоречат друг другу.');
      requireThat(bytes[0] === 0xe9, 'BIN не начинается с образа ESP32.');
      image = await decodeEspApplication(bytes,destructive ? 0x10000 : 0,!destructive,cryptoProvider);
    }
    const text = new TextDecoder('latin1').decode(image);
    const markers = [...text.matchAll(/SmartUI-source:([a-zA-Z0-9+._-]+)\x00/g)].map(match => match[1]);
    requireThat(markers.length > 0 && markers.every(marker => marker === manifest.commit.slice(0,8)), 'Встроенный source marker отсутствует, dirty или не совпадает с commit манифеста.');
    requireThat(text.includes(profile.marker + ' SmartUI ' + manifest.version), 'Встроенная метка платы/версии не совпала с манифестом.');
    return Object.freeze({board:profile.label, version:manifest.version, source:manifest.commit, sha256, bytes:bytes.length, kind:record.image_kind, offset, destructive, matchedConnectedBoard:Boolean(reported), sameBuild:Boolean(info && info.build === manifest.commit.slice(0,8)),
      warning:destructive ? 'MERGED: чистая установка с заменой identity, контактов и настроек, даже без Erase. Не используйте для обычного обновления.' : profile.format === 'bin' ? 'UPDATE: приложение по адресу 0x10000. Нужны уже установленные совместимые bootloader и таблица разделов; их наличие эта проверка не доказывает.' : 'UF2: файл для bootloader именно выбранной платы. Готовность bootloader на устройстве не проверяется.',
      integrityNotice:'SHA-256 проверяет целостность относительно выбранного манифеста, а не подлинность. Манифест не подписан. Прошивка устройства не выполнялась.'});
  }
  return Object.freeze({PROFILES, MAX_BYTES, reportedProfile, verify});
}));
