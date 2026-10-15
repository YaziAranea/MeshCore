(function(root,factory){
  const catalog=typeof module==='object'&&module.exports?require('./console_catalog'):root.SmartUiConsoleCatalog;
  const value=factory(catalog);if(typeof module==='object'&&module.exports)module.exports=value;else root.SmartUiMacroRunner=value;
})(typeof globalThis!=='undefined'?globalThis:this,function(catalog){
  'use strict';
  const warnings={
    battery:'Отключение защиты 3,2 В оставляет только аварийную отсечку. Нужны исправная BMS и проверенная калибровка ADC.',
    tx:'Изменение мощности влияет на радиосвязь. Учитывайте допустимую мощность, антенну и ограничения региона.',
    profile:'Профиль изменяет несколько настроек уведомлений.',
    pin:'Изменяется физический вывод. Проверьте распиновку и подключённую нагрузку.',
    bridge:'Мост требует совместимого плавающего пьезоизлучателя между выводами, без соединения с землёй.'
  };
  function failure(message){return Object.assign(new Error(message),{safe:true});}
  class Runner{
    constructor(bridge,onEvent=()=>{}){this.bridge=bridge;this.onEvent=onEvent;this.busy=false;this.stopRequested=false;}
    stop(){this.stopRequested=true;}
    async run(macro){
      if(this.busy)throw failure('Другая последовательность уже выполняется.');
      const before=this.bridge.getContext();
      const plan=catalog.validateMacro(macro,before.transport);
      if(!before.connected||before.busy)throw failure('Подключите ноду и дождитесь окончания текущей операции.');
      for(const step of plan.steps){const state=catalog.getAvailability(step,before);if(!state.available)throw failure(state.reason);}
      this.busy=true;this.stopRequested=false;
      let acquired=false,completed=0,attemptedWrite=false;
      try{
        this.bridge.acquire(before.session);acquired=true;
        if(plan.mutates){
          const notes=[...new Set(plan.steps.map(step=>warnings[step.warning]).filter(Boolean))];
          const text='Выполнить «'+plan.name+'»?\n\n'+plan.commands.join('\n')+'\n\nКоманды могут изменять настройки или запускать действия. При ошибке оставшиеся шаги остановятся; выполненные изменения не откатываются.'+(notes.length?'\n\n'+notes.join('\n'):'');
          if(!await this.bridge.confirm(text))return {status:'cancelled',completed:0};
        }
        for(let index=0;index<plan.steps.length;index++){
          if(this.stopRequested){this.onEvent({type:'stopped',completed});return {status:'stopped',completed};}
          const context=this.bridge.getContext();
          if(context.session!==before.session||context.transport!==before.transport||!context.connected)throw failure('Подключение изменилось. Оставшиеся команды остановлены; проверьте состояние ноды.');
          const step=plan.steps[index],state=catalog.getAvailability(step,{...context,busy:false});
          if(!state.available)throw failure(state.reason);
          this.onEvent({type:'command',command:step.canonical,index,total:plan.steps.length});
          attemptedWrite=attemptedWrite||step.mutates;
          const result=await this.bridge.execute(step);
          if(this.bridge.getContext().session!==before.session)throw failure('Сеанс сменился до подтверждения ответа. Переподключитесь и прочитайте настройки.');
          completed++;
          this.onEvent({type:'reply',command:step.canonical,result,index,total:plan.steps.length});
        }
        this.onEvent({type:'complete',completed});return {status:'complete',completed};
      }catch(error){
        const message=error?.safe?error.message:'Операция не подтверждена. Переподключитесь и прочитайте состояние ноды.';
        this.onEvent({type:'error',message,completed,attemptedWrite});throw failure(message);
      }finally{
        try{if(acquired)await this.bridge.release();}finally{this.busy=false;this.onEvent({type:'idle'});}
      }
    }
  }
  return Object.freeze({Runner});
});
