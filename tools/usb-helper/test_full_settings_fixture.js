'use strict';
// T096-shaped simulated 0.16 board, not a claim of physical hardware testing.
// Values and pin choices mirror the public build, with a disconnected vibration output.
function fullSettingsFixture() {
  const {SETTING_KEYS}=require('./core');
  const schemas=Object.fromEntries(SETTING_KEYS.map(key=>[key,{supported:1,min:0,max:1,step:1,options:'-'}]));
  const range=(key,min,max,options='-',step=1)=>{schemas[key]={supported:1,min,max,step,options};};
  range('volume',1,10);
  for(const key of ['melody','melody_dm','melody_mention','melody_system'])range(key,0,30);
  for(const key of ['notify_mode','important_notify_mode'])range(key,0,7,'0,1,2,3');
  range('tone_pin',0,127,'29,31,33,34,35,36,37,39,43');
  range('led_pin',0,127,'29,33,34,35,36,37,39,43,45');
  range('vibe_pin',-1,127,'-1,29,33,34,35,36,37,39,43');
  schemas.vibration.supported=0;
  range('resonance_hz',1800,4200,'-',400);
  range('ui_font',0,14);range('ui_theme',0,6);
  range('ui_top_color',0,5);range('ui_bottom_color',0,5);
  range('backlight_timeout',0,2);range('gps_interval',0,86400);
  range('profile',0,3);range('gps_source',0,1,'0');
  // Current public profile deliberately omits these optional UI features.
  for(const key of ['profile','melody_dm','melody_mention'])schemas[key].supported=0;
  const settings={sound_quiet:0,volume:7,melody:0,board_led:1,unread_led:1,vibration:0,gps:0,battery_protection:1,muted:0,
    notify_mode:3,important_notify_mode:3,tone_pin:31,led_pin:45,vibe_pin:-1,melody_dm:0,melody_mention:1,melody_system:0,
    tone_8bit:0,high_drive:1,resonance_hz:2600,bridge:0,offline_dm_led:1,ble_dm_led:0,msg_popup:1,
    ui_font:5,ui_theme:0,ui_top_color:1,ui_bottom_color:0,backlight_timeout:1,gps_source:0,gps_interval:60,
    advert_location:1,profile:0,agc_reset:0,fem_lna:1,fem_pa:1};
  return {schemas,settings,caps:{schema:1,display:1,gps:1,vibration:0,melody_max:30,adc_service:1,fem_lna:1,fem_pa:1,bridge:1}};
}
module.exports={fullSettingsFixture};
