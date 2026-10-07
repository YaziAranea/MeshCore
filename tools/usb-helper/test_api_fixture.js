'use strict';
// Synthetic CLI66 board. No actual serial port or radio is opened.
function installApiMock(options={}) {
  const enc=new TextEncoder(),hex=text=>Array.from(enc.encode(text),b=>b.toString(16).padStart(2,'0')).join('');
  const mock={
    commands:[],packets:[],requests:0,openCount:0,maxOpen:0,closed:true,readerCount:0,readCalls:0,drop:false,wrong:false,errorNext:null,
    caps:{v:1,adc:1,sound:1,board_led:1,unread_led:1,vibration:0,gps:0,battery_protection:1,display:0,melody_max:2,adc_min:options.adcMin??3.675,adc_max:options.adcMax??6.125,agc_reset:1,fem_lna:1,fem_pa:0,bridge:1,melody_names:1,...options.caps},
    settings:{battery_mv:3800,adc_multiplier:4.9,adc_default:4.9,sound_quiet:0,volume:7,melody:0,board_led:1,unread_led:1,vibration:0,gps:0,battery_protection:1,shutdown_mv:3200,muted:0,agc_reset:0,fem_lna:0,fem_pa:0,bridge:0,...options.settings},
    adcReference:options.adcReference??null,adcSourceMissing:false,wifi:'idle',adcService:{supported:1,active:0,remaining_ms:0,external:1},adcServiceDeadline:0,
    radio:{freq_khz:869525,bw_hz:250000,sf:11,cr:5,path_bytes:2,tx_dbm:20,repeat:0,...options.radio},advert:{interval_min:60},
    emit(packet){if(this.closed)return;const bytes=Uint8Array.from([62,packet.length&255,packet.length>>8,...packet]);
      if(options.fragment===false)this.controller.enqueue(bytes);else{this.controller.enqueue(bytes.slice(0,2));this.controller.enqueue(bytes.slice(2,7));this.controller.enqueue(bytes.slice(7));}},
    reply(tag,text){this.emit(Uint8Array.from([29,...enc.encode((this.wrong?'ZZ':tag)+'|'+text)]));},
    handle(request){
      this.packets.push(Array.from(request));
      if(request[0]===22){this.emit(Uint8Array.of(13,13));return;}
      if(request[0]===40){this.emit(Uint8Array.from([21,...enc.encode(options.discovery??(options.oldFirmware?'smartui_api:1':'smartui_cli:1'))]));return;}
      if(request[0]!==66)throw new Error('Unexpected protocol opcode');
      const raw=new TextDecoder().decode(request.slice(1)),tag=raw.slice(0,2),cmd=raw.slice(3);this.commands.push(cmd);
      if(this.drop)return;
      if(this.errorNext){const e=this.errorNext;this.errorNext=null;this.reply(tag,e);return;}
      let text;
      if(cmd==='ui hello')text='OK ui hello version=1 firmware=0.14 max_command=156 max_reply=156 write='+(options.readonly?'0':'1')+' sync=0 events=0';
      else if(/^ui (radio|advert)( |$)/.test(cmd)){
        const [,kind,action,...values]=cmd.split(' ');
        if(options.network===false)text='ERR ui unsupported';
        else if(action==='set'&&(options.readonly||this.networkError))text='ERR ui '+(options.readonly?'readonly':this.networkError);
        else{if(action==='set'){const keys=kind==='radio'?['freq_khz','bw_hz','sf','cr','path_bytes']:['interval_min'];keys.forEach((key,i)=>this[kind][key]=Number(values[i]));}text='OK ui '+kind+' '+Object.entries(this[kind]).map(([k,v])=>k+'='+v).join(' ');}
      }
      else if(cmd.startsWith('ui caps ')){const key=cmd.slice(8);text=Object.hasOwn(this.caps,key)?'OK ui caps key='+key+' value='+this.caps[key]:'ERR ui '+(key==='adc_service'?'invalid':'unsupported');}
      else if(cmd.startsWith('ui get ')){const key=cmd.slice(7);text=Object.hasOwn(this.settings,key)?'OK ui get key='+key+' value='+this.settings[key]:'ERR ui unsupported';}
      else if(cmd.startsWith('ui set ')){const [, ,key,v]=cmd.split(' ');if(options.readonly)text='ERR ui readonly';else{this.settings[key]=Number(v);if(key==='battery_protection')this.settings.shutdown_mv=Number(v)?3200:2700;text='OK ui set key='+key+' value='+v;}}
      else if(cmd.startsWith('ui melody ')){const id=Number(cmd.split(' ').at(-1));text='OK ui melody id='+id+' name_hex='+hex(['Пульс','Трель','Колокол'][id]||'Мелодия '+id);}
      else if(cmd==='ui connection')text='OK ui connection mode=usb client=usb caps=7 write='+(options.readonly?'0':'1');
      else if(cmd==='ui mode status')text='OK ui mode pending=none error=none';
      else if(cmd==='ui test')text=options.readonly?'ERR ui readonly':'OK ui test';
      else if(cmd==='ui adc manual')text=options.manualAdc===undefined?'ERR ui invalid':'OK ui adc_manual supported='+Number(options.manualAdc);
      else if(cmd.startsWith('ui adc set ')){
        if(options.readonly||!options.manualAdc)text='ERR ui '+(options.readonly?'readonly':'unsupported');
        else{this.settings.adc_multiplier=Number(cmd.split(' ').at(-1));this.adcServiceDeadline=0;text='OK ui adc_set';if(this.dropAdcAck)return;}
      }
      else if(cmd.startsWith('ui adc service')){
        if(!this.caps.adc_service)text='ERR ui unsupported';
        else if(cmd.endsWith(' start')&&(options.readonly||!this.adcService.external))text='ERR ui '+(options.readonly?'readonly':'usb_required');
        else{
          if(cmd.endsWith(' start')&&!this.adcService.active)this.adcServiceDeadline=Date.now()+120000;
          if(cmd.endsWith(' stop'))this.adcServiceDeadline=0;
          this.adcService.remaining_ms=Math.max(0,this.adcServiceDeadline-Date.now());this.adcService.active=Number(this.adcService.remaining_ms>0);
          text='OK ui adc_service '+Object.entries(this.adcService).map(([k,v])=>k+'='+v).join(' ');
        }
      }
      else if(cmd.startsWith('ui adc preview ')){
        if(this.adcSourceMissing){this.reply(tag,'ERR ui source');return;}
        const measured=Number(cmd.split(' ').at(-1)),sampled=this.adcReference??this.settings.battery_mv;
        this.preview=Number((this.settings.adc_multiplier*measured/sampled).toFixed(6));
        if(this.preview<this.caps.adc_min||this.preview>this.caps.adc_max)text='ERR ui range';
        else text='OK ui adc_preview token=7 sampled_mv='+sampled+' measured_mv='+measured+' multiplier='+this.preview;
      }else if(cmd==='ui adc apply 7'){this.adcServiceDeadline=0;this.settings.adc_multiplier=this.preview;text='OK ui adc_apply';}
      else if(cmd==='ui adc reset'){this.adcServiceDeadline=0;this.settings.adc_multiplier=this.settings.adc_default;text='OK ui adc_reset';}
      else if(cmd==='ui wifi status')text='OK ui wifi state='+this.wifi+' supported='+(options.wifi===false?'0':'1')+' configured=1 associated=0 ip=none';
      else if(cmd.startsWith('ui wifi ')){
        const action=cmd.split(' ')[2];const states={begin:'ssid',ssid:'password',password:'ready',test:'test_ok',save:'saved',cancel:'cancelled'};
        this.wifi=states[action]||this.wifi;text='OK ui wifi '+action+(['save','cancel'].includes(action)?'':' state='+(action==='test'?'testing':this.wifi));
      }else if(['board','ver','get name','get radio'].includes(cmd))text=cmd==='get name'?'Тестовая нода':'test';
      else text='Unknown command';
      this.reply(tag,text);
    },
    async open(){if(!this.closed)throw new Error('already open');this.closed=false;this.openCount++;this.maxOpen=Math.max(this.maxOpen,this.openCount);
      this.readable=new ReadableStream({start:c=>{this.controller=c;},cancel:()=>{}});
      const getReader=this.readable.getReader.bind(this.readable);this.readable.getReader=()=>{this.readerCount++;const r=getReader(),read=r.read.bind(r);r.read=()=>{this.readCalls++;return read();};return r;};
      this.writable=new WritableStream({write:bytes=>{if(this.closed)throw new Error('write after close');const length=bytes[1]|bytes[2]<<8;if(bytes[0]!==60||length!==bytes.length-3)throw new Error('bad frame');this.handle(bytes.slice(3));if(options.delayWriteCommand&&options.delayWriteCommand===this.commands.at(-1))return new Promise(resolve=>{this.releaseWrite=resolve;});}});
    },
    async close(){if(!this.closed){this.closed=true;this.openCount--;}},
  };
  if(typeof window!=='undefined'){window.__apiMock=mock;Object.defineProperty(navigator,'serial',{configurable:true,value:{requestPort:async()=>{mock.requests++;return mock;}}});}
  return mock;
}
if(typeof module==='object'&&module.exports)module.exports={installApiMock};
