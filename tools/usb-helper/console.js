'use strict';
(() => {
  const catalog=SmartUiConsoleCatalog,bridge=SmartUiConsoleBridge;
  const section=document.createElement('section');section.id='command-console';section.className='card wide page-hidden';section.dataset.pages='console';
  // Only fixed application markup. Device strings and imported files use textContent.
  section.innerHTML=`
    <div class="command-head"><div><p class="panel-kicker">Локальное управление</p><h2>Консоль и макросы</h2><p class="hint">Нода → подсистема → действие. Команды и ответы — в журнале ниже.</p></div><span id="command-session" class="status-pill">Нет подключения</span></div>
    <div class="command-work"><div class="command-map"><label class="command-search field" for="command-search">Найти действие или команду</label><input id="command-search" type="text" placeholder="Например, мелодия, ADC или get battery" autocomplete="off"><div class="command-tree"><div class="command-origin" aria-hidden="true">NODE</div><div id="command-groups" class="command-groups" aria-label="Подсистемы"></div><div id="command-leaves" class="command-leaves" aria-label="Макросы"></div></div></div>
    <div class="command-inspector"><div class="command-inspector-header"><p id="command-category" class="panel-kicker"></p><h3 id="command-title"></h3><p id="command-description" class="command-description"></p><span id="command-kind" class="command-kind"></span></div><div><label id="command-parameter" class="command-parameter" hidden><span id="command-parameter-label"></span><span id="command-parameter-control"></span></label><pre id="command-preview" class="command-code"></pre><p id="command-reason" class="command-reason"></p></div><div class="buttons"><button id="command-run" type="button" class="primary">Выполнить макрос</button><button id="command-insert" type="button">В консоль</button><button id="command-favorite" type="button" aria-pressed="false">В избранное</button><button id="command-edit" type="button" hidden>Изменить</button><button id="command-delete" type="button" hidden>Удалить</button></div></div></div>
    <div class="command-terminal"><div class="command-terminal-head"><h3>Консоль ноды</h3><div class="buttons"><button id="command-stop" type="button" disabled>Остановить</button><button id="command-clear" type="button">Очистить журнал</button><button id="command-log-save" type="button">Скачать журнал</button></div></div><div id="command-journal" class="command-journal" role="log" aria-label="Команды и ответы ноды" aria-live="polite"></div><label class="field" for="command-input">Команда или последовательность · до 16 строк</label><div class="command-entry"><textarea id="command-input" rows="2" spellcheck="false" autocomplete="off" placeholder="get battery"></textarea><button id="command-send" type="button">Выполнить</button></div><p id="command-status" class="command-state" role="status">Enter — выполнить; Shift+Enter — новая строка; ↑↓ — история одной команды; Tab — дополнение.</p><p class="hint">Один запрос за раз. При ошибке выполнение прекращается. «Остановить» дождётся текущего ответа; уже выполненные изменения сохранятся. PIN, Wi-Fi, смена подключения и запись ADC доступны через отдельные формы.</p></div>
    <details id="command-editor" class="command-editor"><summary>Свои макросы · создать, импортировать, сохранить</summary><p class="hint">Название, пояснение и команды сохраняются только в этом браузере. Для переноса в другой файл Helper экспортируйте JSON. Журнал и история остаются в памяти до закрытия страницы.</p><div class="command-editor-grid"><label>Название<input id="macro-name" type="text" maxlength="48" autocomplete="off" placeholder="Моя настройка звука"></label><label>Краткое пояснение<input id="macro-description" type="text" maxlength="240" autocomplete="off" placeholder="Что изменится на ноде"></label><label class="wide">Команды · одна на строку<textarea id="macro-commands" rows="4" spellcheck="false" autocomplete="off" placeholder="set volume 7&#10;get volume"></textarea></label></div><div class="buttons"><button id="macro-save" type="button" class="primary">Сохранить макрос</button><button id="macro-new" type="button">Новый</button><button id="macro-from-console" type="button">Взять из консоли</button><button id="macro-export" type="button">Экспорт JSON</button><button id="macro-import-button" type="button">Импорт JSON</button><input id="macro-import" type="file" accept=".json,application/json" hidden></div><p id="macro-status" class="command-state" role="status"></p></details>`;
  document.getElementById('firmware-section').before(section);
  const $=id=>document.getElementById(id);
  const compatibility=document.createElement('details');compatibility.id='legacy-cli-details';compatibility.className='wide';compatibility.dataset.pages='service';
  const compatibilityTitle=document.createElement('summary');compatibilityTitle.textContent='Совместимая консоль для прежних прошивок';compatibility.append(compatibilityTitle);$('api-developer').before(compatibility);compatibility.append($('api-developer'));compatibility.classList.add('page-hidden');
  const STORAGE_KEY='smartui.helper.macros.v1',MAX_CUSTOM=32,MAX_FILE=65536;
  let custom=[],favorites=[],selected='diagnostics',group='connection',editing=null,parameterValues={},history=[],historyIndex=0,logs=[],lastSession=bridge.getContext().session;
  const message=(id,text,kind='info')=>{$(id).textContent=text;$(id).dataset.kind=kind;};
  const allActions=()=>catalog.actions.concat(custom.map(item=>({...item,label:item.name,group:'custom',custom:true})));
  const selectedAction=()=>allActions().find(item=>item.id===selected)||catalog.actions[0];
  const idValid=id=>typeof id==='string'&&/^[a-z0-9:-]{1,80}$/.test(id);
  function cleanLibrary(input){
    if(!input||input.version!==1||!Array.isArray(input.macros)||input.macros.length>MAX_CUSTOM||!Array.isArray(input.favorites)||input.favorites.length>100)throw new Error('Неверный формат библиотеки макросов.');
    const ids=new Set(),macros=input.macros.map(item=>{if(!item||!idValid(item.id)||!item.id.startsWith('user:')||ids.has(item.id))throw new Error('Некорректный идентификатор макроса.');ids.add(item.id);const checked=catalog.validateMacro(item);return {id:item.id,name:checked.name,description:checked.description,commands:checked.commands};});
    const known=new Set(catalog.actions.map(item=>item.id).concat(macros.map(item=>item.id)));
    return {version:1,macros,favorites:[...new Set(input.favorites.filter(id=>idValid(id)&&known.has(id)))]};
  }
  function saveLibrary(){
    const data=cleanLibrary({version:1,macros:custom,favorites});
    try{localStorage.setItem(STORAGE_KEY,JSON.stringify(data));return true;}
    catch(_){message('macro-status','Браузер не разрешил локальное сохранение. Макросы доступны до закрытия страницы; экспортируйте JSON.','error');return false;}
  }
  try{const raw=localStorage.getItem(STORAGE_KEY);if(raw){if(raw.length>MAX_FILE)throw new Error('size');const data=cleanLibrary(JSON.parse(raw));custom=data.macros;favorites=data.favorites;}}
  catch(_){message('macro-status','Сохранённая библиотека недоступна или не прошла проверку. Можно импортировать проверенный JSON.','error');}
  function log(text,kind='info'){
    const entry={time:new Date().toLocaleTimeString('ru-RU'),text:String(text).slice(0,4096),kind};logs.push(entry);logs=logs.slice(-300);
    const row=document.createElement('div');row.className='command-line';row.dataset.kind=kind;const time=document.createElement('time'),body=document.createElement('span');time.textContent=entry.time;body.textContent=entry.text;row.append(time,body);$('command-journal').append(row);while($('command-journal').children.length>300)$('command-journal').firstElementChild.remove();$('command-journal').scrollTop=$('command-journal').scrollHeight;
  }
  const runner=new SmartUiMacroRunner.Runner(bridge,event=>{
    if(event.type==='command'){log('› '+event.command,'command');history.push(event.command);history=history.slice(-100);historyIndex=history.length;message('command-status','Выполняется шаг '+(event.index+1)+' из '+event.total+'…');}
    if(event.type==='reply'){log(event.result.reply,'reply');if(event.result.readback)log('Прочитано после изменения: '+event.result.readback,'reply');if(event.result.verified)log('Сохранение проверено чтением обратно.');}
    if(event.type==='complete')message('command-status','Готово: '+event.completed+' шагов.');
    if(event.type==='stopped'){log('Последовательность остановлена после '+event.completed+' шагов.');message('command-status','Остановлено. Уже выполненные изменения остаются на ноде.');}
    if(event.type==='error'){log(event.message+' Выполнение остановлено.','error');message('command-status',event.message+(event.attemptedWrite?' Часть настроек могла измениться; автоматического повтора нет.':''),'error');}
    renderState();
  });
  function commandsFor(item){return item.custom?item.commands:catalog.renderAction(item,parameterValues[item.id]||{});}
  function availability(item){
    try{const context={...bridge.getContext(),params:parameterValues[item.id]||{}};if(item.custom){const plan=catalog.validateMacro(item,context.transport);for(const step of plan.steps){const state=catalog.getAvailability(step,context);if(!state.available)return state;}return {available:true,state:'ready',reason:'Готов к выполнению.'};}return catalog.getAvailability(item,context);}
    catch(error){return {available:false,state:'invalid',reason:error.safe?error.message:'Проверьте параметры макроса.'};}
  }
  function selectAction(id){selected=id;const item=selectedAction();if(group!=='favorites'&&group!=='custom')group=item.group;renderTree();renderCard(true);}
  function renderTree(){
    const groups=catalog.groups.concat([{id:'favorites',label:'Избранное'},{id:'custom',label:'Свои макросы'}]);
    $('command-groups').replaceChildren();for(const item of groups){const button=document.createElement('button');button.type='button';button.textContent=item.label;button.dataset.commandGroup=item.id;button.setAttribute('aria-pressed',String(group===item.id));button.onclick=()=>{group=item.id;$('command-search').value='';const first=allActions().find(action=>group==='favorites'?favorites.includes(action.id):action.group===group);if(first)selected=first.id;renderTree();renderCard(true);};$('command-groups').append(button);}
    const query=$('command-search').value.trim().toLocaleLowerCase('ru-RU');let visible=allActions().filter(item=>query?((item.label||item.name)+' '+item.description+' '+(item.commands||[]).join(' ')).toLocaleLowerCase('ru-RU').includes(query):group==='favorites'?favorites.includes(item.id):item.group===group);
    $('command-leaves').replaceChildren();for(const item of visible){const state=availability(item),button=document.createElement('button'),title=document.createElement('strong'),caption=document.createElement('small');button.type='button';button.className='command-leaf';button.dataset.actionId=item.id;button.dataset.available=state.available;button.setAttribute('aria-pressed',String(selected===item.id));title.textContent=(favorites.includes(item.id)?'★ ':'')+(item.label||item.name);caption.textContent=item.navigation?'Открыть настройку':state.available?(item.custom?item.commands.length+' команд':'Команды и пояснение'):({offline:'Подключите ноду',busy:'Выполняется запрос',readonly:'Только чтение',unsupported:'Не поддерживается',unknown:'Нужна проверка',range:'Проверьте значение'}[state.state]||'Недоступно');button.append(title,caption);button.onclick=()=>selectAction(item.id);$('command-leaves').append(button);}
    if(!visible.length){const empty=document.createElement('p');empty.className='command-empty';empty.textContent=query?'Совпадений нет. Попробуйте название функции или команды.':group==='favorites'?'Выберите действие и нажмите «В избранное».':'Сохраните свой макрос в разделе ниже.';$('command-leaves').append(empty);}
  }
  function renderCard(rebuildParameter=false){
    const item=selectedAction(),state=availability(item),context=bridge.getContext();let commands=[],mutates=false,valid=true;
    try{commands=commandsFor(item);mutates=commands.some(command=>catalog.compile(command,context.transport).mutates);}catch(_){valid=false;}
    $('command-category').textContent=item.custom?'Свои макросы':catalog.groups.find(g=>g.id===item.group)?.label||'Макрос';$('command-title').textContent=item.label||item.name;$('command-description').textContent=item.description;$('command-kind').textContent=item.navigation?'Отдельная форма':mutates?'Изменяет настройки / запускает действие':'Только чтение';$('command-kind').dataset.write=mutates;
    $('command-preview').textContent=item.navigation?'Настройка с отдельной проверкой и подтверждением.':commands.join('\n');
    if(valid&&context.transport==='service'&&commands.length)$('command-preview').textContent+='\n\nUSB: текстовый протокол\n'+commands.map(command=>catalog.compile(command,'service').wire).join('\n');
    $('command-reason').textContent=state.reason;
    if(item.id==='melody'&&context.caps?.melody_max!==undefined)$('command-reason').textContent+=' Нода сообщает максимум: '+context.caps.melody_max+'.';
    $('command-run').textContent=item.navigation?'Открыть настройку':'Выполнить макрос';$('command-run').disabled=runner.busy||!state.available||!valid;$('command-insert').disabled=runner.busy||!valid||Boolean(item.navigation);
    $('command-favorite').textContent=favorites.includes(item.id)?'★ В избранном':'В избранное';$('command-favorite').setAttribute('aria-pressed',String(favorites.includes(item.id)));$('command-edit').hidden=!item.custom;$('command-delete').hidden=!item.custom;$('command-edit').disabled=runner.busy;$('command-delete').disabled=runner.busy;
    $('command-parameter').hidden=!item.parameter;
    if(rebuildParameter){$('command-parameter-control').replaceChildren();if(item.parameter){const p=item.parameter,input=document.createElement(p.type==='select'?'select':'input');input.id='command-value';input.setAttribute('aria-label',p.label);$('command-parameter-label').textContent=p.label;if(p.type==='select'){for(const entry of p.options){const option=document.createElement('option');option.value=entry.value;option.textContent=entry.label;input.append(option);}}else{input.type='number';input.min=p.min;input.max=item.id==='melody'&&context.caps?.melody_max!==undefined?context.caps.melody_max:p.max;input.step=p.step;}
      input.value=parameterValues[item.id]?.[p.name]??p.default;input.oninput=()=>{parameterValues[item.id]={[p.name]:input.value};renderCard();renderTree();};$('command-parameter-control').append(input);}}
    if($('command-value'))$('command-value').disabled=runner.busy;
  }
  function renderState(){
    const context=bridge.getContext();
    if(context.session!==lastSession){history=[];historyIndex=0;lastSession=context.session;if(logs.length)log('Сеанс подключения изменился.');}
    $('command-session').textContent=!context.connected?'Нода не подключена':(context.transport==='companion'?'USB-компаньон':'Сервисная USB-консоль')+' · '+(context.firmware||'версия не прочитана');
    $('command-send').disabled=runner.busy||!context.connected||context.busy;$('command-stop').disabled=!runner.busy;$('command-input').disabled=runner.busy;
    for(const id of ['macro-save','macro-new','macro-from-console','macro-import-button'])$(id).disabled=runner.busy;
    renderTree();renderCard();
  }
  async function execute(macro){try{const result=await runner.run(macro);if(result.status==='cancelled')message('command-status','Выполнение отменено; команды не отправлены.');}catch(error){message('command-status',error?.safe?error.message:'Макрос не прошёл проверку.','error');}finally{renderState();}}
  $('command-run').onclick=()=>{const item=selectedAction();if(item.navigation){bridge.navigate(item.navigation);return;}let commands;try{commands=commandsFor(item);}catch(error){message('command-status',error.message,'error');return;}void execute({name:item.label||item.name,description:item.description,commands});};
  $('command-insert').onclick=()=>{try{$('command-input').value=commandsFor(selectedAction()).join('\n');$('command-input').focus();}catch(error){message('command-status',error.message,'error');}};
  $('command-send').onclick=()=>{const raw=$('command-input').value;let macro;try{macro=catalog.validateMacro({name:'Команды из консоли',commands:raw},bridge.getContext().transport);}catch(error){message('command-status',error.safe?error.message:'Команда не прошла проверку.','error');return;}$('command-input').value='';void execute(macro);};
  $('command-stop').onclick=()=>{runner.stop();message('command-status','Остановка запрошена. Ожидаем ответ на текущую команду; следующие не отправятся.');};
  $('command-clear').onclick=()=>{logs=[];$('command-journal').replaceChildren();};
  $('command-search').oninput=renderTree;
  $('command-favorite').onclick=()=>{const item=selectedAction();favorites=favorites.includes(item.id)?favorites.filter(id=>id!==item.id):favorites.concat(item.id);saveLibrary();renderTree();renderCard();};
  function download(name,text,type){const url=URL.createObjectURL(new Blob([text],{type})),link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  $('command-log-save').onclick=()=>download('SmartUI-console-log.txt',logs.map(item=>item.time+' '+item.text).join('\n'),'text/plain;charset=utf-8');
  $('command-input').onkeydown=event=>{
    if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();if(!$('command-send').disabled)$('command-send').click();}
    if(['ArrowUp','ArrowDown'].includes(event.key)&&!event.shiftKey&&!$('command-input').value.includes('\n')&&history.length){event.preventDefault();historyIndex=Math.max(0,Math.min(history.length,historyIndex+(event.key==='ArrowUp'?-1:1)));$('command-input').value=history[historyIndex]||'';}
    if(event.key==='Tab'&&!event.shiftKey){const query=$('command-input').value.trim();if(!query||query.includes('\n'))return;const candidates=[...new Set(catalog.actions.filter(item=>!item.navigation).flatMap(item=>catalog.renderAction(item)))].filter(command=>command.startsWith(query));const choice=candidates.find(command=>command!==query);if(choice){event.preventDefault();$('command-input').value=choice;}}
  };
  function openEditor(item){editing=item?.id||null;$('macro-name').value=item?.name||'';$('macro-description').value=item?.description||'';$('macro-commands').value=item?.commands?.join('\n')||'';$('macro-save').textContent=editing?'Сохранить изменения':'Сохранить макрос';$('command-editor').open=true;$('macro-name').focus();}
  $('command-edit').onclick=()=>openEditor(selectedAction());$('macro-new').onclick=()=>openEditor(null);
  $('macro-from-console').onclick=()=>{openEditor(null);$('macro-commands').value=$('command-input').value;};
  function newId(){const bytes=new Uint32Array(2);crypto.getRandomValues(bytes);return 'user:'+Array.from(bytes,n=>n.toString(16)).join('');}
  $('macro-save').onclick=()=>{
    try{const checked=catalog.validateMacro({name:$('macro-name').value,description:$('macro-description').value,commands:$('macro-commands').value});if(!editing&&custom.length>=MAX_CUSTOM)throw new Error('Допустимо до 32 собственных макросов.');const item={id:editing||newId(),name:checked.name,description:checked.description,commands:checked.commands};custom=custom.filter(m=>m.id!==item.id).concat(item);selected=item.id;group='custom';editing=item.id;if(saveLibrary())message('macro-status','Макрос сохранён в этом браузере. Для переноса экспортируйте JSON.');renderTree();renderCard(true);}
    catch(error){message('macro-status',error.safe?error.message:error.message||'Макрос не прошёл проверку.','error');}
  };
  $('command-delete').onclick=async()=>{const item=selectedAction();if(!item.custom||!await bridge.confirm('Удалить собственный макрос «'+item.name+'» из этого браузера?'))return;if(runner.busy)return;custom=custom.filter(m=>m.id!==item.id);favorites=favorites.filter(id=>id!==item.id);selected='diagnostics';group='connection';if(editing===item.id)openEditor(null);saveLibrary();renderTree();renderCard(true);};
  $('macro-export').onclick=()=>download('SmartUI-macros.json',JSON.stringify(cleanLibrary({version:1,macros:custom,favorites}),null,2)+'\n','application/json');
  $('macro-import-button').onclick=()=>$('macro-import').click();
  $('macro-import').onchange=async()=>{
    const file=$('macro-import').files[0];$('macro-import').value='';if(!file)return;
    try{if(file.size>MAX_FILE)throw new Error('Файл больше 64 КБ.');const data=cleanLibrary(JSON.parse(await file.text()));if(runner.busy)throw new Error('Дождитесь окончания макроса и повторите импорт.');const added=data.macros.filter(item=>!custom.some(old=>old.id===item.id));if(custom.length+added.length>MAX_CUSTOM)throw new Error('После импорта получится больше 32 макросов.');custom=custom.concat(added);favorites=[...new Set(favorites.concat(data.favorites))];if(saveLibrary())message('macro-status','Добавлено макросов: '+added.length+'. Совпадающие идентификаторы пропущены. Команды не выполнялись.');group='custom';if(added[0])selected=added[0].id;renderTree();renderCard(true);}
    catch(error){message('macro-status',error.safe?error.message:'Импорт не выполнен: '+(error instanceof SyntaxError?'некорректный JSON.':error.message),'error');}
  };
  window.addEventListener('smartui-helper-state',renderState);
  window.addEventListener('beforeunload',event=>{if(runner.busy){event.preventDefault();event.returnValue='';}});
  renderTree();renderCard(true);renderState();log('Журнал текущей страницы. PIN и сетевые реквизиты сюда не записываются.');
})();
