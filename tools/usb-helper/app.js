"use strict";
(() => {
  const $ = id => document.getElementById(id);
  let state = {connected:false,busy:false,verified:false,testPassed:false,status:null,info:null};
  let choosingPort = false;
  let confirmation = null;
  let renderedReplies = Array(9).fill(null);
  let firmwareBusy = false;
  let adcOperation = null;
  let droppedFirmware = null, droppedManifest = null;
  const settingsDirty = new Set();
  const modeNames = {ble:"Bluetooth",wifi:"Wi-Fi",usb:"USB-компаньон"};
  const supported = Boolean(window.isSecureContext && navigator.serial);
  // Keep the existing connect -> Wi-Fi -> mode workflow ahead of optional tools.
  $("device-section").before($("mode-title").closest("section"));
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
  const settingFields = [
    {key:"battery_protection",cap:"battery_protection",group:"battery",label:"Защита аккумулятора",options:[[1,"Включена · 3,2 В"],[0,"Выключена · нижняя отсечка 2,7 В"]]},
    {key:"muted",cap:null,group:"sound",label:"Общая тишина",options:[[0,"Выключена"],[1,"Включена"]]},
    {key:"sound_quiet",cap:"sound",group:"sound",label:"Звук уведомлений ЛС",options:[[0,"Включён"],[1,"Выключен"]]},
    {key:"volume",cap:"sound",group:"sound",label:"Громкость",options:Array.from({length:10},(_,i)=>[i+1,(i+1)+" / 10"])},
    {key:"melody",cap:"sound",group:"sound",label:"Общая мелодия",options:[]},
    {key:"board_led",cap:"board_led",group:"lights",label:"LED платы",options:[[1,"Включён"],[0,"Выключен"]]},
    {key:"unread_led",cap:"unread_led",group:"lights",label:"LED уведомлений",options:[[1,"Включён"],[0,"Выключен"]]},
    {key:"vibration",cap:"vibration",group:"lights",label:"Вибрация",options:[[1,"Включена"],[0,"Выключена"]]},
    {key:"gps",cap:"gps",group:"gps",label:"Аппаратный GPS",options:[[1,"Включён"],[0,"Выключен"]]},
  ];
  // Exact public 0.08..0.14 notify_tones order; the package test checks source parity.
  // Other versions retain numeric names unless they share this known catalog.
  const melodyNames = ["Пульс","Бумер","К Элизе","Менуэт","Канон","Рукава","Маяк","Перезв","Колокол","SOS","Ода","Коробейники","Колыбельная","Бадинери","Князь Игорь","Тихая ночь","День рожд.","Гран-вальс","Лебеди","Пинг","Дубль","Рост","Мягк","Ода коротк.","Аркада","Лифт","Nova","Radar","Echo","Tiny","Alert"];
  const addOptions = (select, options) => {
    select.replaceChildren();
    for (const [value,text] of options) { const option=document.createElement("option"); option.value=String(value); option.textContent=text; select.append(option); }
  };
  for (const field of settingFields) {
    const row=document.createElement("div"); row.className="setting-row"; row.id="row-"+field.key;
    const label=document.createElement("label"); label.htmlFor="setting-"+field.key; label.textContent=field.label;
    const controls=document.createElement("div"); controls.className="setting-controls";
    const select=document.createElement("select"); select.id="setting-"+field.key; select.disabled=true; select.setAttribute("aria-describedby","saved-"+field.key); addOptions(select,field.options);
    const save=document.createElement("button"); save.id="save-"+field.key; save.textContent="Сохранить"; save.setAttribute("aria-label","Сохранить: "+field.label); save.disabled=true;
    const status=document.createElement("p"); status.className="setting-state"; status.id="saved-"+field.key; status.textContent="Не прочитано";
    select.onchange=()=>{settingsDirty.add(field.key); renderDeviceSettings();};
    save.onclick=async()=>{
      const value=Number(select.value);
      if (field.key==="battery_protection" && value===0 && !await confirmAction("Выключить защиту аккумулятора 3,2 В? Останется только нижняя отсечка 2,7 В. Это не безопасная цель разряда; необходим исправный BMS и проверенная калибровка ADC.")) return;
      await run(()=>client.saveDeviceSetting(field.key,value));
    };
    controls.append(select,save); row.append(label,controls,status); $(field.group+"-settings").append(row);
  }
  function renderDeviceSettings() {
    const caps=state.settingsCaps, saved=state.deviceSettings;
    const readReady=state.connected && state.verified && !state.busy && !state.testPassed;
    const ready=readReady && !state.status?.readOnly && Boolean(caps && saved);
    if (!state.connected) settingsDirty.clear();
    $("settings-load").disabled=!readReady || !state.settingsSupported;
    $("device-fields").hidden=!caps;
    $("settings-status").textContent=!state.connected ? "Ожидает подключения" : !state.settingsSupported ? "Совместимый режим" : !saved ? "Значения не подтверждены" : state.status?.readOnly ? "Только чтение" : settingsDirty.size ? "Есть несохранённые поля" : "Прочитано с ноды";
    $("settings-hint").textContent=state.settingsSupported ? "У каждого поля отдельное сохранение. Успех — только после подтверждения и совпавшего чтения с ноды." : "Эта консоль пока не сообщает Settings 1. Помощник не отправляет ей новые команды; подключение и прежние инструменты сохранены.";
    const names={adc:"ADC",sound:"звук",board_led:"LED платы",unread_led:"LED уведомлений",vibration:"вибрация",gps:"GPS",battery_protection:"защита АКБ"};
    $("settings-capabilities").textContent=caps ? "Поддержка сборки: "+Object.entries(names).filter(([key])=>caps[key]).map(([,name])=>name).join(", ")+". "+(caps.display ? "Драйвер экрана активен." : "Настройка без дисплея.") : "Новые настройки доступны в SmartUI 0.08 с протоколом Settings 1. Возможности определяются ответом ноды, не её названием.";
    renderAdcService(readReady,ready);
    if (!caps) return;
    const melody=$("setting-melody");
    const melodyCatalog=["0.08","0.09","0.10","0.11","0.12","0.13","0.14"].includes(state.info?.firmware) && caps.melody_max===melodyNames.length-1;
    const catalogKey=String(melodyCatalog)+":"+caps.melody_max;
    if (melody.dataset.catalog!==catalogKey) {
      addOptions(melody,Array.from({length:caps.melody_max+1},(_,i)=>[i,melodyCatalog ? i+" · "+melodyNames[i] : "Мелодия "+i]));
      melody.dataset.catalog=catalogKey;
    }
    for (const field of settingFields) {
      const supported=!field.cap || Boolean(caps[field.cap]);
      $("row-"+field.key).hidden=!supported;
      const input=$("setting-"+field.key), stored=saved?.[field.key];
      if (stored!==undefined && (!settingsDirty.has(field.key) || Number(input.value)===stored)) { input.value=String(stored); settingsDirty.delete(field.key); }
      const dirty=stored!==undefined && Number(input.value)!==stored;
      input.disabled=!ready || !supported;
      $("save-"+field.key).disabled=!ready || !supported || !dirty;
      const label=stored===undefined ? "—" : [...input.options].find(o=>Number(o.value)===stored)?.textContent || String(stored);
      $("saved-"+field.key).textContent=stored===undefined ? "Значение не подтверждено" : "На ноде: "+label+(dirty ? " · Изменение ещё не сохранено" : " · Прочитано");
      $("saved-"+field.key).dataset.dirty=String(dirty);
    }
    $("settings-status").textContent=!saved ? "Значения не подтверждены" : state.status?.readOnly ? "Только чтение" : settingsDirty.size ? "Есть несохранённые поля" : "Прочитано с ноды";
    $("battery-panel").hidden=!(caps.adc || caps.battery_protection);
    $("adc-fields").hidden=!caps.adc;
    $("battery-protection-warning").hidden=!caps.battery_protection;
    $("lights-panel").hidden=!(caps.board_led || caps.unread_led || caps.vibration);
    $("lights-panel").classList.toggle("device-panel-wide",!caps.gps);
    $("gps-panel").hidden=!caps.gps;
    $("battery-voltage").textContent=saved?.battery_mv ? (saved.battery_mv/1000).toLocaleString("ru-RU",{minimumFractionDigits:3,maximumFractionDigits:3})+" В" : "Нет данных";
    $("adc-current").textContent=saved ? saved.adc_multiplier.toFixed(6) : "—";
    $("adc-range").textContent="Заводской: "+(saved ? saved.adc_default.toFixed(6) : "—")+". Допустимо: "+caps.adc_min.toFixed(6)+"–"+caps.adc_max.toFixed(6)+".";
    $("adc-measured").disabled=!ready || !caps.adc;
    $("adc-preview").disabled=!ready || !caps.adc;
    $("adc-reset").disabled=!ready || !caps.adc;
    $("adc-manual-value").disabled=!ready||!state.adcManualSupported;
    $("adc-manual-save").disabled=!ready||!state.adcManualSupported||!$("adc-manual-value").value.trim();
    $("adc-manual-hint").textContent=state.status?.readOnly?"Запись недоступна: нода сообщает режим только для чтения.":state.adcManualSupported?"Правильный множитель уже известен? Сохраните напрямую, без опорного замера. Не подбирайте значение наугад.":"Прямой ввод не поддерживается этой прошивкой. Обновите файлы SmartUI 0.14; расчёт по мультиметру остаётся доступен.";
    const preview=state.adcPreview;
    $("adc-preview-box").hidden=!preview;
    $("adc-apply").disabled=!ready || !preview || Date.now()>=preview.expiresAt;
    if (preview) $("adc-preview-result").textContent="Расчёт, ещё не сохранён: "+preview.multiplier.toFixed(6)+". Опорный замер: "+(preview.sampled_mv/1000).toFixed(3)+" В; мультиметр — "+(preview.measured_mv/1000).toFixed(3)+" В.";
    $("settings-test").disabled=!ready || !(caps.sound || caps.unread_led || caps.vibration);
  }
  function renderAdcService(readReady,ready) {
    const enabled=Boolean(state.settingsCaps?.adc_service), service=state.adcService;
    $("adc-service-box").hidden=!enabled;
    $("adc-service-start").disabled=!enabled||!ready||!service?.external||Boolean(service?.active);
    $("adc-service-stop").disabled=!enabled||!readReady||!service?.active;
    $("adc-service-refresh").disabled=!enabled||!readReady;
    $("adc-service-status").textContent=!service ? "Состояние окна не подтверждено. Нажмите «Проверить окно»." : service.active
      ? "Окно активно · осталось по данным ноды: "+Math.ceil(service.remaining_ms/1000)+" с. Проверяем каждые 5 секунд."
      : service.external ? "Окно выключено. Обычная защита питания действует." : "Окно выключено. Нода не подтвердила питание USB.";
    if (!state.connected) {$("adc-measured").value="";$("adc-manual-value").value="";}
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
    renderDeviceSettings();
    window.dispatchEvent(new CustomEvent("smartui-console-state",{detail:state}));
  }
  const client = new SmartUiConsole.ConsoleClient({
    onState(next) { const lost=state.connected&&!next.connected;state = next; if (!state.connected) clearPassword(); render();if(lost){for(const id of ['adc-result','adc-manual-result'])adcNote(adcOperation?.id===id?'USB отключён. Сохранение не подтверждено; переподключитесь и прочитайте ADC.':'USB отключён. Подключите ноду для проверки ADC.',adcOperation?.id===id?'error':'info',id);} },
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
  $("settings-load").onclick=async()=>{
    if (settingsDirty.size && !await confirmAction("Прочитать значения с ноды заново? Несохранённые изменения в полях помощника будут отменены.")) return;
    settingsDirty.clear(); await run(()=>client.loadDeviceSettings());
  };
  const adcNote=(text,kind='info',id='adc-result')=>{$(id).textContent=text;$(id).classList.add('adc-feedback');$(id).dataset.kind=kind;};
  async function runAdc(operation,{progress='Выполняем запрос к ноде…',success,id='adc-result'}={}) {
    const session=client._session,token={session,id};adcOperation=token;adcNote(progress,'info',id);
    try{const result=await operation();if(session===client._session&&success)adcNote(typeof success==='function'?success(result):success,'success',id);return result;}
    catch(error){if(session===client._session){const text=error?.safe?error.message:'Ответ не подтверждён. Переподключитесь и прочитайте настройки.';adcNote(text,'error',id);feedback(text,'error');}}
    finally{if(adcOperation===token)adcOperation=null;}
  }
  $("adc-measured").oninput=()=>{client.clearAdcPreview();adcNote('Замер изменён. Рассчитайте поправку заново.');};
  $("adc-manual-value").oninput=()=>{client.clearAdcPreview();adcNote('Коэффициент ещё не сохранён. Проверьте значение и нажмите «Сохранить коэффициент».','info','adc-manual-result');renderDeviceSettings();};
  $("adc-manual-save").onclick=async()=>{
    const session=client._session,text=$("adc-manual-value").value;
    let value;try{value=SmartUiConsole.adcMultiplier(text,state.settingsCaps);}catch(error){adcNote(error.message,'error','adc-manual-result');return;}
    if(!await confirmAction('Сохранить ADC-множитель '+value+' напрямую? Используйте только проверенный коэффициент для этой платы. Он влияет на показание напряжения и защиту аккумулятора.'))return;
    if(session!==client._session||text!==$("adc-manual-value").value||!state.connected||!state.verified){adcNote('Подключение или значение изменилось. Проверьте ввод и подтвердите заново.','error','adc-manual-result');return;}
    await runAdc(()=>client.setAdcMultiplier(value,{confirmed:true}),{id:'adc-manual-result',progress:'Сохраняем коэффициент '+value+' и читаем обратно…',success:s=>{adcNote('Коэффициент сохранён вручную. Для нового расчёта нужен свежий замер.');return 'Сохранено на ноде и проверено: '+s.adc_multiplier.toFixed(6)+'. Напряжение ProMicro сверяйте от АКБ: USB искажает измерение.';}});
  };
  $("adc-service-start").onclick=async()=>{
    const session=client._session;
    if (await confirmAction("На 2 минуты приостановить отключение по показаниям ADC? Нужно подтверждённое питание USB. Для расчёта нужен свежий замер мультиметром; для прямого ввода — проверенный коэффициент. После сохранения, тайм-аута или потери USB защита вернётся автоматически. Это только сервисная калибровка, не обычный режим работы.") && session===client._session && state.connected && state.verified) await run(()=>client.startAdcService({confirmed:true}));
  };
  $("adc-service-stop").onclick=()=>run(()=>client.stopAdcService());
  $("adc-service-refresh").onclick=()=>run(()=>client.loadAdcService());
  setInterval(()=>{
    if (state.connected&&state.verified&&!state.busy&&!state.testPassed&&state.adcService?.active) void run(()=>client.loadAdcService());
  },5000);
  $("adc-preview").onclick=()=>runAdc(()=>client.previewAdc($("adc-measured").value),{progress:'Получаем опорный замер и рассчитываем поправку…',success:p=>'Рассчитано: '+p.multiplier.toFixed(6)+'. Пока не сохранено — проверьте результат и нажмите «Сохранить калибровку».'});
  $("adc-apply").onclick=async()=>{
    if (await confirmAction("Сохранить рассчитанную калибровку ADC? Убедитесь, что напряжение измерено мультиметром непосредственно на аккумуляторе. Поправка влияет на оценку заряда и защиту питания.")) await runAdc(()=>client.applyAdc({confirmed:true}),{progress:'Сохраняем калибровку и читаем обратно…',success:s=>'Калибровка сохранена и проверена: '+s.adc_multiplier.toFixed(6)+'.'});
  };
  $("adc-reset").onclick=async()=>{
    if (await confirmAction("Вернуть только калибровку ADC к заводскому множителю этой платы? Контакты, ключ ноды и остальные настройки не удаляются.")) await runAdc(()=>client.resetAdc({confirmed:true}),{progress:'Восстанавливаем заводской коэффициент…',success:s=>'Заводской коэффициент сохранён и проверен: '+s.adc_multiplier.toFixed(6)+'.'});
  };
  $("settings-test").onclick=()=>run(()=>client.testDeviceNotification());
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
    const message = mode === "usb" ? "Включить USB-компаньон? Помощник потеряет связь с консолью. Для возврата выберите Bluetooth/Wi-Fi на экране. В SmartUI 0.08–0.14 без дисплея: перезапустите ноду, после запуска прошивки в первые 8 секунд выполните долгое нажатие пользовательской кнопки. Не удерживайте ESP BOOT во время перезапуска. Результат переключения в USB не подтверждается закрытием порта." : "Переключить ноду на " + modeNames[mode] + "? Текущее соединение приложения-компаньона будет разорвано.";
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
  window.SmartUiLegacy = {client,confirmAction,feedback,getState:()=>state};
  render();
})();
