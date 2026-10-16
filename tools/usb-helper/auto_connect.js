(function(root,factory){
  'use strict';
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.SmartUiAutoConnect=api;
}(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const encoder=new TextEncoder(),active=new WeakMap();
  const defaults=Object.freeze({open:6000,binary:2500,service:2500,close:1500});
  // SmartUI 0.20 discards incomplete binary input after 2000 ms. Never send a
  // probe while an earlier application's partial frame could consume it as data.
  const SETTLE_MS=2100;
  const serialOptions=Object.freeze({baudRate:115200,dataBits:8,stopBits:1,parity:'none',flowControl:'none'});
  const messages={
    BUSY:'USB-порт уже используется. Завершите текущую операцию.',
    OPEN:'Порт недоступен. Закройте другие приложения и проверьте USB-кабель.',
    OPEN_TIMEOUT:'USB-порт не открылся вовремя. Проверьте кабель и подключите ноду заново.',
    CANCELLED:'Подключение отменено.',
    LOST:'USB-соединение прервано. Проверьте кабель и подключите ноду заново.',
    UNKNOWN:'Не удалось определить протокол ноды. Проверьте прошивку, USB-порт и выбранный кабель; при необходимости выберите подключение вручную.',
    DEVICE_BUSY:'USB-консоль занята настройкой Wi-Fi через другое приложение. Завершите её там и подключитесь заново.',
    CLEANUP:'Не удалось освободить USB-порт. Переподключите кабель перед новой попыткой.'
  };
  const cancelLine='\b'.repeat(160)+'cancel\n';
  const acceptedCancel=new Set(['WiFi setup cancelled.',"Unknown command. Type 'help'.",'Connection settings are read-only during storage recovery.']);
  const overflow='Input too long; discarded.';
  const owned='WiFi setup is owned by the companion API; use that client to finish or cancel.';
  const helpEnd='Credential input is not echoed. WiFi is saved only after a passed test.';
  const helpHeaders=new Set([
    'Commands: status | mode ble | mode usb | mode wifi | wifi setup | wifi status | wifi save | wifi cancel | wifi forget | help',
    'Commands: info | status | mode ble | mode usb | mode wifi | wifi setup | wifi status | wifi save | wifi cancel | wifi forget | help',
    'Commands: info | status | mode ble | mode usb | mode wifi | wifi setup | wifi status | wifi save | wifi cancel | wifi forget | reply get N | reply set N HEX | help'
  ]);
  class AutoConnectError extends Error{
    constructor(code){super(messages[code]||messages.UNKNOWN);this.name='AutoConnectError';this.code=code;this.safe=true;}
  }
  const fail=code=>new AutoConnectError(code);
  function configured(options){
    const result={...defaults};
    for(const key of Object.keys(result))if(Number.isFinite(options?.[key])&&options[key]>0)result[key]=options[key];
    return result;
  }
  async function detect(port,{signal,onProgress,timeouts:overrides}={}){
    if(!port||typeof port.open!=='function'||typeof port.close!=='function')throw fail('OPEN');
    if(signal?.aborted)throw fail('CANCELLED');
    if(active.has(port)||port.readable||port.writable)throw fail('BUSY');
    const timeouts=configured(overrides);
    const session={port,opened:false,opening:false,stopped:false,reader:null,writer:null,waiter:null,readTask:null,phase:'idle',bytes:[],line:'',overflow:false};
    active.set(port,session);
    let abortReject;
    const aborted=new Promise((_,reject)=>{abortReject=reject;});aborted.catch(()=>{});
    const abort=()=>{session.stopped=true;session.waiter?.reject(fail('CANCELLED'));abortReject(fail('CANCELLED'));};
    signal?.addEventListener('abort',abort,{once:true});
    function assertCurrent(){if(signal?.aborted||session.stopped)throw fail('CANCELLED');if(session.lost)throw fail('LOST');}
    function progress(phase){try{onProgress?.({phase});}catch(_){} }
    async function bounded(promise,ms,code,withAbort=true){
      let timer;
      try{return await Promise.race([Promise.resolve(promise),new Promise((_,reject)=>{timer=setTimeout(()=>reject(fail(code)),ms);}),...(withAbort?[aborted]:[])]);}
      finally{clearTimeout(timer);}
    }
    function clearParser(){session.bytes.fill(0);session.bytes=[];session.line='';session.overflow=false;}
    function lineReceived(line){
      if(line===owned){session.waiter?.reject(fail('DEVICE_BUSY'));return;}
      session.waiter?.line?.(line);
    }
    function incoming(chunk){
      if(session.stopped||!(chunk instanceof Uint8Array))return;
      if(session.phase==='binary'){
        // The probe never returns packet content. DEVICE_INFO contains BLE PIN;
        // retain only bounded parsing bytes and zero them immediately afterward.
        for(const byte of chunk){
          const bytes=session.bytes;
          if(!bytes.length&&byte!==62)continue;
          bytes.push(byte);
          if(bytes.length===3){const length=bytes[1]|bytes[2]<<8;if(length<1||length>176){bytes.fill(0);session.bytes=[];continue;}}
          if(bytes.length>=3&&bytes.length===(bytes[1]|bytes[2]<<8)+3){
            const valid=bytes[3]===13&&bytes.length>=83&&bytes[4]>=3;
            bytes.fill(0);session.bytes=[];
            if(valid)session.waiter?.resolve('companion');
          }
        }
      }else if(session.phase==='text'){
        for(const byte of chunk){
          if(byte===10||byte===13){
            if(session.line&&!session.overflow)lineReceived(session.line);
            session.line='';session.overflow=false;
          }else if(byte>=32&&byte<=126&&!session.overflow){
            if(session.line.length<511)session.line+=String.fromCharCode(byte);
            else{session.line='';session.overflow=true;}
          }else{session.line='';session.overflow=true;}
        }
      }
    }
    function waitFor(phase,makeHandler){
      clearParser();session.phase=phase;
      const promise=new Promise((resolve,reject)=>{session.waiter={resolve,reject,...makeHandler?.(resolve,reject)};});
      promise.catch(()=>{});return promise;
    }
    async function send(bytes,response,timeout){
      try{assertCurrent();await bounded(session.writer.write(bytes),timeout,'LOST');assertCurrent();return await bounded(response,timeout,'UNKNOWN');}
      catch(error){if(error instanceof AutoConnectError)throw error;throw fail('LOST');}
      finally{session.waiter=null;clearParser();session.phase='idle';}
    }
    async function releaseStreams(){
      session.stopped=true;session.waiter=null;clearParser();
      // Releasing (not cancelling) a pending read preserves the readable stream
      // for the verified SDK handshake on the same open native port.
      try{session.reader?.releaseLock();}catch(_){throw fail('CLEANUP');}
      try{session.writer?.releaseLock();}catch(_){throw fail('CLEANUP');}
      if(session.readTask)await bounded(session.readTask,timeouts.close,'CLEANUP',false);
      if(port.readable?.locked||port.writable?.locked)throw fail('CLEANUP');
    }
    async function closeNative(){
      const closing=Promise.resolve().then(()=>port.close()).finally(()=>{
        if(!port.readable&&!port.writable&&active.get(port)===session)active.delete(port);
      });
      await bounded(closing,timeouts.close,'CLEANUP',false);
    }
    try{
      progress('opening');session.opening=true;
      const opening=Promise.resolve().then(()=>port.open(serialOptions)).then(async()=>{
        session.opening=false;session.opened=true;
        if(session.stopped){await closeNative();throw fail('CANCELLED');}
      },()=>{session.opening=false;if(active.get(port)===session)active.delete(port);throw fail('OPEN');});
      await bounded(opening,timeouts.open,'OPEN_TIMEOUT');assertCurrent();
      if(!port.readable||!port.writable)throw fail('OPEN');
      session.reader=port.readable.getReader();session.writer=port.writable.getWriter();
      session.readTask=(async()=>{
        try{while(!session.stopped){const {value,done}=await session.reader.read();if(done){if(!session.stopped)throw fail('LOST');break;}incoming(value);}}
        catch(error){if(!session.stopped){session.lost=true;session.waiter?.reject(fail('LOST'));abortReject(fail('LOST'));}}
      })();
      progress('settling');
      await bounded(new Promise(resolve=>setTimeout(resolve,SETTLE_MS)),SETTLE_MS+timeouts.open,'LOST');assertCurrent();
      progress('probing_companion');
      let transport;
      try{
        const response=waitFor('binary');
        transport=await send(Uint8Array.of(60,2,0,22,3),response,timeouts.binary);
      }catch(error){if(error.code!=='UNKNOWN')throw error;}
      if(!transport){
        progress('probing_service');
        // Binary DEVICE_QUERY contributes only '<' to a text-console input.
        // Clear that AND any pre-existing credential draft before the newline.
        // Overflow is sticky in firmware, so its discarded line needs one more
        // cancel. No blank password, wifi save or setting write is ever sent.
        const cancelResponse=()=>waitFor('text',resolve=>({line(line){if(acceptedCancel.has(line)||line===overflow)resolve(line);}}));
        let reply=await send(encoder.encode(cancelLine),cancelResponse(),timeouts.service);
        if(reply===overflow)reply=await send(encoder.encode(cancelLine),cancelResponse(),timeouts.service);
        if(!acceptedCancel.has(reply))throw fail('UNKNOWN');
        const help=waitFor('text',resolve=>{let header=false;return {line(line){if(helpHeaders.has(line))header=true;if(header&&line===helpEnd)resolve('service');}};});
        transport=await send(encoder.encode('help\n'),help,timeouts.service);
      }
      assertCurrent();
      await releaseStreams();
      if(signal?.aborted)throw fail('CANCELLED');
      let claimed=false,closed=false;
      const adoptedPort={
        originalPort:port,
        get readable(){return port.readable;},get writable(){return port.writable;},
        getInfo(){return port.getInfo?.()||{};},
        async open(options){
          if(closed||claimed||Object.keys(serialOptions).some(key=>options?.[key]!==serialOptions[key]))throw fail('BUSY');
          claimed=true;
        },
        async close(){if(closed)return;closed=true;await closeNative();}
      };
      progress('detected');
      if(signal?.aborted)throw fail('CANCELLED');
      return {transport,port:adoptedPort,originalPort:port};
    }catch(error){
      session.stopped=true;
      try{await releaseStreams();}catch(_){}
      if(session.opened)try{await closeNative();}catch(_){}
      if(!session.opening&&!session.opened&&active.get(port)===session)active.delete(port);
      throw error instanceof AutoConnectError?error:fail('OPEN');
    }finally{signal?.removeEventListener('abort',abort);}
  }
  return Object.freeze({detect,AutoConnectError,SETTLE_MS,defaults});
}));
