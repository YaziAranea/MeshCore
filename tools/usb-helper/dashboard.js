'use strict';
(() => {
  const $=id=>document.getElementById(id), api=SmartUiCli, legacy=SmartUiLegacy;
  let mode='console',choosing=false,running=false,caps=null,settings=null,preview=null,wifiState=null,connectionState=null,acknowledgedLoss=false,adcService=null,adcManualSupported=false;
  let activePage='connection';
  function renderPages(){
    for(const panel of document.querySelectorAll('[data-pages]'))panel.classList.toggle('page-hidden',!panel.dataset.pages.split(' ').includes(activePage));
    for(const tab of document.querySelectorAll('[data-page-target]')){const selected=tab.dataset.pageTarget===activePage;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;}
    if($('device-title'))$('device-title').textContent=activePage==='sound'?'Звук, свет и пины':'Настройки устройства';
    const apiTitle=$('api-settings')?.querySelector('h2');if(apiTitle)apiTitle.textContent=activePage==='sound'?'Звук, свет и пины':'Настройки устройства';
  }
  const settingEdits=new Map(),melodyNames=new Map();
  let schemas=Object.create(null);
  let radioState=null,advertState=null,radioSupport=null,advertSupport=null,networkRunning=false;
  let pathEdited=false;
  let identityState=null,txState=null;
  const coreEdits=new Set();
  const catalog=globalThis.SmartUiPresets;
  let binaryState={connected:false,busy:false,phase:'disconnected',hello:null,uncertain:false};
  let adcOperation=null;
  const grid=document.querySelector('.grid');
  const consolePanels=[$('device-section'),$('replies-section'),$('wifi-title').closest('section'),$('mode-title').closest('section'),$('feedback')];
  const consoleNotices=[...document.querySelectorAll('main > .notice')];
  $('connection-actions').append($('connect').parentElement);
  const dock=document.querySelector('.transport-dock');dock.id='connection-dock';
  const connectionMeta=document.createElement('p');connectionMeta.id='api-connection-meta';connectionMeta.className='hint';connectionMeta.hidden=true;dock.append(connectionMeta);
  // Constant application markup only. Device text is inserted with textContent.
  const workspace=document.createElement('div');workspace.id='api-workspace';workspace.className='wide';workspace.hidden=true;
  workspace.innerHTML=`
    <div id="api-feedback" class="notice" role="status" aria-live="polite">Выберите режим USB-компаньона на ноде, затем подключите порт.</div>
    <p id="cli-scope" class="notice">Настройки подключённой ноды через CMD66. Сообщения не читаются; синхронизация прочтения и события API 0.11 не поддерживаются. Для старой 0.11 сохранён <a href="https://github.com/YaziAranea/MeshCore/releases/tag/smartui-0.11" target="_blank" rel="noopener noreferrer">архивный Helper 1.4</a>.</p>
    <div class="api-workspace" style="margin-top:20px">
      <section id="api-settings" class="card wide"><div class="section-heading"><div><p class="panel-kicker">Устройство и радио</p><h2>Настройки ноды · локальный CLI</h2></div><span id="api-settings-status" class="status-pill">Не прочитано</span></div><p class="hint">Только поддерживаемые сборкой функции. У каждого изменения отдельное сохранение и контрольное чтение.</p><div class="buttons"><button id="api-settings-load" disabled>Прочитать настройки</button><button id="api-notify-test" disabled>Проверить уведомление</button></div><div id="api-settings-fields"></div>
      <details id="api-adc"><summary>Калибровка аккумулятора</summary><p id="api-adc-value" class="hint">Нет измерения</p><p id="api-adc-range" class="hint"></p><p class="hint">Выберите один из двух способов калибровки.</p><h4>Способ 1: рассчитать по мультиметру</h4><p id="api-adc-source-warning" class="safety-note"></p><label class="field" for="api-adc-measured">Напряжение мультиметра, В</label><input id="api-adc-measured" type="text" inputmode="decimal" placeholder="Например, 3,82"><div class="buttons"><button id="api-adc-preview" disabled>Рассчитать поправку</button><button id="api-adc-apply" disabled>Сохранить калибровку</button></div><p id="api-adc-result" class="hint" role="status" aria-live="polite">Расчёт не меняет настройки. Сохранение требует подтверждения.</p><div id="api-adc-reset-actions" class="buttons"><button id="api-adc-reset" disabled>Заводская калибровка ADC</button></div></details>
      <p class="safety-note">AGC-сброс — пробная профилактика каждые 60 с с отсрочкой при активности. Мост звука требует совместимого плавающего пьезоизлучателя между двумя штатными выводами; не подключайте такой выход к земле. Возможности сборки не доказывают наличие внешнего оборудования.</p></section>
      <section id="api-wifi" class="card wide"><p class="panel-kicker">Локальная сеть</p><h2>Wi-Fi без потери настроек</h2><p class="hint">USB остаётся подключённым во время проверки. Старые данные заменяются только после успешного теста и отдельного сохранения. TCP без пароля и TLS — только доверенная сеть, без доступа из интернета.</p><form id="api-wifi-form" autocomplete="off"><label class="field" for="api-ssid">Имя сети (SSID)</label><input id="api-ssid" type="text" autocomplete="off" spellcheck="false"><label class="field" for="api-password">Пароль сети</label><input id="api-password" type="password" autocomplete="new-password"><label class="check"><input id="api-open-network" type="checkbox">Сеть без пароля — понимаю риск</label><div class="buttons"><button id="api-wifi-test" type="submit" class="primary" disabled>Проверить сеть</button><button id="api-wifi-status" type="button" disabled>Результат проверки</button><button id="api-wifi-save" type="button" disabled>Сохранить сеть</button><button id="api-wifi-cancel" type="button" disabled>Отменить</button></div></form><p id="api-wifi-state" class="hint">Доступность определяется прошивкой. Через 120 секунд бездействия проверка отменяется.</p></section>
      <section id="api-developer" class="card wide"><p class="panel-kicker">Консоль ноды</p><h2>Команды и справка</h2><p class="hint">Одна команда за раз. Ответы разрешённых команд видны здесь; в журнал не попадают. Изменения требуют подтверждения. Короткие команды и help доступны с SmartUI 0.15, ui-команды сохраняют совместимость.</p><div id="api-command-presets" class="buttons"><button type="button" data-command="help">Справка</button><button type="button" data-command="help sound">Звук и вибро</button><button type="button" data-command="help adc">ADC</button><button type="button" data-command="help radio">Радио</button><button type="button" data-command="get tx">Мощность TX</button><button type="button" data-command="set tx 20">TX: пример</button></div><label class="field" for="api-command">Команда</label><input id="api-command" type="text" autocomplete="off" spellcheck="false" placeholder="get volume"><div class="buttons"><button id="api-command-send" disabled>Выполнить</button></div><p class="hint">Кнопки выше только подставляют пример, не отправляют его. Например: get volume, set volume 7, help adc 2. Для Wi-Fi и ADC используйте формы. PIN и пароли в это поле не вводите.</p><p id="api-command-result" role="status" style="white-space:pre-wrap">Ожидает команды. Для Wi-Fi используйте форму выше: секреты в командную строку не вводите.</p></section>
      <section class="card wide"><h2>Журнал действий</h2><p class="hint">Статусы операций помощника, не события ноды. Без команд, значений и секретов.</p><ul id="api-log" class="hint" aria-label="Журнал действий"></ul><button id="api-log-clear">Очистить</button></section>
    </div>`;
  $('firmware-section').before(workspace);
  $('api-settings').dataset.pages='sound device';$('api-settings-load').dataset.pages='device';$('api-notify-test').dataset.pages='sound';$('api-adc').dataset.pages='device';
  $('api-wifi').dataset.pages='wifi';$('api-developer').dataset.pages='service';$('api-log').closest('section').dataset.pages='service';$('cli-scope').dataset.pages='service';
  const soundRead=document.createElement('button');soundRead.id='api-sound-read';soundRead.textContent='Считать звук и пины с ноды';soundRead.dataset.pages='sound';soundRead.disabled=true;$('api-notify-test').before(soundRead);
  const soundPreview=document.createElement('button');soundPreview.id='api-sound-preview';soundPreview.textContent='Прослушать мелодию';soundPreview.dataset.pages='sound';soundPreview.disabled=true;$('api-notify-test').before(soundPreview);
  const previewHint=document.createElement('p');previewHint.id='api-sound-preview-hint';previewHint.className='hint';previewHint.dataset.pages='sound';$('api-settings-fields').before(previewHint);
  const soundAction=document.createElement('p');soundAction.id='api-sound-action-status';soundAction.className='notice';soundAction.dataset.pages='sound';soundAction.setAttribute('role','status');soundAction.textContent='Считайте настройки ноды перед проверкой звука.';$('api-settings-fields').before(soundAction);
  const phrases=document.createElement('section');phrases.className='card wide';phrases.id='api-phrases';
  const transport=document.createElement('section');transport.className='card wide';transport.id='api-transport';
  transport.innerHTML='<p class="panel-kicker">Подключение</p><h2>Как приложение подключается к ноде</h2><p class="hint">Радио LoRa продолжит работать. При выборе Bluetooth или Wi-Fi текущий USB-компаньон отключится. Wi-Fi сначала настройте и сохраните ниже.</p><div class="buttons"><button id="api-mode-ble" disabled>Bluetooth</button><button id="api-mode-wifi" disabled>Wi-Fi</button><button id="api-mode-usb" disabled>USB-компаньон</button></div><p id="api-mode-result" class="setting-state" role="status">Текущий режим не прочитан.</p>';$('api-wifi').before(transport);
  transport.dataset.pages='connection';phrases.dataset.pages='phrases';
  for(const target of ['ble','wifi','usb'])$('api-mode-'+target).onclick=async()=>{
    if(!writable()||!await legacy.confirmAction('Переключить подключение на '+({ble:'Bluetooth',wifi:'Wi-Fi',usb:'USB-компаньон'}[target])+'? Текущее подключение может закрыться. Отправленный запрос не является подтверждением сохранения.'))return;
    if(!writable())return;
    $('api-mode-result').dataset.action='1';
    await run(async()=>{try{const reply=await rec('ui mode '+target,'OK ui mode',true);if(reply.target!==target||reply.state!=='pending')throw new api.CliError('PROTOCOL');
      $('api-mode-result').textContent='Запрос принят. Проверяем состояние переключения…';
      await new Promise(resolve=>setTimeout(resolve,400));
      const result=await rec('ui mode status','OK ui mode');if(result.error!=='none')throw new api.CliError('FAILED');
      if(result.pending!=='none'){$('api-mode-result').textContent='Запрос ещё обрабатывается. Проверьте режим на ноде; сохранение пока не подтверждено.';return;}
      connectionState=await rec('ui connection','OK ui connection');
      $('api-mode-result').textContent=connectionState.mode===target?'Режим подтверждён нодой: '+target+'.':'Переключение не подтверждено. На ноде: '+connectionState.mode+'.';
    }catch(error){$('api-mode-result').textContent='Связь прервалась либо переключение не подтверждено. Проверьте режим на ноде и подключитесь заново. Автоматического повтора не было.';throw error;}});
  };
  phrases.innerHTML='<p class="panel-kicker">Сообщения</p><h2>Свои быстрые фразы</h2><details id="api-phrases-panel"><summary>Настроить 9 быстрых фраз</summary><p class="hint">9 фраз, до 64 байт UTF-8 каждая. Пустое поле возвращает стандартную фразу. Сообщения из эфира не читаются и не отправляются.</p><button id="api-phrases-load" disabled>Прочитать фразы</button><p id="api-phrases-status" role="status">Нужна SmartUI 0.16.</p><div id="api-phrase-fields"></div></details>';
  $('api-developer').before(phrases);
  const filter=document.createElement('div');filter.className='settings-filter';filter.innerHTML='<input id="api-settings-filter" type="text" placeholder="Найти настройку: звук, pin, GPS…" aria-label="Поиск настроек CLI"><label class="check"><input id="api-settings-advanced" type="checkbox">Расширенные настройки</label><label class="check"><input id="api-settings-unavailable" type="checkbox">Показать недоступные</label>';$('api-settings-fields').before(filter);
  const notifyState=document.createElement('p');notifyState.id='api-notify-state';notifyState.className='notice';notifyState.setAttribute('role','status');filter.before(notifyState);
  notifyState.dataset.pages='sound';
  function filterSettings(){
    const text=$('api-settings-filter').value.trim().toLowerCase();
    for(const row of $('api-settings-fields').querySelectorAll('.setting-row'))row.hidden=!(row.dataset.search||'').includes(text)||row.dataset.supported==='false'&&!$('api-settings-unavailable').checked||(!text&&!$('api-settings-advanced').checked&&row.dataset.advanced==='true');
    for(const panel of $('api-settings-fields').children)panel.hidden=![...panel.querySelectorAll('.setting-row')].some(row=>!row.hidden);
  }
  $('api-settings-filter').oninput=filterSettings;$('api-settings-unavailable').onchange=filterSettings;$('api-settings-advanced').onchange=filterSettings;
  const phraseValues=Array(9).fill(null),phraseEdits=new Set();
  for(let slot=1;slot<=9;slot++){
    const row=document.createElement('div');row.className='reply-row';const label=document.createElement('label');label.className='field';label.htmlFor='api-phrase-'+slot;label.textContent='Фраза '+slot;
    const input=document.createElement('input');input.id='api-phrase-'+slot;input.type='text';input.autocomplete='off';input.disabled=true;
    const save=document.createElement('button');save.id='api-phrase-save-'+slot;save.textContent='Сохранить фразу '+slot;save.disabled=true;
    const status=document.createElement('p');status.id='api-phrase-state-'+slot;status.className='setting-state';status.textContent='Не прочитано';
    input.oninput=()=>{phraseEdits.add(slot);status.textContent=new TextEncoder().encode(input.value).length+' / 64 байта · Не сохранено';renderShell();};
    save.onclick=async()=>{
      const value=input.value,bytes=new TextEncoder().encode(value);if(bytes.length>64||/[\x00-\x1f\x7f]/.test(value)||new TextDecoder().decode(bytes)!==value){status.textContent='Не более 64 байт UTF-8, без управляющих символов.';return;}
      if(!value&&!await legacy.confirmAction('Вернуть стандартную фразу '+slot+'?'))return;
      await run(async()=>{let acknowledged=false;try{status.textContent='Сохраняем и проверяем…';const reply=await rec('ui reply set '+slot+' '+(api.toHex(value)||'-'),'OK ui reply_saved',true);acknowledged=true;
        if(Number(reply.slot)!==slot)throw new api.CliError('PROTOCOL');const actual=await readPhrase(slot);if(actual!==value)throw new api.CliError('PROTOCOL');phraseEdits.delete(slot);phraseValues[slot-1]=actual;status.textContent='Сохранено и прочитано обратно';
      }catch(error){status.textContent=error.safe?error.message:'Сохранение не подтверждено';if(acknowledged){client.update({uncertain:true,phase:'uncertain'});throw new api.CliError('UNCERTAIN');}throw error;}});
    };
    row.append(label,input,save,status);$('api-phrase-fields').append(row);
  }
  async function readPhrase(slot){const reply=await rec('ui reply get '+slot,'OK ui reply');if(Number(reply.slot)!==slot)throw new api.CliError('PROTOCOL');const value=api.decodeHex(reply.hex,64);if(/[\x00-\x1f\x7f]/.test(value))throw new api.CliError('PROTOCOL');return value;}
  $('api-phrases-load').onclick=()=>run(async()=>{for(let slot=1;slot<=9;slot++){const value=await readPhrase(slot);phraseValues[slot-1]=value;if(!phraseEdits.has(slot))$('api-phrase-'+slot).value=value;$('api-phrase-state-'+slot).textContent=phraseEdits.has(slot)?'Есть несохранённый ввод':'Прочитано с ноды';}$('api-phrases-status').textContent='Фразы прочитаны. Каждая сохраняется отдельно.';});
  const serviceBox=$('adc-service-box').cloneNode(true);
  for(const element of [serviceBox,...serviceBox.querySelectorAll('[id]')])element.id='api-'+element.id;
  $('api-adc').append(serviceBox);
  const manualBox=$('adc-manual-fields').cloneNode(true);
  for(const element of [manualBox,...manualBox.querySelectorAll('[id]')])element.id='api-'+element.id;
  manualBox.querySelector('label').htmlFor='api-adc-manual-value';
  manualBox.querySelector('input').setAttribute('aria-describedby','api-adc-manual-hint api-adc-manual-result');
  $('api-adc-reset-actions').before(manualBox);
  $('api-adc-source-warning').textContent=$('adc-source-warning').textContent;
  const CAP_KEYS=['v','adc','sound','board_led','unread_led','vibration','gps','battery_protection','display','melody_max','adc_min','adc_max','agc_reset','fem_lna','fem_pa','bridge','melody_names','adc_service','schema','sound_preview'];
  const GET_KEYS=['battery_mv','adc_multiplier','adc_default','sound_quiet','volume','melody','board_led','unread_led','vibration','gps','battery_protection','shutdown_mv','muted','agc_reset','fem_lna','fem_pa','bridge'];
  const OPTIONAL_CAPS=new Set(['agc_reset','fem_lna','fem_pa','bridge','melody_names','adc_service','schema','sound_preview']),OPTIONAL_GET=new Set(['agc_reset','fem_lna','fem_pa','bridge']);
  function note(text,kind='info'){$('api-feedback').textContent=text;$('api-feedback').className='notice'+(kind==='error'?' error':kind==='warning'?' warning':'');}
  function log(text){const li=document.createElement('li');li.textContent=new Date().toLocaleTimeString('ru-RU')+' · '+text;$('api-log').prepend(li);while($('api-log').children.length>40)$('api-log').lastChild.remove();}
  const available=()=>mode==='api'&&binaryState.connected&&binaryState.phase==='ready'&&!binaryState.busy&&!running&&!choosing&&!networkRunning;
  const writable=()=>available()&&binaryState.hello?.write==='1';
  function renderShell(){
    const s=mode==='api'?binaryState:legacy.getState(),busy=Boolean(s.busy||running||networkRunning||choosing||(mode==='api'&&(client.opening||client.closing||(!s.connected&&client.session))));
    $('helper-mode').disabled=Boolean(s.connected||busy);
    $('connect').disabled=!window.isSecureContext||!navigator.serial||Boolean(s.connected||busy);
    $('disconnect').disabled=!s.connected||choosing;
    $('connect').textContent=choosing?'Выберите порт…':acknowledgedLoss?'Переподключить USB':'Выбрать USB-порт';
    const phases={opening:'Открываем USB-порт…',negotiating:'Проверяем локальный CLI…',ready:running||s.busy?'Выполняется операция…':'USB-компаньон подключён',uncertain:'Результат неизвестен — требуется переподключение',disconnected:'Нода не подключена'};
    $('transport-state').textContent=mode==='api'?phases[s.phase]||'Нода не подключена':s.busy?'Выполняется операция…':s.verified?'Консоль SmartUI подключена':s.connected?'Порт открыт; консоль не подтверждена':'Нода не подключена';
    $('transport-help').textContent=mode==='api'?'На ноде выберите USB-компаньон. Локальные команды CMD66, без чтения сообщений.':'На ноде выберите Bluetooth или Wi-Fi. Помощник подключается USB-кабелем; телефон и сопряжение не нужны.';
    connectionMeta.textContent=binaryState.hello?'SmartUI '+(binaryState.hello.firmware||'—')+' · '+(binaryState.hello.write==='1'?'Изменения разрешены':'Только чтение')+(connectionState?' · Режим: '+connectionState.mode:''):'';
    for(const id of ['api-settings-load','api-sound-read','api-command-send'])$(id).disabled=!available();
    $('api-notify-test').disabled=!writable()||!settings||!['sound','vibration','board_led','unread_led'].some(key=>caps?.[key]==='1');
    soundPreview.disabled=!writable()||!settings||caps?.sound_preview!=='1'||caps?.sound!=='1';
    previewHint.textContent=!settings?'Сначала считайте настройки звука.':caps?.sound_preview!=='1'?'Для отдельного прослушивания нужен обновлённый UF2/BIN 0.16. Старый тест уведомления не играет мелодию при выключенном звуке.':'Прослушивание: сохранённая мелодия один раз, без включения уведомлений. «Общая тишина» должна быть выключена.';
    notifyState.textContent=SmartUiConsole.notificationStatus(settings,caps);
    if(!binaryState.connected){soundAction.textContent='Подключите ноду и считайте звук и пины.';delete soundAction.dataset.action;}
    else if(settings&&!soundAction.dataset.action)soundAction.textContent='Показаны настройки, прочитанные с ноды. «Считать звук и пины» обновит их.';
    const wifi=wifiState?.supported==='1';$('api-wifi').hidden=wifiState?.supported==='0';
    for(const target of ['ble','wifi','usb']){$('api-mode-'+target).disabled=!writable()||!(Number(connectionState?.caps)&({ble:1,usb:2,wifi:4}[target]))||connectionState?.mode===target||target==='wifi'&&wifiState?.configured!=='1';$('api-mode-'+target).setAttribute('aria-pressed',String(connectionState?.mode===target));}
    if(!binaryState.connected){$('api-mode-result').textContent='Текущий режим не прочитан.';delete $('api-mode-result').dataset.action;}
    else if(connectionState&&!$('api-mode-result').dataset.action)$('api-mode-result').textContent='Текущий режим: '+({ble:'Bluetooth',wifi:'Wi-Fi',usb:'USB-компаньон'}[connectionState.mode]||connectionState.mode)+'.';
    for(const id of ['api-ssid','api-password','api-open-network','api-wifi-test','api-wifi-cancel'])$(id).disabled=!writable()||!wifi;
    $('api-wifi-status').disabled=!available()||!wifi;
    $('api-wifi-save').disabled=!writable()||!wifi||wifiState?.state!=='test_ok';
    for(const el of $('api-settings-fields').querySelectorAll('select,input,button'))el.disabled=!writable()||!settings||el.dataset.supported==='false'||Boolean(el.dataset.settingKey&&!settingEdits.has(el.dataset.settingKey));
    $('api-phrases-load').disabled=!available()||caps?.schema!=='1';
    for(let slot=1;slot<=9;slot++){
      $('api-phrase-'+slot).disabled=!writable()||phraseValues[slot-1]===null;
      $('api-phrase-save-'+slot).disabled=!writable()||phraseValues[slot-1]===null||!phraseEdits.has(slot);
      if(!binaryState.connected){phraseValues[slot-1]=null;phraseEdits.delete(slot);$('api-phrase-'+slot).value='';}
    }
    $('api-adc-preview').disabled=!writable()||caps?.adc!=='1';
    $('api-adc-reset').disabled=!writable()||caps?.adc!=='1';
    $('api-adc-apply').disabled=!writable()||!preview||Date.now()>=preview.expires;
    $('api-adc-manual-value').disabled=!writable()||!adcManualSupported;
    $('api-adc-manual-save').disabled=!writable()||!adcManualSupported||!$('api-adc-manual-value').value.trim();
    $('api-adc-manual-hint').textContent=binaryState.hello?.write==='0'?'Запись недоступна: нода сообщает режим только для чтения.':adcManualSupported?'Правильный множитель уже известен? Сохраните напрямую, без опорного замера. Не подбирайте значение наугад.':'Прямой ввод не поддерживается этой прошивкой. Обновите SmartUI до актуальной версии; расчёт по мультиметру остаётся доступен.';
    $('api-adc-service-box').hidden=caps?.adc_service!=='1';
    $('api-adc-service-start').disabled=!writable()||caps?.adc_service!=='1'||!adcService?.external||Boolean(adcService?.active);
    $('api-adc-service-stop').disabled=!available()||!adcService?.active;
    $('api-adc-service-refresh').disabled=!available()||caps?.adc_service!=='1';
    $('api-adc-service-status').textContent=!adcService?'Состояние окна не подтверждено. Нажмите «Проверить окно».':adcService.active
      ?'Окно активно · осталось по данным ноды: '+Math.ceil(adcService.remaining_ms/1000)+' с. Проверяем каждые 5 секунд.'
      :adcService.external?'Окно выключено. Обычная защита питания действует.':'Окно выключено. Нода не подтвердила питание USB.';
    renderNetworkControls();
    renderPages();
  }
  async function run(operation){
    if(running)return;running=true;renderShell();
    try{await operation();}catch(error){
      if(error?.code==='PROTOCOL'&&binaryState.connected)client.update({uncertain:true,phase:'uncertain'});
      note(error?.safe?error.message:'Операция не завершена. Сырые ответы не отображаются.','error');
    }finally{running=false;renderShell();}
  }
  const client=new api.CliClient({
    onState(next){const lost=binaryState.connected&&!next.connected;binaryState=next;if(!next.connected){$('api-password').value='';$('api-adc-measured').value='';$('api-adc-manual-value').value='';adcManualSupported=false;preview=null;adcService=null;caps=null;settings=null;settingEdits.clear();melodyNames.clear();if(next.uncertain)acknowledgedLoss=true;}if(next.uncertain){adcService=null;preview=null;}renderShell();if(lost){for(const id of ['api-adc-result','api-adc-manual-result'])adcNote(adcOperation?.id===id?'USB отключён. Сохранение не подтверждено; переподключитесь и прочитайте ADC.':'USB отключён. Подключите ноду для проверки ADC.',adcOperation?.id===id?'error':'info',id);}},
    onEvent({action,result}){log(result==='ok'?(action==='write'?'Ответ на изменение получен; проверяем результат.':action==='connect'?'Локальный CLI подключён.':'Ответ на чтение получен.'):result==='not_supported'?'Дополнительная возможность не поддерживается этой сборкой.':result==='FAILED'?'Нода ответила отказом. Подробности — в текущем разделе.':'Операция не подтверждена.');}
  });
  const rec=async(command,prefix,mutate=false)=>api.record(await client.execute(command,{mutate}),prefix);
  const exact=async(command,expected)=>{if(await client.execute(command,{mutate:true})!==expected)throw new api.CliError('PROTOCOL');};
  async function readAdcService(action=''){
    const session=client.session;
    try{
      const value=SmartUiConsole.parseAdcService(await client.execute('ui adc service'+(action?' '+action:''),{mutate:action==='start'}),'ui');
      if(session!==client.session||!binaryState.connected)throw new api.CliError('CLOSED');
      if(!value||action==='start'&&!value.active||action==='stop'&&value.active)throw new api.CliError('PROTOCOL');
      if(adcService?.active&&!value.active){preview=null;$('api-adc-result').textContent='Сервисное окно завершено. Несохранённый расчёт отменён.';}
      adcService={...value,receivedAt:Date.now()};return value;
    }catch(error){if(session===client.session){adcService=null;preview=null;}throw error;}
  }
  function numeric(value,max=0xffffffff){if(!/^\d+$/.test(value)||Number(value)>max)throw new api.CliError('PROTOCOL');return Number(value);}
  const networkReady=()=>{
    const state=legacy.getState();
    return !networkRunning&&(mode==='api'?available():state.connected&&state.verified&&!state.busy&&!state.testPassed);
  };
  const networkWritable=()=>networkReady()&&(mode==='api'?binaryState.hello?.write==='1':!legacy.getState().status?.readOnly);
  function networkNote(text,kind='info'){$('radio-status').textContent=text;$('radio-status').dataset.kind=kind;}
  function radioText(r){return (r.freq_khz/1000).toFixed(3)+' МГц · BW '+(r.bw_hz/1000)+' кГц · SF'+r.sf+' · CR 4/'+r.cr;}
  function renderNetworkControls(){
    const ready=networkReady(),write=networkWritable();
    $('radio-refresh').disabled=!ready;
    $('preset-apply').disabled=!write||!radioState||radioSupport!==true||!catalog?.get($('preset-city').value);
    $('advert-interval').disabled=!write||!advertState||advertSupport!==true;
    $('advert-save').disabled=!write||!advertState||advertSupport!==true||Number($('advert-interval').value)===advertState.interval_min;
    $('path-bytes').disabled=!write||!radioState||radioSupport!==true;
    $('path-save').disabled=!write||!radioState||radioSupport!==true||Number($('path-bytes').value)===radioState.path_bytes;
    for(const [kind,state]of [['name',identityState],['tx',txState]]){
      $('node-'+kind).disabled=!write||!state;$('node-'+kind+'-save').disabled=!write||!state||!coreEdits.has(kind);
    }
    const s=mode==='api'?binaryState:legacy.getState();
    $('radio-capability').textContent=!s.connected?'Ожидает подключения':networkRunning?'Проверяем настройки…':!ready?'Соединение занято':radioSupport===false?'Нужна поддержка прошивки':!write?'Только чтение':radioState?'Готово к настройке':'Не прочитано';
  }
  function resetNetwork(){radioState=null;advertState=null;identityState=null;txState=null;pathEdited=false;$('path-current').textContent='Сначала подключите ноду.';coreEdits.clear();for(const kind of ['name','tx']){$('node-'+kind).value='';$('node-'+kind+'-status').textContent='Не прочитано';}radioSupport=null;advertSupport=null;$('radio-current').textContent='Настройки ноды ещё не прочитаны.';$('advert-current').textContent='Сначала подключите ноду.';renderNetworkControls();}
  function showNetworkState(){
    $('radio-current').textContent=radioState?'Сейчас на ноде: '+radioText(radioState)+' · '+radioState.tx_dbm+' дБм · хеш '+radioState.path_bytes+' байт.':radioSupport===false?'Сборка не поддерживает чтение городского пресета. Остальные инструменты работают.':'Настройки радио не подтверждены.';
    $('advert-current').textContent=advertState?'На ноде: '+(advertState.interval_min?'каждые '+advertState.interval_min+' мин':'выключен')+'.':advertSupport===false?'Автоанонс недоступен в этой сборке.':'Интервал не прочитан.';
    if(advertState)$('advert-interval').value=String(advertState.interval_min);
    if(radioState){if(!pathEdited)$('path-bytes').value=String(radioState.path_bytes);$('path-current').textContent='На ноде: '+radioState.path_bytes+' байт.'+(pathEdited?' Есть несохранённое изменение.':'');}
    renderNetworkControls();
  }
  async function readNetwork(kind){
    if(mode==='console')return legacy.client.loadNetworkSetting(kind);
    const value=SmartUiConsole.parseNetworkSetting(await client.execute('ui '+kind),kind,'ui');
    if(!value)throw new api.CliError('PROTOCOL');return value;
  }
  async function saveNetwork(kind,values,{pathOnly=false}={}){
    if(pathOnly?kind!=='radio'||![1,2,3].includes(values?.path_bytes):!SmartUiConsole.networkValuesValid(kind,values))throw new api.CliError('INPUT');
    if(mode==='console')return legacy.client.saveNetworkSetting(kind,values,{pathOnly});
    const keys=kind==='radio'?['freq_khz','bw_hz','sf','cr','path_bytes']:['interval_min'];
    const before=await readNetwork(kind);
    if(kind==='radio')values=pathOnly?{...before,path_bytes:values.path_bytes}:{...values,path_bytes:before.path_bytes};
    let acknowledged=false;
    try{
      const text=await client.execute('ui '+kind+' set '+keys.map(k=>values[k]).join(' '),{mutate:true});acknowledged=true;
      const ack=SmartUiConsole.parseNetworkSetting(text,kind,'ui');
      if(!ack||keys.some(k=>ack[k]!==values[k]))throw new api.CliError('PROTOCOL');
      const saved=await readNetwork(kind);
      if(keys.some(k=>saved[k]!==values[k])||kind==='radio'&&(saved.tx_dbm!==before.tx_dbm||saved.repeat!==before.repeat))throw new api.CliError('PROTOCOL');
      return saved;
    }catch(error){
      if(acknowledged){client.update({uncertain:true,phase:'uncertain'});throw new api.CliError('UNCERTAIN');}throw error;
    }
  }
  async function networkOperation(operation){
    if(networkRunning)return;networkRunning=true;renderShell();
    try{await operation();}catch(error){
      if((error.code==='PROTOCOL'||error.reason==='restore')&&mode==='api'&&binaryState.connected)client.update({uncertain:true,phase:'uncertain'});
      if(mode==='api'?binaryState.uncertain:!legacy.getState().verified){radioState=null;advertState=null;showNetworkState();}
      networkNote(error.safe?error.message:'Не удалось подтвердить операцию. Прочитайте настройки заново.','error');
    }finally{networkRunning=false;renderShell();}
  }
  async function loadNetwork(){
    for(const kind of ['radio','advert']){
      try{const value=await readNetwork(kind);if(kind==='radio'){radioState=value;radioSupport=true;}else{advertState=value;advertSupport=true;}}
      catch(error){
        if(error.reason==='unsupported'||error.reason==='invalid'||['SETTINGS_UNSUPPORTED','SETTINGS_UNAVAILABLE'].includes(error.code)){
          if(kind==='radio'){radioState=null;radioSupport=false;}else{advertState=null;advertSupport=false;}
        }else{if(kind==='radio')radioState=null;else advertState=null;showNetworkState();throw error;}
      }
    }
    if(mode==='api'?caps?.schema==='1':Object.keys(legacy.getState().settingSchemas||{}).length){
      identityState=await readCore('identity');txState=await readCore('tx');showCore();
    }
    showNetworkState();networkNote(radioState?'Текущие параметры прочитаны. Выберите город и подтвердите применение.':'Для городских пресетов нужна SmartUI 0.13 или новее; остальные настройки доступны.',radioState?'info':'warning');
  }
  async function readCore(kind){if(mode==='console')return legacy.client.readCoreSetting(kind);const value=SmartUiConsole.parseCoreSetting(await client.execute('ui '+kind),kind,'ui');if(!value)throw new api.CliError('PROTOCOL');return value;}
  function showCore(){
    if(identityState){if(!coreEdits.has('name'))$('node-name').value=identityState.name;$('node-name-status').textContent='На ноде: '+identityState.name;}
    if(txState){const input=$('node-tx');input.min=txState.min;input.max=txState.max;if(!coreEdits.has('tx'))input.value=txState.value;$('node-tx-status').textContent='На ноде: '+txState.value+' дБм · допустимо '+txState.min+'…'+txState.max;}
  }
  for(const field of ['name','tx']){
    $('node-'+field).oninput=()=>{coreEdits.add(field);$('node-'+field+'-status').textContent='Изменение ещё не сохранено';renderNetworkControls();};
    $('node-'+field+'-save').onclick=async()=>{
      if(!networkWritable())return;const input=$('node-'+field),raw=input.value,value=field==='name'?raw:Number(raw),kind=field==='name'?'identity':'tx';
      if(field==='name'&&(!raw||new TextEncoder().encode(raw).length>31||/[\x00-\x1f\x7f]/.test(raw))||field==='tx'&&(!raw||!Number.isInteger(value)||value<txState.min||value>txState.max)){$('node-'+field+'-status').textContent='Проверьте значение: оно не соответствует ограничениям ноды.';return;}
      if(!await legacy.confirmAction(field==='name'?'Сохранить новое имя ноды?':'Сохранить мощность '+value+' дБм? Проверьте допустимую мощность для своего региона и антенны.'))return;
      if(!networkWritable()||input.value!==raw)return;
      await networkOperation(async()=>{let ack=false;try{
        $('node-'+field+'-status').textContent='Сохраняем и проверяем…';let saved;
        if(mode==='console')saved=await legacy.client.saveCoreSetting(kind,value);
        else{
          const hex=field==='name'?api.toHex(value):null,text=await client.execute(field==='name'?'ui name '+hex:'ui tx set '+value,{mutate:true});ack=true;
          if(field==='name'?text!=='OK ui name name_hex='+hex:SmartUiConsole.parseCoreSetting(text,'tx','ui')?.value!==value)throw new api.CliError('PROTOCOL');
          saved=await readCore(kind);if((field==='name'?saved.name:saved.value)!==value)throw new api.CliError('PROTOCOL');
        }
        if(field==='name')identityState=saved;else txState=saved;coreEdits.delete(field);showCore();$('node-'+field+'-status').textContent+=' · Сохранено и проверено';
      }catch(error){$('node-'+field+'-status').textContent=error.safe?error.message:'Сохранение не подтверждено';if(ack){client.update({uncertain:true,phase:'uncertain'});throw new api.CliError('UNCERTAIN');}throw error;}});
    };
  }
  function populateCities(){
    const selected=$('preset-city').value,records=catalog?.list($('preset-search').value)||[];
    $('preset-city').replaceChildren(new Option(records.length?'Выберите город':'Город не найден',''));
    for(const city of records)$('preset-city').append(new Option(city.name+' · '+city.code,city.id));
    if(records.some(city=>city.id===selected))$('preset-city').value=selected;
    previewCity();
  }
  function previewCity(){
    const box=$('preset-preview'),city=catalog?.get($('preset-city').value);box.replaceChildren();
    const title=document.createElement('strong'),description=document.createElement('p');
    title.textContent=city?city.name+' · '+city.code:'Сначала выберите город';
    description.textContent=city?'Параметры из снимка MeshCoreTel. Ещё не применены.':'Параметры появятся здесь. Текущие настройки ноды сохраняются до подтверждения.';
    box.append(title,description);
    if(city){const chips=document.createElement('div');chips.className='radio-chips';for(const text of [city.frequencyMHz.toFixed(3)+' МГц','BW '+city.bandwidthKHz+' кГц','SF'+city.sf,'CR 4/'+city.cr]){const span=document.createElement('span');span.textContent=text;chips.append(span);}box.append(chips);}
    renderNetworkControls();
  }
  $('preset-search').oninput=populateCities;$('preset-city').onchange=previewCity;
  $('advert-interval').onchange=renderNetworkControls;
  $('path-bytes').onchange=()=>{pathEdited=Boolean(radioState&&Number($('path-bytes').value)!==radioState.path_bytes);showNetworkState();};
  $('path-save').onclick=async()=>{
    if(!networkWritable()||!radioState)return;
    const value=Number($('path-bytes').value),session=mode==='api'?client.session:legacy.client._session;
    if(![1,2,3].includes(value)||value===radioState.path_bytes)return;
    if(!await legacy.confirmAction('Сохранить длину хеша маршрута: '+value+' байт? Меняется только формат маршрута. Частота, полоса, SF, CR, мощность и ретрансляция останутся прежними.'))return;
    if(!networkWritable()||session!==(mode==='api'?client.session:legacy.client._session)||Number($('path-bytes').value)!==value)return;
    await networkOperation(async()=>{radioState=await saveNetwork('radio',{path_bytes:value},{pathOnly:true});pathEdited=false;showNetworkState();networkNote('Хеш маршрута сохранён и прочитан обратно: '+value+' байт. Остальные параметры радио проверены.');});
  };
  $('radio-refresh').onclick=()=>{if(networkReady())networkOperation(loadNetwork);};
  $('preset-apply').onclick=async()=>{
    if(!networkWritable()||!radioState)return;const city=catalog?.get($('preset-city').value);if(!city)return;
    const values={freq_khz:city.frequencyKHz??Math.round(city.frequencyMHz*1000),bw_hz:city.bandwidthHz??Math.round(city.bandwidthKHz*1000),sf:city.sf,cr:city.cr,path_bytes:radioState.path_bytes};
    if(!await legacy.confirmAction('Применить пресет «'+city.name+'»: '+radioText(values)+'? Нода перейдёт в другой эфир. Мощность, FEM, ретрансляция и хеш маршрута не меняются. Убедитесь, что параметры разрешены в вашем регионе.'))return;
    if(!networkWritable())return;
    await networkOperation(async()=>{radioState=await saveNetwork('radio',values);showNetworkState();networkNote('Пресет «'+city.name+'» сохранён и прочитан обратно с ноды.');});
  };
  $('advert-save').onclick=async()=>{
    if(!networkWritable()||!advertState)return;const interval=Number($('advert-interval').value);
    if(!await legacy.confirmAction(interval?'Сохранить автоанонс каждые '+interval+' минут? Отсчёт следующего анонса начнётся заново.':'Выключить периодический автоанонс? Ручной анонс останется доступен.'))return;
    if(!networkWritable())return;
    await networkOperation(async()=>{advertState=await saveNetwork('advert',{interval_min:interval});showNetworkState();networkNote('Интервал автоанонса сохранён и прочитан обратно с ноды.');});
  };
  if(catalog){const stamp=new Date(catalog.metadata.snapshotAt);$('preset-source').textContent='Снимок каталога: '+(Number.isNaN(stamp.getTime())?catalog.metadata.snapshotAt:stamp.toLocaleDateString('ru-RU'))+' · '+catalog.list().length+' городов. Автономно; параметры сообщества могут меняться.';}
  populateCities();
  async function readFields(kind,keys,optional){
    const result=Object.create(null);
    for(const key of keys){
      try{const reply=await rec('ui '+kind+' '+key,'OK ui '+kind);
        if(reply.key!==key||typeof reply.value!=='string'||!/^[-+]?\d+(?:\.\d+)?$/.test(reply.value)||!Number.isFinite(Number(reply.value)))throw new api.CliError('PROTOCOL');
        result[key]=reply.value;
      }catch(error){if(optional.has(key)&&(error.reason==='unsupported'||['adc_service','schema','sound_preview'].includes(key)&&error.reason==='invalid'))result[key]='0';else throw error;}
    }
    return result;
  }
  const fields=[['muted',null,'Общая тишина',0,1],['sound_quiet','sound','Звук уведомлений ЛС',0,1],['volume','sound','Громкость',1,10],['melody','sound','Общая мелодия',0,30],['board_led','board_led','LED платы',0,1],['unread_led','unread_led','LED уведомлений',0,1],['vibration','vibration','Вибрация',0,1],['gps','gps','Аппаратный GPS',0,1],['battery_protection','battery_protection','Защита АКБ 3,2 В',0,1],['agc_reset','agc_reset','AGC-сброс · каждые 60 с',0,1],['fem_lna','fem_lna','FEM · усилитель приёма',0,1],['fem_pa','fem_pa','FEM · усилитель передачи',0,1],['bridge','bridge','Мостовой звук · два вывода',0,1]];
  async function loadSettings({discardEdits=false}={}){
    try {
    caps=await readFields('caps',CAP_KEYS,OPTIONAL_CAPS);settings=await readFields('get',GET_KEYS,OPTIONAL_GET);preview=null;if(discardEdits)settingEdits.clear();
    schemas=Object.create(null);
    if(caps.schema==='1')for(const key of SmartUiConsole.SETTING_KEYS){
      const schema=SmartUiConsole.parseSettingSchema(await client.execute('ui schema '+key),key,'ui');if(!schema)throw new api.CliError('PROTOCOL');schemas[key]=schema;
      if(schema.supported){const value=SmartUiConsole.parseSettingValue(await client.execute('ui get '+key),key,'ui');if(!SmartUiConsole.settingValueValid(schema,value))throw new api.CliError('PROTOCOL');settings[key]=String(value);}
    }
    // Reuse the strict legacy value schema for the shared subset. API extensions
    // are additive; the same battery and capability safety checks still apply.
    const line=(prefix,keys,values)=>prefix+' '+keys.map(k=>k+'='+values[k]).join(' ');
    const capKeys=['v','adc','sound','board_led','unread_led','vibration','gps','battery_protection','display','melody_max','adc_min','adc_max'];
    const valueKeys=['battery_mv','adc_multiplier','adc_default','sound_quiet','volume','melody','board_led','unread_led','vibration','gps','battery_protection','shutdown_mv','muted'];
    const sharedCaps=SmartUiConsole.parseSettingsCaps(line('OK settings caps',capKeys,caps));
    if(!sharedCaps||!SmartUiConsole.parseDeviceSettings(line('OK settings get',valueKeys,settings),sharedCaps)||!['0','1'].includes(caps.adc_service))throw new api.CliError('PROTOCOL');
    if(caps.adc_service==='1')await readAdcService();else adcService=null;
    adcManualSupported=false;
    if(caps.adc==='1'&&binaryState.hello?.write==='1')try{
      const manual=SmartUiConsole.parseAdcManual(await client.execute('ui adc manual'),'ui');
      if(!manual)throw new api.CliError('PROTOCOL');adcManualSupported=Boolean(manual.supported);
    }catch(error){if(!['invalid','unsupported'].includes(error.reason))throw error;}
    if(caps.melody_names==='1'&&caps.sound==='1'){
      const maximum=numeric(caps.melody_max,255);
      for(let id=0;id<=maximum;id++)if(!melodyNames.has(id)){
        const melody=await rec('ui melody '+id,'OK ui melody');if(numeric(melody.id,255)!==id)throw new api.CliError('PROTOCOL');
        const name=api.decodeHex(melody.name_hex,64);if(!name||/[\u0000-\u001f\u007f]/.test(name))throw new api.CliError('PROTOCOL');melodyNames.set(id,name);
      }
    }
    const container=$('api-settings-fields');container.replaceChildren();
    const groups={sound:'Звук и уведомления',lights:'Свет и вибрация',display:'Экран и оформление',gps:'Координаты',battery:'Аккумулятор',system:'Система и FEM'},panels={};
    for(const [group,title]of Object.entries(groups)){const panel=document.createElement('section');panel.className='device-panel';panel.dataset.pages=['sound','lights'].includes(group)?'sound':'device';const heading=document.createElement('h3');heading.textContent=title;panel.append(heading);panels[group]=panel;container.append(panel);}
    const extra=SmartUiConsole.EXTENDED_FIELDS.filter(f=>!fields.some(row=>row[0]===f.key));
    for(const[key,cap,label,min,maxDefault]of fields.concat(extra.map(f=>[f.key,null,f.label,0,1]))){
      const meta=SmartUiConsole.EXTENDED_FIELDS.find(f=>f.key===key),schema=schemas[key];
      if(!schema&&(meta&&!fields.some(row=>row[0]===key)||cap&&caps[cap]!=='1'))continue;
      const max=key==='melody'?numeric(caps.melody_max,255):maxDefault;
      const supported=schema?schema.supported:true,current=supported?Number(settings[key]):null;
      if(supported&&!(schema?SmartUiConsole.settingValueValid(schema,current):Number.isInteger(current)&&current>=min&&current<=max))throw new api.CliError('PROTOCOL');
      const row=document.createElement('div');row.className='setting-row';row.dataset.advanced=String(SmartUiConsole.ADVANCED_SETTING_KEYS.includes(key));row.dataset.search=(label+' '+key).toLowerCase();row.dataset.supported=String(supported);const caption=document.createElement('label');caption.htmlFor='api-setting-'+key;caption.textContent=label;
      const options=schema?SmartUiConsole.settingOptions({key},schema,Object.fromEntries(melodyNames)):Array.from({length:max-min+1},(_,i)=>[i+min,key==='sound_quiet'?(i?'Выключен':'Включён'):key==='melody'?(melodyNames.has(i+min)?(i+min)+' · '+melodyNames.get(i+min):'Мелодия '+(i+min)):max===1?(i?'Включено':'Выключено'):String(i+min)]);
      const controls=document.createElement('div');controls.className='setting-controls';const select=document.createElement(options?'select':'input');select.id='api-setting-'+key;select.dataset.supported=String(supported);
      if(options)for(const [value,text]of options){const option=document.createElement('option');option.value=String(value);option.textContent=text;select.append(option);}
      else{select.type='number';select.min=schema.min;select.max=schema.max;select.step=schema.step;}
      select.value=supported?String(current):'';const storedLabel=select.selectedOptions?.[0]?.textContent||String(current);
      if(settingEdits.has(key)&&Number(settingEdits.get(key))!==current)select.value=settingEdits.get(key);else settingEdits.delete(key);
      const save=document.createElement('button');save.textContent='Сохранить';save.setAttribute('aria-label','Сохранить CLI: '+label);save.dataset.supported=String(supported);save.dataset.settingKey=key;
      const status=document.createElement('p');status.className='setting-state';status.id='api-saved-'+key;status.textContent=!supported?'Недоступно на этой плате или в этой сборке':'На ноде: '+storedLabel+(settingEdits.has(key)?' · Изменение не сохранено':' · Прочитано')+(key.endsWith('_pin')?' · Только разрешённые прошивкой выводы.':'');status.dataset.dirty=String(settingEdits.has(key));
      select.onchange=()=>{const dirty=Number(select.value)!==Number(settings[key]);if(dirty)settingEdits.set(key,select.value);else settingEdits.delete(key);status.textContent=dirty?'Изменение не сохранено':'На ноде: '+storedLabel+' · Прочитано';status.dataset.dirty=String(dirty);$('api-settings-status').textContent=settingEdits.size?'Есть несохранённые поля: '+settingEdits.size:'Прочитано с ноды';renderShell();};
      if(select.tagName==='INPUT')select.oninput=select.onchange;
      save.onclick=async()=>{
        const value=Number(select.value);if(value===Number(settings[key]))return;
        if(schema&&!SmartUiConsole.settingValueValid(schema,value)){status.textContent='Значение не входит в допустимые варианты платы.';return;}
        if(key.endsWith('_pin')&&!await legacy.confirmAction('Изменить '+label.toLowerCase()+' на '+value+'? Номера — выводы прошивки, не номера ножек корпуса. Проверьте проводку. LED требует резистор, вибромотор — совместимый драйвер.'))return;
        if(key==='profile'&&!await legacy.confirmAction('Применить профиль? Несколько настроек звука и индикации изменятся сразу.'))return;
        if((key==='battery_protection'&&value===0||key==='bridge'&&value===1)&&!await legacy.confirmAction(key==='bridge'?'Включить мостовой звук? Требуется плавающий пьезоизлучатель между штатными выводами. Нельзя соединять такой выход с землёй.':'Выключить защиту аккумулятора 3,2 В? Останется только аварийная отсечка 2,7 В. Это не безопасная цель разряда.'))return;
        await run(async()=>{try{status.textContent='Сохраняем и проверяем…';preview=null;const ack=await rec(`ui set ${key} ${value}`,'OK ui set',true);if(ack.key!==key||Number(ack.value)!==value)throw new api.CliError('PROTOCOL');settingEdits.delete(key);await loadSettings();if(Number(settings[key])!==value)throw new api.CliError('PROTOCOL');note('Настройка сохранена и прочитана обратно с ноды.');}catch(error){($('api-saved-'+key)||status).textContent=error.safe?error.message:'Сохранение не подтверждено.';throw error;}});
      };
      controls.append(select,save);row.append(caption,controls,status);(panels[meta?.group||(key==='battery_protection'?'battery':['board_led','unread_led','vibration'].includes(key)?'lights':key==='gps'?'gps':'sound')]).append(row);
    }
    filterSettings();
    $('api-adc').hidden=caps.adc!=='1';$('api-adc-value').textContent='Напряжение: '+(Number(settings.battery_mv)?(Number(settings.battery_mv)/1000).toFixed(3)+' В':'нет данных')+' · Сохранённый ADC-множитель: '+settings.adc_multiplier;
    $('api-adc-range').textContent='Заводской: '+settings.adc_default+'. Допустимо: '+caps.adc_min+'–'+caps.adc_max+'.';
    $('api-settings-status').textContent=settingEdits.size?'Есть несохранённые поля: '+settingEdits.size:'Прочитано с ноды';renderShell();
    } catch(error) {
      settings=null;caps=null;schemas=Object.create(null);preview=null;adcManualSupported=false;
      $('api-settings-fields').replaceChildren();$('api-settings-status').textContent='Чтение не подтверждено';
      throw error;
    }
  }
  async function wifiStatus(){wifiState=await rec('ui wifi status','OK ui wifi');if(!['supported','configured','associated'].every(key=>['0','1'].includes(wifiState[key]))||!(wifiState.ip==='none'||/^(?:\d{1,3}\.){3}\d{1,3}$/.test(wifiState.ip)&&wifiState.ip.split('.').every(n=>Number(n)<=255)))throw new api.CliError('PROTOCOL');const names={idle:'Нет незавершённой настройки',ssid:'Ожидает имя сети',password:'Ожидает пароль',ready:'Можно начать проверку',testing:'Проверка идёт — запросите результат через несколько секунд',test_ok:'Проверка успешна. Сеть ещё не сохранена',saved:'Сеть сохранена',cancelled:'Проверка отменена',failed:'Проверка не прошла; старые настройки сохранены',timeout:'Время проверки истекло'};$('api-wifi-state').textContent=names[wifiState.state]||'Состояние не распознано';renderShell();}
  $('helper-mode').onchange=()=>{
    if(legacy.getState().connected||legacy.getState().busy||binaryState.connected||binaryState.busy||client.session||client.opening||client.closing||running||choosing){$('helper-mode').value=mode;return;}
    mode=$('helper-mode').value;workspace.hidden=mode!=='api';$('connection-section').hidden=mode==='api';connectionMeta.hidden=mode!=='api';consolePanels.forEach(el=>el.hidden=mode==='api');consoleNotices.forEach(el=>{if(el.id!=='unsupported'&&el.id!=='connection-help')el.hidden=mode==='api';});
    $('refresh').hidden=mode==='api';renderPages();renderShell();
  };
  const originalConnect=$('connect').onclick,originalDisconnect=$('disconnect').onclick;
  $('connect').onclick=async()=>{
    if(mode==='console'){resetNetwork();await originalConnect();renderShell();if(networkReady()&&!legacy.getState().status?.readOnly)await networkOperation(loadNetwork);return;}
    if(legacy.getState().connected||legacy.getState().busy||binaryState.connected||binaryState.busy||client.session||client.opening||client.closing||running||choosing)return;
    choosing=true;renderShell();
    try{const port=await navigator.serial.requestPort();choosing=false;await run(async()=>{
      resetNetwork();await client.connect(port);acknowledgedLoss=false;settings=null;caps=null;settingEdits.clear();melodyNames.clear();wifiState=null;note('Локальный CLI подключён. Читаем настройки; сообщения не запрашиваются.');
      connectionState=await rec('ui connection','OK ui connection');if(!['ble','usb','wifi'].includes(connectionState.mode)||!['none','ble','usb','wifi'].includes(connectionState.client)||!['0','1'].includes(connectionState.write))throw new api.CliError('PROTOCOL');numeric(connectionState.caps,7);await wifiStatus();await loadSettings();await loadNetwork();note('Настройки прочитаны. Изменения сохраняются отдельно.');
    });}catch(error){note(error.name==='NotFoundError'?'Порт не выбран.':error.safe?error.message:'Не удалось открыть порт. Проверьте разрешения браузера.','warning');}
    finally{choosing=false;renderShell();}
  };
  $('disconnect').onclick=async()=>{if(mode==='console')await originalDisconnect();else{if(adcService?.active&&available())try{await readAdcService('stop');}catch(_){}await client.disconnect();note('Отключено. Для продолжения подключите порт заново.');}resetNetwork();renderShell();};
  window.addEventListener('smartui-console-state',()=>{if(mode==='console')renderShell();});





  $('api-settings-load').onclick=async()=>{if(settingEdits.size&&!await legacy.confirmAction('Отменить несохранённые поля и прочитать значения с ноды заново?'))return;await run(()=>loadSettings({discardEdits:true}));};
  const soundNote=(text,kind='info')=>{soundAction.textContent=text;soundAction.dataset.kind=kind;soundAction.dataset.action='1';};
  $('api-sound-read').onclick=async()=>{
    if(SmartUiConsole.SOUND_SETTING_KEYS.some(key=>settingEdits.has(key))&&!await legacy.confirmAction('Считать звук и пины с ноды? Несохранённые поля звука и индикации будут заменены фактическими значениями. Остальные поля сохранятся.'))return;
    await run(async()=>{soundNote('Считываем фактические настройки звука и пинов…');try{
      await loadSettings();for(const key of SmartUiConsole.SOUND_SETTING_KEYS){settingEdits.delete(key);const field=$('api-setting-'+key);if(field&&settings[key]!==undefined){field.value=String(settings[key]);field.onchange();}}
      soundNote('Прочитано с ноды в '+new Date().toLocaleTimeString('ru-RU')+'. '+SmartUiConsole.notificationStatus(settings,caps));
    }catch(error){soundNote(error.safe?error.message:'Не удалось прочитать звук и пины. Старые значения не подтверждены.','error');throw error;}});
  };
  soundPreview.onclick=async()=>{
    const session=client.session;
    if(SmartUiConsole.SOUND_SETTING_KEYS.some(key=>settingEdits.has(key))&&!await legacy.confirmAction('Есть несохранённые поля звука. Прослушать мелодию с прежними настройками, сохранёнными на ноде?'))return;
    if(session!==client.session)return;
    await run(async()=>{try{
      soundNote('Читаем настройки перед прослушиванием…');await loadSettings();
      if(Number(settings?.muted)===1){soundNote('Общая тишина включена. Выключите её и сохраните: прослушивание не меняет этот переключатель.','warning');return;}
      if(caps?.sound_preview!=='1'){soundNote('Для отдельного прослушивания нужен обновлённый UF2/BIN 0.16.','warning');return;}
      if(await client.execute('ui sound preview',{mutate:true})!=='OK ui sound_preview')throw new api.CliError('PROTOCOL');
      soundNote('Нода приняла запуск сохранённой мелодии '+settings.melody+' на выводе '+settings.tone_pin+'. Настройки уведомлений не изменены. Проверьте звук на устройстве.');
    }catch(error){soundNote(error.safe?error.message:'Запуск мелодии не подтверждён.','error');throw error;}});
  };
  $('api-notify-test').onclick=async()=>{const session=client.session;if(settingEdits.size&&!await legacy.confirmAction('Есть несохранённые поля. Проверить уведомление с прежними настройками, уже сохранёнными на ноде?'))return;if(session!==client.session)return;await run(async()=>{try{
    soundNote('Читаем настройки перед проверкой уведомления…');await loadSettings();
    if(Number(settings?.muted)===1){soundNote('Общая тишина включена: уведомление подавлено. Выключите её и сохраните, если хотите проверить уведомление.','warning');return;}
    if(await client.execute('ui test',{mutate:true})!=='OK ui test')throw new api.CliError('PROTOCOL');soundNote('Запрос уведомления принят. '+SmartUiConsole.notificationStatus(settings,caps));
  }catch(error){soundNote(error.safe?error.message:'Тест не подтверждён.','error');throw error;}});};

  const adcNote=(text,kind='info',id='api-adc-result')=>{$(id).textContent=text;$(id).classList.add('adc-feedback');$(id).dataset.kind=kind;};
  async function runAdc(operation,{progress='Выполняем запрос к ноде…',success,id='api-adc-result'}={}){
    if(running)return;
    const session=client.session,token={session,id};adcOperation=token;adcNote(progress,'info',id);
    await run(async()=>{try{const value=await operation();if(session===client.session&&success)adcNote(typeof success==='function'?success(value):success,'success',id);}
      catch(error){if(session===client.session&&binaryState.connected)adcNote(error?.safe?error.message:'Ответ не подтверждён. Переподключитесь и прочитайте настройки.','error',id);throw error;}
      finally{if(adcOperation===token)adcOperation=null;}});
  }
  $('api-adc-measured').oninput=()=>{preview=null;adcNote('Замер изменён. Рассчитайте поправку заново.');renderShell();};
  $('api-adc-manual-value').oninput=()=>{preview=null;adcNote('Коэффициент ещё не сохранён. Проверьте значение и нажмите «Сохранить коэффициент».','info','api-adc-manual-result');renderShell();};
  $('api-adc-manual-save').onclick=async()=>{
    const session=client.session,text=$('api-adc-manual-value').value;
    let value;try{value=SmartUiConsole.adcMultiplier(text,caps);}catch(error){adcNote(error.message,'error','api-adc-manual-result');return;}
    if(!await legacy.confirmAction('Сохранить ADC-множитель '+value+' напрямую? Используйте только проверенный коэффициент для этой платы. Он влияет на показание напряжения и защиту аккумулятора.'))return;
    if(session!==client.session||text!==$('api-adc-manual-value').value||!writable()){adcNote('Подключение или значение изменилось. Проверьте ввод и подтвердите заново.','error','api-adc-manual-result');return;}
    await runAdc(async()=>{
      preview=null;let acknowledged=false;
      try{
        const reply=await client.execute('ui adc set '+value,{mutate:true});
        if(reply!=='OK ui adc_set')throw new api.CliError('PROTOCOL');acknowledged=true;
        await loadSettings();if(Math.abs(Number(settings.adc_multiplier)-Number(value))>0.000002)throw new api.CliError('PROTOCOL');
        return Number(settings.adc_multiplier).toFixed(6);
      }catch(error){if(acknowledged&&session===client.session){client.update({uncertain:true,phase:'uncertain'});throw new api.CliError('UNCERTAIN');}throw error;}
    },{id:'api-adc-manual-result',progress:'Сохраняем коэффициент '+value+' и читаем обратно…',success:s=>{adcNote('Коэффициент сохранён вручную. Для нового расчёта нужен свежий замер.');return 'Сохранено на ноде и проверено: '+s+'. Напряжение ProMicro сверяйте от АКБ: USB искажает измерение.';}});
  };
  $('api-adc-service-start').onclick=async()=>{
    const session=client.session;
    if(!await legacy.confirmAction('На 2 минуты приостановить отключение по показаниям ADC? Нужно подтверждённое питание USB. Для расчёта нужен свежий замер мультиметром; для прямого ввода — проверенный коэффициент. После сохранения, тайм-аута или потери USB защита вернётся автоматически. Это только сервисная калибровка, не обычный режим работы.'))return;
    if(session!==client.session||!writable())return;
    await run(async()=>{preview=null;await readAdcService('start');$('api-adc-result').textContent='Сервисное окно открыто. Рассчитайте и сохраните ADC по свежему измерению.';note('Сервисное окно подтверждено нодой. Таймер не продлевается при чтении состояния.','warning');});
  };
  $('api-adc-service-stop').onclick=()=>run(async()=>{preview=null;await readAdcService('stop');$('api-adc-result').textContent='Сервисное окно закрыто. Несохранённая калибровка не применялась.';note('Нода подтвердила завершение сервисного окна.');});
  $('api-adc-service-refresh').onclick=()=>run(()=>readAdcService());
  setInterval(()=>{if(available()&&adcService?.active)void run(()=>readAdcService());},5000);
  $('api-adc-preview').onclick=()=>runAdc(async()=>{const mv=SmartUiConsole.measuredMilliVolts($('api-adc-measured').value);preview=null;$('api-adc-result').textContent='Запрашиваем опорный замер. Настройки не изменены.';const p=await rec('ui adc preview '+mv,'OK ui adc_preview');
    if(numeric(p.token)<1||numeric(p.sampled_mv,65535)<1||Number(p.measured_mv)!==mv||!Number.isFinite(Number(p.multiplier))||Number(p.multiplier)<Number(caps.adc_min)-0.000002||Number(p.multiplier)>Number(caps.adc_max)+0.000002)throw new api.CliError('PROTOCOL');
    preview={...p,expires:Date.now()+60000};adcNote('Расчёт, ещё не сохранён: ADC '+p.multiplier+' · Опорный замер: '+p.sampled_mv+' мВ. Проверьте и нажмите «Сохранить калибровку».');});
  $('api-adc-apply').onclick=async()=>{
    const candidate=preview,session=client.session;
    const expired=()=>!candidate||preview!==candidate||session!==client.session||Date.now()>=candidate.expires;
    const stale=()=>{preview=null;$('api-adc-result').textContent='Расчёт устарел. Повторите измерение и расчёт.';renderShell();};
    if(expired()){stale();return;}
    if(!await legacy.confirmAction('Сохранить калибровку ADC? Убедитесь, что напряжение измерено мультиметром непосредственно на аккумуляторе. Изменение влияет на защиту питания.'))return;
    if(expired()||!writable()){stale();return;}
    await runAdc(async()=>{const expected=Number(candidate.multiplier);const reply=await client.execute('ui adc apply '+candidate.token,{mutate:true});if(reply!=='OK ui adc_apply')throw new api.CliError('PROTOCOL');await loadSettings();if(Math.abs(Number(settings.adc_multiplier)-expected)>0.000002)throw new api.CliError('PROTOCOL');return Number(settings.adc_multiplier).toFixed(6);},{progress:'Сохраняем калибровку и читаем обратно…',success:s=>'Калибровка подтверждена и прочитана обратно с ноды: '+s+'.'});
  };
  $('api-adc-reset').onclick=async()=>{if(!await legacy.confirmAction('Вернуть только заводскую калибровку ADC? Контакты, ключи и остальные настройки сохранятся.'))return;await runAdc(async()=>{const reply=await client.execute('ui adc reset',{mutate:true});if(reply!=='OK ui adc_reset')throw new api.CliError('PROTOCOL');await loadSettings();if(Math.abs(Number(settings.adc_multiplier)-Number(settings.adc_default))>0.000002)throw new api.CliError('PROTOCOL');return Number(settings.adc_multiplier).toFixed(6);},{progress:'Восстанавливаем заводской коэффициент…',success:s=>'Заводской коэффициент сохранён и проверен: '+s+'.'});};
  $('api-wifi-form').onsubmit=e=>{e.preventDefault();run(async()=>{
    let password=$('api-password').value;const ssid=$('api-ssid').value;SmartUiConsole.validateCredentials(ssid,password,{openNetwork:$('api-open-network').checked,allowReservedSsid:true});$('api-password').value='';
    await exact('ui wifi begin','OK ui wifi begin state=ssid');await exact('ui wifi ssid '+api.toHex(ssid),'OK ui wifi ssid state=password');
    const encoded=password?api.toHex(password):'-';password='';await exact('ui wifi password '+encoded,'OK ui wifi password state=ready');await exact('ui wifi test','OK ui wifi test state=testing');await wifiStatus();note('Проверка сети начата. Данные ещё не сохранены.');
  });};
  $('api-wifi-status').onclick=()=>run(wifiStatus);
  $('api-wifi-save').onclick=()=>run(async()=>{await exact('ui wifi save','OK ui wifi save');await wifiStatus();if(wifiState.state!=='saved')throw new api.CliError('PROTOCOL');note('Сохранение сети подтверждено нодой.');});
  $('api-wifi-cancel').onclick=()=>run(async()=>{await exact('ui wifi cancel','OK ui wifi cancel');$('api-password').value='';await wifiStatus();});
  $('api-log-clear').onclick=()=>{$('api-log').replaceChildren();};
  for(const button of $('api-command-presets').querySelectorAll('button'))button.onclick=()=>{$('api-command').value=button.dataset.command;$('api-command').focus();};
  $('api-command-send').onclick=async()=>{
    const command=$('api-command').value.trim();
    let policy;
    try{policy=api.developerCommand(command);}catch(_){note('Команда недоступна в этом поле. Используйте help, get/set или ui get/set. Для сети и ADC есть специальные формы; PIN и секреты сюда не вводите.','warning');return;}
    const {write,warning}=policy;
    if(write&&!await legacy.confirmAction('Отправить изменение ноде? Оно может изменить сохранённые настройки. Автоматического повтора не будет.'))return;
    const warnings={bridge:'Мост требует плавающего пьезоизлучателя между совместимыми выводами, не землёй. Продолжить?',battery:'Защита 3,2 В отключится; останется аварийный порог 2,7 В. Продолжить?',pin:'Меняется физический вывод. Проверьте распиновку платы и внешнюю схему; мотору нужен драйвер, LED — резистор. Продолжить?',profile:'Профиль изменит несколько настроек звука и индикации. Продолжить?'};
    if(warning&&!await legacy.confirmAction(warnings[warning]))return;
    $('api-command').value='';await run(async()=>{
      $('api-command-result').textContent='Ожидаем ответ ноды…';
      try{
        const reply=await client.execute(command,{mutate:write});
        $('api-command-result').textContent='Ответ ноды: '+reply;
        const key=/^(ui )?set ([a-z_.]+) /.exec(command);
        if(key){const readback=await client.execute((key[1]||'')+'get '+key[2]);$('api-command-result').textContent+='\nПрочитано после изменения: '+readback;}
        if(write)await loadSettings();
      }catch(error){$('api-command-result').textContent=error?.safe?error.message:'Ответ не подтверждён. Обновите состояние ноды.';throw error;}
    });
  };
  window.addEventListener('beforeunload',()=>{$('api-password').value='';});
  const tabs=[...document.querySelectorAll('[data-page-target]')];
  for(const tab of tabs){tab.onclick=()=>{activePage=tab.dataset.pageTarget;renderPages();};tab.onkeydown=event=>{let index=tabs.indexOf(tab);if(event.key==='ArrowRight'||event.key==='ArrowDown')index=(index+1)%tabs.length;else if(event.key==='ArrowLeft'||event.key==='ArrowUp')index=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')index=0;else if(event.key==='End')index=tabs.length-1;else return;event.preventDefault();tabs[index].click();tabs[index].focus();};}
  renderPages();
  renderShell();
})();
