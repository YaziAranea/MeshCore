(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SmartUiConsole = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // Exact wire strings from examples/companion_radio/ConnectionController.cpp.
  // Never forward arbitrary serial input, exceptions, or credentials to the UI.
  const RX = Object.freeze({
    ssid: 'SSID input is hidden; enter SSID, then Enter:',
    password: "Password input is hidden; enter 8..64 bytes, blank for open WiFi, or 'cancel':",
    testing: 'Testing WiFi without saving...',
    passed: "WiFi test passed. Type 'wifi save' to store it.",
    failed: 'WiFi test failed; credentials were not saved.',
    expired: 'WiFi setup timed out; credentials were not saved.',
    cancelled: 'WiFi setup cancelled.',
    unknown: "Unknown command. Type 'help'.",
    overflow: 'Input too long; discarded.',
    readonly: 'Connection settings are read-only during storage recovery.',
    help: 'Commands: status | mode ble | mode usb | mode wifi | wifi setup | wifi status | wifi save | wifi cancel | wifi forget | help',
    helpInfo: 'Commands: info | status | mode ble | mode usb | mode wifi | wifi setup | wifi status | wifi save | wifi cancel | wifi forget | help',
    helpReplies: 'Commands: info | status | mode ble | mode usb | mode wifi | wifi setup | wifi status | wifi save | wifi cancel | wifi forget | reply get N | reply set N HEX | help',
    helpEnd: 'Credential input is not echoed. WiFi is saved only after a passed test.',
    helpSettings: 'Settings protocol: 1'
  });
  const MESSAGES = Object.freeze({
    BUSY: 'Дождитесь завершения текущей операции.',
    DISCONNECTED: 'USB-соединение закрыто.',
    NOT_CONNECTED: 'Сначала подключите устройство.',
    NOT_VERIFIED: 'Сервисная консоль не подтверждена. Переподключитесь; на устройстве выберите BLE или WiFi.',
    TIMEOUT: 'Устройство не ответило вовремя. Проверьте USB и выбранный режим.',
    SERIAL_ERROR: 'Ошибка USB-соединения. Закройте другие программы, использующие порт, и переподключитесь.',
    OPEN_FAILED: 'Не удалось открыть USB-порт. Закройте другие программы, использующие порт.',
    READ_ONLY: 'Настройки доступны только для чтения: запись заблокирована из-за состояния хранилища. Обновите состояние; если блокировка остаётся, сообщите версию и build прошивки для диагностики. Автоматическое исправление не подтверждено.',
    STORAGE_RECOVERY_REQUIRED: 'Ошибка хранилища подключения (storage=recovery-required). Настройки доступны только для чтения. Обновите состояние; если ошибка остаётся, сообщите версию и build прошивки для диагностики. Автоматическое исправление не подтверждено.',
    WIFI_PENDING: 'Сначала сохраните или отмените проверенные настройки WiFi.',
    INVALID_SSID: 'SSID должен содержать 1–32 байта UTF-8 без управляющих символов.',
    RESERVED_SSID: 'SSID «cancel» зарезервирован прошивкой и не поддерживается мастером.',
    INVALID_PASSWORD: 'Пароль: 8–63 байта UTF-8 или ровно 64 шестнадцатеричных символа; управляющие символы запрещены.',
    OPEN_CONFIRMATION: 'Для пустого пароля явно подтвердите открытую сеть.',
    OPEN_PASSWORD: 'У открытой сети пароль должен быть пустым.',
    INVALID_TEXT: 'Введите SSID и пароль текстом без повреждённых Unicode-символов.',
    WIFI_UNAVAILABLE: 'Настройка WiFi недоступна на устройстве.',
    TEST_FAILED: 'Проверка WiFi не прошла. Новые настройки не сохранены.',
    WIFI_EXPIRED: 'Время настройки WiFi истекло. Новые настройки не сохранены.',
    SAVE_FAILED: 'Устройство не подтвердило сохранение WiFi. Повторите проверку сети.',
    SAVE_UNCERTAIN: 'Подтверждение сохранения WiFi не получено. Оно могло выполниться; проверьте устройство.',
    NO_TEST: 'Сначала успешно проверьте WiFi.',
    MODE_INVALID: 'Допустимые режимы: BLE, WiFi, USB.',
    MODE_FAILED: 'Режим недоступен или устройство не смогло сохранить настройку.',
    MODE_UNCERTAIN: 'Подтверждение смены режима не получено. Проверьте режим на устройстве и переподключитесь.',
    FORGET_FAILED: 'WiFi очищен в памяти, но очистка постоянного хранилища не подтверждена. Проверьте устройство.',
    FORGET_UNCERTAIN: 'Подтверждение удаления WiFi не получено. Проверьте устройство; результат неизвестен.',
    PROTOCOL: 'Ответ не соответствует сервисной консоли SmartUI. Переподключитесь.',
    INPUT_OVERFLOW: 'Устройство отклонило слишком длинный ввод.',
    REPLIES_UNAVAILABLE: 'Свои фразы требуют прошивку с поддержкой этой функции.',
    INVALID_REPLY: 'Фраза: не более 64 байт UTF-8, без управляющих символов. Пустое поле возвращает стандартную фразу.',
    REPLY_FAILED: 'Фраза не сохранена. Проверьте состояние хранилища.',
    REPLY_UNCERTAIN: 'Результат сохранения фразы неизвестен. Переподключитесь и прочитайте фразы с ноды.',
    SETTINGS_UNAVAILABLE: 'Прошивка не сообщает поддержку настроек устройства. Другие инструменты доступны.',
    SETTINGS_INVALID: 'Недопустимое значение настройки.',
    SETTINGS_UNSUPPORTED: 'Эта функция не поддерживается оборудованием или сборкой.',
    SETTINGS_STORAGE: 'Нода отклонила сохранение: ошибка хранилища. Изменение не подтверждено.',
    SETTINGS_STALE: 'Предварительный расчёт устарел. Измерьте напряжение и повторите расчёт.',
    SETTINGS_MEASUREMENT: 'Нода не получила пригодное измерение аккумулятора. Проверьте питание и повторите.',
    SETTINGS_SOURCE: 'Запустите ProMicro от АКБ, дождитесь измерения, подключите USB без перезапуска и повторите расчёт в течение 2 минут. При USB питание искажает замер.',
    SETTINGS_RANGE: 'Значение вне допустимого диапазона. Проверьте измерение и параметры платы.',
    SETTINGS_UNCERTAIN: 'Результат изменения неизвестен. Переподключитесь и прочитайте настройки: не считайте их сохранёнными.',
    SETTINGS_READBACK: 'Не удалось прочитать настройки. Текущие значения не подтверждены.',
    SETTINGS_PIN: 'Этот вывод занят другой функцией или не разрешён для выбранного выхода. Прочитайте настройки заново и выберите свободный вывод.',
    SOUND_MUTED: 'Общая тишина включена. Выключите её и сохраните перед прослушиванием.',
    RADIO_FAILED: 'Радио отклонило параметры. Изменение не подтверждено; прочитайте состояние ноды.',
    RADIO_RESTORE: 'Не удалось восстановить прежнее состояние радио. Перезапустите ноду и проверьте параметры.',
    RADIO_REPEAT: 'Включённая ретрансляция несовместима с выбранной частотой. Помощник не выключает её автоматически; измените настройку на ноде.',
    ADC_INPUT: 'Введите измеренное мультиметром напряжение от 2,500 до 4,500 В, например 3,82.',
    ADC_CONFIRM: 'Сначала выполните расчёт, затем явно подтвердите сохранение.',
    ADC_SERVICE_CONFIRM: 'Временное окно калибровки включается только после отдельного подтверждения.',
    ADC_MANUAL_INPUT: 'Введите известный коэффициент: положительное число с точкой или запятой, не более 6 знаков после неё.',
    ADC_MANUAL_UNAVAILABLE: 'Эта прошивка не поддерживает прямой ввод ADC. Обновите прошивку до SmartUI 0.15; расчёт по мультиметру остаётся доступен.',
    ADC_USB_REQUIRED: 'Нода не подтвердила питание USB и локальное USB-подключение. Сервисное окно не включено.'
  });
  const DEFAULT_TIMEOUTS = Object.freeze({ command: 6000, test: 25000, usb: 2000, close: 1500, candidate: 120000, adcPreview: 60000 });
  const encoder = new TextEncoder();

  class ConsoleError extends Error {
    constructor(code) {
      super(MESSAGES[code] || MESSAGES.SERIAL_ERROR);
      this.name = 'ConsoleError';
      this.code = MESSAGES[code] ? code : 'SERIAL_ERROR';
      this.safe = true;
    }
  }
  const failure = code => new ConsoleError(code);
  const safeError = error => error instanceof ConsoleError ? error : failure('SERIAL_ERROR');
  const success = value => ({ value });
  const rejected = code => ({ error: failure(code) });
  const controls = /[\u0000-\u001f\u007f-\u009f\u2028\u2029]/u;
  function validUnicode(text) {
    for (let i = 0; i < text.length; i++) {
      const ch = text.charCodeAt(i);
      if (ch >= 0xd800 && ch <= 0xdbff) {
        const next = text.charCodeAt(++i);
        if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
      } else if (ch >= 0xdc00 && ch <= 0xdfff) return false;
    }
    return true;
  }
  function validateCredentials(ssid, password, options = {}) {
    if (typeof ssid !== 'string' || typeof password !== 'string' || !validUnicode(ssid) || !validUnicode(password)) throw failure('INVALID_TEXT');
    const ssidBytes = encoder.encode(ssid).length;
    const passwordBytes = encoder.encode(password).length;
    if (!ssidBytes || ssidBytes > 32 || controls.test(ssid)) throw failure('INVALID_SSID');
    if (ssid === 'cancel' && options.allowReservedSsid !== true) throw failure('RESERVED_SSID');
    if (options.openNetwork === true && password !== '') throw failure('OPEN_PASSWORD');
    if (password === '' && options.openNetwork !== true) throw failure('OPEN_CONFIRMATION');
    if (controls.test(password) || (password !== '' && !((passwordBytes >= 8 && passwordBytes <= 63) || /^[0-9a-fA-F]{64}$/.test(password)))) throw failure('INVALID_PASSWORD');
    return { ssidBytes, passwordBytes, openNetwork: password === '' };
  }
  function parseStatus(line) {
    if (typeof line !== 'string') return null;
    const match = /^Mode=(BLE|WiFi|USB) companion=(connected|idle) via=(BLE|WiFi|USB|none) USB-service=(on|off) WiFi-config=(yes|no) link=(associated|down) IP=(none|\d{1,3}(?:\.\d{1,3}){3}) approval=(pending|none)(?: storage=(ok|recovery-required))?$/.exec(line);
    if (!match || (match[7] !== 'none' && match[7].split('.').some(part => Number(part) > 255))) return null;
    return {
      mode: match[1].toLowerCase(), companion: match[2], via: match[3].toLowerCase(),
      usbService: match[4] === 'on', wifiConfigured: match[5] === 'yes', link: match[6],
      ip: match[7] === 'none' ? null : match[7], approval: match[8], readOnly: match[9] === 'recovery-required',
      recoveryRequired: match[9] === 'recovery-required'
    };
  }

  function encodeReply(text) {
    if (typeof text !== 'string' || !validUnicode(text) || controls.test(text) || encoder.encode(text).length > 64) throw failure('INVALID_REPLY');
    return text === '' ? '-' : Array.from(encoder.encode(text), value => value.toString(16).padStart(2, '0')).join('');
  }
  function decodeReply(line, slot) {
    const match = /^Reply=([1-9]) hex=(-|(?:[0-9a-f]{2}){1,64})$/.exec(line);
    if (!match || Number(match[1]) !== slot + 1) return null;
    try {
      const text = match[2] === '-' ? '' : new TextDecoder('utf-8', {fatal:true}).decode(Uint8Array.from(match[2].match(/../g), value => parseInt(value, 16)));
      encodeReply(text);
      return { text };
    } catch (_) { return null; }
  }
  function parseInfo(line) {
    // Accept only the advertised, bounded ASCII record, never arbitrary serial
    // text. Board names may contain spaces but no markup/control characters.
    if (typeof line !== 'string' || line.length > 383) return null;
    const match = /^SmartUI=([A-Za-z0-9][A-Za-z0-9._+-]{0,31}) core=([A-Za-z0-9][A-Za-z0-9._+-]{0,31}) build=([A-Za-z0-9][A-Za-z0-9._+-]{0,39}) upstream=([A-Za-z0-9][A-Za-z0-9._+-]{0,39}) capabilities=(BLE(?:,USB)?(?:,WiFi)?|USB(?:,WiFi)?|WiFi) board=([A-Za-z0-9][A-Za-z0-9 ._()+:/-]{0,95})$/.exec(line);
    if (!match || match[6].trim() !== match[6]) return null;
    return { firmware: match[1], core: match[2], build: match[3], upstream: match[4], capabilities: match[5].split(','), board: match[6] };
  }

  const SETTING_CAPS = Object.freeze({sound_quiet:'sound',volume:'sound',melody:'sound',board_led:'board_led',unread_led:'unread_led',vibration:'vibration',gps:'gps',battery_protection:'battery_protection',muted:null});
  // Firmware owns availability, bounds and safe pins. Labels are presentation only.
  const EXTENDED_FIELDS = Object.freeze([
    ['notify_mode','sound','Каналы обычных уведомлений'],['important_notify_mode','sound','Каналы важных уведомлений'],
    ['tone_pin','sound','Вывод звука'],['melody_dm','sound','Мелодия личных сообщений'],['melody_mention','sound','Мелодия упоминаний'],['melody_system','sound','Мелодия системы'],
    ['tone_8bit','sound','Стиль звука 8-bit'],['high_drive','sound','Усиленный выход звука'],['resonance_hz','sound','Резонанс пьезоизлучателя, Гц'],['bridge','sound','Мостовой звук · два вывода'],
    ['led_pin','lights','Вывод LED уведомлений'],['vibe_pin','lights','Вывод вибромотора'],['offline_dm_led','lights','LED личных сообщений без приложения'],['ble_dm_led','lights','LED личных сообщений с приложением'],
    ['msg_popup','display','Всплывающий экран сообщения'],['ui_font','display','Шрифт'],['ui_theme','display','Оформление'],['ui_top_color','display','Верхний цвет'],['ui_bottom_color','display','Нижний цвет'],['backlight_timeout','display','Тайм-аут экрана'],
    ['gps_source','gps','Источник координат'],['gps_interval','gps','Интервал GPS, секунд'],['advert_location','gps','Координаты в анонсе'],
    ['profile','system','Профиль устройства'],['agc_reset','system','AGC-сброс · каждые 60 с'],['fem_lna','system','FEM · усилитель приёма'],['fem_pa','system','FEM · усилитель передачи']
  ].map(([key,group,label])=>Object.freeze({key,group,label})));
  const SETTING_KEYS=Object.freeze([...new Set([...Object.keys(SETTING_CAPS),...EXTENDED_FIELDS.map(f=>f.key)])]);
  const SOUND_SETTING_KEYS=Object.freeze(['muted','sound_quiet','volume','melody','board_led','unread_led','vibration',...EXTENDED_FIELDS.filter(f=>['sound','lights'].includes(f.group)).map(f=>f.key)]);
  const ADVANCED_SETTING_KEYS=Object.freeze(['notify_mode','important_notify_mode','melody_dm','melody_mention','melody_system','tone_8bit','high_drive','resonance_hz','offline_dm_led','ble_dm_led','msg_popup','ui_top_color','ui_bottom_color','gps_source','gps_interval','advert_location']);
  function parseSettingSchema(line,key,transport='settings') {
    if(!['settings','ui'].includes(transport)||!SETTING_KEYS.includes(key)||typeof line!=='string'||line.length>156)return null;
    const prefix='OK '+transport+' schema key='+key+' ';
    if(!line.startsWith(prefix))return null;
    const m=/^supported=([01]) min=(-?\d+) max=(-?\d+) step=(\d+) options=(-|(?:-?\d+)(?:,-?\d+)*)$/.exec(line.slice(prefix.length));
    if(!m)return null;
    const [supported,min,max,step]=m.slice(1,5).map(Number),options=m[5]==='-'?null:m[5].split(',').map(Number);
    if(![min,max,step].every(Number.isSafeInteger)||min < -1||max>1000000||max<min||step<1||options&&(options.length>64||new Set(options).size!==options.length||options.some(v=>v<min||v>max)))return null;
    return {key,supported:Boolean(supported),min,max,step,options};
  }
  function settingValueValid(schema,value){return Boolean(schema?.supported&&Number.isInteger(value)&&value>=schema.min&&value<=schema.max&&(schema.options?schema.options.includes(value):(value-schema.min)%schema.step===0));}
  function settingOptions(field,schema,melodies=[]){
    const values=schema.options||((schema.max-schema.min)/schema.step<=255?Array.from({length:Math.floor((schema.max-schema.min)/schema.step)+1},(_,i)=>schema.min+i*schema.step):null);
    if(!values)return null;
    const choices={backlight_timeout:['15 секунд','30 секунд','60 секунд'],gps_source:['GPS-модуль ноды','Координаты телефона'],profile:['Свой','Тихий','На улице','Ночной'],ui_top_color:['Белый','Зелёный','Жёлтый','Синий','Оранжевый','Красный'],ui_bottom_color:['Белый','Зелёный','Жёлтый','Синий','Оранжевый','Красный']};
    return values.map(value=>[value,field.key==='sound_quiet'?(value?'Выключен':'Включён'):field.key.endsWith('_pin')?(value===-1?'Отключён':'Вывод '+value):field.key.startsWith('melody')?(value+' · '+(melodies[value]||'Мелодия '+value)):
      field.key.endsWith('notify_mode')?(value===0?'Без уведомлений':[value&1?'LED':null,value&2?'Звук':null,value&4?'Вибро':null].filter(Boolean).join(' + ')):
      choices[field.key]?.[value]||(schema.min===0&&schema.max===1?(value?'Включено':'Выключено'):String(value))]);
  }
  function notificationStatus(settings,caps){
    if(!settings||!caps)return 'Сначала прочитайте настройки ноды.';
    if(Number(settings.muted)===1)return 'Общая тишина включена. Тест уведомления не подаст звук, свет или вибрацию. Индикаторы состояния и зарядки — отдельные.';
    if(!Number(caps.sound))return 'Звук недоступен в этой сборке. Тест проверяет только доступные каналы уведомлений.';
    if(Number(settings.sound_quiet)===1)return 'Звук выключен на ноде. Для мелодии включите «Звук уведомлений ЛС» и сохраните. Тест не включает отключённые каналы.';
    return 'Звук включён на ноде · громкость '+settings.volume+' / 10'+(settings.tone_pin===undefined?'':' · вывод '+settings.tone_pin)+'. Тест использует сохранённые настройки; ответ команды не подтверждает работу излучателя.';
  }
  function soundOutputStatus(settings,schemas={},caps={}){
    const hasValue=key=>settings?.[key]!==undefined&&settings[key]!==null;
    const bridgeSupported=schemas?.bridge?schemas.bridge.supported:caps?.bridge===undefined?null:Number(caps.bridge)===1;
    const bridge=!settings?'не прочитан':bridgeSupported===false?'недоступен в этой сборке':bridgeSupported===true&&hasValue('bridge')&&[0,1,'0','1'].includes(settings.bridge)?(Number(settings.bridge)?'включён':'выключен'):'не прочитан';
    return 'Мост: '+bridge+' · Вывод звука: '+(hasValue('tone_pin')?settings.tone_pin:'не прочитан')+' · Громкость: '+(hasValue('volume')?settings.volume+' / 10':'не прочитана');
  }
  function parseSettingValue(line,key,transport='settings'){
    const prefix='OK '+transport+' get key='+key+' value=';
    if(typeof line!=='string'||!line.startsWith(prefix))return null;
    const value=line.slice(prefix.length);return /^-?\d+(?:\.\d{1,6})?$/.test(value)&&Number.isFinite(Number(value))?Number(value):null;
  }
  function parseCoreSetting(line,kind,transport='settings'){
    if(!['settings','ui'].includes(transport)||typeof line!=='string'||line.length>156)return null;
    if(kind==='tx'){
      const m=new RegExp('^OK '+transport+' tx value=(-?\\d+) min=(-?\\d+) max=(-?\\d+)$').exec(line);if(!m)return null;
      const [value,min,max]=m.slice(1).map(Number);return min>=-30&&max<=50&&min<=value&&value<=max?{value,min,max}:null;
    }
    if(kind==='identity'){
      const m=new RegExp('^OK '+transport+' identity name_hex=([a-fA-F0-9]+|-) max_name_bytes=(\\d+)$').exec(line);if(!m||Number(m[2])!==31||m[1].length>62||m[1]!=='-'&&m[1].length%2)return null;
      try{const name=m[1]==='-'?'':new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(m[1].match(/../g),b=>parseInt(b,16)));if(/[\x00-\x1f\x7f]/.test(name))return null;return {name,max_name_bytes:31};}catch(_){return null;}
    }
    return null;
  }
  function record(line, prefix, keys) {
    if (typeof line !== 'string' || line.length > 479 || !line.startsWith(prefix + ' ') || /[^\x20-\x7e]/.test(line)) return null;
    const result = Object.create(null), parts = line.slice(prefix.length + 1).split(' ');
    if (parts.length !== keys.length) return null;
    for (const part of parts) {
      const match = /^([a-z_]+)=([0-9]+(?:\.[0-9]{1,6})?)$/.exec(part);
      if (!match || !keys.includes(match[1]) || Object.hasOwn(result, match[1])) return null;
      result[match[1]] = Number(match[2]);
      if (!Number.isFinite(result[match[1]])) return null;
    }
    return result;
  }
  const integer = (value, min, max) => Number.isInteger(value) && value >= min && value <= max;
  const ADVERT_INTERVALS = Object.freeze([0,15,30,60,120,180]);
  function parseNetworkSetting(line, kind, transport='settings') {
    if (!['radio','advert'].includes(kind) || !['settings','ui'].includes(transport)) return null;
    if (kind === 'advert') {
      const r=record(line,'OK '+transport+' advert',['interval_min']);
      return r && ADVERT_INTERVALS.includes(r.interval_min) ? {...r} : null;
    }
    // TX can be negative on supported radios. Keep exact keys and bounded ASCII.
    if (typeof line!=='string' || line.length>156 || /[^\x20-\x7e]/.test(line)) return null;
    const prefix='OK '+transport+' radio ',keys=['freq_khz','bw_hz','sf','cr','path_bytes','tx_dbm','repeat'];
    if (!line.startsWith(prefix)) return null;
    const parts=line.slice(prefix.length).split(' '),r=Object.create(null);
    if(parts.length!==keys.length)return null;
    for(const part of parts){const m=/^([a-z_]+)=(-?\d+)$/.exec(part);if(!m||!keys.includes(m[1])||Object.hasOwn(r,m[1]))return null;r[m[1]]=Number(m[2]);}
    if(!integer(r.freq_khz,150000,2500000)||!integer(r.bw_hz,7000,500000)||!integer(r.sf,5,12)||!integer(r.cr,5,8)||!integer(r.path_bytes,1,3)||!integer(r.tx_dbm,-30,50)||!integer(r.repeat,0,1))return null;
    return {...r};
  }
  function networkValuesValid(kind, values) {
    if(kind==='advert')return values && ADVERT_INTERVALS.includes(values.interval_min);
    return kind==='radio' && values && parseNetworkSetting('OK settings radio '+['freq_khz','bw_hz','sf','cr','path_bytes'].map(k=>k+'='+values[k]).join(' ')+' tx_dbm=0 repeat=0','radio')!==null;
  }
  function parseSettingsCaps(line) {
    const flags = ['adc','sound','board_led','unread_led','vibration','gps','battery_protection','display'];
    const keys = ['v',...flags,'melody_max','adc_min','adc_max'];
    const r = record(line, 'OK settings caps', keys) || record(line, 'OK settings caps', [...keys,'adc_service']);
    if (!r || r.v !== 1 || flags.some(k => !integer(r[k],0,1)) || !integer(r.melody_max,0,255) || r.adc_min < 0 || r.adc_max > 1000 || r.adc_min > r.adc_max || (r.adc && r.adc_min <= 0)) return null;
    if (r.adc_service !== undefined && !integer(r.adc_service,0,1)) return null;
    return {...r};
  }
  function parseAdcService(line, transport='settings') {
    if (!['settings','ui'].includes(transport)) return null;
    const r = record(line, 'OK '+transport+' adc_service', ['supported','active','remaining_ms','external']);
    if (!r || ['supported','active','external'].some(k=>!integer(r[k],0,1)) || !integer(r.remaining_ms,0,120000)) return null;
    if (r.active ? (!r.supported || !r.external || r.remaining_ms===0) : r.remaining_ms!==0) return null;
    return {...r};
  }
  function parseAdcManual(line, transport='settings') {
    if (!['settings','ui'].includes(transport)) return null;
    const r=record(line,'OK '+transport+' adc_manual',['supported']);
    return r&&integer(r.supported,0,1)?{...r}:null;
  }
  function adcMultiplier(text,caps) {
    if(typeof text!=='string'||!/^\d+(?:[.,]\d{1,6})?$/.test(text.trim()))throw failure('ADC_MANUAL_INPUT');
    const value=Number(text.trim().replace(',','.'));
    if(!Number.isFinite(value)||value<=0)throw failure('ADC_MANUAL_INPUT');
    if(!caps||value<Number(caps.adc_min)||value>Number(caps.adc_max))throw failure('SETTINGS_RANGE');
    return value.toFixed(6);
  }
  function parseDeviceSettings(line, caps) {
    const r = record(line, 'OK settings get', ['battery_mv','adc_multiplier','adc_default','sound_quiet','volume','melody','board_led','unread_led','vibration','gps','battery_protection','shutdown_mv','muted']);
    if (!r || !caps || !integer(r.battery_mv,0,65535) || !integer(r.volume,1,10) || !integer(r.melody,0,255)) return null;
    for (const key of ['sound_quiet','board_led','unread_led','vibration','gps','battery_protection','muted']) if (!integer(r[key],0,1)) return null;
    if (r.adc_multiplier < 0 || r.adc_default < 0 || r.adc_multiplier > 1000 || r.adc_default > 1000) return null;
    if (caps.adc && (r.adc_default <= 0 || r.adc_multiplier < caps.adc_min - 0.000002 || r.adc_multiplier > caps.adc_max + 0.000002)) return null;
    if (caps.sound && r.melody > caps.melody_max) return null;
    if (r.shutdown_mv !== (caps.battery_protection ? r.battery_protection ? 3200 : 2700 : 0)) return null;
    return {...r};
  }
  function parseAdcPreview(line, caps, measured) {
    const r = record(line, 'OK settings adc_preview', ['token','sampled_mv','measured_mv','multiplier']);
    if (!r || !caps?.adc || !integer(r.token,1,0xffffffff) || !integer(r.sampled_mv,1,65535) || !integer(r.measured_mv,2500,4500) || r.measured_mv !== measured || r.multiplier < caps.adc_min - 0.000002 || r.multiplier > caps.adc_max + 0.000002) return null;
    return {...r};
  }
  function measuredMilliVolts(text) {
    if (typeof text !== 'string' || !/^[2-4](?:[.,][0-9]{1,3})?$/.test(text.trim())) throw failure('ADC_INPUT');
    const value = Math.round(Number(text.trim().replace(',','.')) * 1000);
    if (!integer(value,2500,4500)) throw failure('ADC_INPUT');
    return value;
  }
  function settingsError(line) {
    if (line === RX.readonly || line === 'ERR settings readonly') return 'READ_ONLY';
    const errors = {invalid:'SETTINGS_INVALID',unsupported:'SETTINGS_UNSUPPORTED',storage:'SETTINGS_STORAGE',stale:'SETTINGS_STALE',measurement:'SETTINGS_MEASUREMENT',source:'SETTINGS_SOURCE',range:'SETTINGS_RANGE',pin_conflict:'SETTINGS_PIN',muted:'SOUND_MUTED',buffer:'PROTOCOL',internal:'PROTOCOL',busy:'BUSY',unavailable:'SETTINGS_UNAVAILABLE',radio:'RADIO_FAILED',restore:'RADIO_RESTORE',repeat:'RADIO_REPEAT'};
    const match = /^ERR settings ([a-z_]+)$/.exec(line);
    if (match) return match[1] === 'usb_required' ? 'ADC_USB_REQUIRED' : errors[match[1]] || 'PROTOCOL';
    if (line.startsWith('ERR settings') || line === RX.unknown) return 'PROTOCOL';
    return null;
  }

  class ConsoleClient {
    constructor({ onState, onStatus, onEvent, timeouts = {} } = {}) {
      this._callbacks = { onState, onStatus, onEvent };
      this._timeouts = { ...DEFAULT_TIMEOUTS };
      // Optional shorter deadlines make fake-stream tests independent of hardware.
      for (const key of Object.keys(DEFAULT_TIMEOUTS)) {
        if (Number.isFinite(timeouts[key]) && timeouts[key] > 0) this._timeouts[key] = timeouts[key];
      }
      this._state = { connected: false, busy: false, verified: false, testPassed: false, status: null, info: null, quickRepliesSupported: false, replies: Array(9).fill(null), settingsSupported:false, settingsCaps:null,settingSchemas:null, deviceSettings:null, adcPreview:null, adcService:null,adcManualSupported:false,soundPreviewSupported:false };
      this._session = null;
      this._operation = null;
      this._closing = null;
      this._setupActive = false;
      this._candidateTimer = null;
      this._adcTimer = null;
      this._pendingPorts = new WeakSet();
    }
    get state() {
      return { ...this._state, status: this._state.status ? { ...this._state.status } : null,
        replies: [...this._state.replies],
        settingsCaps: this._state.settingsCaps ? {...this._state.settingsCaps} : null,
        settingSchemas:this._state.settingSchemas?Object.fromEntries(Object.entries(this._state.settingSchemas).map(([key,s])=>[key,{...s,options:s.options?[...s.options]:null}])):null,
        deviceSettings: this._state.deviceSettings ? {...this._state.deviceSettings} : null,
        adcPreview: this._state.adcPreview ? {...this._state.adcPreview} : null,
        adcService: this._state.adcService ? {...this._state.adcService} : null,
        info: this._state.info ? { ...this._state.info, capabilities: [...this._state.info.capabilities] } : null };
    }
    _call(name, value) {
      try { if (typeof this._callbacks[name] === 'function') this._callbacks[name](value); } catch (_) { /* UI exceptions must not interrupt serial cleanup. */ }
    }
    _stateChanged(patch = {}) {
      Object.assign(this._state, patch, { busy: Boolean(this._operation || this._closing) });
      this._call('onState', this.state);
    }
    _event(kind, text) { this._call('onEvent', { kind, text }); }
    _setStatus(status) {
      this._state.status = status ? { ...status } : null;
      this._call('onStatus', status ? { ...status } : null);
      this._stateChanged();
    }
    _clearCandidate() {
      clearTimeout(this._candidateTimer);
      this._candidateTimer = null;
      this._setupActive = false;
      this._state.testPassed = false;
    }
    _current(session) { return this._session === session && !session.stopping; }
    _assertCurrent(session) { if (!this._current(session)) throw failure('DISCONNECTED'); }
    _rejectWaiter(session, error) {
      if (session.waiter) session.waiter.finish({ error });
    }
    async _operate(action, { allowSetup = false, connect = false, mutate = false, wifi = false, recovery = false } = {}) {
      if (this._operation || this._closing) throw failure('BUSY');
      if (!connect) {
        if (!this._state.connected || !this._session) throw failure('NOT_CONNECTED');
        if (!this._state.verified) throw failure('NOT_VERIFIED');
        if (this._setupActive && !allowSetup) throw failure('WIFI_PENDING');
        const localRecovery = recovery && this._state.status && this._state.status.recoveryRequired;
        if (mutate && this._state.status && this._state.status.readOnly && !localRecovery) throw failure('READ_ONLY');
        if (wifi && this._state.info && !this._state.info.capabilities.includes('WiFi') && !localRecovery) throw failure('WIFI_UNAVAILABLE');
      } else if (this._session) throw failure('BUSY');
      const token = {};
      this._operation = token;
      this._stateChanged();
      try { return await action(this._session); }
      catch (error) {
        const safe = safeError(error);
        if (safe.code !== 'DISCONNECTED') this._event('error', safe.message);
        throw safe;
      } finally {
        if (this._operation === token) this._operation = null;
        this._stateChanged();
      }
    }
    async connect(port) {
      return this._operate(async () => {
        if (!port || typeof port.open !== 'function') throw failure('OPEN_FAILED');
        if (this._pendingPorts.has(port)) throw failure('BUSY');
        const session = { port, reader: null, writer: null, openTask: null, opened: false, rejectOpen: null, abortController: new AbortController(), readTask: null, stopping: false, waiter: null, buffer: '', overflow: false, rxEpoch: 0, lineEpoch: 0, readOnly: false };
        this._session = session;
        try {
          this._pendingPorts.add(port);
          session.openTask = Promise.resolve().then(() => port.open({ baudRate: 115200, dataBits: 8, stopBits: 1, parity: 'none', flowControl: 'none' })).then(async () => {
            session.opened = true;
            // An OS open may finish after timeout/disconnect. Close that handle
            // without touching newer UI/session state; never reuse a pending port.
            if (session.stopping) {
              try { await this._bounded(port.close()); } catch (_) {}
              throw failure('DISCONNECTED');
            }
          }, () => { throw failure('OPEN_FAILED'); }).finally(() => this._pendingPorts.delete(port));
          let openTimer;
          try {
            await Promise.race([
              session.openTask,
              new Promise((_, reject) => { session.rejectOpen = reject; }),
              new Promise((_, reject) => { openTimer = setTimeout(() => reject(failure('TIMEOUT')), this._timeouts.command); })
            ]);
          } finally { clearTimeout(openTimer); session.rejectOpen = null; }
          this._assertCurrent(session);
          if (!port.readable || !port.writable) throw failure('OPEN_FAILED');
          // Do not pulse DTR/RTS: some USB-UART boards reset on those edges.
          // Native Web Serial's open defaults are sufficient for this console.
          session.reader = port.readable.getReader();
          session.writer = port.writable.getWriter();
          this._stateChanged({ connected: true, verified: false, testPassed: false, status: null, info: null, quickRepliesSupported: false, replies: Array(9).fill(null), settingsSupported:false,settingsCaps:null,settingSchemas:null,deviceSettings:null,adcPreview:null,adcService:null,adcManualSupported:false,soundPreviewSupported:false });
          session.readTask = this._readLoop(session);
          await this._resync(session);
          let helpSeen = false;
          let infoSupported = false;
          // New firmware permits help/current-value reads during recovery;
          // legacy read-only replies are still accepted without probing settings.
          await this._exchange(session, 'help', line => {
            if (line === RX.help) helpSeen = true;
            if (line === RX.helpInfo) { helpSeen = true; infoSupported = true; }
            if (line === RX.helpReplies) { helpSeen = true; infoSupported = true; this._stateChanged({quickRepliesSupported:true}); }
            if (line === RX.helpSettings) this._stateChanged({settingsSupported:true});
            if (line === RX.helpEnd && helpSeen) return success(true);
            if (line === RX.readonly) { session.readOnly = true; return success(false); }
          });
          const status = await this._readStatus(session);
          if (!status.usbService || (status.mode === 'usb' && !status.recoveryRequired)) throw failure('PROTOCOL');
          // Never probe an unknown command on the legacy 0.05 console. The
          // exact new help response is required before requesting identity.
          if (infoSupported) {
            const info = await this._exchange(session, 'info', line => {
              const parsed = parseInfo(line);
              if (parsed) return success(parsed);
              if (line.startsWith('SmartUI=') || line === RX.unknown) return rejected('PROTOCOL');
            });
            this._stateChanged({ info });
          }
          if (this._state.settingsSupported) await this._loadDeviceSettings(session);
          this._assertCurrent(session);
          this._stateChanged({ verified: true });
          const currentStatus = this._state.status;
          if (currentStatus?.readOnly) {
            this._event('warning', currentStatus.recoveryRequired ? MESSAGES.STORAGE_RECOVERY_REQUIRED : MESSAGES.READ_ONLY);
          } else {
            this._event('success', 'Сервисная консоль SmartUI подключена.');
          }
          return this.state;
        } catch (error) {
          if (this._session === session) await this._shutdown(session, false);
          throw error;
        }
      }, { connect: true });
    }
    async _resync(session) {
      // Clear any partial credential/command without submitting it. The firmware
      // retains partial input across browser disconnects (up to 160 bytes).
      // Backspace cannot clear its overflow flag: one discarded line is followed
      // by a second cancellation. Neither step can save credentials.
      const cancel = '\b'.repeat(160) + 'cancel';
      const result = await this._exchange(session, cancel, line => {
        if (line === RX.cancelled || line === RX.unknown) return success('idle');
        if (line === RX.overflow) return success('overflow');
        if (line === RX.readonly) { session.readOnly = true; return success('idle'); }
      });
      if (result === 'overflow') await this._exchange(session, cancel, line => {
        if (line === RX.cancelled || line === RX.unknown) return success(true);
        if (line === RX.readonly) { session.readOnly = true; return success(true); }
      });
      // A bare cancel is unknown during TESTING/TEST_OK, but establishes that we
      // are no longer at a credential prompt. Only now is this command safe.
      await this._exchange(session, 'wifi cancel', line => {
        if (line === RX.cancelled) return success(true);
        if (line === RX.readonly) { session.readOnly = true; return success(true); }
      });
      this._clearCandidate();
      this._stateChanged();
    }
    async disconnect() {
      if (this._closing) return this._closing;
      if (!this._session) return;
      if (this._state.adcService?.active && this._state.verified && !this._operation && !this._setupActive) {
        try { await this.stopAdcService(); } catch (_) { /* Close USB even if acknowledgement is lost. Firmware enforces timeout and USB loss. */ }
      }
      if (this._session) await this._shutdown(this._session, true);
    }
    async _bounded(promise) {
      let timer;
      try { await Promise.race([Promise.resolve(promise).catch(() => {}), new Promise(resolve => { timer = setTimeout(resolve, this._timeouts.close); })]); }
      finally { clearTimeout(timer); }
    }
    async _shutdown(session, announce) {
      if (session.stopping) return this._closing;
      session.stopping = true;
      session.abortController.abort();
      if (session.rejectOpen) session.rejectOpen(failure('DISCONNECTED'));
      this._rejectWaiter(session, failure('DISCONNECTED'));
      if (this._session === session) this._session = null;
      this._clearCandidate();
      clearTimeout(this._adcTimer); this._adcTimer = null;
      this._stateChanged({ connected: false, verified: false, status: null, info: null, quickRepliesSupported: false, replies: Array(9).fill(null), settingsSupported:false,settingsCaps:null,settingSchemas:null,deviceSettings:null,adcPreview:null,adcService:null,adcManualSupported:false,soundPreviewSupported:false });
      this._call('onStatus', null);
      const closing = (async () => {
        if (session.openTask) await this._bounded(session.openTask);
        if (session.reader) {
          try { await this._bounded(session.reader.cancel()); } catch (_) {}
          if (session.readTask) await this._bounded(session.readTask);
          try { session.reader.releaseLock(); } catch (_) {}
        }
        if (session.writer) { try { session.writer.releaseLock(); } catch (_) {} }
        if (session.opened) { try { await this._bounded(session.port.close()); } catch (_) {} }
        session.buffer = '';
      })();
      this._closing = closing;
      this._stateChanged();
      try { await closing; }
      finally {
        if (this._closing === closing) this._closing = null;
        this._stateChanged();
        if (announce) this._event('info', 'USB-соединение закрыто. Несохранённые настройки останутся временными до отмены или тайм-аута устройства.');
      }
    }
    async _readLoop(session) {
      const decoder = new TextDecoder('utf-8', { fatal: false });
      let unexpectedEnd = false;
      try {
        while (this._current(session)) {
          const result = await session.reader.read();
          if (result.done) { unexpectedEnd = true; break; }
          this._assertCurrent(session);
          if (!(result.value instanceof Uint8Array)) continue;
          // Process bounded chunks and discard oversized/invalid lines. No raw
          // input is logged or used as HTML, an error message, or a status field.
          for (let offset = 0; offset < result.value.length; offset += 256) {
            const text = decoder.decode(result.value.subarray(offset, offset + 256), { stream: true });
            for (const char of text) {
              if (char === '\r' || char === '\n') {
                if (session.buffer && !session.overflow) this._line(session, session.buffer, session.lineEpoch);
                session.buffer = '';
                session.overflow = false;
              } else {
                if (!session.buffer && !session.overflow) session.lineEpoch = session.rxEpoch;
                if (session.buffer.length < 511 && !session.overflow) session.buffer += char;
                else { session.buffer = ''; session.overflow = true; }
              }
            }
          }
        }
      } catch (_) { unexpectedEnd = true; }
      finally { try { session.reader.releaseLock(); } catch (_) {} }
      if (unexpectedEnd && this._current(session)) {
        this._event('warning', 'USB-соединение прервано. Сохранение настроек не подтверждается разрывом связи.');
        // Do not await shutdown here: shutdown itself waits for the read loop.
        void this._shutdown(session, false);
      }
    }
    _line(session, line, epoch) {
      if (!this._current(session) || /[^\x20-\x7e]/.test(line)) return;
      if (line === RX.expired) {
        const relevant = this._setupActive || this._state.testPassed;
        this._clearCandidate();
        this._stateChanged();
        if (relevant) this._event('warning', MESSAGES.WIFI_EXPIRED);
        if (session.waiter && session.waiter.wizard) this._rejectWaiter(session, failure('WIFI_EXPIRED'));
        return;
      }
      const waiter = session.waiter;
      if (!waiter || epoch !== waiter.epoch) return;
      if (line === RX.readonly) {
        session.readOnly = true;
        if (this._state.status) this._setStatus({ ...this._state.status, readOnly: true });
      }
      const result = waiter.match(line);
      if (result) waiter.finish(result);
    }
    async _exchange(session, line, match, timeout = this._timeouts.command, wizard = false) {
      this._assertCurrent(session);
      if (session.waiter) throw failure('BUSY');
      const epoch = ++session.rxEpoch;
      let waiter;
      let sent = false;
      const response = new Promise((resolve, reject) => {
        waiter = {
          epoch, match, wizard,
          finish: result => {
            if (session.waiter !== waiter) return;
            session.waiter = null;
            if (result.error) reject(result.error); else resolve(result.value);
          }
        };
        session.waiter = waiter;
      });
      const bytes = encoder.encode(line + '\n');
      const write = Promise.resolve().then(() => {
        this._assertCurrent(session);
        return session.writer.write(bytes);
      }).then(() => { sent = true; }, () => { throw failure('SERIAL_ERROR'); }).finally(() => bytes.fill(0));
      let timer;
      const deadline = new Promise((_, reject) => {
        timer = setTimeout(() => reject(failure('TIMEOUT')), timeout);
      });
      let abort;
      const aborted = new Promise((_, reject) => {
        abort = () => reject(failure('DISCONNECTED'));
        session.abortController.signal.addEventListener('abort', abort, { once: true });
        if (session.abortController.signal.aborted) abort();
      });
      try {
        const result = await Promise.race([Promise.all([response, write]).then(values => values[0]), deadline, aborted]);
        this._assertCurrent(session);
        return result;
      } catch (error) {
        waiter.finish({ error: safeError(error) });
        const safe = safeError(error);
        safe.sent = sent;
        throw safe;
      } finally { clearTimeout(timer); session.abortController.signal.removeEventListener('abort', abort); }
    }
    async _readStatus(session) {
      const status = await this._exchange(session, 'status', line => {
        const parsed = parseStatus(line);
        return parsed ? success(parsed) : undefined;
      });
      status.readOnly = status.readOnly || session.readOnly;
      this._setStatus(status);
      return status;
    }
    async refreshStatus() {
      return this._operate(async session => {
        try {
          const status = await this._readStatus(session);
          if (status.readOnly) this._event('warning', status.recoveryRequired ? MESSAGES.STORAGE_RECOVERY_REQUIRED : MESSAGES.READ_ONLY);
          return status;
        }
        catch (error) {
          if (this._current(session)) { this._stateChanged({ verified: false }); this._setStatus(null); }
          throw error;
        }
      });
    }
    async testWifi(ssid, password, options = {}) {
      validateCredentials(ssid, password, options);
      return this._operate(async session => {
        this._clearCandidate();
        this._setupActive = true;
        try {
          await this._exchange(session, 'wifi setup', line => {
            if (line === RX.ssid) return success(true);
            if (line === 'WiFi setup unavailable.') return rejected('WIFI_UNAVAILABLE');
            if (line === RX.readonly) return rejected('READ_ONLY');
          }, this._timeouts.command, true);
          this._assertCurrent(session);
          await this._exchange(session, ssid, line => {
            if (line === RX.password) return success(true);
            if (line === "Invalid hidden SSID; enter 1..32 bytes or 'cancel'.") return rejected('INVALID_SSID');
            if (line === RX.cancelled) return rejected('PROTOCOL');
          }, this._timeouts.command, true);
          ssid = '';
          let testing = false;
          await this._exchange(session, password, line => {
            if (line === RX.testing) testing = true;
            if (line === RX.passed && testing) return success(true);
            if (line === RX.failed) return rejected('TEST_FAILED');
            if (line === 'Invalid hidden password; use blank or 8..64 bytes.') return rejected('INVALID_PASSWORD');
            if (line === RX.cancelled) return rejected('PROTOCOL');
          }, this._timeouts.test, true);
          password = '';
          this._stateChanged({ testPassed: true });
          this._candidateTimer = setTimeout(() => {
            if (!this._current(session) || !this._state.testPassed) return;
            this._clearCandidate();
            this._stateChanged({ verified: false });
            this._setStatus(null);
            this._event('warning', 'Срок проверки WiFi истёк. Переподключитесь и повторите тест; сохранение не выполнено.');
          }, this._timeouts.candidate);
          this._event('success', 'Проверка WiFi успешна. Настройки ещё не сохранены; нажмите «Сохранить».');
          return { testPassed: true };
        } catch (error) {
          this._clearCandidate();
          if (this._current(session)) {
            try { await this._resync(session); }
            catch (_) { this._stateChanged({ verified: false }); this._setStatus(null); }
          }
          throw error;
        } finally { ssid = ''; password = ''; }
      }, { mutate: true, wifi: true });
    }
    async _refreshAfterCommit(session) {
      try { await this._readStatus(session); }
      catch (_) {
        if (this._current(session)) { this._stateChanged({ verified: false }); this._setStatus(null); }
        this._event('warning', 'Операция подтверждена, но свежий статус получить не удалось. Переподключитесь.');
      }
    }
    async saveWifi() {
      return this._operate(async session => {
        if (!this._state.testPassed) throw failure('NO_TEST');
        clearTimeout(this._candidateTimer);
        this._candidateTimer = null;
        try {
          await this._exchange(session, 'wifi save', line => {
            if (line === 'Tested WiFi saved.') return success(true);
            if (line === 'Nothing saved; pass WiFi test first.') return rejected('SAVE_FAILED');
            if (line === RX.readonly) return rejected('READ_ONLY');
          }, this._timeouts.command, true);
        } catch (error) {
          this._clearCandidate();
          const uncertain = ['TIMEOUT', 'SERIAL_ERROR', 'DISCONNECTED'].includes(error.code);
          if (this._current(session)) {
            try { await this._resync(session); }
            catch (_) { this._stateChanged({ verified: false }); this._setStatus(null); }
            if (uncertain) { this._stateChanged({ verified: false }); this._setStatus(null); }
          }
          throw uncertain ? failure('SAVE_UNCERTAIN') : error;
        }
        this._clearCandidate();
        this._stateChanged();
        this._event('success', 'Проверенные настройки WiFi сохранены на устройстве.');
        await this._refreshAfterCommit(session);
        return { saved: true, status: this.state.status };
      }, { allowSetup: true, mutate: true, wifi: true });
    }
    async cancelWifi() {
      return this._operate(async session => {
        try { await this._resync(session); }
        catch (error) {
          this._clearCandidate();
          if (this._current(session)) { this._stateChanged({ verified: false }); this._setStatus(null); }
          throw error;
        }
        this._event('info', 'Настройка WiFi отменена. Новые параметры не сохранены.');
        await this._refreshAfterCommit(session);
        return { cancelled: true };
      }, { allowSetup: true, wifi: true });
    }
    async setMode(mode) {
      if (!['ble', 'wifi', 'usb'].includes(mode)) throw failure('MODE_INVALID');
      return this._operate(async session => {
        if (mode === 'usb') {
          try {
            await this._exchange(session, 'mode usb', line => {
              if (line === 'USB mode unavailable or save failed.') return rejected('MODE_FAILED');
              if (line === RX.readonly) return rejected('READ_ONLY');
              // Even the switching notice precedes saving and is not an ACK.
            }, this._timeouts.usb);
          } catch (error) {
            if (!['TIMEOUT', 'SERIAL_ERROR', 'DISCONNECTED'].includes(error.code)) throw error;
          }
          this._clearCandidate();
          if (this._current(session)) await this._shutdown(session, false);
          this._event('warning', 'Переход в USB запрошен, результат неизвестен. Проверьте сохранённый режим на устройстве.');
          return { uncertain: true, requestedMode: 'usb' };
        }
        const label = mode === 'ble' ? 'BLE' : 'WiFi';
        try {
          await this._exchange(session, 'mode ' + mode, line => {
            if (line === 'Mode ' + label + ' saved.') return success(true);
            if (line === label + ' mode unavailable or save failed.') return rejected('MODE_FAILED');
            if (line === RX.readonly) return rejected('READ_ONLY');
          });
        } catch (error) {
          if (['TIMEOUT', 'SERIAL_ERROR', 'DISCONNECTED'].includes(error.code)) {
            if (this._current(session)) { this._stateChanged({ verified: false }); this._setStatus(null); }
            throw failure('MODE_UNCERTAIN');
          }
          throw error;
        }
        this._event('success', 'Режим ' + label + ' сохранён на устройстве.');
        await this._refreshAfterCommit(session);
        return { saved: true, mode, status: this.state.status };
      }, { mutate: true, wifi: mode === 'wifi' });
    }
    async forgetWifi() {
      return this._operate(async session => {
        try {
          await this._exchange(session, 'wifi forget', line => {
            if (line === 'WiFi credentials forgotten.') return success(true);
            if (line === 'WiFi cleared in RAM; persistent cleanup failed.' || line === "WiFi cleared in RAM; persistent cleanup failed. Do not assume credentials were erased. Retry 'wifi forget'.") return rejected('FORGET_FAILED');
            if (line === RX.readonly) return rejected('READ_ONLY');
          });
        } catch (error) {
          if (error.code === 'FORGET_FAILED') {
            await this._refreshAfterCommit(session);
            throw error;
          }
          if (['TIMEOUT', 'SERIAL_ERROR', 'DISCONNECTED', 'FORGET_FAILED'].includes(error.code)) {
            if (this._current(session)) { this._stateChanged({ verified: false }); this._setStatus(null); }
            if (error.code !== 'FORGET_FAILED') throw failure('FORGET_UNCERTAIN');
          }
          throw error;
        }
        this._clearCandidate();
        session.readOnly = false;
        this._event('success', 'Устройство подтвердило удаление сохранённых настроек WiFi.');
        await this._refreshAfterCommit(session);
        return { forgotten: true, status: this.state.status };
      }, { mutate: true, wifi: true, recovery: true });
    }
    async _settingsExchange(session, command, parser) {
      return this._exchange(session, command, line => {
        const error = settingsError(line);
        if (error === 'READ_ONLY') {
          session.readOnly = true;
          if (this._state.status) this._setStatus({...this._state.status,readOnly:true});
        }
        if (error) return rejected(error);
        const value = parser(line);
        if (value !== null && value !== undefined && value !== false) return success(value);
        if (line.startsWith('OK settings')) return rejected('PROTOCOL');
      });
    }
    async _loadDeviceSettings(session) {
      const caps = await this._settingsExchange(session, 'settings caps', parseSettingsCaps);
      const settings = await this._settingsExchange(session, 'settings get', line => parseDeviceSettings(line,caps));
      const schemaSupport=await this._exchange(session,'settings caps schema',line=>{
        if(['ERR settings invalid','ERR settings unsupported',RX.unknown,RX.readonly].includes(line))return success(false);
        if(line==='OK settings caps key=schema value=1')return success(true);
        const error=settingsError(line);if(error)return rejected(error);
        if(line.startsWith('OK settings'))return rejected('PROTOCOL');
      });
      const schemas=Object.create(null);
      if(schemaSupport)for(const key of SETTING_KEYS){
        const schema=await this._settingsExchange(session,'settings schema '+key,line=>parseSettingSchema(line,key));schemas[key]=schema;
        if(schema.supported){
          const value=await this._settingsExchange(session,'settings get '+key,line=>parseSettingValue(line,key));
          if(!settingValueValid(schema,value))throw failure('PROTOCOL');settings[key]=value;
        }
      }
      const soundPreviewSupported=await this._exchange(session,'settings caps sound_preview',line=>{
        if(['ERR settings invalid','ERR settings unsupported',RX.unknown,RX.readonly].includes(line))return success(false);
        if(line==='OK settings caps key=sound_preview value=1')return success(true);
        if(line==='OK settings caps key=sound_preview value=0')return success(false);
        const error=settingsError(line);if(error)return rejected(error);
        if(line.startsWith('OK settings'))return rejected('PROTOCOL');
      });
      this._stateChanged({settingsCaps:caps,deviceSettings:settings,settingSchemas:schemas,soundPreviewSupported});
      if (caps.adc_service) await this._readAdcService(session);
      else this._stateChanged({adcService:null});
      const manual=caps.adc && !this._state.status?.readOnly ? await this._exchange(session,'settings adc manual',line=>{
        if(['ERR settings invalid','ERR settings unsupported',RX.unknown].includes(line))return success({supported:0});
        const value=parseAdcManual(line);if(value)return success(value);
        const error=settingsError(line);if(error)return rejected(error);
        if(line.startsWith('OK settings'))return rejected('PROTOCOL');
      }) : {supported:0};
      this._assertCurrent(session);this._stateChanged({adcManualSupported:Boolean(manual.supported)});
      return settings;
    }
    async _readAdcService(session, command='settings adc service') {
      const value = await this._settingsExchange(session,command,parseAdcService);
      this._assertCurrent(session);
      if (this._state.adcService?.active && !value.active) this.clearAdcPreview();
      this._stateChanged({adcService:{...value,receivedAt:Date.now()}});
      return value;
    }
    async loadAdcService() {
      return this._operate(async session=>{
        this._requireSettings('adc_service');
        try { return await this._readAdcService(session); }
        catch(error) { this._invalidateAdcService(session,error); throw error; }
      });
    }
    async startAdcService({confirmed=false}={}) {
      if (!confirmed) throw failure('ADC_SERVICE_CONFIRM');
      return this._operate(async session=>{
        this._requireSettings('adc_service'); this.clearAdcPreview();
        try {
          const value = await this._readAdcService(session,'settings adc service start');
          if (!value.active) throw failure('PROTOCOL');
          this._event('warning','Сервисное окно подтверждено нодой. Рассчитайте и сохраните ADC по свежему измерению; таймер не продлевается.');
          return value;
        } catch(error) { this._invalidateAdcService(session,error); throw error; }
      },{mutate:true});
    }
    async stopAdcService() {
      return this._operate(async session=>{
        this._requireSettings('adc_service'); this.clearAdcPreview();
        try {
          const value = await this._readAdcService(session,'settings adc service stop');
          if (value.active) throw failure('PROTOCOL');
          this._event('info','Нода подтвердила завершение сервисного окна. Несохранённая калибровка не применялась.');
          return value;
        } catch(error) { this._invalidateAdcService(session,error); throw error; }
      }); // Ending a temporary suspension is allowed even in read-only recovery.
    }
    _invalidateAdcService(session,error) {
      if (!this._current(session)) return;
      const uncertain=['TIMEOUT','SERIAL_ERROR','DISCONNECTED','PROTOCOL'].includes(error.code);
      this.clearAdcPreview();
      this._stateChanged({adcService:null,...(uncertain?{verified:false}:{})});
    }
    _requireSettings(capability) {
      if (!this._state.settingsSupported || !this._state.settingsCaps) throw failure('SETTINGS_UNAVAILABLE');
      if (capability && !this._state.settingsCaps[capability]) throw failure('SETTINGS_UNSUPPORTED');
    }
    clearAdcPreview() {
      clearTimeout(this._adcTimer); this._adcTimer = null;
      this._stateChanged({adcPreview:null});
    }
    async loadDeviceSettings() {
      return this._operate(async session => {
        if (!this._state.settingsSupported) throw failure('SETTINGS_UNAVAILABLE');
        this.clearAdcPreview();
        try { return await this._loadDeviceSettings(session); }
        catch (error) { this._stateChanged({deviceSettings:null}); throw error; }
      });
    }
    async _commitDeviceSettings(session, command, acknowledgement, verify) {
      this.clearAdcPreview();
      let acknowledged = false;
      try {
        await this._settingsExchange(session,command,line => line === acknowledgement);
        acknowledged = true;
        const settings = await this._readSavedSettings(session);
        if (!verify(settings)) throw failure('PROTOCOL');
        this._stateChanged({deviceSettings:settings});
        if (this._state.settingsCaps.adc_service && /^settings adc (apply|reset|set)/.test(command)) await this._readAdcService(session);
        this._event('success','Настройка сохранена и прочитана обратно с ноды.');
        return settings;
      } catch (error) {
        if (acknowledged || ['TIMEOUT','SERIAL_ERROR','DISCONNECTED','PROTOCOL'].includes(error.code)) {
          if (this._current(session)) this._stateChanged({verified:false,deviceSettings:null});
          throw failure('SETTINGS_UNCERTAIN');
        }
        throw error;
      }
    }
    async saveDeviceSetting(key,value) {
      if (!SETTING_KEYS.includes(key) || !Number.isInteger(value)) throw failure('SETTINGS_INVALID');
      return this._operate(async session => {
        const schema=this._state.settingSchemas?.[key];
        this._requireSettings(schema?null:SETTING_CAPS[key]);
        if(schema){if(!settingValueValid(schema,value))throw failure(schema.supported?'SETTINGS_INVALID':'SETTINGS_UNSUPPORTED');}
        else{if(!Object.hasOwn(SETTING_CAPS,key))throw failure('SETTINGS_UNSUPPORTED');
          const max = key === 'melody' ? this._state.settingsCaps.melody_max : key === 'volume' ? 10 : 1;
          if (!integer(value,key === 'volume' ? 1 : 0,max)) throw failure('SETTINGS_INVALID');}
        return this._commitDeviceSettings(session,`settings set ${key} ${value}`,`OK settings set key=${key} value=${value}`,settings => settings[key] === value);
      },{mutate:true});
    }
    async _readSavedSettings(session){
      // Pin assignments and profiles change availability and dependent values.
      // Re-read the schema as well, never leave new hardware controls disabled.
      if(Object.keys(this._state.settingSchemas||{}).length)return this._loadDeviceSettings(session);
      return this._settingsExchange(session,'settings get',line=>parseDeviceSettings(line,this._state.settingsCaps));
    }
    async previewAdc(text) {
      const measured = measuredMilliVolts(text);
      return this._operate(async session => {
        this._requireSettings('adc'); this.clearAdcPreview();
        const preview = await this._settingsExchange(session,'settings adc preview '+measured,line => parseAdcPreview(line,this._state.settingsCaps,measured));
        preview.expiresAt = Date.now()+Math.min(this._timeouts.adcPreview,60000);
        this._stateChanged({adcPreview:preview});
        this._adcTimer = setTimeout(() => this.clearAdcPreview(),Math.min(this._timeouts.adcPreview,60000));
        this._event('info','Расчёт готов. Настройка ещё не изменена; сохраните её отдельной кнопкой.');
        return {...preview};
      });
    }
    async applyAdc({confirmed=false}={}) {
      return this._operate(async session => {
        this._requireSettings('adc');
        const preview = this._state.adcPreview;
        if (!confirmed || !preview) throw failure('ADC_CONFIRM');
        if (Date.now() >= preview.expiresAt) { this.clearAdcPreview(); throw failure('SETTINGS_STALE'); }
        return this._commitDeviceSettings(session,'settings adc apply '+preview.token,'OK settings adc_apply',settings => Math.abs(settings.adc_multiplier-preview.multiplier)<=0.000002);
      },{mutate:true});
    }
    async resetAdc({confirmed=false}={}) {
      return this._operate(async session => {
        this._requireSettings('adc'); if (!confirmed) throw failure('ADC_CONFIRM');
        return this._commitDeviceSettings(session,'settings adc reset','OK settings adc_reset',settings => Math.abs(settings.adc_multiplier-settings.adc_default)<=0.000002);
      },{mutate:true});
    }
    async setAdcMultiplier(text,{confirmed=false}={}) {
      if(!confirmed)throw failure('ADC_CONFIRM');
      return this._operate(async session=>{
        this._requireSettings('adc');
        if(!this._state.adcManualSupported)throw failure('ADC_MANUAL_UNAVAILABLE');
        const value=adcMultiplier(text,this._state.settingsCaps);
        return this._commitDeviceSettings(session,'settings adc set '+value,'OK settings adc_set',settings=>Math.abs(settings.adc_multiplier-Number(value))<=0.000002);
      },{mutate:true});
    }
    async testDeviceNotification() {
      return this._operate(async session => {
        this._requireSettings();
        const caps=this._state.settingsCaps;
        if (!(caps.sound || caps.unread_led || caps.vibration)) throw failure('SETTINGS_UNSUPPORTED');
        await this._settingsExchange(session,'settings test',line => line === 'OK settings test');
        this._event('info','Команда теста принята. Используются сохранённые настройки; общая тишина может отключать звук и вибрацию.');
      },{mutate:true});
    }
    async previewSound() {
      return this._operate(async session=>{
        this._requireSettings('sound');
        if(!this._state.soundPreviewSupported)throw failure('SETTINGS_UNSUPPORTED');
        await this._settingsExchange(session,'settings sound preview',line=>line==='OK settings sound_preview');
        this._event('info','Нода приняла запрос прослушивания. Настройки уведомлений не изменены.');
      },{mutate:true});
    }
    async readCoreSetting(kind){
      if(!['identity','tx'].includes(kind))throw failure('SETTINGS_INVALID');
      return this._operate(session=>this._settingsExchange(session,'settings '+kind,line=>parseCoreSetting(line,kind)));
    }
    async saveCoreSetting(kind,value){
      if(!['identity','tx'].includes(kind))throw failure('SETTINGS_INVALID');
      const bytes=typeof value==='string'?new TextEncoder().encode(value):null;
      if(kind==='identity'&&(!bytes||!bytes.length||bytes.length>31||/[\x00-\x1f\x7f]/.test(value)||new TextDecoder().decode(bytes)!==value))throw failure('SETTINGS_INVALID');
      if(kind==='tx'&&!Number.isInteger(value))throw failure('SETTINGS_INVALID');
      return this._operate(async session=>{
        const before=await this._settingsExchange(session,'settings '+kind,line=>parseCoreSetting(line,kind));
        if(kind==='tx'&&(value<before.min||value>before.max))throw failure('SETTINGS_RANGE');
        const hex=bytes?Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join(''):null;
        let acknowledged=false;
        try{
          await this._settingsExchange(session,kind==='identity'?'settings name '+hex:'settings tx set '+value,line=>kind==='identity'?line==='OK settings name name_hex='+hex:parseCoreSetting(line,'tx')?.value===value);acknowledged=true;
          const after=await this._settingsExchange(session,'settings '+kind,line=>parseCoreSetting(line,kind));
          if((kind==='identity'?after.name:after.value)!==value)throw failure('PROTOCOL');return after;
        }catch(error){if(acknowledged||['TIMEOUT','SERIAL_ERROR','DISCONNECTED','PROTOCOL'].includes(error.code)){this._stateChanged({verified:false});throw failure('SETTINGS_UNCERTAIN');}throw error;}
      },{mutate:true});
    }
    async _readReply(session, slot) {
      return this._exchange(session, 'reply get ' + (slot + 1), line => {
        const result = decodeReply(line, slot);
        if (result) return success(result.text);
        if (line.startsWith('Reply=') || line === 'Quick replies unavailable.' || line === RX.unknown) return rejected('PROTOCOL');
      });
    }
    async _readNetworkSetting(session,kind,command='settings '+kind) {
      return this._exchange(session,command,line=>{
        // Feature discovery is nonfatal on older releases; no version guessing.
        if(line===RX.unknown||line==='ERR settings unsupported'||command==='settings '+kind&&line==='ERR settings invalid')return rejected('SETTINGS_UNSUPPORTED');
        const error=settingsError(line);
        if(error){if(error==='READ_ONLY'){session.readOnly=true;if(this._state.status)this._setStatus({...this._state.status,readOnly:true});}return rejected(error);}
        const value=parseNetworkSetting(line,kind);if(value)return success(value);
        if(line.startsWith('OK settings'))return rejected('PROTOCOL');
      });
    }
    async loadNetworkSetting(kind) {
      if(!['radio','advert'].includes(kind))throw failure('SETTINGS_INVALID');
      return this._operate(async session=>{
        try{return await this._readNetworkSetting(session,kind);}
        catch(error){if(['TIMEOUT','PROTOCOL','SERIAL_ERROR','DISCONNECTED'].includes(error.code)&&this._current(session))this._stateChanged({verified:false});throw error;}
      });
    }
    async saveNetworkSetting(kind,values,{pathOnly=false}={}) {
      if(pathOnly?kind!=='radio'||!integer(values?.path_bytes,1,3):!networkValuesValid(kind,values))throw failure('SETTINGS_INVALID');
      return this._operate(async session=>{
        const keys=kind==='radio'?['freq_khz','bw_hz','sf','cr','path_bytes']:['interval_min'];
        let acknowledged=false;
        try{
          const before=await this._readNetworkSetting(session,kind);
          if(kind==='radio')values=pathOnly?{...before,path_bytes:values.path_bytes}:{...values,path_bytes:before.path_bytes};
          const command='settings '+kind+' set '+keys.map(k=>values[k]).join(' ');
          const ack=await this._readNetworkSetting(session,kind,command);acknowledged=true;
          if(keys.some(k=>ack[k]!==values[k]))throw failure('PROTOCOL');
          const saved=await this._readNetworkSetting(session,kind);
          if(keys.some(k=>saved[k]!==values[k])||kind==='radio'&&(saved.tx_dbm!==before.tx_dbm||saved.repeat!==before.repeat))throw failure('PROTOCOL');
          return saved;
        }catch(error){
          if(error.code==='RADIO_RESTORE'&&this._current(session))this._stateChanged({verified:false});
          if(acknowledged||['TIMEOUT','SERIAL_ERROR','DISCONNECTED','PROTOCOL'].includes(error.code)){
            if(this._current(session))this._stateChanged({verified:false});throw failure('SETTINGS_UNCERTAIN');
          }throw error;
        }
      },{mutate:true});
    }
    async loadQuickReplies() {
      return this._operate(async session => {
        if (!this._state.quickRepliesSupported) throw failure('REPLIES_UNAVAILABLE');
        const replies = [];
        for (let slot = 0; slot < 9; ++slot) replies.push(await this._readReply(session, slot));
        this._stateChanged({replies});
        return [...replies];
      });
    }
    async saveQuickReply(slot, text) {
      if (!Number.isInteger(slot) || slot < 0 || slot >= 9) throw failure('INVALID_REPLY');
      const hex = encodeReply(text);
      return this._operate(async session => {
        if (!this._state.quickRepliesSupported) throw failure('REPLIES_UNAVAILABLE');
        try {
          await this._exchange(session, 'reply set ' + (slot + 1) + ' ' + hex, line => {
            if (line === 'Reply ' + (slot + 1) + ' saved.') return success(true);
            if (line === 'Invalid quick reply.' || line === 'Invalid reply command.') return rejected('INVALID_REPLY');
            if (line === 'Quick reply save failed.') return rejected('REPLY_FAILED');
            if (line === RX.readonly) return rejected('READ_ONLY');
          });
          const stored = await this._readReply(session, slot);
          if (stored !== text) throw failure('PROTOCOL');
          const replies = [...this._state.replies]; replies[slot] = stored;
          this._stateChanged({replies});
          this._event('success', 'Фраза ' + (slot + 1) + ' сохранена и прочитана обратно с ноды.');
          return {saved:true, slot, text:stored};
        } catch (error) {
          if (['TIMEOUT','SERIAL_ERROR','DISCONNECTED','PROTOCOL'].includes(error.code)) {
            if (this._current(session)) this._stateChanged({verified:false, replies:Array(9).fill(null)});
            throw failure('REPLY_UNCERTAIN');
          }
          throw error;
        }
      }, {mutate:true});
    }
  }
  return Object.freeze({ ConsoleClient, ConsoleError, validateCredentials, parseStatus, parseInfo, encodeReply, decodeReply, parseSettingsCaps, parseDeviceSettings, parseAdcPreview, parseAdcService, parseAdcManual, adcMultiplier, measuredMilliVolts, parseNetworkSetting, networkValuesValid, ADVERT_INTERVALS, EXTENDED_FIELDS, SETTING_KEYS, SOUND_SETTING_KEYS, ADVANCED_SETTING_KEYS, parseSettingSchema, parseSettingValue, settingValueValid, settingOptions, notificationStatus, soundOutputStatus, parseCoreSetting });
}));
