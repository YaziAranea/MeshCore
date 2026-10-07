'use strict';
(() => {
  const $=id=>document.getElementById(id), api=SmartUiCli, legacy=SmartUiLegacy;
  let mode='console',choosing=false,running=false,caps=null,settings=null,preview=null,wifiState=null,connectionState=null,acknowledgedLoss=false,adcService=null,adcManualSupported=false;
  const settingEdits=new Map(),melodyNames=new Map();
  let radioState=null,advertState=null,radioSupport=null,advertSupport=null,networkRunning=false;
  const catalog=globalThis.SmartUiPresets;
  let binaryState={connected:false,busy:false,phase:'disconnected',hello:null,uncertain:false};
  let adcOperation=null;
  const grid=document.querySelector('.grid');
  const consolePanels=[$('device-section'),$('replies-section'),$('wifi-title').closest('section'),$('mode-title').closest('section')];
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
      <section id="api-developer" class="card wide"><p class="panel-kicker">Интеграция</p><h2>Проверка команд CLI</h2><p class="hint">Одна команда за раз. Стандартный вывод скрывает значения, текст и секреты; сырые пакеты не записываются. Команды изменения требуют подтверждения.</p><label class="field" for="api-command">Команда</label><input id="api-command" type="text" autocomplete="off" spellcheck="false" placeholder="ui get volume"><div class="buttons"><button id="api-command-send" disabled>Выполнить</button></div><p id="api-command-result" role="status">Ожидает команды. Для Wi-Fi используйте форму выше: секреты в командную строку не вводите.</p></section>
      <section class="card wide"><h2>Журнал действий</h2><p class="hint">Статусы операций помощника, не события ноды. Без команд, значений и секретов.</p><ul id="api-log" class="hint" aria-label="Журнал действий"></ul><button id="api-log-clear">Очистить</button></section>
    </div>`;
  $('firmware-section').before(workspace);
  const serviceBox=$('adc-service-box').cloneNode(true);
  for(const element of [serviceBox,...serviceBox.querySelectorAll('[id]')])element.id='api-'+element.id;
  $('api-adc').append(serviceBox);
  const manualBox=$('adc-manual-fields').cloneNode(true);
  for(const element of [manualBox,...manualBox.querySelectorAll('[id]')])element.id='api-'+element.id;
  manualBox.querySelector('label').htmlFor='api-adc-manual-value';
  manualBox.querySelector('input').setAttribute('aria-describedby','api-adc-manual-hint api-adc-manual-result');
  $('api-adc-reset-actions').before(manualBox);
  $('api-adc-source-warning').textContent=$('adc-source-warning').textContent;
  const CAP_KEYS=['v','adc','sound','board_led','unread_led','vibration','gps','battery_protection','display','melody_max','adc_min','adc_max','agc_reset','fem_lna','fem_pa','bridge','melody_names','adc_service'];
  const GET_KEYS=['battery_mv','adc_multiplier','adc_default','sound_quiet','volume','melody','board_led','unread_led','vibration','gps','battery_protection','shutdown_mv','muted','agc_reset','fem_lna','fem_pa','bridge'];
  const OPTIONAL_CAPS=new Set(['agc_reset','fem_lna','fem_pa','bridge','melody_names','adc_service']),OPTIONAL_GET=new Set(['agc_reset','fem_lna','fem_pa','bridge']);
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
    for(const id of ['api-settings-load','api-command-send'])$(id).disabled=!available();
    $('api-notify-test').disabled=!writable()||!settings||!['sound','vibration','board_led','unread_led'].some(key=>caps?.[key]==='1');
    const wifi=wifiState?.supported==='1';$('api-wifi').hidden=wifiState?.supported==='0';
    for(const id of ['api-ssid','api-password','api-open-network','api-wifi-test','api-wifi-cancel'])$(id).disabled=!writable()||!wifi;
    $('api-wifi-status').disabled=!available()||!wifi;
    $('api-wifi-save').disabled=!writable()||!wifi||wifiState?.state!=='test_ok';
    for(const el of $('api-settings-fields').querySelectorAll('select,button'))el.disabled=!writable()||!settings;
    $('api-adc-preview').disabled=!available()||caps?.adc!=='1';
    $('api-adc-reset').disabled=!writable()||caps?.adc!=='1';
    $('api-adc-apply').disabled=!writable()||!preview||Date.now()>=preview.expires;
    $('api-adc-manual-value').disabled=!writable()||!adcManualSupported;
    $('api-adc-manual-save').disabled=!writable()||!adcManualSupported||!$('api-adc-manual-value').value.trim();
    $('api-adc-manual-hint').textContent=binaryState.hello?.write==='0'?'Запись недоступна: нода сообщает режим только для чтения.':adcManualSupported?'Правильный множитель уже известен? Сохраните напрямую, без опорного замера. Не подбирайте значение наугад.':'Прямой ввод не поддерживается этой прошивкой. Обновите файлы SmartUI 0.14; расчёт по мультиметру остаётся доступен.';
    $('api-adc-service-box').hidden=caps?.adc_service!=='1';
    $('api-adc-service-start').disabled=!writable()||caps?.adc_service!=='1'||!adcService?.external||Boolean(adcService?.active);
    $('api-adc-service-stop').disabled=!available()||!adcService?.active;
    $('api-adc-service-refresh').disabled=!available()||caps?.adc_service!=='1';
    $('api-adc-service-status').textContent=!adcService?'Состояние окна не подтверждено. Нажмите «Проверить окно».':adcService.active
      ?'Окно активно · осталось по данным ноды: '+Math.ceil(adcService.remaining_ms/1000)+' с. Проверяем каждые 5 секунд.'
      :adcService.external?'Окно выключено. Обычная защита питания действует.':'Окно выключено. Нода не подтвердила питание USB.';
    renderNetworkControls();
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
    onEvent({action,result}){log(result==='ok'?(action==='write'?'Ответ на изменение получен; проверяем результат.':action==='connect'?'Локальный CLI подключён.':'Ответ на чтение получен.'):'Операция не подтверждена.');}
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
    const s=mode==='api'?binaryState:legacy.getState();
    $('radio-capability').textContent=!s.connected?'Ожидает подключения':networkRunning?'Проверяем настройки…':!ready?'Соединение занято':radioSupport===false?'Нужна поддержка прошивки':!write?'Только чтение':radioState?'Готово к настройке':'Не прочитано';
  }
  function resetNetwork(){radioState=null;advertState=null;radioSupport=null;advertSupport=null;$('radio-current').textContent='Настройки ноды ещё не прочитаны.';$('advert-current').textContent='Сначала подключите ноду.';renderNetworkControls();}
  function showNetworkState(){
    $('radio-current').textContent=radioState?'Сейчас на ноде: '+radioText(radioState)+' · '+radioState.tx_dbm+' дБм · хеш '+radioState.path_bytes+' байт.':radioSupport===false?'Сборка не поддерживает чтение городского пресета. Остальные инструменты работают.':'Настройки радио не подтверждены.';
    $('advert-current').textContent=advertState?'На ноде: '+(advertState.interval_min?'каждые '+advertState.interval_min+' мин':'выключен')+'.':advertSupport===false?'Автоанонс недоступен в этой сборке.':'Интервал не прочитан.';
    if(advertState)$('advert-interval').value=String(advertState.interval_min);
    renderNetworkControls();
  }
  async function readNetwork(kind){
    if(mode==='console')return legacy.client.loadNetworkSetting(kind);
    const value=SmartUiConsole.parseNetworkSetting(await client.execute('ui '+kind),kind,'ui');
    if(!value)throw new api.CliError('PROTOCOL');return value;
  }
  async function saveNetwork(kind,values){
    if(!SmartUiConsole.networkValuesValid(kind,values))throw new api.CliError('INPUT');
    if(mode==='console')return legacy.client.saveNetworkSetting(kind,values);
    const keys=kind==='radio'?['freq_khz','bw_hz','sf','cr','path_bytes']:['interval_min'];
    const before=await readNetwork(kind);
    if(kind==='radio')values={...values,path_bytes:before.path_bytes};
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
    showNetworkState();networkNote(radioState?'Текущие параметры прочитаны. Выберите город и подтвердите применение.':'Для городских пресетов нужна SmartUI 0.13 или новее; остальные настройки доступны.',radioState?'info':'warning');
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
      }catch(error){if(optional.has(key)&&(error.reason==='unsupported'||key==='adc_service'&&error.reason==='invalid'))result[key]='0';else throw error;}
    }
    return result;
  }
  const fields=[['muted',null,'Общая тишина',0,1],['sound_quiet','sound','Без звука уведомлений ЛС',0,1],['volume','sound','Громкость',1,10],['melody','sound','Общая мелодия',0,30],['board_led','board_led','LED платы',0,1],['unread_led','unread_led','LED уведомлений',0,1],['vibration','vibration','Вибрация',0,1],['gps','gps','Аппаратный GPS',0,1],['battery_protection','battery_protection','Защита АКБ 3,2 В',0,1],['agc_reset','agc_reset','AGC-сброс · каждые 60 с',0,1],['fem_lna','fem_lna','FEM · усилитель приёма',0,1],['fem_pa','fem_pa','FEM · усилитель передачи',0,1],['bridge','bridge','Мостовой звук · два вывода',0,1]];
  async function loadSettings({discardEdits=false}={}){
    caps=await readFields('caps',CAP_KEYS,OPTIONAL_CAPS);settings=await readFields('get',GET_KEYS,OPTIONAL_GET);preview=null;if(discardEdits)settingEdits.clear();
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
    for(const[key,cap,label,min,maxDefault]of fields){
      if(cap&&caps[cap]!=='1')continue;
      const max=key==='melody'?numeric(caps.melody_max,255):maxDefault;
      const current=numeric(settings[key],max);if(current<min)throw new api.CliError('PROTOCOL');
      const row=document.createElement('div');row.className='setting-row';const caption=document.createElement('label');caption.htmlFor='api-setting-'+key;caption.textContent=label;
      const controls=document.createElement('div');controls.className='setting-controls';const select=document.createElement('select');select.id='api-setting-'+key;
      for(let value=min;value<=max;value++){const option=document.createElement('option');option.value=String(value);option.textContent=key==='melody'?(melodyNames.has(value)?value+' · '+melodyNames.get(value):'Мелодия '+value):max===1?(value?'Включено':'Выключено'):String(value);select.append(option);}
      select.value=String(current);const storedLabel=select.selectedOptions[0].textContent;
      if(settingEdits.has(key)&&Number(settingEdits.get(key))!==current)select.value=settingEdits.get(key);else settingEdits.delete(key);
      const save=document.createElement('button');save.textContent='Сохранить';save.setAttribute('aria-label','Сохранить CLI: '+label);
      const status=document.createElement('p');status.className='setting-state';status.textContent='На ноде: '+storedLabel+(settingEdits.has(key)?' · Изменение не сохранено':' · Прочитано');status.dataset.dirty=String(settingEdits.has(key));
      select.onchange=()=>{settingEdits.set(key,select.value);status.textContent='Изменение не сохранено';status.dataset.dirty='true';};
      save.onclick=async()=>{
        const value=Number(select.value);if(value===Number(settings[key]))return;
        if((key==='battery_protection'&&value===0||key==='bridge'&&value===1)&&!await legacy.confirmAction(key==='bridge'?'Включить мостовой звук? Требуется плавающий пьезоизлучатель между штатными выводами. Нельзя соединять такой выход с землёй.':'Выключить защиту аккумулятора 3,2 В? Останется только аварийная отсечка 2,7 В. Это не безопасная цель разряда.'))return;
        await run(async()=>{preview=null;const ack=await rec(`ui set ${key} ${value}`,'OK ui set',true);if(ack.key!==key||Number(ack.value)!==value)throw new api.CliError('PROTOCOL');settingEdits.delete(key);await loadSettings();if(Number(settings[key])!==value)throw new api.CliError('PROTOCOL');note('Настройка сохранена и прочитана обратно с ноды.');});
      };
      controls.append(select,save);row.append(caption,controls,status);container.append(row);
    }
    $('api-adc').hidden=caps.adc!=='1';$('api-adc-value').textContent='Напряжение: '+(Number(settings.battery_mv)?(Number(settings.battery_mv)/1000).toFixed(3)+' В':'нет данных')+' · Сохранённый ADC-множитель: '+settings.adc_multiplier;
    $('api-adc-range').textContent='Заводской: '+settings.adc_default+'. Допустимо: '+caps.adc_min+'–'+caps.adc_max+'.';
    $('api-settings-status').textContent='Прочитано с ноды';renderShell();
  }
  async function wifiStatus(){wifiState=await rec('ui wifi status','OK ui wifi');if(!['supported','configured','associated'].every(key=>['0','1'].includes(wifiState[key]))||!(wifiState.ip==='none'||/^(?:\d{1,3}\.){3}\d{1,3}$/.test(wifiState.ip)&&wifiState.ip.split('.').every(n=>Number(n)<=255)))throw new api.CliError('PROTOCOL');const names={idle:'Нет незавершённой настройки',ssid:'Ожидает имя сети',password:'Ожидает пароль',ready:'Можно начать проверку',testing:'Проверка идёт — запросите результат через несколько секунд',test_ok:'Проверка успешна. Сеть ещё не сохранена',saved:'Сеть сохранена',cancelled:'Проверка отменена',failed:'Проверка не прошла; старые настройки сохранены',timeout:'Время проверки истекло'};$('api-wifi-state').textContent=names[wifiState.state]||'Состояние не распознано';renderShell();}
  $('helper-mode').onchange=()=>{
    if(legacy.getState().connected||legacy.getState().busy||binaryState.connected||binaryState.busy||client.session||client.opening||client.closing||running||choosing){$('helper-mode').value=mode;return;}
    mode=$('helper-mode').value;workspace.hidden=mode!=='api';$('connection-section').hidden=mode==='api';connectionMeta.hidden=mode!=='api';consolePanels.forEach(el=>el.hidden=mode==='api');consoleNotices.forEach(el=>{if(el.id!=='unsupported'&&el.id!=='connection-help')el.hidden=mode==='api';});
    document.querySelector('.tool-nav a').href=mode==='api'?'#connection-dock':'#connection-section';
    document.querySelectorAll('[data-api-nav]').forEach(el=>el.hidden=mode!=='api');document.querySelectorAll('[data-console-nav]').forEach(el=>el.hidden=mode==='api');$('refresh').hidden=mode==='api';renderShell();
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

  $('api-notify-test').onclick=()=>run(async()=>{if(await client.execute('ui test',{mutate:true})!=='OK ui test')throw new api.CliError('PROTOCOL');note('Команда теста принята. Используются сохранённые параметры; общая тишина и выключенные каналы учитываются. Это не проверка исправности оборудования.');});

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
  $('api-command-send').onclick=async()=>{
    const command=$('api-command').value.trim();
    const read=/^ui (hello|caps [a-z_]+|get [a-z_]+|connection|melody \d+|mode status)$/.test(command)||['board','ver','get name','get radio'].includes(command);
    const write=/^ui set (sound_quiet|volume|melody|board_led|unread_led|vibration|gps|battery_protection|muted|agc_reset|fem_lna|fem_pa|bridge) \d+$/.test(command);
    if(!read&&!write){note('Используйте короткую команду чтения или ui set. Для сети и ADC есть специальные формы. Секреты сюда не вводите.','warning');return;}
    if(write&&!await legacy.confirmAction('Отправить изменение ноде? Оно может изменить сохранённые настройки. Автоматического повтора не будет.'))return;
    if(/^ui set (battery_protection 0|bridge 1)$/.test(command)&&!await legacy.confirmAction(command.includes('bridge')?'Мост требует плавающего пьезоизлучателя между штатными выводами, не землёй. Продолжить?':'Защита 3,2 В отключится; останется аварийный порог 2,7 В. Продолжить?'))return;
    $('api-command').value='';await run(async()=>{
      const reply=await client.execute(command,{mutate:write});
      const names=reply.split(' ').slice(3).map(token=>token.split('=')[0]).filter(name=>/^[a-z][a-z0-9_]*$/.test(name));
      $('api-command-result').textContent='Ответ получен. Поля: '+(names.join(', ')||'текст')+'. Значения скрыты; сырой ответ не сохранён.';
      if(write)await loadSettings();
    });
  };
  window.addEventListener('beforeunload',()=>{$('api-password').value='';});
  for(const anchor of document.querySelectorAll('.tool-nav a'))anchor.addEventListener('click',()=>{document.querySelectorAll('.tool-nav a').forEach(a=>a.removeAttribute('aria-current'));anchor.setAttribute('aria-current','location');});
  renderShell();
})();
