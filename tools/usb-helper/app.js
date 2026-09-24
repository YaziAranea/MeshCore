"use strict";
(() => {
  const $ = id => document.getElementById(id);
  let state = {connected:false,busy:false,verified:false,testPassed:false,status:null};
  let choosingPort = false;
  let confirmation = null;
  const modeNames = {ble:"Bluetooth",wifi:"Wi-Fi",usb:"USB-компаньон"};
  const supported = Boolean(window.isSecureContext && navigator.serial);
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
    $("connect").disabled = !supported || state.connected || state.busy || choosingPort;
    $("disconnect").disabled = !state.connected || choosingPort;
    $("connect").textContent = choosingPort ? "Выберите порт в окне браузера…" : "Выбрать USB-порт";
    $("connection").textContent = state.busy ? "Выполняется операция…" : state.verified ? "Консоль SmartUI подключена" : state.connected ? "Порт открыт; консоль не подтверждена" : "Нода не подключена";
    $("refresh").disabled = !idle;
    ["ssid","open-network","test"].forEach(id => $(id).disabled = !idle);
    $("password").disabled = !idle || $("open-network").checked;
    $("show-password").disabled = !idle || $("open-network").checked;
    $("save").disabled = !ready || !state.testPassed;
    $("cancel").disabled = !ready;
    $("forget").disabled = !idle;
    for (const mode of Object.keys(modeNames)) {
      $("mode-" + mode).disabled = !idle;
      $("mode-" + mode).setAttribute("aria-pressed",String(state.status?.mode === mode));
    }
    const s = state.status;
    $("mode").textContent = s ? modeNames[s.mode] || "—" : "—";
    $("companion").textContent = s ? s.companion === "connected" ? "Подключено: " + (modeNames[s.via] || s.via) : "Не подключено" : "—";
    $("configured").textContent = s ? s.wifiConfigured ? "Есть" : "Не задана" : "—";
    $("network").textContent = s ? s.link === "associated" ? "Подключено" : "Нет соединения" : "—";
    $("ip").textContent = s?.ip || "—";
    $("wifi-hint").textContent = state.testPassed ? "Сеть проверена, но ещё не сохранена. Нажмите «Сохранить сеть» или отмените проверку. Через две минуты бездействия нода отменит настройку." : "Сначала проверка, потом сохранение. Старые данные не заменяются неудачным тестом. Имя и пароль чувствительны к регистру и пробелам.";
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
