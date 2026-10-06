'use strict';
(() => {
  const $=id=>document.getElementById(id), api=SmartUiBinary, legacy=SmartUiLegacy;
  let mode='console', choosing=false, running=false, synchronized=false, boot=null, cursor=0, rows=[], caps=null, settings=null;
  let dirtyHint=false, eventTimer=null, eventPollTimer=null, preview=null, wifiState=null, acknowledgedLoss=false, notificationState=null, connectionState=null;
  const EVENT_POLL_MILLIS=7500;
  const bodies=new Map(), settingEdits=new Map(), melodyNames=new Map();
  let binaryState={connected:false,busy:false,phase:'disconnected',hello:null,uncertain:false};
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
    <div class="api-overview">
      <dl class="stat-card"><div><dt>Непрочитанные</dt><dd id="api-unread">—</dd></div><small>Получено ≠ прочитано</small></dl>
      <dl class="stat-card"><div><dt>Уведомления</dt><dd id="api-notification">Не прочитано</dd></div><small id="api-notification-note">Состояние ноды</small></dl>
      <dl class="stat-card"><div><dt>Синхронизация</dt><dd id="api-sync-state">Выключена</dd></div><small id="api-boot">Только текущий сеанс</small></dl>
    </div>
    <div class="api-workspace" style="margin-top:20px">
      <section id="api-inbox" class="card"><div class="section-heading"><div><p class="panel-kicker">Входящие</p><h2>Ваши сообщения</h2></div><span id="api-inbox-count" class="status-pill">0 записей</span></div>
      <p class="hint">Открытие списка не отмечает сообщения прочитанными и не отключает напоминания.</p>
      <div class="buttons"><button id="api-sync-enable" class="primary" disabled>Включить синхронизацию</button><button id="api-fetch" disabled>Получить сообщения</button><button id="api-resync" disabled>Сверить с нодой</button></div>
      <p id="api-inbox-hint" class="hint">Синхронизация включается отдельно. Тексты хранятся только в памяти этой вкладки.</p><div id="api-message-list" class="inbox-list"></div>
      <p class="privacy-note">«Получить» подтверждает только доставку в помощник. «Прочитано», «Не напоминать» и «Отложить» — отдельные действия. После закрытия вкладки полученный текст не восстанавливается с ноды.</p></section>
      <section id="api-events-section" class="card"><p class="panel-kicker">В реальном времени</p><h2>События ноды</h2><p class="hint">Изменения состояния без текста сообщений, паролей и сырых пакетов.</p><ul id="api-events" aria-label="События API"></ul><div class="buttons"><button id="api-events-clear">Очистить журнал</button><button id="api-events-pull" disabled>Обновить</button></div></section>
      <section id="api-settings" class="card wide"><div class="section-heading"><div><p class="panel-kicker">Устройство и радио</p><h2>Настройки по API</h2></div><span id="api-settings-status" class="status-pill">Не прочитано</span></div><p class="hint">Только поддерживаемые сборкой функции. У каждого изменения отдельное сохранение и контрольное чтение.</p><div class="buttons"><button id="api-settings-load" disabled>Прочитать настройки</button><button id="api-notify-test" disabled>Тест уведомления</button></div><div id="api-settings-fields"></div>
      <details id="api-adc"><summary>Калибровка аккумулятора</summary><p id="api-adc-value" class="hint">Нет измерения</p><p id="api-adc-source-warning" class="safety-note">ProMicro: при USB питание искажает замер АКБ. Запустите ноду от АКБ, дождитесь измерения, подключите USB без перезапуска и рассчитайте поправку в течение 2 минут. Прошивка использует сохранённый опорный замер, а не текущее напряжение USB.</p><label class="field" for="api-adc-measured">Напряжение мультиметра, В</label><input id="api-adc-measured" type="text" inputmode="decimal" placeholder="Например, 3,82"><div class="buttons"><button id="api-adc-preview" disabled>Рассчитать поправку</button><button id="api-adc-apply" disabled>Сохранить калибровку</button><button id="api-adc-reset" disabled>Заводская калибровка ADC</button></div><p id="api-adc-result" class="hint">Расчёт не меняет настройки. Сохранение требует подтверждения.</p></details>
      <p class="safety-note">AGC-сброс — пробная профилактика каждые 60 с с отсрочкой при активности. Мост звука требует совместимого плавающего пьезоизлучателя между двумя штатными выводами; не подключайте такой выход к земле. Возможности сборки не доказывают наличие внешнего оборудования.</p></section>
      <section id="api-wifi" class="card wide"><p class="panel-kicker">Локальная сеть</p><h2>Wi-Fi без потери настроек</h2><p class="hint">USB остаётся подключённым во время проверки. Старые данные заменяются только после успешного теста и отдельного сохранения. TCP без пароля и TLS — только доверенная сеть, без доступа из интернета.</p><form id="api-wifi-form" autocomplete="off"><label class="field" for="api-ssid">Имя сети (SSID)</label><input id="api-ssid" type="text" autocomplete="off" spellcheck="false"><label class="field" for="api-password">Пароль сети</label><input id="api-password" type="password" autocomplete="new-password"><label class="check"><input id="api-open-network" type="checkbox">Сеть без пароля — понимаю риск</label><div class="buttons"><button id="api-wifi-test" type="submit" class="primary" disabled>Проверить сеть</button><button id="api-wifi-status" type="button" disabled>Результат проверки</button><button id="api-wifi-save" type="button" disabled>Сохранить сеть</button><button id="api-wifi-cancel" type="button" disabled>Отменить</button></div></form><p id="api-wifi-state" class="hint">Доступность определяется прошивкой. Через 120 секунд бездействия проверка отменяется.</p></section>
      <section id="api-developer" class="card wide"><p class="panel-kicker">Интеграция</p><h2>Проверка команд API</h2><p class="hint">Одна команда за раз. Стандартный вывод скрывает значения, текст и секреты; сырые пакеты не записываются. Команды изменения требуют подтверждения.</p><label class="field" for="api-command">Команда</label><input id="api-command" type="text" autocomplete="off" spellcheck="false" placeholder="api caps"><div class="buttons"><button id="api-command-send" disabled>Выполнить</button></div><p id="api-command-result" role="status">Ожидает команды. Для Wi-Fi используйте форму выше: секреты в командную строку не вводите.</p></section>
    </div>`;
  $('firmware-section').before(workspace);
  const logNames={1:'Новое сообщение',2:'Получено приложением',3:'Отмечено прочитанным',4:'Напоминание снято',5:'Напоминание отложено',6:'Напоминание возобновлено',7:'Изменились настройки',8:'Изменилось подключение',9:'Изменилось состояние батареи',10:'Изменилось уведомление'};
  function note(text,kind='info'){$('api-feedback').textContent=text;$('api-feedback').className='notice'+(kind==='error'?' error':kind==='warning'?' warning':'');}
  function log(text){const li=document.createElement('li');const time=document.createElement('span');time.className='event-time';time.textContent=new Date().toLocaleTimeString('ru-RU');li.append(time,document.createTextNode(text));$('api-events').prepend(li);while($('api-events').children.length>64)$('api-events').lastChild.remove();}
  const available=()=>mode==='api'&&binaryState.connected&&binaryState.phase==='ready'&&!binaryState.busy&&!running&&!choosing;
  const writable=()=>available()&&binaryState.hello?.write==='1';
  function renderShell(){
    const s=mode==='api'?binaryState:legacy.getState(),busy=Boolean(s.busy||running||choosing||(mode==='api'&&(client.opening||client.closing||(!s.connected&&client.session))));
    $('helper-mode').disabled=Boolean(s.connected||busy);
    $('connect').disabled=!window.isSecureContext||!navigator.serial||Boolean(s.connected||busy);
    $('disconnect').disabled=!s.connected||choosing;
    $('connect').textContent=choosing?'Выберите порт…':acknowledgedLoss?'Переподключить USB':'Выбрать USB-порт';
    const phases={opening:'Открываем USB-порт…',negotiating:'Проверяем API ноды…',ready:running||s.busy?'Выполняется операция…':'USB-компаньон подключён',uncertain:'Результат неизвестен — требуется переподключение',disconnected:'Нода не подключена'};
    $('transport-state').textContent=mode==='api'?phases[s.phase]||'Нода не подключена':s.busy?'Выполняется операция…':s.verified?'Консоль SmartUI подключена':s.connected?'Порт открыт; консоль не подтверждена':'Нода не подключена';
    $('transport-help').textContent=mode==='api'?'На ноде выберите USB-компаньон. Закройте другие приложения: этот режим использует бинарный API, а не текстовую консоль.':'На ноде выберите Bluetooth или Wi-Fi. Помощник подключается USB-кабелем; телефон и сопряжение не нужны.';
    const syncSupported=binaryState.hello?.sync==='1'&&binaryState.hello?.events==='1';
    $('api-sync-enable').disabled=!writable()||!syncSupported||synchronized;
    for(const id of ['api-fetch','api-resync','api-events-pull'])$(id).disabled=!available()||!synchronized;
    for(const id of ['api-settings-load','api-command-send'])$(id).disabled=!available();
    $('api-notify-test').disabled=!writable()||!settings;
    $('api-sync-state').textContent=!binaryState.connected?'Не подключено':synchronized?'Включена':syncSupported?'Готова':'Не поддерживается';
    $('api-boot').textContent=boot?'Сессия ноды · '+boot.slice(-8):'Только текущий сеанс';
    $('api-unread').textContent=synchronized?String(rows.filter(r=>!(Number(r.state)&2)).length):'—';
    $('api-inbox-count').textContent=rows.length+' '+(rows.length%10===1&&rows.length%100!==11?'запись':rows.length%10>=2&&rows.length%10<=4&&(rows.length%100<12||rows.length%100>14)?'записи':'записей');
    connectionMeta.textContent=binaryState.hello?'SmartUI '+(binaryState.hello.firmware||'—')+' · '+(binaryState.hello.write==='1'?'Изменения разрешены':'Только чтение')+(connectionState?' · Wi-Fi: '+(connectionState.wifi_associated==='1'?'подключён':'нет соединения'):''):'';
    $('api-notification').textContent=notificationState?notificationState.muted==='1'?'Общая тишина':notificationState.active==='1'?'Активно':'Не активно':settings?Number(settings.muted)?'Общая тишина':'Тишина выключена':'Не прочитано';
    $('api-notification-note').textContent='Цепочка уведомлений, не фактическое звучание';
    $('api-inbox-hint').textContent=syncSupported?'Тексты сохраняются только в памяти вкладки. Если другой клиент уже получил текст, здесь останется только состояние.':'Эта прошивка не сообщает sync=1. Настройки API доступны отдельно; список сообщений не запрашивается.';
    const wifi=!!binaryState.hello&&binaryState.hello.wifi_setup==='1';
    for(const id of ['api-ssid','api-password','api-open-network','api-wifi-test','api-wifi-status','api-wifi-cancel'])$(id).disabled=!writable()||!wifi;
    $('api-wifi-save').disabled=!writable()||!wifi||wifiState?.state!=='test_ok';
    for(const el of $('api-settings-fields').querySelectorAll('select,button'))el.disabled=!writable()||!settings;
    for(const id of ['api-adc-preview','api-adc-reset'])$(id).disabled=!writable()||caps?.adc!=='1';
    $('api-adc-apply').disabled=!writable()||!preview||Date.now()>=preview.expires;
    for(const el of $('api-message-list').querySelectorAll('button'))el.disabled=!writable()||!synchronized||el.dataset.unsupported==='true';
  }
  async function run(operation){
    if(running)return;running=true;renderShell();
    try{await operation();}
    catch(error){
      if(error?.reason==='negotiate'||error?.reason==='boot'){synchronized=false;dirtyHint=false;stopEventTimers();if(error.reason==='boot'){bodies.clear();rows=[];renderMessages();}}
      if(error?.code==='PROTOCOL'&&binaryState.connected)client.update({uncertain:true,phase:'uncertain'});
      note(error?.safe?error.message:'Операция не завершена. Проверьте подключение. Сырые ответы не отображаются.','error');
    }
    finally{running=false;renderShell();if(dirtyHint&&available()&&synchronized)scheduleEvents();armEventPolling();}
  }
  const client=new api.ApiClient({
    onState(next){binaryState=next;if(!next.connected){synchronized=false;dirtyHint=false;stopEventTimers();$('api-password').value='';preview=null;if(next.uncertain)acknowledgedLoss=true;}else if(next.phase==='uncertain')stopEventTimers();renderShell();},
    onEvent({action,result}){if(result!=='ok'){log(action==='write'?'Операция изменения не подтверждена.':'Операция не завершена.');}},
    onPush(packet){const hint=api.parsePush(packet);if(hint){dirtyHint=true;if(boot&&boot!==hint.boot){synchronized=false;dirtyHint=false;stopEventTimers();bodies.clear();rows=[];renderMessages();note('Нода перезапустилась. Включите синхронизацию заново.','warning');}scheduleEvents();}}
  });
  const rec=async(command,prefix,mutate=false)=>api.record(await client.execute(command,{mutate}),prefix);
  function acceptBoot(value){if(!/^[0-9a-f]{16}$/.test(value)||/^0+$/.test(value))throw new api.ApiError('PROTOCOL');if(boot&&boot!==value){bodies.clear();rows=[];log('Нода перезапустилась: старые идентификаторы сброшены.');}boot=value;}
  function numeric(value,max=0xffffffff){if(!/^\d+$/.test(value)||Number(value)>max)throw new api.ApiError('PROTOCOL');return Number(value);}
  function checkId(id,allowZero=false){if(!/^[0-9a-f]{8}$/.test(id)||(!allowZero&&/^0+$/.test(id)))throw new api.ApiError('PROTOCOL');return id;}
  async function snapshot(resetCursor=false){
    for(let attempt=0;attempt<3;attempt++){
      const snap=await rec('api inbox snapshot','OK api inbox snapshot');acceptBoot(snap.boot);
      const count=numeric(snap.count,32), revision=numeric(snap.revision), next=[];
      try{for(let i=0;i<count;i++){
        const item=await rec(`api inbox item ${boot} ${revision} ${i}`,'OK api inbox item');
        if(item.boot!==boot||numeric(item.revision)!==revision||numeric(item.index,31)!==i)throw new api.ApiError('PROTOCOL');
        checkId(item.id);numeric(item.state,15);numeric(item.flags,255);numeric(item.snooze,86400);next.push(item);
      }}catch(error){if(error.reason==='changed')continue;throw error;}
      rows=next;if(resetCursor)cursor=numeric(snap.cursor);renderMessages();return;
    }
    throw new api.ApiError('BUSY');
  }
  async function enableSync(){
    const status=await rec('api sync enable','OK api sync',true);acceptBoot(status.boot);
    if(status.explicit!=='1')throw new api.ApiError('PROTOCOL');
    const subscribed=await rec('api events subscribe 15','OK api events',true);if(subscribed.boot!==boot||subscribed.subscribed!=='15')throw new api.ApiError('PROTOCOL');synchronized=true;await snapshot(true);await loadNotification();
    note('Синхронизация включена. Сообщения не отмечены прочитанными.');log('Синхронизация состояний включена.');
  }
  async function pullEvents(){
    dirtyHint=false;if(!synchronized||!boot)return;
    let metadataChanged=false;
    for(let i=0;i<33;i++){
      let event;
      try{const text=await client.execute(`api events next ${boot} ${cursor}`);event=api.record(text,text.startsWith('OK api events ')?'OK api events':'OK api event');}
      catch(error){if(['gap','boot'].includes(error.reason)){await resyncEventSnapshot();if(error.reason==='boot'){synchronized=false;stopEventTimers();note('Нода перезапустилась. Состояния сверены без прочтения сообщений; включите синхронизацию заново.','warning');}return;}throw error;}
      if(event.boot!==boot)throw new api.ApiError('PROTOCOL');
      if(event.end==='1'){if(numeric(event.cursor)!==cursor)await resyncEventSnapshot();break;}
      const seq=numeric(event.seq),kind=numeric(event.kind,10);if(kind<1)throw new api.ApiError('PROTOCOL');
      if(seq!==cursor+1){await resyncEventSnapshot();return;}cursor=seq;
      log(logNames[kind]);if(kind<=6)metadataChanged=true;
      if(kind===7){notificationState=null;$('api-settings-status').textContent='Изменено на ноде';note('Настройки изменились на ноде. Прочитайте актуальные значения.');}
      if(kind===8)connectionState=await rec('api connection','OK api connection');
      if(kind===10)notificationState=null;
      if(i===32){dirtyHint=true;break;}
    }
    if(metadataChanged)await snapshot();
    if(!notificationState)await loadNotification();
  }
  async function resyncEventSnapshot(){
    await snapshot(true);await loadNotification();$('api-settings-status').textContent='Нужна сверка';
    log('История событий изменилась. Состояние сверено заново; настройки прочитайте повторно.');
  }
  function stopEventTimers(){clearTimeout(eventTimer);clearTimeout(eventPollTimer);eventTimer=null;eventPollTimer=null;}
  function scheduleEvents(){clearTimeout(eventTimer);eventTimer=null;if(!dirtyHint||!available()||!synchronized)return;eventTimer=setTimeout(()=>{eventTimer=null;if(available()&&synchronized)void run(pullEvents);},150);}
  function armEventPolling(){
    if(eventPollTimer!==null||mode!=='api'||!binaryState.connected||binaryState.phase!=='ready'||!synchronized)return;
    // Hints are advisory. One bounded fallback poll is armed at a time; busy
    // operations are never interrupted and a future poll owns no serial reader.
    eventPollTimer=setTimeout(async()=>{
      eventPollTimer=null;
      if(mode!=='api'||!binaryState.connected||binaryState.phase!=='ready'||!synchronized)return;
      if(available())await run(pullEvents);
      armEventPolling();
    },EVENT_POLL_MILLIS);
  }
  async function loadNotification(){
    if(binaryState.hello?.sync!=='1')return;
    const status=await rec('api notify status','OK api notify');
    if(!['0','1'].includes(status.active)||!['0','1'].includes(status.muted))throw new api.ApiError('PROTOCOL');checkId(status.id,true);notificationState=status;
  }
  async function receiveMessages(){
    const seen=new Set();
    for(let i=0;i<32;i++){
      const text=await client.execute('api inbox next');
      if(text.startsWith('OK api inbox empty=')){const empty=api.record(text,'OK api inbox');if(empty.empty!=='1'||empty.boot!==boot)throw new api.ApiError('PROTOCOL');break;}
      const item=api.record(text,'OK api inbox next');if(item.boot!==boot)throw new api.ApiError('PROTOCOL');checkId(item.id);
      if(seen.has(item.id))throw new api.ApiError('PROTOCOL');seen.add(item.id);
      const decoded=api.decodeMessage(item.frame_hex);bodies.set(boot+':'+item.id,decoded);
      while(bodies.size>64)bodies.delete(bodies.keys().next().value);
      const ack=await rec(`api inbox received ${boot} ${item.id}`,'OK api inbox received',true);
      if(ack.id!==item.id||!(numeric(ack.state,15)&1)||!['0','1'].includes(ack.changed))throw new api.ApiError('PROTOCOL');
    }
      await snapshot();await loadNotification();note('Сообщения получены в память вкладки. Прочтение не подтверждалось.');
  }
  function renderMessages(){
    const list=$('api-message-list');list.replaceChildren();
    if(!rows.length){const empty=document.createElement('div');empty.className='empty-state';const title=document.createElement('strong');title.textContent=synchronized?'Список пока пуст':'Начните с синхронизации';empty.append(title,document.createTextNode('Сообщения появятся здесь после получения с ноды.'));list.append(empty);renderShell();return;}
    for(const row of [...rows].reverse()){
      const body=bodies.get(boot+':'+row.id),state=Number(row.state),card=document.createElement('article');card.className='message-card';card.dataset.unread=String(!(state&2));
      const head=document.createElement('div');head.className='message-top';const sender=document.createElement('strong');sender.textContent=body?.sender||(Number(row.flags)&1?'Личное сообщение':'Сообщение');const label=document.createElement('span');label.className='status-pill';label.textContent=state&2?'Прочитано':state&8?'Отложено':state&4?'Без напоминания':'Не прочитано';head.append(sender,label);
      const text=document.createElement('p');text.className='message-text';text.textContent=body?.text||'Текст недоступен в этой вкладке. Можно получить оставшуюся очередь; уже выданные другому клиенту тексты нода не хранит.';
      const footer=document.createElement('p');footer.className='hint';footer.textContent='ID '+row.id+(body?.timestamp?' · '+new Date(body.timestamp*1000).toLocaleString('ru-RU'):'');
      const buttons=document.createElement('div');buttons.className='buttons';
      for(const [action,title]of [['read','Прочитано'],['dismiss','Не напоминать'],['snooze','Отложить на 10 мин']]){
        const button=document.createElement('button');button.textContent=title;button.dataset.action=action;
        if(action==='snooze'&&row.snoozable!=='1'){button.dataset.unsupported='true';button.title='Для этой записи отложенное напоминание недоступно.';}
        button.onclick=()=>run(async()=>{
          const response=await rec(`api inbox ${action} ${boot} ${row.id}`+(action==='snooze'?' 600':''),'OK api inbox '+action,true);
          if(response.id!==row.id||!['0','1'].includes(response.changed))throw new api.ApiError('PROTOCOL');
          await snapshot();await loadNotification();note(action==='read'?'Нода подтвердила прочтение.':action==='dismiss'?'Напоминание снято. Сообщение не отмечено прочитанным.':'Напоминание отложено на 10 минут.');
        });buttons.append(button);
      }
      card.append(head,text,footer,buttons);list.append(card);
    }
    renderShell();
  }
  const fields=[['muted',null,'Общая тишина',0,1],['sound_quiet','sound','Без звука уведомлений ЛС',0,1],['volume','sound','Громкость',1,10],['melody','sound','Общая мелодия',0,30],['board_led','board_led','LED платы',0,1],['unread_led','unread_led','LED уведомлений',0,1],['vibration','vibration','Вибрация',0,1],['gps','gps','Аппаратный GPS',0,1],['battery_protection','battery_protection','Защита АКБ 3,2 В',0,1],['agc_reset','agc_reset','AGC-сброс · каждые 60 с',0,1],['fem_lna','fem_lna','FEM · усилитель приёма',0,1],['fem_pa','fem_pa','FEM · усилитель передачи',0,1],['bridge','bridge','Мостовой звук · два вывода',0,1]];
  async function loadSettings({discardEdits=false}={}){
    caps=await rec('api caps','OK api caps');settings=await rec('api get','OK api get');preview=null;if(discardEdits)settingEdits.clear();
    // Reuse the strict legacy value schema for the shared subset. API extensions
    // are additive; the same battery and capability safety checks still apply.
    const line=(prefix,keys,values)=>prefix+' '+keys.map(k=>k+'='+values[k]).join(' ');
    const capKeys=['v','adc','sound','board_led','unread_led','vibration','gps','battery_protection','display','melody_max','adc_min','adc_max'];
    const valueKeys=['battery_mv','adc_multiplier','adc_default','sound_quiet','volume','melody','board_led','unread_led','vibration','gps','battery_protection','shutdown_mv','muted'];
    const sharedCaps=SmartUiConsole.parseSettingsCaps(line('OK settings caps',capKeys,caps));
    if(!sharedCaps||!SmartUiConsole.parseDeviceSettings(line('OK settings get',valueKeys,settings),sharedCaps))throw new api.ApiError('PROTOCOL');
    if(caps.melody_names==='1'&&caps.sound==='1'){
      const maximum=numeric(caps.melody_max,255);
      for(let id=0;id<=maximum;id++)if(!melodyNames.has(id)){
        const melody=await rec('api melody '+id,'OK api melody');if(numeric(melody.id,255)!==id)throw new api.ApiError('PROTOCOL');
        const name=api.decodeHex(melody.name_hex,64);if(!name||/[\u0000-\u001f\u007f]/.test(name))throw new api.ApiError('PROTOCOL');melodyNames.set(id,name);
      }
    }
    const container=$('api-settings-fields');container.replaceChildren();
    for(const[key,cap,label,min,maxDefault]of fields){
      if(cap&&caps[cap]!=='1')continue;
      const max=key==='melody'?numeric(caps.melody_max,255):maxDefault;
      const current=numeric(settings[key],max);if(current<min)throw new api.ApiError('PROTOCOL');
      const row=document.createElement('div');row.className='setting-row';const caption=document.createElement('label');caption.htmlFor='api-setting-'+key;caption.textContent=label;
      const controls=document.createElement('div');controls.className='setting-controls';const select=document.createElement('select');select.id='api-setting-'+key;
      for(let value=min;value<=max;value++){const option=document.createElement('option');option.value=String(value);option.textContent=key==='melody'?(melodyNames.has(value)?value+' · '+melodyNames.get(value):'Мелодия '+value):max===1?(value?'Включено':'Выключено'):String(value);select.append(option);}
      select.value=String(current);const storedLabel=select.selectedOptions[0].textContent;
      if(settingEdits.has(key)&&Number(settingEdits.get(key))!==current)select.value=settingEdits.get(key);else settingEdits.delete(key);
      const save=document.createElement('button');save.textContent='Сохранить';save.setAttribute('aria-label','Сохранить API: '+label);
      const status=document.createElement('p');status.className='setting-state';status.textContent='На ноде: '+storedLabel+(settingEdits.has(key)?' · Изменение не сохранено':' · Прочитано');status.dataset.dirty=String(settingEdits.has(key));
      select.onchange=()=>{settingEdits.set(key,select.value);status.textContent='Изменение не сохранено';status.dataset.dirty='true';};
      save.onclick=async()=>{
        const value=Number(select.value);if(value===Number(settings[key]))return;
        if((key==='battery_protection'&&value===0||key==='bridge'&&value===1)&&!await legacy.confirmAction(key==='bridge'?'Включить мостовой звук? Требуется плавающий пьезоизлучатель между штатными выводами. Нельзя соединять такой выход с землёй.':'Выключить защиту аккумулятора 3,2 В? Останется только аварийная отсечка 2,7 В. Это не безопасная цель разряда.'))return;
        await run(async()=>{preview=null;const ack=await rec(`api set ${key} ${value}`,'OK api set',true);if(ack.key!==key||Number(ack.value)!==value)throw new api.ApiError('PROTOCOL');settingEdits.delete(key);await loadSettings();if(Number(settings[key])!==value)throw new api.ApiError('PROTOCOL');note('Настройка сохранена и прочитана обратно с ноды.');});
      };
      controls.append(select,save);row.append(caption,controls,status);container.append(row);
    }
    $('api-adc').hidden=caps.adc!=='1';$('api-adc-value').textContent='Напряжение: '+(Number(settings.battery_mv)?(Number(settings.battery_mv)/1000).toFixed(3)+' В':'нет данных')+' · ADC: '+settings.adc_multiplier;
    await loadNotification();$('api-settings-status').textContent='Прочитано с ноды';renderShell();
  }
  async function wifiStatus(){wifiState=await rec('api wifi status','OK api wifi');const names={idle:'Нет незавершённой настройки',ssid:'Ожидает имя сети',password:'Ожидает пароль',ready:'Можно начать проверку',testing:'Проверка идёт — запросите результат через несколько секунд',test_ok:'Проверка успешна. Сеть ещё не сохранена',saved:'Сеть сохранена',cancelled:'Проверка отменена',failed:'Проверка не прошла; старые настройки сохранены',timeout:'Время проверки истекло'};$('api-wifi-state').textContent=names[wifiState.state]||'Состояние не распознано';renderShell();}
  $('helper-mode').onchange=()=>{
    if(legacy.getState().connected||legacy.getState().busy||binaryState.connected||binaryState.busy||client.session||client.opening||client.closing||running||choosing){$('helper-mode').value=mode;return;}
    mode=$('helper-mode').value;workspace.hidden=mode!=='api';$('connection-section').hidden=mode==='api';connectionMeta.hidden=mode!=='api';consolePanels.forEach(el=>el.hidden=mode==='api');consoleNotices.forEach(el=>{if(el.id!=='unsupported')el.hidden=mode==='api';});
    document.querySelector('.tool-nav a').href=mode==='api'?'#connection-dock':'#connection-section';
    document.querySelectorAll('[data-api-nav]').forEach(el=>el.hidden=mode!=='api');document.querySelectorAll('[data-console-nav]').forEach(el=>el.hidden=mode==='api');$('refresh').hidden=mode==='api';renderShell();
  };
  const originalConnect=$('connect').onclick,originalDisconnect=$('disconnect').onclick;
  $('connect').onclick=async()=>{
    if(mode==='console'){await originalConnect();renderShell();return;}
    if(legacy.getState().connected||legacy.getState().busy||binaryState.connected||binaryState.busy||client.session||client.opening||client.closing||running||choosing)return;
    choosing=true;renderShell();
    try{const port=await navigator.serial.requestPort();choosing=false;await run(async()=>{
      await client.connect(port);acknowledgedLoss=false;settings=null;caps=null;settingEdits.clear();melodyNames.clear();note('API подключён. Синхронизация сообщений включается отдельно.');
      await loadSettings();connectionState=await rec('api connection','OK api connection');
    });}catch(error){note(error.name==='NotFoundError'?'Порт не выбран.':error.safe?error.message:'Не удалось открыть порт. Проверьте разрешения браузера.','warning');}
    finally{choosing=false;renderShell();}
  };
  $('disconnect').onclick=async()=>{if(mode==='console')await originalDisconnect();else{await client.disconnect();synchronized=false;note('Отключено. Для продолжения выберите порт и заново включите синхронизацию.');}renderShell();};
  window.addEventListener('smartui-console-state',()=>{if(mode==='console')renderShell();});
  $('api-sync-enable').onclick=()=>run(enableSync);
  $('api-fetch').onclick=()=>run(receiveMessages);
  $('api-resync').onclick=()=>run(async()=>{await snapshot();await loadNotification();note('Состояние сверено с нодой. Прочтение не подтверждалось.');});
  $('api-events-pull').onclick=()=>run(pullEvents);
  $('api-events-clear').onclick=()=>{$('api-events').replaceChildren();};
  $('api-settings-load').onclick=async()=>{if(settingEdits.size&&!await legacy.confirmAction('Отменить несохранённые поля и прочитать значения с ноды заново?'))return;await run(()=>loadSettings({discardEdits:true}));};
  $('api-notify-test').onclick=()=>run(async()=>{await client.execute('api test',{mutate:true});note('Команда теста принята. Учитываются общая тишина и выбранные каналы; это не проверка исправности оборудования.');});
  $('api-adc-measured').oninput=()=>{preview=null;renderShell();};
  $('api-adc-preview').onclick=()=>run(async()=>{const mv=SmartUiConsole.measuredMilliVolts($('api-adc-measured').value);preview=null;$('api-adc-result').textContent='Запрашиваем опорный замер. Настройки не изменены.';const p=await rec('api adc preview '+mv,'OK api adc_preview');
    if(numeric(p.token)<1||numeric(p.sampled_mv,65535)<1||Number(p.measured_mv)!==mv||!Number.isFinite(Number(p.multiplier))||Number(p.multiplier)<Number(caps.adc_min)-0.000002||Number(p.multiplier)>Number(caps.adc_max)+0.000002)throw new api.ApiError('PROTOCOL');
    preview={...p,expires:Date.now()+60000};$('api-adc-result').textContent='Расчёт, ещё не сохранён: ADC '+p.multiplier+' · Опорный замер: '+p.sampled_mv+' мВ.';});
  $('api-adc-apply').onclick=async()=>{if(!preview||Date.now()>=preview.expires){preview=null;$('api-adc-result').textContent='Расчёт устарел. Повторите измерение и расчёт.';renderShell();return;}if(!await legacy.confirmAction('Сохранить калибровку ADC? Убедитесь, что напряжение измерено мультиметром непосредственно на аккумуляторе. Изменение влияет на защиту питания.'))return;await run(async()=>{const expected=Number(preview.multiplier);const reply=await client.execute('api adc apply '+preview.token,{mutate:true});if(reply!=='OK api adc_apply')throw new api.ApiError('PROTOCOL');await loadSettings();if(Math.abs(Number(settings.adc_multiplier)-expected)>0.000002)throw new api.ApiError('PROTOCOL');$('api-adc-result').textContent='Калибровка подтверждена и прочитана обратно с ноды.';});};
  $('api-adc-reset').onclick=async()=>{if(!await legacy.confirmAction('Вернуть только заводскую калибровку ADC? Контакты, ключи и остальные настройки сохранятся.'))return;await run(async()=>{const reply=await client.execute('api adc reset',{mutate:true});if(reply!=='OK api adc_reset')throw new api.ApiError('PROTOCOL');await loadSettings();if(Math.abs(Number(settings.adc_multiplier)-Number(settings.adc_default))>0.000002)throw new api.ApiError('PROTOCOL');});};
  $('api-wifi-form').onsubmit=e=>{e.preventDefault();run(async()=>{
    let password=$('api-password').value;const ssid=$('api-ssid').value;SmartUiConsole.validateCredentials(ssid,password,{openNetwork:$('api-open-network').checked,allowReservedSsid:true});$('api-password').value='';
    await client.execute('api wifi begin',{mutate:true});await client.execute('api wifi ssid '+api.toHex(ssid),{mutate:true});
    const encoded=password?api.toHex(password):'-';password='';await client.execute('api wifi password '+encoded,{mutate:true});await client.execute('api wifi test',{mutate:true});await wifiStatus();note('Проверка сети начата. Данные ещё не сохранены.');
  });};
  $('api-wifi-status').onclick=()=>run(wifiStatus);
  $('api-wifi-save').onclick=()=>run(async()=>{await client.execute('api wifi save',{mutate:true});await wifiStatus();if(wifiState.state!=='saved')throw new api.ApiError('PROTOCOL');note('Сохранение сети подтверждено нодой.');});
  $('api-wifi-cancel').onclick=()=>run(async()=>{await client.execute('api wifi cancel',{mutate:true});$('api-password').value='';await wifiStatus();});
  $('api-command-send').onclick=async()=>{
    const command=$('api-command').value.trim();
    // Secrets and lifecycle commands belong to their guarded, stateful forms.
    if(!/^api [\x20-\x7e]{1,147}$/.test(command)||/^api (wifi|mode|inbox|sync|events)(?: |$)/.test(command)){note('Для сети, сообщений и синхронизации используйте соответствующие разделы. Секреты в командную строку не вводите.','warning');return;}
    const read=/^api (hello|caps|get|connection|melody \d+)$/.test(command);
    if(!read&&!await legacy.confirmAction('Отправить команду изменения ноде? Команда может изменить сохранённые настройки. Автоматического повтора не будет.'))return;
    $('api-command').value='';await run(async()=>{const reply=await client.execute(command,{mutate:!read});const names=reply.split(' ').slice(3).map(token=>token.split('=')[0]).filter(name=>/^[a-z][a-z0-9_]*$/.test(name));$('api-command-result').textContent='Нода подтвердила команду. Поля ответа: '+names.join(', ')+'. Значения скрыты; сырой ответ не сохранён.';});
  };
  window.addEventListener('beforeunload',()=>{stopEventTimers();$('api-password').value='';bodies.clear();});
  for(const anchor of document.querySelectorAll('.tool-nav a'))anchor.addEventListener('click',()=>{document.querySelectorAll('.tool-nav a').forEach(a=>a.removeAttribute('aria-current'));anchor.setAttribute('aria-current','location');});
  renderMessages();renderShell();
})();
