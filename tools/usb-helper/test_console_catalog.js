'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const catalog=require('./console_catalog');
const cli=require('./api');
const service=require('./core');
const both=['companion','service'];
const schema=(min=0,max=1,options=null)=>({supported:true,min,max,step:1,options});
const context={connected:true,write:true,control:true,meshcore:true,transport:'companion',
  caps:{sound:1,sound_preview:1,display:0,gps:1,adc:1,unread_led:1,vibration:0},
  schemas:{muted:schema(),sound_quiet:schema(),volume:schema(1,10),melody:schema(0,30),
    fem_pa:{...schema(),supported:false},ui_theme:{...schema(0,3),supported:false}},ranges:{tx:{min:-9,max:22}}};

test('browser UMD works without Node or dependencies and freezes the catalog',()=>{
  const sandbox={TextEncoder,TextDecoder};
  vm.runInNewContext(fs.readFileSync(require.resolve('./console_catalog'),'utf8'),sandbox);
  assert.equal(sandbox.SmartUiConsoleCatalog.actions.length,40);
  assert(Object.isFrozen(catalog.actions));
  assert(Object.isFrozen(catalog.actions[0].commands));
  assert.throws(()=>{catalog.actions[0].label='changed';},TypeError);
});

test('all forty actions have unique ids, explanations and valid group membership',()=>{
  assert.equal(catalog.actions.length,40);
  assert.equal(new Set(catalog.actions.map(a=>a.id)).size,40);
  assert.equal(catalog.groups.length,6);
  for(const action of catalog.actions){
    assert(catalog.groups.some(group=>group.id===action.group));
    assert(action.label.length>2&&action.description.length>15);
    assert(action.navigation||action.commands.length);
  }
});

test('every built-in action passes both independently enforced protocol allowlists',()=>{
  for(const action of catalog.actions)for(const command of catalog.renderAction(action)){
    for(const transport of both){
      const compiled=catalog.compile(command,transport);
      assert.equal(compiled.transport,transport);
      assert(compiled.wire.length<=156);
      if(transport==='companion')assert.doesNotThrow(()=>cli.developerCommand(compiled.wire),command);
      else assert.doesNotThrow(()=>service.consoleCommandPolicy(compiled.wire),compiled.wire);
      if(compiled.readback)assert.doesNotThrow(()=>catalog.compile(compiled.readback,transport));
    }
  }
});

test('positive sound maps to inverse service storage and unambiguous readback',()=>{
  for(const transport of both){
    for(const value of ['on','1']){
      const step=catalog.compile('set sound '+value,transport);
      assert.equal(step.expectedValue,0);
      assert.equal(step.schemaKey,'sound_quiet');
      assert.equal(step.readback,'get sound_quiet');
      assert.equal(step.wire,transport==='service'?'settings set sound_quiet 0':'set sound '+value);
    }
    assert.equal(catalog.compile('set sound off',transport).expectedValue,1);
  }
  const read=catalog.compile('get sound','service');
  assert.equal(read.wire,'settings get sound_quiet');
  assert.equal(read.invert,true);
});

test('mute aliases preserve general mute semantics and expose dependent reads',()=>{
  const mute=catalog.compile('set mute on','service');
  assert.equal(mute.wire,'settings set muted 1');
  assert.equal(mute.readback,'get muted');
  assert.deepEqual(mute.extraReadbacks,['get muted','get night_quiet']);
  assert.equal(catalog.compile('get muted','service').wire,'settings get muted');
  assert.equal(catalog.compile('set night_quiet off').warning,'night_quiet');
});

test('dotted capabilities use the correct service source without confusing sound and ADC aliases',()=>{
  for(const key of ['sound','adc','display','adc_min','melody_max']){
    const step=catalog.compile('caps '+key,'service');
    assert.equal(step.wire,'settings caps');
    assert.equal(step.capabilityKey,key);
    assert.equal(step.source,'caps');
  }
  const fem=catalog.compile('caps fem.pa','service');
  assert.equal(fem.wire,'settings schema fem_pa');
  assert.equal(fem.source,'schema');
  assert.equal(catalog.compile('caps sound_preview','service').wire,'settings caps sound_preview');
});

test('capability inspection remains possible for unsupported features',()=>{
  assert.equal(catalog.getAvailability(catalog.compile('caps fem.pa'),context).available,true);
  assert.equal(catalog.getAvailability(catalog.compile('get fem.pa'),context).available,true);
  assert.equal(catalog.getAvailability(catalog.compile('schema ui_theme'),context).available,true);
  assert.equal(catalog.getAvailability('fem-pa',context).state,'unsupported');
  assert.equal(catalog.getAvailability('theme',context).state,'unsupported');
});

