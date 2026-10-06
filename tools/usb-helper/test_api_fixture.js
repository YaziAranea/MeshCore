'use strict';
// Shared synthetic wire fixture. No port, network, credentials or physical board.
function installApiMock(options={}) {
  const enc=new TextEncoder(),boot='0123456789abcdef';
  const hex=bytes=>Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
  const message=Uint8Array.from([16,12,0,0,1,2,3,4,5,6,255,0,0,0,0,0,...enc.encode(options.markup?'Тест: <script>не HTML</script>':'Тест: встречаемся у реки. Канал связи работает.')]);
  const caps=`v=1 adc=1 sound=1 board_led=1 unread_led=1 vibration=0 gps=0 battery_protection=1 display=0 melody_max=30 adc_min=${options.adcMin??'3.675000'} adc_max=${options.adcMax??'6.125000'} agc_reset=1 fem_lna=1 fem_pa=0 bridge=1 melody_names=1`;
  const mock={commands:[],packets:[],requests:0,openCount:0,maxOpen:0,closed:true,readerCount:0,readCalls:0,boot,seq:1,explicit:false,subscribed:0,received:false,recordState:0,drop:false,wrong:false,fragment:options.fragment!==false,
    settings:{battery_mv:3800,adc_multiplier:4.9,adc_default:4.9,sound_quiet:0,volume:7,melody:0,board_led:1,unread_led:1,vibration:0,gps:0,battery_protection:1,shutdown_mv:3200,muted:0,agc_reset:0,fem_lna:0,fem_pa:0,bridge:0,...options.settings},adcReference:options.adcReference??null,adcSourceMissing:false,wifi:'idle',events:[],replyCache:new Map(),
    emit(packet){const data=Uint8Array.from([62,packet.length&255,packet.length>>8,...packet]);if(this.fragment){this.controller.enqueue(data.slice(0,2));this.controller.enqueue(data.slice(2,9));this.controller.enqueue(data.slice(9));}else this.controller.enqueue(data);},
    respond(request,text,status=0){const bytes=enc.encode(text),id=request[5]|request[6]<<8,op=request[7];if(op!==2)this.replyCache.set(id,{bytes,status});const cached=this.replyCache.get(id),offset=op===2?request[8]|request[9]<<8:0;this.emit(Uint8Array.from([201,83,85,73,1,id&255,id>>8,op,cached.status,offset&255,offset>>8,cached.bytes.length&255,cached.bytes.length>>8,...cached.bytes.slice(offset,offset+147)]));},
    event(kind,id='00000001',value=0,{hint=true}={}){this.seq++;this.events.push({seq:this.seq,kind,id,state:this.recordState,flags:1,value,key:0});if(!hint)return;const text=enc.encode(`EV api events boot=${this.boot} cursor=${this.seq} mask=15`);this.emit(Uint8Array.from([201,83,85,73,1,0,0,3,0,0,0,text.length,0,...text]));},
    command(request){
      this.packets.push(Array.from(request));if(this.drop)return;
      if(request[0]===22){this.emit(Uint8Array.of(13,3,1,2,3,4));return;}
      if(request[0]===40){this.emit(Uint8Array.from([21,...enc.encode(options.unsupported?'other:1':'smartui_api:1,other:2')]));return;}
      if(request[7]===2){this.respond(request,'');return;}
      if(this.wrong){this.emit(Uint8Array.of(62));return;}
      const cmd=request[7]===0?'api hello':new TextDecoder().decode(request.slice(8));this.commands.push(cmd);
      if(/^api (events next|inbox (item|received|read|dismiss|snooze)) /.test(cmd)&&cmd.split(' ')[3]!==this.boot)return this.respond(request,`ERR api boot boot=${this.boot}`,7);
      let text;
      if(cmd==='api hello')text=`OK api hello v=1 firmware=${options.legacy?'0.10':'0.11'} stage=release max_command=152 max_reply=479 max_frame=160 transport=usb write=${options.readonly?0:1} events=${options.legacy?0:1} sync=${options.legacy?0:1} wifi_setup=1`;
      else if(cmd==='api caps')text='OK api caps '+caps;
      else if(cmd==='api get')text='OK api get '+Object.entries(this.settings).map(([k,v])=>`${k}=${v}`).join(' ');
      else if(cmd.startsWith('api melody ')){const id=Number(cmd.split(' ').at(-1));text=`OK api melody id=${id} name_hex=${hex(enc.encode(id===0?'Пульс':'Тестовая мелодия '+id))}`;}
      else if(cmd==='api connection')text='OK api connection selected=usb via=usb caps=7 wifi_configured=0 wifi_associated=0 ip=none readonly=0';
      else if(cmd==='api notify status')text=`OK api notify active=${this.recordState&6?0:1} id=00000001 muted=${this.settings.muted}`;
      else if(cmd==='api sync enable'){this.explicit=true;text=`OK api sync boot=${this.boot} explicit=1 subscribed=${this.subscribed} cursor=${this.seq} oldest=1 revision=${this.seq} count=1 capacity=32`;}
      else if(cmd==='api events subscribe 15'){this.subscribed=15;text=`OK api events subscribed=15 boot=${this.boot} cursor=${this.seq}`;}
      else if(cmd==='api inbox snapshot')text=`OK api inbox snapshot boot=${this.boot} revision=${this.seq} count=1 cursor=${this.seq} capacity=32`;
      else if(cmd.startsWith('api inbox item ')){const [, , ,b,revision,index]=cmd.split(' ');if(revision!==String(this.seq))return this.respond(request,'ERR api changed',7);text=`OK api inbox item boot=${this.boot} revision=${this.seq} index=${index} id=00000001 flags=1 state=${this.recordState} snooze=${this.recordState&8?600:0} snoozable=1`;}
      else if(cmd==='api inbox next')text=this.received?`OK api inbox empty=1 boot=${this.boot}`:`OK api inbox next boot=${this.boot} id=00000001 flags=1 frame_hex=${hex(message)}`;
      else if(/^api inbox (received|read|dismiss|snooze) /.test(cmd)){
        const action=cmd.split(' ')[2],value={received:1,read:2,dismiss:4,snooze:8}[action];if(action==='received')this.received=true;const changed=!(this.recordState&value);this.recordState|=value;
        if(changed)this.event({received:2,read:3,dismiss:4,snooze:5}[action],'00000001',0,{hint:false});
        text=`OK api inbox ${action} id=00000001 state=${this.recordState} changed=${changed?1:0}`;
      }
      else if(cmd.startsWith('api events next ')){
        if(this.gap){this.gap=false;return this.respond(request,`ERR api gap boot=${this.boot} oldest=${this.seq} cursor=${this.seq}`,7);}
        const cursor=Number(cmd.split(' ').at(-1)),e=this.events.find(e=>e.seq>cursor);text=e?`OK api event boot=${this.boot} `+Object.entries(e).map(([k,v])=>`${k}=${v}`).join(' '):`OK api events end=1 boot=${this.boot} cursor=${this.seq}`;
      }
      else if(cmd.startsWith('api set ')){const [, ,key,value]=cmd.split(' ');this.settings[key]=Number(value);if(key==='battery_protection')this.settings.shutdown_mv=Number(value)?3200:2700;text=`OK api set key=${key} value=${value}`;}
      else if(cmd==='api test')text='OK api test';
      else if(cmd.startsWith('api adc preview ')){if(this.adcSourceMissing)return this.respond(request,'ERR api source',7);const mv=Number(cmd.split(' ').at(-1)),sampled=this.adcReference??this.settings.battery_mv;this.adcPreview=Number((this.settings.adc_multiplier*mv/sampled).toFixed(6));text=`OK api adc_preview token=7 sampled_mv=${sampled} measured_mv=${mv} multiplier=${this.adcPreview}`;}
      else if(cmd==='api adc apply 7'){this.settings.adc_multiplier=this.adcPreview;text='OK api adc_apply';}
      else if(cmd==='api adc reset'){this.settings.adc_multiplier=this.settings.adc_default;text='OK api adc_reset';}
      else if(cmd==='api wifi begin'){this.wifi='ssid';text='OK api wifi begin state=ssid';}
      else if(cmd.startsWith('api wifi ssid ')){this.wifi='password';text='OK api wifi ssid state=password';}
      else if(cmd.startsWith('api wifi password ')){this.wifi='ready';text='OK api wifi password state=ready';}
      else if(cmd==='api wifi test'){this.wifi='test_ok';text='OK api wifi test state=testing';}
      else if(cmd==='api wifi save'){this.wifi='saved';text='OK api wifi save';}
      else if(cmd==='api wifi cancel'){this.wifi='cancelled';text='OK api wifi cancel';}
      else if(cmd==='api wifi status')text=`OK api wifi state=${this.wifi} owner=api supported=1 configured=${this.wifi==='saved'?1:0} associated=1 ip=192.168.1.2 ssid_set=1 password_set=1 mode_pending=none last_mode_error=none`;
      else return this.respond(request,'ERR api unsupported',7);
      this.respond(request,text);
    },
    async open(){if(!this.closed)throw new Error('already open');this.closed=false;this.openCount++;this.maxOpen=Math.max(this.maxOpen,this.openCount);this.buffer=new Uint8Array();
      this.readable=new ReadableStream({start:controller=>{this.controller=controller;}});
      const reader=this.readable.getReader.bind(this.readable);this.readable.getReader=(...args)=>{this.readerCount++;const result=reader(...args),read=result.read.bind(result);result.read=()=>{this.readCalls++;return read();};return result;};
      this.writable=new WritableStream({write:bytes=>{this.buffer=Uint8Array.from([...this.buffer,...bytes]);while(this.buffer.length>=3){if(this.buffer[0]!==60)throw new Error('not binary');const n=this.buffer[1]|this.buffer[2]<<8;if(this.buffer.length<n+3)break;const p=this.buffer.slice(3,n+3);this.buffer=this.buffer.slice(n+3);this.command(p);}}});
    },
    async close(){this.closed=true;this.openCount--;},
    unplug(){this.controller.error(new Error('private device bytes must never be shown'));}
  };
  globalThis.__apiMock=mock;
  if(typeof navigator!=='undefined')Object.defineProperty(Navigator.prototype,'serial',{configurable:true,get:()=>({requestPort:async()=>{mock.requests++;return mock;}})});
  return mock;
}
if(typeof module==='object'&&module.exports)module.exports={installApiMock};
