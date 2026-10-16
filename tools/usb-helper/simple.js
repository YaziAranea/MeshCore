'use strict';
(() => {
  const bridge=SmartUiConsoleBridge,catalog=SmartUiConsoleCatalog,$=id=>document.getElementById(id);
  const definitions=[
    ['muted','Общая тишина','Отключает звук, свет и вибрацию уведомлений. Индикаторы состояния работают отдельно.'],
    ['sound_quiet','Звук личных сообщений','Разрешает звуковые уведомления ЛС. Общая тишина имеет приоритет.'],
    ['volume','Громкость','Отпустите ползунок — новое значение сохранится на ноде.'],
    ['melody','Мелодия','Выберите мелодию для уведомлений. Выбор сразу сохраняется.'],
    ['board_led','Индикатор платы','Включает доступную в прошивке световую индикацию платы.'],
    ['unread_led','Непрочитанные сообщения','Световая индикация новых непрочитанных сообщений.'],
    ['vibration','Вибрация','Уведомления через настроенный вибромотор.'],
    ['ui_theme','Оформление экрана','Номер оформления из доступных на этой ноде.'],
    ['ui_font','Шрифт экрана','Номер шрифта из доступных на этой ноде.'],
    ['backlight_timeout','Тайм-аут экрана','Через сколько секунд бездействия гасить экран.']
  ];
  const panel=document.createElement('section');panel.id='simple-panel';panel.className='card wide';panel.dataset.pages='simple';
  panel.innerHTML='<div class="simple-intro"><div><p class="panel-kicker">Настроить и пользоваться</p><h2 id="simple-title">Всё нужное — под рукой</h2><p class="hint">Выбор применяется автоматически. Helper проверяет результат на ноде — отдельная кнопка сохранения не нужна.</p></div><span id="simple-device" class="status-pill">Ожидает подключения</span></div><p id="simple-status" class="simple-status" role="status" aria-live="polite">Подключите ноду кнопкой выше.</p><div id="simple-fields" class="simple-fields" hidden></div><p id="simple-empty" class="simple-empty">После подключения здесь появятся доступные настройки вашей ноды.</p><div class="simple-links"><p class="hint">PIN телефона, ADC, радио, выводы, консоль и макросы — в расширенном режиме. Там изменения применяются отдельными кнопками.</p><div class="buttons"><button id="simple-pin" type="button">Bluetooth PIN</button><button id="simple-advanced" type="button">Все настройки</button></div></div>';
  document.querySelector('.grid').prepend(panel);
  const rows=new Map(),rowMessages=new Map();
  let session=null,transport=null,message='',messageState='',blocked=false;
  function status(text,state=''){message=text;messageState=state;$('simple-status').textContent=text;$('simple-status').dataset.state=state;}
  const save=new SmartUiAutoSave.Coordinator(bridge,event=>{
    if(event.type==='applying'){
      rowMessages.set(event.key,'Применяем и проверяем…');status('Применяем и проверяем на ноде…','applying');
    }else if(event.type==='saved'){
      bridge.clearSettingDraft(event.key);
      rowMessages.set(event.key,'Сохранено и проверено');status('Сохранено и проверено на ноде.','saved');
    }else if(event.type==='error'){
      blocked=Boolean(event.attemptedWrite)||event.code==='UNCONFIRMED'||event.code==='BLOCKED';
      rowMessages.clear();status(event.message,'error');
      if(blocked)window.dispatchEvent(new Event('smartui-reconnect-required'));
    }
    render();
  });
  for(const [key,title,hint]of definitions){
    const row=document.createElement('div');row.className='simple-setting';row.hidden=true;row.dataset.key=key;
    const label=document.createElement('label');label.htmlFor='simple-setting-'+key;label.textContent=title;
    const description=document.createElement('p');description.className='hint';description.id='simple-hint-'+key;description.textContent=hint;
    const field=document.createElement(key==='volume'?'input':'select');field.id='simple-setting-'+key;field.setAttribute('aria-describedby',description.id);
    if(key==='volume'){field.type='range';field.oninput=()=>{value.textContent=field.value;};}
    const value=document.createElement('output');value.htmlFor=field.id;value.hidden=key!=='volume';
    const result=document.createElement('p');result.id='simple-state-'+key;result.className='setting-state';
    field.onchange=async()=>{
      const context=bridge.getContext(),selected=Number(field.value);
      if(field.disabled||!context.connected||context.busy||blocked){render();return;}
      if(selected===Number(context.settings?.[key])){render();return;}
      try{await save.set(key,selected);}catch(error){status(error?.safe?error.message:'Сохранение не подтверждено. Переподключите ноду.','error');render();}
    };
    row.append(label,description,field,value,result);$('simple-fields').append(row);
    rows.set(key,{row,field,value,result,signature:''});
  }
  function render(){
    const context=bridge.getContext();
    if(context.session!==session||context.transport!==transport){
      save.cancel();session=context.session;transport=context.transport;blocked=false;message='';messageState='';rowMessages.clear();
    }
    const ready=Boolean(context.connected&&context.settings);
    $('simple-device').textContent=ready?'SmartUI '+(context.firmware||'—')+' · '+(context.transport==='companion'?'USB-компаньон':'USB-консоль'):'Ожидает подключения';
    $('simple-title').textContent=ready&&context.name?context.name:'Всё нужное — под рукой';
    $('simple-pin').disabled=!context.connected||context.busy||Number(context.caps?.ble_pin)!==1;
    let visible=0;
    for(const [key,item]of rows){
      const schema=context.schemas?.[key],current=Number(context.settings?.[key]);
      const display=['ui_theme','ui_font','backlight_timeout'].includes(key);
      const exists=ready&&schema?.supported&&context.settings?.[key]!==undefined&&SmartUiConsole.settingValueValid(schema,current)&&(!display||Number(context.caps?.display)===1);
      item.row.hidden=!exists;
      if(!exists)continue;
      visible++;
      const step=catalog.compile('set '+key+' '+current,context.transport);
      const availability=catalog.getAvailability(step,context);
      item.field.disabled=blocked||save.busy||!availability.available;
      const signature=JSON.stringify([schema,context.melodyNames]);
      if(signature!==item.signature){
        item.signature=signature;
        if(key==='volume'){item.field.min=String(schema.min);item.field.max=String(schema.max);item.field.step=String(schema.step);}
        else{
          const options=SmartUiConsole.settingOptions({key},schema,context.melodyNames||{});
          item.field.replaceChildren();
          for(const [value,label]of options||[]){const option=document.createElement('option');option.value=String(value);option.textContent=label;item.field.append(option);}
          if(!options)item.field.disabled=true;
        }
      }
      // These values always come from the verified node snapshot. Rendering
      // never dispatches change events, replays drafts or starts a write.
      if(!save.busy||save.activeKey!==key){item.field.value=String(current);item.value.textContent=String(current);}
      item.result.textContent=blocked?'Сохранение не подтверждено':rowMessages.get(key)||(context.write?'Прочитано с ноды':'Только чтение');
    }
    $('simple-fields').hidden=!visible;
    $('simple-empty').hidden=Boolean(visible);
    $('simple-empty').textContent=ready?'Для этой прошивки нет простых настроек. Откройте «Все настройки».':'После подключения здесь появятся доступные настройки вашей ноды.';
    if(!context.connected&&!message){
      $('simple-status').textContent='Подключите ноду кнопкой выше.';$('simple-status').dataset.state='';
    }else if(!message){
      $('simple-status').textContent=!ready||context.busy?'Читаем настройки ноды…':context.write?'Прочитано с ноды. Выберите настройку — она применится автоматически.':'Нода доступна только для чтения. Изменения отключены.';
      $('simple-status').dataset.state='';
    }else{$('simple-status').textContent=message;$('simple-status').dataset.state=messageState;}
    // The dashboard owns navigation. This script loads after its first render.
    panel.classList.toggle('page-hidden',document.querySelector('main').dataset.view!=='simple');
  }
  $('simple-pin').onclick=()=>bridge.navigate('pin');
  $('simple-advanced').onclick=()=>$('view-advanced').click();
  window.addEventListener('smartui-helper-state',render);
  window.addEventListener('beforeunload',()=>save.cancel());
  render();
})();