test('setting writes respect known schema options; missing cache needs a confirmed capability',()=>{
  assert.equal(catalog.getAvailability(catalog.compile('set volume 7'),context).available,true);
  assert.equal(catalog.getAvailability(catalog.compile('set volume 7'),{...context,schemas:{}}).available,true);
  assert.equal(catalog.getAvailability(catalog.compile('set volume 7'),{...context,schemas:{},caps:{}}).state,'unknown');
  const stepped={...context,schemas:{volume:schema(1,10,[2,4,8])}};
  assert.equal(catalog.getAvailability(catalog.compile('set volume 7'),stepped).state,'range');
  assert.equal(catalog.getAvailability(catalog.compile('set volume 8'),stepped).available,true);
  assert.equal(catalog.getAvailability(catalog.compile('set melody 31'),context).state,'range');
});

test('inverse sound validates the storage value against the node schema',()=>{
  const onlyOff={...context,schemas:{sound_quiet:schema(0,1,[1])}};
  assert.equal(catalog.getAvailability(catalog.compile('set sound on'),onlyOff).state,'range');
  assert.equal(catalog.getAvailability(catalog.compile('set sound off'),onlyOff).available,true);
});

test('malformed schemas cannot silently authorize writes',()=>{
  const step=catalog.compile('set volume 7');
  for(const broken of [{supported:true},{...schema(1,10),step:0},{...schema(1,10),min:'1'},{...schema(1,10),max:NaN}])
    assert.equal(catalog.getAvailability(step,{...context,schemas:{volume:broken}}).available,false);
});

test('offline, busy, uncertain and read-only states fail closed',()=>{
  const step=catalog.compile('set volume 7');
  assert.equal(catalog.getAvailability(step,{}).state,'offline');
  assert.equal(catalog.getAvailability(step,{...context,busy:true}).state,'busy');
  assert.equal(catalog.getAvailability(step,{...context,uncertain:true}).state,'uncertain');
  assert.equal(catalog.getAvailability(step,{...context,write:false}).state,'readonly');
  assert.equal(catalog.getAvailability(catalog.compile('get volume'),{...context,write:false}).available,true);
});

test('service control is not gated on Companion hello; Companion control is',()=>{
  assert.equal(catalog.getAvailability(catalog.compile('set mute on'),{...context,control:false}).state,'unsupported');
  assert.equal(catalog.getAvailability(catalog.compile('set mute on','service'),{...context,control:false,transport:'service'}).available,true);
});

test('compact syntax requires its marker while legacy diagnostics remain usable',()=>{
  assert.equal(catalog.getAvailability(catalog.compile('get volume'),{...context,compact:false}).available,false);
  assert.equal(catalog.getAvailability(catalog.compile('ver'),{...context,compact:false}).available,true);
  assert.equal(catalog.getAvailability(catalog.compile('get volume','service'),{...context,compact:false,transport:'service'}).available,true);
});

test('sound preview needs both sound and explicit preview support',()=>{
  const step=catalog.compile('sound preview');
  assert.equal(catalog.getAvailability(step,context).available,true);
  assert.equal(catalog.getAvailability(step,{...context,caps:{sound:1}}).state,'unknown');
  assert.equal(catalog.getAvailability(step,{...context,caps:{sound:0,sound_preview:1}}).state,'unsupported');
  assert.equal(catalog.getAvailability(catalog.compile('test'),{...context,caps:{sound:0,unread_led:0,vibration:0}}).available,false);
});

test('TX accepts negative values but requires the live board range',()=>{
  assert.equal(catalog.compile('set tx -9','service').wire,'settings tx set -9');
  assert.equal(catalog.getAvailability(catalog.compile('set tx 22'),context).available,true);
  assert.equal(catalog.getAvailability(catalog.compile('set tx 22'),{...context,ranges:{tx:{min:-9,max:10}}}).state,'range');
  assert.equal(catalog.getAvailability(catalog.compile('set tx 10'),{...context,ranges:{}}).state,'unknown');
  for(const value of [-10,23,1.5])assert.throws(()=>catalog.compile('set tx '+value));
});

test('name translation preserves UTF-8 rather than treating text as commands',()=>{
  const name='Моя нода';
  const step=catalog.compile('set name '+name,'service');
  assert.equal(step.wire,'settings name '+Buffer.from(name).toString('hex'));
  assert.equal(step.expectedValue,name);
  assert.equal(step.readback,'get name');
  assert.throws(()=>catalog.compile('set name '+'Я'.repeat(16)));
});

