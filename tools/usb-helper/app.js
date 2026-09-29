"use strict";
(() => {
  const $ = id => document.getElementById(id);
  let state = {connected:false,busy:false,verified:false,testPassed:false,status:null,info:null};
  let choosingPort = false;
  let confirmation = null;
  let renderedReplies = Array(9).fill(null);
  let firmwareBusy = false;
  let droppedFirmware = null, droppedManifest = null;
  const modeNames = {ble:"Bluetooth",wifi:"Wi-Fi",usb:"USB-компаньон"};
  const supported = Boolean(window.isSecureContext && navigator.serial);
  // Keep the existing connect -> Wi-Fi -> mode workflow ahead of optional tools.
  $("replies-title").closest("section").before($("mode-title").closest("section"));
  const replyDefaults = ["Да","Нет","Потом","Сейчас","Завтра","Сегодня","Привет","Пока","Тест?"];
  for (let slot = 0; slot < 9; ++slot) {
    const row = document.createElement("div"); row.className = "reply-row";
    const label = document.createElement("label"); label.className = "field"; label.htmlFor = "reply-" + slot;
    label.textContent = "Фраза " + (slot + 1) + " · стандартная: «" + replyDefaults[slot] + "»";
    const input = document.createElement("input"); input.type = "text"; input.id = "reply-" + slot; input.disabled = true; input.autocomplete = "off";
    const bytes = document.createElement("p"); bytes.className = "hint"; bytes.id = "reply-bytes-" + slot;
    input.oninput = () => { bytes.textContent = new TextEncoder().encode(input.value).length + " / 64 байт UTF-8"; };
    const buttons = document.createElement("div"); buttons.className = "buttons";
    const save = document.createElement("button"); save.id = "reply-save-" + slot; save.disabled = true; save.textContent = "Сохранить фразу " + (slot + 1);
    const clear = document.createElement("button"); clear.id = "reply-clear-" + slot; clear.disabled = true; clear.textContent = "Вернуть стандартную";
    save.onclick = () => run(async () => { const result = await client.saveQuickReply(slot,input.value); input.value = result.text; input.oninput(); });
    clear.onclick = async () => {
      if (await confirmAction("Вернуть стандартную фразу «" + replyDefaults[slot] + "» в слот " + (slot + 1) + "?")) await run(async () => { const result = await client.saveQuickReply(slot,""); input.value = result.text; input.oninput(); });
    };
    buttons.append(save,clear); row.append(label,input,bytes,buttons); $("reply-fields").append(row);
  }
  for (const profile of SmartUiFirmware.PROFILES) {
    const option = document.createElement("option"); option.value = profile.id; option.textContent = profile.label; $("firmware-board").append(option);
  }
  const feedback = (text, kind = "info") => {
    $("feedback").textContent = text;
    $("feedback").dataset.kind = kind;
  };
  const event = ({text,kind}) => {
    if (typeof text !== "string") return;
    feedback(text,kind);
    const li = document.createElement("li");
    const time = document.createElement("span");
    time.className = "event-time";
    time.textContent = new Date().toLocaleTimeString("ru-RU");
    li.append(time,document.createTextNode(text));
    $("events").prepend(li);
    while ($("events").children.length > 50) $("events").lastChild.remove();
  };
  const clearPassword = () => {
    $("password").value = "";
    $("password").type = "password";
    $("show-password").checked = false;
  };
  function render() {
    const ready = state.connected && state.verified && !state.busy && !state.status?.readOnly;
    const idle = ready && !state.testPassed;
    const wifiAvailable = !state.info || state.info.capabilities.includes("WiFi");
    const wifiIdle = idle && wifiAvailable;
    $("connect").disabled = !supported || state.connected || state.busy || choosingPort;
    $("disconnect").disabled = !state.connected || choosingPort;
    $("connect").textContent = choosingPort ? "Выберите порт в окне браузера…" : "Выбрать USB-порт";
    $("connection").textContent = state.busy ? "Выполняется операция…" : state.verified ? "Консоль SmartUI подключена" : state.connected ? "Порт открыт; консоль не подтверждена" : "Нода не подключена";
    $("refresh").disabled = !state.connected || !state.verified || state.busy || state.testPassed;
    ["ssid","open-network","test"].forEach(id => $(id).disabled = !wifiIdle);
    $("password").disabled = !wifiIdle || $("open-network").checked;
    $("show-password").disabled = !wifiIdle || $("open-network").checked;
    $("save").disabled = !ready || !wifiAvailable || !state.testPassed;
    $("cancel").disabled = !ready || !wifiAvailable;
    const recovery = state.connected && state.verified && !state.busy && !state.testPassed && state.status?.recoveryRequired;
    $("forget").disabled = !(wifiIdle || recovery);
    $("forget").textContent = recovery ? "Повторить очистку хранилища подключения" : "Удалить сеть с ноды";
    $("replies-load").disabled = !state.connected || !state.verified || state.busy || state.testPassed || !state.quickRepliesSupported;
    $("replies-hint").textContent = state.quickRepliesSupported ? "Поддержка подтверждена прошивкой. После записи помощник читает сохранённый слот обратно." : "Нужна новая прошивка с поддержкой своих фраз; у 0.05/0.06 этот раздел недоступен.";
    for (let slot = 0; slot < 9; ++slot) {
      const stored = state.replies?.[slot] ?? null;
      if (stored !== renderedReplies[slot]) { $("reply-" + slot).value = stored ?? ""; $("reply-" + slot).oninput(); }
      for (const prefix of ["reply-","reply-save-","reply-clear-"]) $(prefix + slot).disabled = !idle || !state.quickRepliesSupported || stored === null;
    }
    renderedReplies = [...(state.replies || Array(9).fill(null))];
    for (const mode of Object.keys(modeNames)) {
      $("mode-" + mode).disabled = !idle || (mode === "wifi" && !wifiAvailable);
      $("mode-" + mode).setAttribute("aria-pressed",String(state.status?.mode === mode));
    }
    const s = state.status;
    $("mode").textContent = s ? modeNames[s.mode] || "—" : "—";
    $("companion").textContent = s ? s.companion === "connected" ? "Подключено: " + (modeNames[s.via] || s.via) : "Не подключено" : "—";
    $("configured").textContent = s ? s.wifiConfigured ? "Есть" : "Не задана" : "—";
    $("network").textContent = s ? s.link === "associated" ? "Подключено" : "Нет соединения" : "—";
    $("ip").textContent = s?.ip || "—";
    for (const field of ["firmware","core","build","board"]) $("info-" + field).textContent = state.info?.[field] || "—";
    $("info-hint").textContent = state.info ? "Данные сообщены прошивкой. Доступно: " + state.info.capabilities.join(", ") + "." : state.verified ? "Эта консоль не сообщает версию и плату (совместимый режим 0.05). Возможности Wi-Fi не определены." : "Версия и плата появятся после проверки консоли SmartUI 0.06.";
    $("wifi-hint").textContent = !wifiAvailable ? "Прошивка сообщает: у этой платы нет Wi-Fi. Доступны Bluetooth и USB-компаньон." : state.testPassed ? "Сеть проверена, но ещё не сохранена. Нажмите «Сохранить сеть» или отмените проверку. Через две минуты бездействия нода отменит настройку." : "Сначала проверка, потом сохранение. Старые данные не заменяются неудачным тестом. Имя и пароль чувствительны к регистру и пробелам.";
    $("open-warning").hidden = !$("open-network").checked;
  }
  const client = new SmartUiConsole.ConsoleClient({
    onState(next) { state = next; if (!state.connected) clearPassword(); render(); },
    onStatus(status) { state = {...state,status}; render(); },
    onEvent:event,
  });
  const run = async operation => {
    try { await operation(); } catch (error) {
      // Protocol errors are sanitized by core. Never surface device bytes,
      // browser exception text, SSID or passwords through this fallback.
      feedback(error?.safe === true ? error.message : "Операция не завершена. Проверьте подключение и сообщения помощника.","error");
    }
  };
  function confirmAction(text) {
    if (confirmation) return Promise.resolve(false);
    $("confirm-text").textContent = text;
    $("confirm-dialog").showModal();
    $("confirm-no").focus();
    return new Promise(resolve => { confirmation = resolve; });
  }
  function finishConfirmation(accepted) {
    const resolve = confirmation;
    confirmation = null;
    $("confirm-dialog").close();
    if (resolve) resolve(accepted);
  }
  $("confirm-no").onclick = () => finishConfirmation(false);
  $("confirm-yes").onclick = () => finishConfirmation(true);
  $("confirm-dialog").addEventListener("cancel", e => {e.preventDefault();finishConfirmation(false);});
  $("connect").onclick = async () => {
    choosingPort = true; render();
    try {
      const port = await navigator.serial.requestPort();
      choosingPort = false;
      await run(() => client.connect(port));
    } catch (error) {
      feedback(error?.name === "NotFoundError" ? "Порт не выбран. Можно попробовать снова." : "Браузер не предоставил доступ к порту. Проверьте разрешения и закройте другие программы.","warning");
    } finally { choosingPort = false; render(); }
  };
  $("disconnect").onclick = () => run(() => client.disconnect());
  $("refresh").onclick = () => run(() => client.refreshStatus());
  $("replies-load").onclick = () => run(async () => {
    const replies = await client.loadQuickReplies();
    replies.forEach((text,slot) => { $("reply-" + slot).value = text; $("reply-" + slot).oninput(); });
  });
  const resetFirmwareResult = () => { $("firmware-result").textContent = "Файлы изменены. Выполните проверку заново."; };
  $("firmware-file").onchange = () => { droppedFirmware = null; resetFirmwareResult(); };
  $("firmware-manifest").onchange = () => { droppedManifest = null; resetFirmwareResult(); };
  $("firmware-board").onchange = resetFirmwareResult;
  const firmwareSection = $("firmware-title").closest("section");
  firmwareSection.ondragover = e => { e.preventDefault(); };
  firmwareSection.ondrop = e => {
    e.preventDefault();
    if (firmwareBusy) return;
    for (const file of e.dataTransfer.files) {
      if (/\.(bin|uf2)$/i.test(file.name)) droppedFirmware = file;
      else if (/\.json$/i.test(file.name)) droppedManifest = file;
    }
    $("firmware-result").textContent = "Выбраны локальные файлы: " + (droppedFirmware?.name || "нет BIN/UF2") + "; " + (droppedManifest?.name || "нет манифеста") + ". Нажмите «Проверить файлы».";
  };
  $("firmware-check").onclick = async () => {
    if (firmwareBusy) return;
    firmwareBusy = true; $("firmware-check").disabled = true;
    for (const id of ["firmware-file","firmware-manifest","firmware-board"]) $(id).disabled = true;
    $("firmware-result").textContent = "Локальная проверка…";
    const infoAtStart = state.info ? {...state.info} : null;
    try {
      const file = droppedFirmware || $("firmware-file").files[0];
      const manifest = droppedManifest || $("firmware-manifest").files[0];
      if (!file || !manifest || file.size > SmartUiFirmware.MAX_BYTES || manifest.size > 2 * 1024 * 1024) throw new Error("files");
      const target = $("firmware-board").value;
      const result = await SmartUiFirmware.verify({name:file.name, bytes:new Uint8Array(await file.arrayBuffer()), manifestText:await manifest.text(), target, info:infoAtStart});
      $("firmware-result").textContent = "Проверка файла пройдена. " + file.name + "\n" + result.board + ", SmartUI " + result.version + ".\n" +
        (result.matchedConnectedBoard ? "Модель совпала со сведениями ноды на момент начала проверки." : "Модель выбрана вручную; реальная плата не проверена.") + "\n" +
        "Тип: " + result.kind + (result.offset ? "; адрес " + result.offset : "") + ".\nSHA-256: " + result.sha256 + "\nSource: " + result.source + "\n" + result.warning + "\n" + result.integrityNotice;
    } catch (error) {
      $("firmware-result").textContent = error.safe ? error.message : "Проверка не выполнена. Выберите BIN/UF2 до 32 МиБ и манифест до 2 МиБ; проверьте доступ к локальным файлам.";
    } finally { firmwareBusy = false; $("firmware-check").disabled = false; for (const id of ["firmware-file","firmware-manifest","firmware-board"]) $(id).disabled = false; }
  };
  $("show-password").onchange = () => { $("password").type = $("show-password").checked ? "text" : "password"; };
  $("open-network").onchange = () => { if ($("open-network").checked) clearPassword(); render(); };
  $("wifi-form").onsubmit = async e => {
    e.preventDefault();
    if ($("test").disabled) return;
    let password = $("password").value;
    const ssid = $("ssid").value;
    const openNetwork = $("open-network").checked;
    const operation = client.testWifi(ssid,password,{openNetwork});
    password = "";
    clearPassword();
    await run(() => operation);
  };
  $("save").onclick = () => run(() => client.saveWifi());
  $("cancel").onclick = () => run(() => client.cancelWifi());
  for (const mode of Object.keys(modeNames)) $("mode-" + mode).onclick = async () => {
    if (state.status?.mode === mode) return;
    const message = mode === "usb" ? "Включить USB-компаньон? Помощник потеряет связь с консолью. Для возврата нужно выбрать Bluetooth или Wi-Fi кнопками ноды. Результат переключения проверяйте на экране ноды." : "Переключить ноду на " + modeNames[mode] + "? Текущее соединение приложения-компаньона будет разорвано.";
    if (await confirmAction(message)) await run(() => client.setMode(mode));
  };
  $("forget").onclick = async () => {
    if (await confirmAction("Удалить сохранённое имя и пароль Wi-Fi с ноды и вернуться к Bluetooth? Контакты и сообщения не удаляются.")) {
      await run(() => client.forgetWifi()); clearPassword();
    }
  };
  $("clear-events").onclick = () => { $("events").replaceChildren(); };
  window.addEventListener("beforeunload", e => {
    clearPassword();
    if (state.connected && (state.busy || state.testPassed)) {e.preventDefault();e.returnValue = "";}
  });
  $("unsupported").hidden = supported;
  render();
})();
