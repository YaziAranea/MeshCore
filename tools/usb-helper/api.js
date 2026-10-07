(function(root,factory) {
  'use strict';
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.SmartUiCli=api;
}(typeof globalThis!=='undefined'?globalThis:this,function() {
  'use strict';
  const encoder=new TextEncoder(),alphabet='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
  const errors={
    BUSY:'Дождитесь завершения операции.',CLOSED:'USB-соединение закрыто. Подключитесь заново.',
    MODE:'На ноде нужен USB-компаньон. Текстовую консоль нельзя смешивать с бинарным подключением.',
    OPEN:'Порт недоступен. Закройте другие приложения и проверьте USB-кабель.',
    TIMEOUT:'Ответ не получен. Результат операции неизвестен; автоматического повтора не было.',
    PROTOCOL:'Некорректный ответ ноды. Состояние не подтверждено; переподключитесь.',
    UNSUPPORTED:'Нода не сообщает smartui_cli:1. Для API SmartUI 0.11 используйте архивный Helper 1.4; прежние настройки доступны через консоль.',
    MESHCORE_UNSUPPORTED:'Нода не сообщает meshcore=1 в ui hello. Эти команды оригинального MeshCore недоступны; используйте поддержанные ui-команды.',
    CONSOLE_UNSUPPORTED:'Нода не сообщает console=1 в ui hello. Для коротких команд и справки нужна SmartUI 0.15; прежние ui-команды остаются доступны.',
    DENIED:'Нода разрешает только чтение. Изменение не выполнено.',
    FAILED:'Команда отклонена. Изменение не подтверждено.',
    INPUT:'Недопустимая команда или значение.',EXHAUSTED:'Теги запросов исчерпаны. Подключитесь заново.',
    UNCERTAIN:'Предыдущая операция не подтверждена. Переподключитесь и прочитайте состояние; повторной записи не было.'
  };
  const reasonMessages={
    unsupported:'Функция или поле недоступны в текущей сборке.',
    unavailable:'Сервис временно недоступен. Прочитайте состояние после восстановления подключения.',
    invalid:'Нода отклонила недопустимое значение или команду.',
    length:'Команда слишком длинная.',busy:'Нода занята. Дождитесь завершения операции.',
    readonly:errors.DENIED,storage:'Сохранение не подтверждено: ошибка хранилища. Прочитайте настройки заново.',
    stale:'Расчёт устарел. Прочитайте настройки и повторите расчёт.',
    source:'Запустите ProMicro от АКБ, дождитесь измерения, подключите USB без перезапуска и рассчитайте поправку в течение 2 минут.',
    measurement:'Не удалось получить пригодный замер. Проверьте питание ноды.',
    radio:'Радио отклонило параметры. Изменение не подтверждено; прочитайте состояние ноды.',
    restore:'Не удалось восстановить прежнее состояние радио. Перезапустите ноду и проверьте параметры.',
    repeat:'Включённая ретрансляция несовместима с выбранной частотой. Помощник не отключает её автоматически; измените настройку на ноде.',
    range:'Значение выходит за допустимые границы платы.',
    usb_required:'Нода не подтвердила питание USB и локальное USB-подключение. Сервисное окно не включено.',
    transport:'Операция недоступна через этот транспорт. Настраивайте Wi-Fi по BLE или USB.',
    unconfigured:'Сначала настройте и сохраните подключение.',notready:'Нода ещё не готова к этой операции.',
    buffer:'Ответ не помещается в допустимый кадр.',internal:'Нода не смогла сформировать корректный ответ.'
  };
  class CliError extends Error {
    constructor(code){super(errors[code]||errors.FAILED);this.code=code;this.safe=true;}
  }
  const fail=code=>new CliError(code);
  const legacyReads=['board','ver','get name','get radio'];
  const meshcoreReads=['get freq','get tx','get af','get dutycycle','get rxdelay','get multi.acks',
    'get path.hash.mode','get radio.rxgain','get tz.offset','get wifi.status','get wifi.ip'];
  const meshcoreSet=/^set (?:name .+|(?:pin|tx|multi\.acks|path\.hash\.mode) [-+]?\d+|(?:af|dutycycle|rxdelay|tz\.offset) [-+]?(?:\d+(?:\.\d*)?|\.\d+)|radio\.rxgain (?:on|off)|radio [-+]?(?:\d+(?:\.\d*)?|\.\d+),[-+]?(?:\d+(?:\.\d*)?|\.\d+),[-+]?\d+,[-+]?\d+)$/u;
  const friendlyReads=/^(?:get (?:volume|vibration|melody|sound_quiet|muted|board_led|unread_led|gps|battery_protection|agc_reset|fem\.lna|fem\.pa|sound\.bridge|adc(?:\.multiplier|\.default)?|battery|battery_mv|shutdown_mv|advert)|(?:get )?caps [a-z][a-z_.]*|help(?: (?:sound|fem|adc|radio|connection|system|advert|led|gps)(?: [1-9]\d*)?)?|melody \d+|melodies|adc (?:manual|service(?: stop)?))$/;
  const friendlyWrites=/^(?:set (?:(?:volume|melody|advert) \d+|(?:vibration|sound_quiet|muted|board_led|unread_led|gps|battery_protection|agc_reset|fem\.lna|fem\.pa|sound\.bridge) (?:on|off|0|1)|adc(?:\.multiplier)? (?:\d+(?:\.\d*)?|\.\d+))|test notification|adc (?:preview \d+|apply \d+|reset|service start))$/;
  const isFriendly=command=>friendlyReads.test(command)||friendlyWrites.test(command);
  const needsMeshcore=command=>!command.startsWith('ui ')&&!legacyReads.includes(command)&&!isFriendly(command);
  const mutates=command=>friendlyWrites.test(command)||command.startsWith('set ')||/^ui (set |test$|radio set |advert set |adc (preview |apply |set |reset$|service start$)|wifi (?!status$)|mode (?!status$))/.test(command);
  function tagFor(index){
    if(!Number.isInteger(index)||index<0||index>=alphabet.length**2)throw fail('EXHAUSTED');
    return alphabet[Math.floor(index/alphabet.length)]+alphabet[index%alphabet.length];
  }
  function validateCommand(command){
    if(typeof command!=='string'||command.length<2||/[\x00-\x1f\x7f]/.test(command))throw fail('INPUT');
    const bytes=encoder.encode(command);
    // TextEncoder replaces lone UTF-16 surrogates. Reject, never change a name silently.
    if(bytes.length>156||new TextDecoder().decode(bytes)!==command)throw fail('INPUT');
    if(command.startsWith('set name ')){
      if(!meshcoreSet.test(command))throw fail('INPUT');
    }else if(/[^\x20-\x7e]/.test(command)||
      !(command.startsWith('ui ')||legacyReads.includes(command)||meshcoreReads.includes(command)||meshcoreSet.test(command)||isFriendly(command)))throw fail('INPUT');
    return command;
  }
  // The interactive helper is intentionally narrower than the SDK: no PIN,
  // credentials, terminal power operations or ADC writes without their form.
  function developerCommand(command){
    validateCommand(command);
    const uiRead=/^ui (?:hello|caps (?:v|adc|sound|board_led|unread_led|vibration|gps|battery_protection|display|melody_max|adc_min|adc_max|agc_reset|fem_lna|fem_pa|bridge|melody_names|adc_service)|get (?:battery_mv|adc_multiplier|adc_default|sound_quiet|volume|melody|board_led|unread_led|vibration|gps|battery_protection|shutdown_mv|muted|agc_reset|fem_lna|fem_pa|bridge)|connection|radio|advert|melody \d+|mode status|adc (?:manual|service))$/;
    const uiWrite=/^ui set (?:sound_quiet|volume|melody|board_led|unread_led|vibration|gps|battery_protection|muted|agc_reset|fem_lna|fem_pa|bridge) \d+$/;
    if(!(uiRead.test(command)||uiWrite.test(command)||command==='ui test'||legacyReads.includes(command)||
      meshcoreReads.includes(command)||(meshcoreSet.test(command)&&!command.startsWith('set pin '))||
      friendlyReads.test(command)||friendlyWrites.test(command)&&!/^adc |^set adc/.test(command)))throw fail('INPUT');
    const write=mutates(command);
    const warning=/^(?:ui set battery_protection 0|set battery_protection (?:0|off))$/.test(command)?'battery':
      /^(?:ui set bridge 1|set sound\.bridge (?:1|on))$/.test(command)?'bridge':null;
    return {write,warning};
  }
  function encodeCommand(tag,command){
    if(!/^[0-9A-Za-z]{2}$/.test(tag))throw fail('INPUT');
    return Uint8Array.from([66,...encoder.encode(tag+'|'+validateCommand(command))]);
  }
  function decodeReply(packet,tag,ascii=true){
    if(packet.length===2&&packet[0]===1)throw fail('FAILED');
    if(packet.length<4||packet.length>160||packet[0]!==29||
      packet[1]!==tag.charCodeAt(0)||packet[2]!==tag.charCodeAt(1)||packet[3]!==124)throw fail('PROTOCOL');
    let text;
    try{text=new TextDecoder('utf-8',{fatal:true}).decode(packet.slice(4));}catch(_){throw fail('PROTOCOL');}
    if(!text||/[\x00-\x1f\x7f]/.test(text)||(ascii&&/[^\x20-\x7e]/.test(text)))throw fail('PROTOCOL');
    if(text==='Unknown command'){const error=fail('FAILED');error.reason='unsupported';error.message=reasonMessages.unsupported;throw error;}
    const reason=/^(?:ERR ui |Error: )([a-z_]+)$/.exec(text)?.[1];
    if(reason){const error=fail(reason==='readonly'?'DENIED':'FAILED');error.reason=reason;
      error.message=reasonMessages[reason]||errors.FAILED;throw error;}
    if(/^(?:Error[:,]|ERROR:)/.test(text))throw fail('FAILED'); // Never surface raw CLI error text.
    if(ascii&&!text.startsWith('OK ui '))throw fail('PROTOCOL');
    return text;
  }
  function record(text,prefix){
    if(typeof text!=='string'||text.length>156||/[^\x20-\x7e]/.test(text)||
      (text!==prefix&&!text.startsWith(prefix+' ')))throw fail('PROTOCOL');
    const result=Object.create(null);
    for(const token of text.slice(prefix.length).trim().split(' ').filter(Boolean)){
      const match=/^([a-z][a-z0-9_]*)=([^ ]+)$/.exec(token);
      if(!match||Object.hasOwn(result,match[1]))throw fail('PROTOCOL');
      result[match[1]]=match[2];
    }
    return result;
  }
  function decodeHex(hex,max=64){
    if(hex==='-')return '';
    if(typeof hex!=='string'||hex.length>max*2||!/^(?:[0-9a-fA-F]{2})+$/.test(hex))throw fail('PROTOCOL');
    try{return new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(hex.match(/../g),b=>parseInt(b,16)));}
    catch(_){throw fail('PROTOCOL');}
  }
  const toHex=text=>Array.from(encoder.encode(text),b=>b.toString(16).padStart(2,'0')).join('');
  function discover(packet){
    if(packet[0]!==21)throw fail('UNSUPPORTED');
    const text=new TextDecoder().decode(packet.slice(1)).replace(/\0+$/,'');
    const values=text.split(',').filter(s=>s.startsWith('smartui_cli:'));
    if(values.length!==1||values[0]!=='smartui_cli:1')throw fail('UNSUPPORTED');
  }
  class FrameDecoder {
    constructor(){this.buffer=new Uint8Array();}
    feed(bytes){
      this.buffer=Uint8Array.from([...this.buffer,...bytes]);const frames=[];
      while(this.buffer.length){
        if(this.buffer[0]!==62)throw fail('MODE');
        if(this.buffer.length<3)break;
        const length=this.buffer[1]|this.buffer[2]<<8;
        if(length<1||length>176)throw fail('PROTOCOL');
        if(this.buffer.length<length+3)break;
        frames.push(this.buffer.slice(3,length+3));this.buffer=this.buffer.slice(length+3);
      }
      return frames;
    }
  }
  function matches(request,packet){
    if(packet[0]===1)return true; // Standard error belongs to the sole pending request.
    if(request[0]===66)return packet[0]===29&&packet.length>=4&&
      packet[1]===request[1]&&packet[2]===request[2]&&packet[3]===124;
    return request[0]===22?[1,13].includes(packet[0]):request[0]===40&&[1,21].includes(packet[0]);
  }
  class CliClient {
    constructor({onState,onEvent,timeout=6000,closeTimeout=1000}={}){
      this.callbacks={onState,onEvent};this.timeout=timeout;this.closeTimeout=closeTimeout;
      this.session=null;this.opening=false;this.closing=false;this.nextTag=0;
      this.state={connected:false,busy:false,phase:'disconnected',hello:null,uncertain:false};
    }
    call(name,value){try{this.callbacks[name]?.(value);}catch(_){}}
    update(patch){Object.assign(this.state,patch);this.call('onState',{...this.state});}
    audit(action,result='ok'){this.call('onEvent',{action,result});}
    async bounded(promise,ms=this.timeout){let timer;try{return await Promise.race([promise,new Promise((_,reject)=>{
      timer=setTimeout(()=>reject(fail('TIMEOUT')),ms);})]);}finally{clearTimeout(timer);}}
    async connect(port){
      if(this.session||this.opening||this.closing)throw fail('BUSY');
      this.opening=true;this.update({busy:true,phase:'opening',uncertain:false,hello:null});
      const s={port,reader:null,writer:null,waiter:null,stopped:false,opened:false,decoder:new FrameDecoder()};this.session=s;
      try{
        const opening=Promise.resolve().then(()=>port.open({baudRate:115200,dataBits:8,stopBits:1,parity:'none',flowControl:'none'})).then(async()=>{
          s.opened=true;if(s.stopped){try{await port.close();}catch(_){}throw fail('CLOSED');}
        });
        await this.bounded(opening);if(this.session!==s||s.stopped)throw fail('CLOSED');
        if(!port.readable||!port.writable)throw fail('OPEN');
        s.reader=port.readable.getReader();s.writer=port.writable.getWriter();
        this.update({connected:true,phase:'negotiating'});s.readTask=this.readLoop(s);this.nextTag=0;
        // DEVICE_INFO includes BLE PIN. Never retain, expose or log the packet.
        const info=await this.exchange(Uint8Array.of(22,3));
        if(info[0]!==13||info.length<2)throw fail('MODE');
        discover(await this.exchange(Uint8Array.of(40)));
        const hello=record(await this.command('ui hello'),'OK ui hello');
        if(hello.version!=='1'||hello.max_command!=='156'||hello.max_reply!=='156'||
          !['0','1'].includes(hello.write)||hello.sync!=='0'||hello.events!=='0')throw fail('PROTOCOL');
        this.update({hello,phase:'ready'});this.audit('connect');return {...hello};
      }catch(error){await this.disconnect();throw error instanceof CliError?error:fail('OPEN');}
      finally{this.opening=false;this.update({busy:false});}
    }
    async readLoop(s){
      try{
        while(!s.stopped){
          const {value,done}=await s.reader.read();if(done)break;
          if(this.session!==s||s.stopped)break;
          for(const packet of s.decoder.feed(value)){
            if(s.waiter&&matches(s.waiter.request,packet))s.waiter.finish(null,packet);
            else if(s.waiter&&packet[0]===1)s.waiter.finish(fail('FAILED'));
            // No CMD10, second reader, message ACKs, event polling or payload logs.
          }
        }
        if(!s.stopped)throw fail('CLOSED');
      }catch(error){if(!s.stopped){
        s.waiter?.finish(error instanceof CliError?error:fail('CLOSED'));
        this.update({phase:'disconnected',connected:false,uncertain:this.state.busy});
        this.audit('connection','lost');void this.disconnect();
      }}
    }
    async exchange(request){
      const s=this.session;if(!s||s.stopped||!s.writer)throw fail('CLOSED');if(s.waiter)throw fail('BUSY');
      const promise=new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>s.waiter?.finish(fail('TIMEOUT')),this.timeout);
        s.waiter={request,finish:(error,value)=>{if(s.waiter?.request!==request)return;clearTimeout(timer);s.waiter=null;error?reject(error):resolve(value);}};
      });promise.catch(()=>{});
      try{await this.bounded(s.writer.write(Uint8Array.from([60,request.length&255,request.length>>8,...request])));}
      catch(error){s.waiter?.finish(error instanceof CliError?error:fail('CLOSED'));}
      if(this.session!==s||s.stopped)throw fail('CLOSED');
      const packet=await promise;
      if(this.session!==s||s.stopped)throw fail('CLOSED');
      return packet;
    }
    async command(command){
      const tag=tagFor(this.nextTag),request=encodeCommand(tag,command);this.nextTag++;
      return decodeReply(await this.exchange(request),tag,command.startsWith('ui '));
    }
    async execute(command,{mutate=false}={}){
      if(this.state.busy||this.closing)throw fail('BUSY');
      if(!this.state.connected||!this.state.hello)throw fail('CLOSED');
      if(this.state.uncertain)throw fail('UNCERTAIN');
      validateCommand(command);
      if(isFriendly(command)&&this.state.hello.console!=='1')throw fail('CONSOLE_UNSUPPORTED');
      if(needsMeshcore(command)&&this.state.hello.meshcore!=='1')throw fail('MESHCORE_UNSUPPORTED');
      mutate=mutate||mutates(command);
      if(mutate&&this.state.hello.write!=='1')throw fail('DENIED');
      const session=this.session;
      this.update({busy:true});
      try{const reply=await this.command(command);if(this.session!==session||session.stopped)throw fail('CLOSED');this.audit(mutate?'write':'read');return reply;}
      catch(error){const safe=error instanceof CliError?error:fail('PROTOCOL');
        if(this.session===session&&!session.stopped&&['TIMEOUT','PROTOCOL','CLOSED','MODE','EXHAUSTED'].includes(safe.code))this.update({uncertain:true,phase:'uncertain'});
        this.audit(mutate?'write':'read',safe.code);throw safe;
      }finally{if(this.session===session&&!session.stopped)this.update({busy:false});}
    }
    async disconnect(){
      if(this.closing)return;const s=this.session;
      if(!s){this.update({connected:false,phase:'disconnected',hello:null});return;}
      this.closing=true;s.stopped=true;s.waiter?.finish(fail('CLOSED'));
      try{
        if(s.reader)try{await this.bounded(s.reader.cancel(),this.closeTimeout);}catch(_){}
        if(s.readTask)try{await this.bounded(s.readTask,this.closeTimeout);}catch(_){}
        try{s.reader?.releaseLock();}catch(_){}try{s.writer?.releaseLock();}catch(_){}
        if(s.opened)try{await this.bounded(s.port.close(),this.closeTimeout);}catch(_){}
      }finally{if(this.session===s)this.session=null;this.closing=false;this.update({connected:false,busy:false,phase:'disconnected',hello:null});}
    }
  }
  return {CliClient,CliError,FrameDecoder,encodeCommand,decodeReply,record,decodeHex,toHex,matches,discover,tagFor,developerCommand,mutates};
}));