test('short aliases normalize only known operations',()=>{
  assert.equal(catalog.normalize('  get   volume  '),'get volume');
  assert.equal(catalog.normalize('get caps fem.lna'),'caps fem.lna');
  assert.equal(catalog.normalize('test notification'),'test');
  assert.equal(catalog.normalize('get connection'),'connection status');
  assert.equal(catalog.normalize('get fem_lna'),'get fem.lna');
  assert.equal(catalog.compile('get adc_multiplier','service').wire,'settings get adc_multiplier');
});

test('sensitive and connection-breaking operations never enter executable macros',()=>{
  for(const command of ['get pin','get ble.pin','set pin 123456','set connection ble','set connection usb',
    'mode ble','ui mode usb','ui wifi password 123456','wifi setup','reboot','poweroff','shutdown',
    'adc preview 3320','adc apply 123','adc reset','adc service start','set adc 4.9',
    'set tone_pin 9','set led_pin 1','set vibe_pin -1','set profile 2','set sound.bridge on','set high_drive on',
    'ls /','cat /node_prefs','rm /node_prefs','get wifi.pwd','ui get pin'])
    for(const transport of both)assert.throws(()=>catalog.compile(command,transport),command);
});

test('navigation entries expose dedicated forms without executable commands',()=>{
  for(const id of ['ble-pin','transport','wifi','adc-calibration','pins','profile','radio-setup']){
    assert.deepEqual(catalog.renderAction(id),[]);
    assert.equal(catalog.getAvailability(id,{}).state,'navigation');
  }
});

test('raw control characters, invisible Unicode, invalid surrogates and command injection are rejected',()=>{
  for(const command of ['get volume\nset volume 9','get volume\r','get\tvolume','get volume\0','get volume\x7f',
    'get volume;set volume 9','get volume|set volume 9','set name bad\u202e','set name \ud800','get __proto__'])
    assert.throws(()=>catalog.compile(command),JSON.stringify(command));
  assert.throws(()=>catalog.compile('x'.repeat(157)));
});

test('numeric and boolean grammar cannot smuggle extra command fragments',()=>{
  for(const command of ['set volume 0','set volume 11','set volume NaN','set volume 1e1','set volume 2.5',
    'set mute true','set mute 2','set resonance_hz 1900','set gps_interval -1','set gps_interval 86401',
    'get volume 7','schema volume on','set muted on off'])assert.throws(()=>catalog.compile(command),command);
});

test('parameters are constrained before command interpolation',()=>{
  assert.deepEqual(catalog.renderAction('volume',{value:8}),['set volume 8','get volume']);
  assert.deepEqual(catalog.renderAction('sound-enable',{value:'off'}),['set sound off','get sound']);
  for(const value of ['1\nset mute off','on','',0,11])assert.throws(()=>catalog.renderAction('volume',{value}));
  assert.throws(()=>catalog.renderAction('sound-enable',{value:'off;reboot'}));
});

test('macros are all validated before returning executable steps',()=>{
  const macro=catalog.validateMacro({name:'Тихо',description:'Выключить уведомления',commands:'set mute on\r\nget mute'},'service',
    {...context,transport:'service'});
  assert.equal(macro.mutates,true);
  assert.equal(macro.steps[0].wire,'settings set muted 1');
  assert.equal(macro.steps.length,2);
  assert(Object.isFrozen(macro.steps));
  assert.throws(()=>catalog.validateMacro({name:'Плохой',commands:['set volume 7','get pin']}));
  assert.throws(()=>catalog.validateMacro({name:'Не поддержан',commands:['set volume 7','set fem.pa on']},'companion',context),{code:'UNAVAILABLE'});
});

test('macro limits forbid empty lines, hidden extra steps and oversized metadata',()=>{
  assert.equal(catalog.validateMacro({name:'16 чтений',commands:Array(16).fill('get volume')}).steps.length,16);
  for(const macro of [{name:'x',commands:Array(17).fill('get volume')},{name:'',commands:['get volume']},
    {name:'x'.repeat(49),commands:['get volume']},{name:'x',description:'x'.repeat(241),commands:['get volume']},
    {name:'x',commands:['get volume','']},{name:'x',commands:'get volume\n'},{name:'x',commands:[]},
    {name:'x',commands:['get volume',null]},{name:'x\nget pin',commands:['get volume']}])
    assert.throws(()=>catalog.validateMacro(macro));
});

test('service-only gaps report unsupported transport instead of sending guessed syntax',()=>{
  for(const command of ['get af','get tz.offset','get wifi.status','melodies','caps melody_names'])
    assert.throws(()=>catalog.compile(command,'service'),{code:'TRANSPORT'});
  assert.throws(()=>catalog.compile('get volume','bluetooth'),{code:'TRANSPORT'});
});
