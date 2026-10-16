(function(root,factory){
  'use strict';
  const catalog=typeof module==='object'&&module.exports?require('./console_catalog'):root.SmartUiConsoleCatalog;
  const value=factory(catalog);
  if(typeof module==='object'&&module.exports)module.exports=value;
  else root.SmartUiAutoSave=value;
})(typeof globalThis!=='undefined'?globalThis:this,function(catalog){
  'use strict';
  // Only ordinary, independent preferences belong here. Firmware, transport,
  // radio, GPIO, calibration, profiles and credentials keep explicit forms.
  const keys=Object.freeze(['muted','sound_quiet','volume','melody','board_led','unread_led','vibration','ui_theme','ui_font','backlight_timeout']);
  const allowed=new Set(keys);
  const messages={
    INPUT:'Эта настройка или значение недоступны для автоприменения.',
    BUSY:'Дождитесь завершения текущей операции.',
    SESSION:'Подключение изменилось. Ожидающие изменения отменены; прочитайте настройки ноды.',
    UNCONFIRMED:'Сохранение не подтверждено. Переподключитесь и прочитайте настройки ноды.',
    BLOCKED:'Предыдущее сохранение не подтверждено. Переподключитесь перед новым изменением.'
  };
  function failure(code,message){return Object.assign(new Error(message||messages[code]||messages.UNCONFIRMED),{name:'AutoSaveError',code,safe:true});}
  function sameSession(context,captured){return context.connected&&!context.uncertain&&context.session===captured.session&&context.transport===captured.transport;}

  class Coordinator{
    constructor(bridge,onEvent=()=>{}){
      for(const name of ['getContext','acquire','execute','release'])if(typeof bridge?.[name]!=='function')throw new TypeError('AutoSave bridge requires '+name+'().');
      this.bridge=bridge;this.onEvent=onEvent;
      this._busy=false;this._releasing=false;this._queue=new Map();this._captured=null;this._active=null;this._failedSession=null;
    }
    get busy(){return this._busy;}
    get pendingKeys(){return Object.freeze([...this._queue.keys()]);}
    get activeKey(){return this._active?.key||null;}
    _emit(event){
      // A broken view must never interrupt verification, unlock another writer
      // early, or leave queued writes without a settled result.
      try{this.onEvent(Object.freeze(event));}catch(_error){}
    }
    _availability(step,context,ownLease=false){
      const availability=catalog.getAvailability(step,ownLease?{...context,busy:false}:context);
      if(!availability.available)throw failure('UNAVAILABLE',availability.reason);
    }
    _checkSession(){
      const context=this.bridge.getContext();
      if(!sameSession(context,this._captured))throw failure('SESSION');
      return context;
    }
    async set(key,value){
      // Rendering or reading a setting must not call set(). The UI calls it
      // only for an explicit user change; this module has no timers or retries.
      let context,step;
      try{
        if(!allowed.has(key)||!Number.isSafeInteger(value))throw failure('INPUT');
        if(this._releasing)throw failure('BUSY');
        context=this.bridge.getContext();
        if(!context.connected||context.session===undefined||context.session===null)throw failure('SESSION');
        if(context.session===this._failedSession)throw failure('BLOCKED');
        if(this._busy&&!sameSession(context,this._captured))throw failure('SESSION');
        step=catalog.compile('set '+key+' '+value,context.transport);
        if(step.kind!=='setting'||!step.mutates||step.schemaKey!==key||!step.readback||step.warning)throw failure('INPUT');
        this._availability(step,context,this._busy);
      }catch(error){
        this.cancel('Ожидающие изменения отменены после ошибки проверки.');
        throw error;
      }
      return new Promise((resolve,reject)=>{
        const prior=this._queue.get(key);
        const start=!this._busy;
        this._queue.set(key,{key,value,step,resolve,reject});
        if(start){this._busy=true;this._captured={session:context.session,transport:context.transport};}
        if(prior){
          prior.resolve({status:'superseded',key,value:prior.value});
          this._emit({type:'superseded',key,value:prior.value,replacement:value});
        }
        this._emit({type:'queued',key,value});
        if(start){
          // _drain handles both execution and release failures internally.
          void this._drain();
        }
      });
    }
    cancel(reason='Ожидающие изменения отменены.'){
      // The current request still awaits its verified response. Cancelling
      // cannot retract a command that has already reached the device.
      const cancelled=[...this._queue.values()];this._queue.clear();
      for(const item of cancelled){
        item.resolve({status:'cancelled',key:item.key,value:item.value});
        this._emit({type:'cancelled',key:item.key,value:item.value,message:reason});
      }
    }
    async _drain(){
      let acquired=false,attemptedWrite=false;
      try{
        const context=this._checkSession();
        if(context.busy)throw failure('BUSY');
        this.bridge.acquire(this._captured.session);acquired=true;
        while(this._queue.size){
          const item=this._queue.values().next().value;
          this._queue.delete(item.key);this._active=item;
          const current=this._checkSession();
          this._availability(item.step,current,true);
          this._emit({type:'applying',key:item.key,value:item.value});
          // Recheck after notification: a view may synchronously disconnect,
          // change read-only state, or navigate to another connection.
          this._availability(item.step,this._checkSession(),true);
          attemptedWrite=true;
          const result=await this.bridge.execute(item.step);
          this._checkSession();
          if(result?.verified!==true)throw failure('UNCONFIRMED');
          item.resolve({status:'saved',key:item.key,value:item.value,result});
          this._active=null;attemptedWrite=false;
          this._emit({type:'saved',key:item.key,value:item.value,result});
        }
      }catch(error){
        const safe=error?.safe?failure(error.code||'UNCONFIRMED',error.message):failure('UNCONFIRMED');
        if(attemptedWrite)this._failedSession=this._captured.session;
        if(this._active){this._active.reject(safe);this._active=null;}
        for(const item of this._queue.values())item.reject(safe);
        this._queue.clear();
        this._emit({type:'error',message:safe.message,code:safe.code,attemptedWrite});
      }finally{
        this._releasing=true;
        try{if(acquired)await this.bridge.release();}
        catch(_error){
          this._failedSession=this._captured.session;
          this._emit({type:'error',message:messages.UNCONFIRMED,code:'UNCONFIRMED',attemptedWrite:false});
        }finally{
          this._busy=false;this._releasing=false;this._captured=null;this._active=null;
          this._emit({type:'idle'});
        }
      }
    }
  }
  return Object.freeze({Coordinator,keys});
});
