(function(root,factory) {
  'use strict';
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.SmartUiConsoleCatalog=api;
}(typeof globalThis!=='undefined'?globalThis:this,function() {
  'use strict';
  // This catalog contains documentation and pure command translation only.
  // It never opens a port, executes JavaScript or guesses a board's abilities.
  const encoder=new TextEncoder();
  const MAX_COMMAND_BYTES=156,MAX_MACRO_LINES=16;
  const messages={INPUT:'Команда не входит в каталог или содержит недопустимое значение.',
    LENGTH:'Команда длиннее 156 байт UTF-8.',MACRO:'Макрос: название до 48 символов, описание до 240, от 1 до 16 команд.',
    FORM:'Для этой операции используйте отдельную форму Helper.',
    TRANSPORT:'Эта команда недоступна в выбранном USB-протоколе.',
    UNAVAILABLE:'Возможность или диапазон не подтверждены нодой.'};
  class CatalogError extends Error {
    constructor(code,message){super(message||messages[code]||messages.INPUT);this.name='CatalogError';this.code=code;this.safe=true;}
  }
  const fail=code=>new CatalogError(code);
  const own=(object,key)=>Boolean(object&&Object.hasOwn(object,key));
  const flag=value=>value===true||value===1||value==='1';
  function freeze(value){if(value&&typeof value==='object'){for(const item of Object.values(value))freeze(item);Object.freeze(value);}return value;}
  const fields={};
  function field(key,{min=0,max=1,step=1,capability=null,boolean=true,readonly=false,form=null}={}){
    fields[key]={key,min,max,step,capability,boolean,readonly,form};
  }
  for(const [key,capability] of Object.entries({sound_quiet:'sound',board_led:'board_led',unread_led:'unread_led',
    vibration:'vibration',gps:'gps',battery_protection:'battery_protection',muted:null,night_quiet:'night_quiet',
    agc_reset:'agc_reset',fem_lna:'fem_lna',fem_pa:'fem_pa',bridge:'bridge',tone_8bit:'sound',high_drive:'sound',
    offline_dm_led:'unread_led',ble_dm_led:'unread_led',msg_popup:'display',advert_location:null}))field(key,{capability});
  for(const [key,min,max,step,capability] of [
    ['volume',1,10,1,'sound'],['melody',0,255,1,'sound'],['melody_system',0,255,1,'sound'],
    ['melody_dm',0,255,1,'sound'],['melody_mention',0,255,1,'sound'],['notify_mode',0,7,1,null],
    ['important_notify_mode',0,7,1,null],['resonance_hz',1800,4200,400,'sound'],
    ['ui_font',0,255,1,'display'],['ui_theme',0,255,1,'display'],['ui_top_color',0,5,1,'display'],
    ['ui_bottom_color',0,5,1,'display'],['backlight_timeout',0,2,1,'display'],
    ['gps_source',0,1,1,null],['gps_interval',0,86400,1,'gps']])field(key,{min,max,step,capability,boolean:false});
  for(const key of ['led_pin','tone_pin','vibe_pin'])field(key,{min:-1,max:127,boolean:false,form:'pins'});
  field('profile',{max:3,boolean:false,form:'profile'});
  field('adc_multiplier',{max:1000,boolean:false,readonly:true,capability:'adc'});
  field('adc_default',{max:1000,boolean:false,readonly:true,capability:'adc'});
  for(const key of ['battery_mv','shutdown_mv'])field(key,{max:65535,boolean:false,readonly:true});
  const aliases={sound:'sound_quiet',mute:'muted','fem.lna':'fem_lna','fem.pa':'fem_pa',
    'sound.bridge':'bridge',adc:'adc_multiplier','adc.multiplier':'adc_multiplier','adc.default':'adc_default',battery:'battery_mv'};
  const canonicalKeys={fem_lna:'fem.lna',fem_pa:'fem.pa',bridge:'sound.bridge',adc_multiplier:'adc',adc_default:'adc.default'};
  const capAliases={'fem.lna':'fem_lna','fem.pa':'fem_pa','sound.bridge':'bridge'};
  const capKeys=['v','adc','sound','board_led','unread_led','vibration','gps','battery_protection','display','melody_max',
    'adc_min','adc_max','agc_reset','fem_lna','fem_pa','bridge','melody_names','adc_service','schema','sound_preview','night_quiet'];
  const schemaCaps=['agc_reset','fem_lna','fem_pa','bridge'];
  const specialCaps=['schema','sound_preview','night_quiet'];
  const baseReads=['board','ver','get name'];
  const meshReads=['get freq','get af','get dutycycle','get rxdelay','get multi.acks','get path.hash.mode','get radio.rxgain','get tz.offset','get wifi.status','get wifi.ip'];
  function textValid(value,max){return typeof value==='string'&&value.length<=max&&!/[\x00-\x1f\x7f-\x9f\u2028-\u202e\u2066-\u2069]/u.test(value)&&new TextDecoder().decode(encoder.encode(value))===value;}
  function normalize(command){
    if(!textValid(command,MAX_COMMAND_BYTES))throw fail('INPUT');
    if(encoder.encode(command).length>MAX_COMMAND_BYTES)throw fail('LENGTH');
    let result=command.trim();
    if(!result)throw fail('INPUT');
    // Preserve names verbatim; only the command prefix may be normalized.
    if(/^set +name +/.test(result))return result.replace(/^set +name +/,'set name ');
    if(/[^\x20-\x7e]/.test(result))throw fail('INPUT');
    result=result.replace(/ +/g,' ');
    if(result==='test notification')return 'test';
    if(result==='status'||result==='get connection')return 'connection status';
    if(result.startsWith('get caps '))result=result.slice(4);
    const scalar=/^(get|set|schema) ([a-z][a-z0-9_.]*)(.*)$/.exec(result);
    if(scalar&&own(canonicalKeys,scalar[2]))result=scalar[1]+' '+canonicalKeys[scalar[2]]+scalar[3];
    return result;
  }
  function compile(command,transport='companion'){
    if(!['companion','service'].includes(transport))throw fail('TRANSPORT');
    const canonical=normalize(command),service=transport==='service';
    const result={canonical,wire:canonical,transport,mutates:false,kind:'read',requiresControl:false,
      requiresCompact:!baseReads.includes(canonical)&&canonical!=='get radio'&&!canonical.startsWith('ui '),readback:null};
    const finish=patch=>freeze({...result,...patch});
    if(/^(?:(?:get|set) (?:pin|ble\.pin|connection)(?: |$)|ui (?:pin|mode|wifi)|mode(?: |$)|wifi(?: |$)|adc (?:preview|apply|reset|service start)|set adc(?:[ .]|$)|reboot$|poweroff$|shutdown$)/.test(canonical))throw fail('FORM');
    if(canonical==='ui hello')return finish({wire:service?'info':canonical,kind:'hello'});
    if(baseReads.includes(canonical))return finish({wire:service?(canonical==='get name'?'settings identity':'info'):canonical,kind:canonical==='get name'?'identity':'info'});
    if(canonical==='connection status')return finish({wire:service?'status':canonical,kind:'connection',requiresControl:!service});
    if(canonical==='get radio')return finish({wire:service?'settings radio':canonical,kind:'radio'});
    if(canonical==='get tx')return finish({wire:service?'settings tx':canonical,kind:'tx',requiresCompact:false,requiresMeshcore:!service});
    if(canonical==='get advert')return finish({wire:service?'settings advert':canonical,kind:'advert'});
    if(meshReads.includes(canonical)){
      if(service)throw fail('TRANSPORT');
      return finish({kind:'meshcore',requiresMeshcore:true,requiresCompact:false});
    }
    let match=/^set tx (-?\d+)$/.exec(canonical);
    if(match){const value=Number(match[1]);if(!Number.isInteger(value)||value< -9||value>22)throw fail('INPUT');
      return finish({wire:service?'settings tx set '+value:canonical,mutates:true,kind:'tx',value,expectedValue:value,
        readback:'get tx',requiresMeshcore:!service,requiresCompact:false,warning:'tx',rangeKey:'tx'});}
    match=/^set name (.+)$/u.exec(canonical);
    if(match){const value=match[1];if(!textValid(value,31)||encoder.encode(value).length>31)throw fail('INPUT');
      const hex=Array.from(encoder.encode(value),b=>b.toString(16).padStart(2,'0')).join('');
      return finish({wire:service?'settings name '+hex:canonical,mutates:true,kind:'identity',value,expectedValue:value,readback:'get name',requiresMeshcore:!service,requiresCompact:false});}
    match=/^(get|set|schema) ([a-z][a-z0-9_.]*)(?: (\S+))?$/.exec(canonical);
    if(match){
      const operation=match[1],publicKey=match[2],key=own(aliases,publicKey)?aliases[publicKey]:publicKey;
      if(!own(fields,key))throw fail('INPUT');
      const spec=fields[key],invert=publicKey==='sound';
      if(operation!=='set'&&match[3]!==undefined)throw fail('INPUT');
      if(operation==='schema'&&spec.readonly)throw fail('INPUT');
      const common={kind:operation==='schema'?'schema':'setting',operation,key,schemaKey:key,capability:spec.capability,invert,
        requiresControl:!service&&['sound','mute','night_quiet'].includes(publicKey)};
      if(operation!=='set')return finish({...common,wire:service?'settings '+operation+' '+key:canonical});
      if(spec.readonly||spec.form||['bridge','high_drive'].includes(key))throw fail('FORM');
      let value;
      if(spec.boolean){if(!['on','off','0','1'].includes(match[3]))throw fail('INPUT');value=['on','1'].includes(match[3])?1:0;}
      else {if(!/^-?\d+$/.test(match[3]||''))throw fail('INPUT');value=Number(match[3]);}
      if(!Number.isSafeInteger(value)||value<spec.min||value>spec.max||(value-spec.min)%spec.step)throw fail('INPUT');
      const expectedValue=invert?1-value:value;
      const readback='get '+(canonicalKeys[key]||key);
      const extraReadbacks=['muted','night_quiet'].includes(key)?['get muted','get night_quiet']:key==='high_drive'?['get volume']:[];
      return finish({...common,wire:service?'settings set '+key+' '+expectedValue:canonical,mutates:true,value,expectedValue,readback,extraReadbacks,
        warning:key==='battery_protection'&&!value?'battery':key==='high_drive'?'high_drive':key==='night_quiet'?'night_quiet':null});
    }
    match=/^caps ([a-z][a-z0-9_.]*)$/.exec(canonical);
    if(match){
      const key=own(capAliases,match[1])?capAliases[match[1]]:match[1];
      if(!capKeys.includes(key))throw fail('INPUT');
      // The service protocol exposes most capabilities in one bounded record.
      const source=schemaCaps.includes(key)?'schema':specialCaps.includes(key)?'cap':'caps';
      if(service&&key==='melody_names')throw fail('TRANSPORT');
      return finish({wire:service?(source==='schema'?'settings schema '+key:source==='cap'?'settings caps '+key:'settings caps'):canonical,
        kind:'caps',key,capabilityKey:key,source,requiresControl:!service&&['sound_preview','night_quiet'].includes(key)});
    }
    match=/^melody (\d+)$/.exec(canonical);
    if(match){const value=Number(match[1]);if(value>255)throw fail('INPUT');return finish({wire:service?'settings melody '+value:canonical,kind:'melody',value});}
    if(canonical==='melodies'){
      if(service)throw fail('TRANSPORT');
      return finish({kind:'melodies'});
    }
    if(canonical==='sound preview')return finish({wire:service?'settings sound preview':canonical,kind:'preview',mutates:true,
      capability:'sound',requiresCapability:'sound_preview',requiresControl:!service});
    if(canonical==='test')return finish({wire:service?'settings test':canonical,kind:'test',mutates:true,
      anyCapabilities:['sound','unread_led','vibration'],requiresControl:!service});
    if(canonical==='adc manual'||canonical==='adc service')return finish({wire:service?'settings '+canonical:canonical,
      kind:canonical==='adc manual'?'adc_manual':'adc_service',capability:'adc'});
    throw fail('INPUT');
  }
  const classify=command=>compile(command,'companion');
  const groups=freeze([
    {id:'connection',label:'Связь',description:'Версия, соединение и подключение телефона.'},
    {id:'sound',label:'Звук',description:'Тишина, мелодии и уведомления.'},
    {id:'power',label:'Питание',description:'Напряжение, ADC и защита аккумулятора.'},
    {id:'radio',label:'Радио',description:'Параметры эфира, мощность и усилители.'},
    {id:'lights',label:'Индикация',description:'Световые уведомления и выводы.'},
    {id:'device',label:'Устройство',description:'GPS, экран и профиль настроек.'}
  ]);
  const toggle=(label='Режим',value='on')=>({name:'value',label,type:'select',default:value,options:[{value:'on',label:'Включить'},{value:'off',label:'Выключить'}]});
  const number=(label,min,max,value,step=1)=>({name:'value',label,type:'number',min,max,step,default:value});
  const action=(id,group,label,description,commands,extra={})=>({id,group,label,description,commands,...extra});
  const navigation=(id,group,label,description,target)=>action(id,group,label,description,[],{navigation:target});
  const actions=freeze([
    action('diagnostics','connection','Проверить ноду','Плата, версия, имя и состояние соединения. Ничего не меняет.',['board','ver','get name','connection status']),
    action('version','connection','Версия и плата','Показывает установленную сборку и название платы.',['board','ver']),
    action('identity','connection','Имя ноды','Читает имя, которое нода использует в сети.',['get name']),
    action('connection-status','connection','Состояние связи','Выбранный режим и подключённый клиент — разные состояния.',['connection status']),
    action('capabilities','connection','Возможности','Читает поддержку функций прошивки. Это не проверка подключённого зуммера или GPS.',['caps sound','caps display','caps gps','caps adc','caps vibration','caps fem.lna','caps fem.pa']),
    navigation('ble-pin','connection','Показать BLE PIN','Открывает защищённую форму. PIN не попадёт в консоль и историю.','pin'),
    navigation('transport','connection','BLE / USB','Меняет транспорт через отдельную форму: текущее соединение может прерваться.','connection'),
    navigation('wifi','connection','Настроить Wi-Fi','Проверка и сохранение сети через форму. Доступность зависит от платы.','wifi'),
    action('sound-state','sound','Настройки звука','Читает разрешение звука, общую тишину, громкость и мелодию.',['get sound','get mute','get volume','get melody']),
    action('mute-on','sound','Тишина','Отключает уведомления: звук, вибрацию и уведомительный LED. Отменяет ночную тишину.',['set mute on','get mute']),
    action('mute-off','sound','Вернуть уведомления','Снимает общую тишину. Настройки каналов сохраняются.',['set mute off','get mute']),
    action('sound-enable','sound','Звук уведомлений','Разрешает или запрещает звуковой канал. Общая тишина имеет приоритет.',['set sound {value}','get sound'],{parameter:toggle()}),
    action('volume','sound','Громкость','Сохраняет громкость 1–10. Для тишины используйте отдельную команду.',['set volume {value}','get volume'],{parameter:number('Громкость',1,10,7)}),
    action('melody','sound','Выбрать мелодию','Сохраняет номер мелодии. Само по себе мелодию не проигрывает.',['set melody {value}','get melody'],{parameter:number('Номер мелодии',0,255,18)}),
    action('sound-preview','sound','Прослушать','Один раз играет сохранённую мелодию. При общей тишине нода отклонит запрос.',['sound preview']),
    action('notification-test','sound','Тест уведомления','Проверяет сохранённые каналы. Успех команды не доказывает наличие звука.',['test']),
    action('vibration','sound','Вибрация','Управляет каналом вибрации. Требуются разрешённый вывод и внешний драйвер мотора.',['set vibration {value}','get vibration'],{parameter:toggle()}),
    action('night-quiet','sound','Тишина до утра','Работает 23:30–07:30 по часам ноды. Для включения нужно достоверное время.',['set night_quiet {value}','get mute','get night_quiet'],{parameter:toggle()}),
    action('battery','power','Напряжение АКБ','Читает напряжение в милливольтах и порог отключения. 4100 мВ = 4,1 В.',['get battery','get shutdown_mv']),
    action('adc-state','power','Коэффициент ADC','Читает текущую и заводскую поправку. Значения не меняет.',['get adc','get adc.default','caps adc_min','caps adc_max']),
    navigation('adc-calibration','power','Калибровка ADC','Расчёт по мультиметру, проверка и отдельное сохранение через форму.','adc'),
    action('battery-protection','power','Защита АКБ','Меняет защиту от глубокого разряда. Отключение снижает порог отключения.',['set battery_protection {value}','get battery_protection'],{parameter:toggle()}),
    action('radio-state','radio','Параметры радио','Частота, полоса, SF, CR и мощность. Ничего не меняет.',['get radio','get tx']),
    action('tx-power','radio','Мощность TX','Мощность радиочипа в dBm; не измеренная мощность после FEM. Точные границы задаёт нода.',['set tx {value}','get tx'],{parameter:number('Мощность, dBm',-9,22,10)}),
    action('fem-lna','radio','FEM · приём','Переключает внешнее усиление приёма, если драйвер платы это поддерживает.',['set fem.lna {value}','get fem.lna'],{parameter:toggle()}),
    action('fem-pa','radio','FEM · передача','Только при поддержке переключателя TX gain. В публичных профилях 0.20 он недоступен.',['set fem.pa {value}','get fem.pa'],{parameter:toggle()}),
    action('agc','radio','Сброс AGC','Включает или выключает периодический сброс AGC каждые 60 секунд.',['set agc_reset {value}','get agc_reset'],{parameter:toggle()}),
    navigation('radio-setup','radio','Настроить радио','Открывает форму частоты, полосы и пресетов с проверкой параметров.','radio'),
    action('board-led','lights','LED платы','Штатная индикация состояния платы. Отдельна от световых уведомлений.',['set board_led {value}','get board_led'],{parameter:toggle()}),
    action('unread-led','lights','Непрочитанные','Управляет световым напоминанием о непрочитанных сообщениях.',['set unread_led {value}','get unread_led'],{parameter:toggle()}),
    navigation('pins','lights','Выводы уведомлений','Допустимые GPIO зависят от платы и занятых функций. Настройка через форму.','pins'),
    action('led-state','lights','Настройки LED','Читает штатную индикацию и напоминание о непрочитанном. Сохранённое значение не доказывает поддержку.',['get board_led','get unread_led']),
    action('gps','device','GPS ноды','Включает или выключает внешний приёмник, если он поддержан и установлен.',['set gps {value}','get gps'],{parameter:toggle()}),
    action('gps-interval','device','Интервал GPS','Интервал обновления в секундах. Допустимые значения берутся из schema ноды.',['set gps_interval {value}','get gps_interval'],{parameter:number('Интервал, с',0,86400,60)}),
    action('display-state','device','Настройки экрана','Читает тему, шрифт и тайм-аут. На плате без экрана сохранённые поля не включают дисплей.',['caps display','get ui_theme','get ui_font','get backlight_timeout']),
    action('theme','device','Тема экрана','Сохраняет номер темы из вариантов своей ноды. На headless недоступно.',['set ui_theme {value}','get ui_theme'],{parameter:number('Номер темы',0,255,0)}),
    action('font','device','Шрифт экрана','Сохраняет номер шрифта из вариантов своей ноды. На headless недоступно.',['set ui_font {value}','get ui_font'],{parameter:number('Номер шрифта',0,255,0)}),
    action('screen-timeout','device','Тайм-аут экрана','0 — 15 с, 1 — 30 с, 2 — 60 с. На Paper сохранение не включает автоотключение.',['set backlight_timeout {value}','get backlight_timeout'],{parameter:{name:'value',label:'Тайм-аут',type:'select',default:1,options:[{value:0,label:'15 секунд'},{value:1,label:'30 секунд'},{value:2,label:'60 секунд'}]}}),
    navigation('profile','device','Профиль настроек','Меняет несколько настроек сразу. Открывает форму с пояснением.','profile'),
    action('gps-state','device','Источник координат','Читает поддержку GPS, источник и интервал. Не определяет физическое наличие модуля.',['caps gps','get gps_source','get gps_interval'])
  ]);
  function resolveAction(value){const result=typeof value==='string'?actions.find(a=>a.id===value):value;if(!result||typeof result!=='object')throw fail('INPUT');return result;}
  function renderAction(actionOrId,params={}){
    const item=resolveAction(actionOrId);
    if(item.navigation)return [];
    const parameter=item.parameter;let value;
    if(parameter){value=own(params,parameter.name)?params[parameter.name]:parameter.default;
      if(parameter.type==='select'&&!parameter.options.some(option=>String(option.value)===String(value)))throw fail('INPUT');
      if(parameter.type==='number'&&(!Number.isSafeInteger(Number(value))||String(value).trim()===''||Number(value)<parameter.min||Number(value)>parameter.max||(Number(value)-parameter.min)%parameter.step))throw fail('INPUT');}
    return item.commands.map(command=>normalize(parameter?command.replace('{'+parameter.name+'}',String(value)):command));
  }
  function validSchemaValue(schema,value){
    if(!schema||!flag(schema.supported)||!Number.isFinite(schema.min)||!Number.isFinite(schema.max)||!Number.isFinite(schema.step)||schema.step<=0)return false;
    return Number.isSafeInteger(value)&&value>=schema.min&&value<=schema.max&&
      (Array.isArray(schema.options)?schema.options.includes(value):(value-schema.min)%schema.step===0);
  }
  function getAvailability(actionOrStep,context={}){
    const response=(state,reason,available=false)=>({available,state,reason});
    const item=typeof actionOrStep==='string'?resolveAction(actionOrStep):actionOrStep;
    if(!item||typeof item!=='object')return response('unsupported',messages.INPUT);
    if(item.navigation)return response('navigation','Открыть отдельную форму настройки.',true);
    if(!context.connected)return response('offline','Подключите ноду, чтобы проверить доступность.');
    if(context.uncertain)return response('uncertain','Предыдущий результат не подтверждён. Переподключитесь и прочитайте состояние.');
    if(context.busy)return response('busy','Дождитесь завершения текущей операции.');
    if(Array.isArray(item.commands)){
      try {for(const command of renderAction(item,context.params||{})){const availability=getAvailability(compile(command,context.transport||'companion'),context);if(!availability.available)return availability;}}
      catch(error){return response(error.code==='TRANSPORT'?'transport':'invalid',error.message);}
      return response('ready','Доступно на подключённой ноде.',true);
    }
    if(item.requiresCompact&&context.transport!=='service'&&context.compact!==undefined&&!flag(context.compact))return response('unsupported','Короткие команды требуют console=1. Для прежней прошивки используйте прежнюю консоль.');
    if(item.requiresControl&&context.transport!=='service'&&!flag(context.control??context.hello?.control))return response('unsupported','Нужна прошивка с control=1.');
    if(item.requiresMeshcore&&!flag(context.meshcore??context.hello?.meshcore))return response('unsupported','Нужна прошивка с meshcore=1.');
    if(!item.mutates)return response('ready','Только чтение. Ответ не доказывает поддержку изменения.',true);
    if(!flag(context.write??context.hello?.write))return response('readonly','Нода разрешает только чтение.');
    const caps=context.caps||{},schemas=context.schemas||context.schema||{};
    if(item.schemaKey){
      const schema=schemas[item.schemaKey];
      if(schema){
        if(!flag(schema.supported))return response('unsupported','Эта настройка недоступна в текущей сборке или конфигурации.');
        if(!validSchemaValue(schema,item.expectedValue))return response('range','Значение не входит в диапазон или варианты schema ноды.');
      }else{
        // The bridge probes a fresh schema before any write. The catalog must
        // not permanently hide a supported feature absent from an older cache.
        const control=flag(context.control??context.hello?.control)||context.transport==='service';
        if(item.capability&&own(caps,item.capability)&&!flag(caps[item.capability]))return response('unsupported','Эта настройка недоступна в текущей сборке или конфигурации.');
        if(!(item.capability&&flag(caps[item.capability]))&&!(control&&['muted','night_quiet'].includes(item.schemaKey)))
          return response('unknown','Сначала прочитайте schema '+item.schemaKey+' с ноды.');
      }
    } else if(item.capability&&!flag(caps[item.capability]))return response(own(caps,item.capability)?'unsupported':'unknown','Поддержка '+item.capability+' не подтверждена нодой.');
    if(item.requiresCapability&&!flag(caps[item.requiresCapability]))return response(own(caps,item.requiresCapability)?'unsupported':'unknown','Поддержка '+item.requiresCapability+' не подтверждена нодой.');
    if(item.anyCapabilities&&!item.anyCapabilities.some(key=>flag(caps[key])))return response('unsupported','Нода не сообщает доступных каналов уведомления.');
    if(item.rangeKey){const range=context.ranges?.[item.rangeKey]||context[item.rangeKey];
      if(!range||!Number.isFinite(range.min)||!Number.isFinite(range.max))return response('unknown','Сначала прочитайте допустимый диапазон '+item.rangeKey+' с ноды.');
      if(item.expectedValue<range.min||item.expectedValue>range.max)return response('range','Значение выходит за диапазон своей платы.');}
    return response('ready','Изменение сохраняется на ноде.',true);
  }
  function validateMacro(macro,transport='companion',context){
    if(!macro||typeof macro!=='object'||!textValid(macro.name,48)||!macro.name.trim()||!textValid(macro.description||'',240))throw fail('MACRO');
    const lines=typeof macro.commands==='string'?macro.commands.replace(/\r\n/g,'\n').split('\n'):macro.commands;
    if(!Array.isArray(lines)||!lines.length||lines.length>MAX_MACRO_LINES||lines.some(line=>typeof line!=='string'||!line.trim()))throw fail('MACRO');
    // Compile every line before returning anything executable. A late invalid
    // command must never allow a valid earlier write to reach the device.
    const steps=lines.map(line=>compile(line,transport));
    if(context)for(const step of steps){const availability=getAvailability(step,{...context,transport});if(!availability.available)throw new CatalogError('UNAVAILABLE',availability.reason);}
    return freeze({name:macro.name.trim(),description:(macro.description||'').trim(),commands:steps.map(step=>step.canonical),steps,mutates:steps.some(step=>step.mutates)});
  }
  return freeze({CatalogError,MAX_COMMAND_BYTES,MAX_MACRO_LINES,groups,actions,normalize,classify,compile,renderAction,getAvailability,validateMacro,validSchemaValue});
}));
