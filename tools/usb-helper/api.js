(function(root,factory) {
  'use strict';
  const api=factory();
  if (typeof module==='object' && module.exports) module.exports=api;
  else root.SmartUiBinary=api;
}(typeof globalThis!=='undefined'?globalThis:this,function() {
  'use strict';
  const MAGIC=[201,83,85,73], encoder=new TextEncoder();
  const errors={
    BUSY:'Дождитесь завершения операции.', CLOSED:'USB-соединение закрыто. Подключитесь заново.',
    MODE:'Нужен режим USB-компаньона на ноде. Текстовую консоль нельзя смешивать с API.',
    OPEN:'Порт недоступен. Закройте другие приложения и проверьте USB-кабель.',
    TIMEOUT:'Ответ не получен. Результат операции неизвестен; автоматического повтора не было.',
    PROTOCOL:'Некорректный ответ ноды. Состояние не подтверждено; переподключитесь.',
    UNSUPPORTED:'Эта прошивка не сообщает поддержку SmartUI API. Используйте режим настроек через консоль.',
    DENIED:'Нода не разрешает эту операцию в текущем состоянии.',
    FAILED:'Нода отклонила команду. Изменение не подтверждено.',
    INPUT:'Недопустимая команда или значение.', EXHAUSTED:'Идентификаторы запросов исчерпаны. Создайте новое подключение.',
    UNCERTAIN:'Предыдущая операция не подтверждена. Переподключитесь и проверьте состояние; повторной записи не было.'
  };
  const reasonMessages={
    gone:'Статус этого сообщения больше не хранится на ноде. Нажмите «Сверить с нодой». Действие не подтверждено.',
    unsupported:'Эта функция недоступна в текущей сборке или для выбранной записи.',
    negotiate:'Сначала нажмите «Включить синхронизацию» для текущего подключения. Сообщения не отмечались прочитанными.',
    unavailable:'Сервис ноды временно недоступен. Проверьте подключение и повторно прочитайте состояние.',
    gap:'Часть истории событий уже недоступна. Нужно заново сверить состояние с нодой.',
    boot:'Нода перезапустилась. Включите синхронизацию заново; прежние идентификаторы больше не действуют.',
    changed:'Список сообщений изменился во время чтения. Нажмите «Сверить с нодой».',
    unknown:'Запись не найдена. Прочитайте актуальное состояние с ноды.',
    stale:'Расчёт или запрос устарел. Прочитайте текущее состояние и повторите расчёт.',
    source:'Запустите ProMicro от АКБ, дождитесь измерения, подключите USB без перезапуска и повторите расчёт в течение 2 минут. При USB питание искажает замер.',
    notready:'Нода пока не готова к этой операции. Прочитайте текущее состояние.',
    invalid:'Нода отклонила недопустимое значение или команду.',
    busy:'Нода занята. Дождитесь завершения текущей операции.',
    storage:'Нода не подтвердила сохранение: ошибка хранилища. Прочитайте настройки заново.',
    readonly:'Нода разрешает только чтение. Изменение не выполнено.'
  };
  class ApiError extends Error {
    constructor(code,status=null) {super(errors[code]||errors.FAILED);this.code=code;this.status=status;this.safe=true;}
  }
  const fail=code=>new ApiError(code);
  const isMagic=p=>p.length>=4 && MAGIC.every((b,i)=>p[i]===b);
  const uint=(v,min,max)=>Number.isInteger(v)&&v>=min&&v<=max;
  function encode(id,op,payload=new Uint8Array()) {
    if(!uint(id,1,65535)||!uint(op,0,2)||
      (op===0&&payload.length)||(op===1&&(!payload.length||payload.length>152||payload.some(b=>b<32||b>126)))||
      (op===2&&payload.length!==2)) throw fail('INPUT');
    return Uint8Array.from([...MAGIC,1,id&255,id>>8,op,...payload]);
  }
  function decodePage(packet) {
    if(packet.length<13||packet.length>160||!isMagic(packet)||packet[4]!==1||!(packet[5]|packet[6])||packet[7]>2||packet[8]>7) throw fail('PROTOCOL');
    const page={id:packet[5]|packet[6]<<8,op:packet[7],status:packet[8],offset:packet[9]|packet[10]<<8,total:packet[11]|packet[12]<<8,data:packet.slice(13)};
    if(page.total>479||page.offset>page.total||page.offset+page.data.length>page.total||(!page.data.length&&page.offset<page.total)) throw fail('PROTOCOL');
    return page;
  }
  function record(text,prefix) {
    if(typeof text!=='string'||text.length>479||/[^\x20-\x7e]/.test(text)||(text!==prefix&&!text.startsWith(prefix+' '))) throw fail('PROTOCOL');
    const result=Object.create(null);
    for(const part of text.slice(prefix.length).trim().split(' ').filter(Boolean)) {
      const match=/^([a-z][a-z0-9_]*)=([^ ]+)$/.exec(part);
      if(!match||Object.hasOwn(result,match[1])) throw fail('PROTOCOL');
      result[match[1]]=match[2];
    }
    return result;
  }
  function decodeHex(hex,max=512) {
    if(hex==='-') return '';
    if(typeof hex!=='string'||hex.length>max*2||! /^(?:[0-9a-fA-F]{2})+$/.test(hex)) throw fail('PROTOCOL');
    try {return new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(hex.match(/../g),b=>parseInt(b,16)));}
    catch(_) {throw fail('PROTOCOL');}
  }
  const toHex=text=>Array.from(encoder.encode(text),b=>b.toString(16).padStart(2,'0')).join('');
  class FrameDecoder {
    constructor(){this.buffer=new Uint8Array();}
    feed(bytes) {
      this.buffer=Uint8Array.from([...this.buffer,...bytes]);
      const frames=[];
      while(this.buffer.length) {
        if(this.buffer[0]!==62) throw fail('MODE');
        if(this.buffer.length<3) break;
        const length=this.buffer[1]|this.buffer[2]<<8;
        if(length<1||length>176) throw fail('PROTOCOL');
        if(this.buffer.length<length+3) break;
        frames.push(this.buffer.slice(3,length+3));this.buffer=this.buffer.slice(length+3);
      }
      return frames;
    }
  }
  function matches(request,packet) {
    if(isMagic(request)) {
      const offset=request[7]===2 ? request[8]|request[9]<<8 : 0;
      return isMagic(packet)&&packet.length>=13&&packet[5]===request[5]&&packet[6]===request[6]&&packet[7]===request[7]&&
        ((packet[9]|packet[10]<<8)===offset||(packet.length===13&&packet[8]!==0&&!packet.slice(9).some(Boolean)));
    }
    return request[0]===22 ? [1,13].includes(packet[0]) : request[0]===40&&[1,21].includes(packet[0]);
  }
  class ApiClient {
    constructor({onState,onEvent,onPush,timeout=6000,closeTimeout=1000}={}) {
      this.callbacks={onState,onEvent,onPush};this.timeout=timeout;this.closeTimeout=closeTimeout;
      this.session=null;this.opening=false;this.closing=false;this.nextId=1;
      this.state={connected:false,busy:false,phase:'disconnected',hello:null,uncertain:false};
    }
    call(name,value){try{this.callbacks[name]?.(value);}catch(_) {}}
    update(patch){Object.assign(this.state,patch);this.call('onState',{...this.state});}
    audit(action,result='ok'){this.call('onEvent',{action,result});}
    async bounded(promise,ms=this.timeout){let timer;try{return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(fail('TIMEOUT')),ms);})]);}finally{clearTimeout(timer);}}
    async connect(port) {
      if(this.session||this.opening||this.closing) throw fail('BUSY');
      this.opening=true;this.update({busy:true,phase:'opening',uncertain:false,hello:null});
      const s={port,reader:null,writer:null,waiter:null,stopped:false,opened:false,decoder:new FrameDecoder()};this.session=s;
      try {
        const opening=Promise.resolve().then(()=>port.open({baudRate:115200,dataBits:8,stopBits:1,parity:'none',flowControl:'none'})).then(async()=>{
          s.opened=true;if(s.stopped){try{await port.close();}catch(_){}throw fail('CLOSED');}
        });
        await this.bounded(opening);
        if(this.session!==s||s.stopped) throw fail('CLOSED');
        if(!port.readable||!port.writable) throw fail('OPEN');
        s.reader=port.readable.getReader();s.writer=port.writable.getWriter();
        this.update({connected:true,phase:'negotiating'});s.readTask=this.readLoop(s);this.nextId=1;
        // Device info includes BLE PIN. Never return, retain or log its bytes.
        const info=await this.exchange(Uint8Array.of(22,3));
        if(info[0]!==13||info.length<2) throw fail('MODE');
        const discovery=await this.exchange(Uint8Array.of(40));
        if(discovery[0]!==21) throw fail('UNSUPPORTED');
        const values=new TextDecoder().decode(discovery.slice(1)).replace(/\0+$/,'').split(',').filter(s=>s.startsWith('smartui_api:'));
        if(values.length!==1||values[0]!=='smartui_api:1') throw fail('UNSUPPORTED');
        const hello=record(await this.request(0),'OK api hello');
        if(hello.v!=='1'||hello.max_command!=='152'||hello.max_reply!=='479'||hello.max_frame!=='160'||!['0','1'].includes(hello.write)||hello.transport!=='usb') throw fail('PROTOCOL');
        this.update({hello,phase:'ready'});this.audit('connect');return {...hello};
      } catch(error) {await this.disconnect();throw error instanceof ApiError?error:fail('OPEN');}
      finally{this.opening=false;this.update({busy:false});}
    }
    async readLoop(s) {
      try {
        while(!s.stopped) {
          const {value,done}=await s.reader.read();if(done) break;
          if(this.session!==s||s.stopped) break;
          for(const packet of s.decoder.feed(value)) {
            if(s.waiter&&matches(s.waiter.request,packet)) s.waiter.finish(null,packet);
            else this.call('onPush',packet);
          }
        }
        if(!s.stopped) throw fail('CLOSED');
      } catch(error) {
        if(!s.stopped) {s.waiter?.finish(error instanceof ApiError?error:fail('CLOSED'));this.update({phase:'disconnected',connected:false,uncertain:this.state.busy});this.audit('connection','lost');void this.disconnect();}
      }
    }
    async exchange(request) {
      const s=this.session;if(!s||s.stopped||!s.writer) throw fail('CLOSED');
      if(s.waiter) throw fail('BUSY');
      const promise=new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>s.waiter?.finish(fail('TIMEOUT')),this.timeout);
        s.waiter={request,finish:(error,value)=>{if(s.waiter?.request!==request)return;clearTimeout(timer);s.waiter=null;error?reject(error):resolve(value);}};
      });
      // Catch immediately so a write timeout cannot leave an unhandled waiter.
      const accepted=promise.catch(error=>{throw error;});accepted.catch(()=>{});
      try {await this.bounded(s.writer.write(Uint8Array.from([60,request.length&255,request.length>>8,...request])));}
      catch(error){s.waiter?.finish(error instanceof ApiError?error:fail('CLOSED'));}
      return accepted;
    }
    async request(op,payload=new Uint8Array()) {
      if(this.nextId>65535) throw fail('EXHAUSTED');
      const id=this.nextId++, request=encode(id,op,payload);
      let page=decodePage(await this.exchange(request));
      if(page.id!==id||page.op!==op||page.offset!==0) throw fail('PROTOCOL');
      const total=page.total,status=page.status;let bytes=page.data;
      while(bytes.length<total){
        const offset=bytes.length;
        page=decodePage(await this.exchange(encode(id,2,Uint8Array.of(offset&255,offset>>8))));
        if(page.status!==0&&page.total===0) throw new ApiError('FAILED',page.status);
        if(page.id!==id||page.op!==2||page.offset!==offset||page.total!==total||page.status!==status) throw fail('PROTOCOL');
        bytes=Uint8Array.from([...bytes,...page.data]);
      }
      if(bytes.some(b=>b<32||b>126)) throw fail('PROTOCOL');
      const text=new TextDecoder().decode(bytes);
      if(status!==0) {
        const error=new ApiError(status===5?'DENIED':'FAILED',status);
        const reason=/^ERR api ([a-z_]+)(?: |$)/.exec(text)?.[1];
        if(Object.hasOwn(reasonMessages,reason)){error.reason=reason;error.message=reasonMessages[reason];}
        if(reason==='unsupported'&&op===1&&new TextDecoder().decode(payload).startsWith('api inbox snooze '))
          error.message='Для этого сообщения отсрочка напоминания недоступна. Можно отдельно выбрать «Прочитано» или «Не напоминать».';
        throw error;
      }
      if(!text.startsWith('OK api ')) throw fail('PROTOCOL');
      return text;
    }
    async execute(command,{mutate=false}={}) {
      if(this.state.busy||this.closing) throw fail('BUSY');
      if(!this.state.connected||!this.state.hello) throw fail('CLOSED');
      if(this.state.uncertain) throw fail('UNCERTAIN');
      if(mutate&&this.state.hello.write!=='1') throw fail('DENIED');
      if(typeof command!=='string'||!command.startsWith('api ')) throw fail('INPUT');
      const payload=encoder.encode(command);encode(1,1,payload);
      this.update({busy:true});
      try{const reply=await this.request(1,payload);this.audit(mutate?'write':'read');return reply;}
      catch(error){const safe=error instanceof ApiError?error:fail('PROTOCOL');
        if(['TIMEOUT','PROTOCOL','CLOSED','MODE'].includes(safe.code)) this.update({uncertain:true,phase:'uncertain'});
        this.audit(mutate?'write':'read',safe.code);throw safe;
      } finally {this.update({busy:false});}
    }
    async disconnect() {
      if(this.closing) return;
      const s=this.session;if(!s){this.update({connected:false,phase:'disconnected',hello:null});return;}
      this.closing=true;s.stopped=true;s.waiter?.finish(fail('CLOSED'));
      try{
        if(s.reader) try{await this.bounded(s.reader.cancel(),this.closeTimeout);}catch(_){}
        if(s.readTask) try{await this.bounded(s.readTask,this.closeTimeout);}catch(_){}
        try{s.reader?.releaseLock();}catch(_){}
        try{s.writer?.releaseLock();}catch(_){}
        if(s.opened) try{await this.bounded(s.port.close(),this.closeTimeout);}catch(_){}
      } finally{if(this.session===s)this.session=null;this.closing=false;this.update({connected:false,busy:false,phase:'disconnected',hello:null});}
    }
  }
  function parsePush(packet) {
    if(packet.length<13||packet.length>160||!isMagic(packet)||packet[4]!==1||packet[5]||packet[6]||packet[7]!==3||packet[8]||packet[9]||packet[10]||(packet[11]|packet[12]<<8)!==packet.length-13) return null;
    try {
      const fields=record(new TextDecoder().decode(packet.slice(13)),'EV api events');
      if(!/^[0-9a-f]{16}$/i.test(fields.boot)||!/^\d+$/.test(fields.cursor)||!/^\d+$/.test(fields.mask)||Number(fields.mask)>15||Number(fields.cursor)>0xffffffff) return null;
      return fields;
    } catch(_){return null;}
  }
  function decodeMessage(hex) {
    if(typeof hex!=='string'||hex.length>352||!/^(?:[a-f0-9]{2})+$/i.test(hex)) throw fail('PROTOCOL');
    const frame=Uint8Array.from(hex.match(/../g),s=>parseInt(s,16));
    const type=frame[0],v3=type===16||type===17,dm=type===7||type===16,channel=type===8||type===17;
    if(!dm&&!channel)return {text:'Служебное сообщение. Содержимое в этом помощнике не отображается.',sender:'Служебные данные',timestamp:0};
    const base=v3?4:1,typeOffset=base+(dm?7:2),timeOffset=typeOffset+1;
    if(frame.length<timeOffset+4) throw fail('PROTOCOL');
    const txtType=frame[typeOffset],textOffset=timeOffset+4+(dm&&txtType===2?4:0);
    if(frame.length<textOffset)throw fail('PROTOCOL');
    const timestamp=new DataView(frame.buffer,frame.byteOffset,frame.byteLength).getUint32(timeOffset,true);
    const sender=dm?'ЛС · '+Array.from(frame.slice(base,base+6),b=>b.toString(16).padStart(2,'0')).join(''):'Канал '+frame[base];
    if(![0,2].includes(txtType))return {text:'Служебное сообщение. Текст скрыт.',sender,timestamp};
    // Message text is untrusted: consumers MUST use textContent, never HTML.
    const text=new TextDecoder().decode(frame.slice(textOffset)).replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g,'');
    return {text,sender,timestamp};
  }
  return {ApiClient,ApiError,FrameDecoder,encode,decodePage,record,decodeHex,toHex,matches,parsePush,decodeMessage};
}));
