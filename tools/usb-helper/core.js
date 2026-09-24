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
    helpEnd: 'Credential input is not echoed. WiFi is saved only after a passed test.'
  });
  const MESSAGES = Object.freeze({
    BUSY: 'Дождитесь завершения текущей операции.',
    DISCONNECTED: 'USB-соединение закрыто.',
    NOT_CONNECTED: 'Сначала подключите устройство.',
    NOT_VERIFIED: 'Сервисная консоль не подтверждена. Переподключитесь; на устройстве выберите BLE или WiFi.',
    TIMEOUT: 'Устройство не ответило вовремя. Проверьте USB и выбранный режим.',
    SERIAL_ERROR: 'Ошибка USB-соединения. Закройте другие программы, использующие порт, и переподключитесь.',
    OPEN_FAILED: 'Не удалось открыть USB-порт. Закройте другие программы, использующие порт.',
    READ_ONLY: 'Настройки доступны только для чтения: устройство восстанавливает хранилище.',
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
    INPUT_OVERFLOW: 'Устройство отклонило слишком длинный ввод.'
  });
  const DEFAULT_TIMEOUTS = Object.freeze({ command: 6000, test: 25000, usb: 2000, close: 1500, candidate: 120000 });
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
    if (ssid === 'cancel') throw failure('RESERVED_SSID');
    if (options.openNetwork === true && password !== '') throw failure('OPEN_PASSWORD');
    if (password === '' && options.openNetwork !== true) throw failure('OPEN_CONFIRMATION');
    if (controls.test(password) || (password !== '' && !((passwordBytes >= 8 && passwordBytes <= 63) || /^[0-9a-fA-F]{64}$/.test(password)))) throw failure('INVALID_PASSWORD');
    return { ssidBytes, passwordBytes, openNetwork: password === '' };
  }
  function parseStatus(line) {
    if (typeof line !== 'string') return null;
    const match = /^Mode=(BLE|WiFi|USB) companion=(connected|idle) via=(BLE|WiFi|USB|none) USB-service=(on|off) WiFi-config=(yes|no) link=(associated|down) IP=(none|\d{1,3}(?:\.\d{1,3}){3}) approval=(pending|none)$/.exec(line);
    if (!match || (match[7] !== 'none' && match[7].split('.').some(part => Number(part) > 255))) return null;
    return {
      mode: match[1].toLowerCase(), companion: match[2], via: match[3].toLowerCase(),
      usbService: match[4] === 'on', wifiConfigured: match[5] === 'yes', link: match[6],
      ip: match[7] === 'none' ? null : match[7], approval: match[8], readOnly: false
    };
  }

  class ConsoleClient {
    constructor({ onState, onStatus, onEvent, timeouts = {} } = {}) {
      this._callbacks = { onState, onStatus, onEvent };
      this._timeouts = { ...DEFAULT_TIMEOUTS };
      // Optional shorter deadlines make fake-stream tests independent of hardware.
      for (const key of Object.keys(DEFAULT_TIMEOUTS)) {
        if (Number.isFinite(timeouts[key]) && timeouts[key] > 0) this._timeouts[key] = timeouts[key];
      }
      this._state = { connected: false, busy: false, verified: false, testPassed: false, status: null };
      this._session = null;
      this._operation = null;
      this._closing = null;
      this._setupActive = false;
      this._candidateTimer = null;
      this._pendingPorts = new WeakSet();
    }
    get state() { return { ...this._state, status: this._state.status ? { ...this._state.status } : null }; }
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
    async _operate(action, { allowSetup = false, connect = false, mutate = false } = {}) {
      if (this._operation || this._closing) throw failure('BUSY');
      if (!connect) {
        if (!this._state.connected || !this._session) throw failure('NOT_CONNECTED');
        if (!this._state.verified) throw failure('NOT_VERIFIED');
        if (this._setupActive && !allowSetup) throw failure('WIFI_PENDING');
        if (mutate && this._state.status && this._state.status.readOnly) throw failure('READ_ONLY');
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
          this._stateChanged({ connected: true, verified: false, testPassed: false, status: null });
          session.readTask = this._readLoop(session);
          await this._resync(session);
          let helpSeen = false;
          if (!session.readOnly) await this._exchange(session, 'help', line => {
            if (line === RX.help) helpSeen = true;
            if (line === RX.helpEnd && helpSeen) return success(true);
            if (line === RX.readonly) { session.readOnly = true; return success(false); }
          });
          const status = await this._readStatus(session);
          if (!status.usbService || status.mode === 'usb') throw failure('PROTOCOL');
          this._assertCurrent(session);
          this._stateChanged({ verified: true });
          this._event('success', session.readOnly ? 'Консоль подключена. Настройки доступны только для чтения.' : 'Сервисная консоль SmartUI подключена.');
          return this.state;
        } catch (error) {
          if (this._session === session) await this._shutdown(session, false);
          throw error;
        }
      }, { connect: true });
    }
    async _resync(session) {
      // Clear any partial credential/command without submitting it. The firmware
      // retains partial input across browser disconnects (CONSOLE_LINE_MAX=96).
      // Backspace cannot clear its overflow flag: one discarded line is followed
      // by a second cancellation. Neither step can save credentials.
      const cancel = '\b'.repeat(96) + 'cancel';
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
      await this._shutdown(this._session, true);
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
      this._stateChanged({ connected: false, verified: false, status: null });
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
                if (session.buffer.length < 256 && !session.overflow) session.buffer += char;
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
      status.readOnly = session.readOnly;
      this._setStatus(status);
      return status;
    }
    async refreshStatus() {
      return this._operate(async session => {
        try { return await this._readStatus(session); }
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
      }, { mutate: true });
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
      }, { allowSetup: true, mutate: true });
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
      }, { allowSetup: true });
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
      }, { mutate: true });
    }
    async forgetWifi() {
      return this._operate(async session => {
        try {
          await this._exchange(session, 'wifi forget', line => {
            if (line === 'WiFi credentials forgotten.') return success(true);
            if (line === 'WiFi cleared in RAM; persistent cleanup failed.') return rejected('FORGET_FAILED');
            if (line === RX.readonly) return rejected('READ_ONLY');
          });
        } catch (error) {
          if (['TIMEOUT', 'SERIAL_ERROR', 'DISCONNECTED', 'FORGET_FAILED'].includes(error.code)) {
            if (this._current(session)) { this._stateChanged({ verified: false }); this._setStatus(null); }
            if (error.code !== 'FORGET_FAILED') throw failure('FORGET_UNCERTAIN');
          }
          throw error;
        }
        this._clearCandidate();
        this._event('success', 'Устройство подтвердило удаление сохранённых настроек WiFi.');
        await this._refreshAfterCommit(session);
        return { forgotten: true, status: this.state.status };
      }, { mutate: true });
    }
  }
  return Object.freeze({ ConsoleClient, ConsoleError, validateCredentials, parseStatus });
}));
