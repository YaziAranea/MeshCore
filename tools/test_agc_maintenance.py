#!/usr/bin/env python3
"""Execute production cooperative AGC controller bodies against fault-injected hardware.

No MCU, serial port, or radio required. Uses native g++ (WSL on Windows).
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def body(source, signature):
    opening = source.index('{', source.index(signature))
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[opening + 1:end - 1]


def linux(path):
    return subprocess.check_output(['wsl', '--exec', 'wslpath', '-a', str(path)], text=True).strip()


def compile_run(code):
    with tempfile.TemporaryDirectory(prefix='smartui-agc-') as directory:
        path = Path(directory)
        source, executable = path / 'test.cpp', path / 'test'
        source.write_text(code, encoding='utf-8')
        include = ROOT / 'src/helpers/radiolib'
        compiler = shutil.which('g++')
        if compiler:
            command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', str(include), str(source), '-o', str(executable)]
            run = [str(executable)]
        else:
            command = ['wsl', '--exec', 'g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-I', linux(include), linux(source), '-o', linux(executable)]
            run = ['wsl', '--exec', linux(executable)]
        subprocess.run(command, check=True)
        subprocess.run(run, check=True)


def transport_test(sx):
    code = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <vector>
#include <string>
#include "AgcMaintenance.h"
// Pinned SX126x opcodes/registers: framing is asserted below independently
// of the names referenced by the extracted production methods.
#define RADIOLIB_ERR_NONE 0
#define RADIOLIB_ERR_UNSUPPORTED -99
#define RADIOLIB_SX126X_CMD_READ_REGISTER 0x1D
#define RADIOLIB_SX126X_CMD_WRITE_REGISTER 0x0D
#define RADIOLIB_SX126X_CMD_GET_IRQ_STATUS 0x12
#define RADIOLIB_SX126X_CMD_GET_RSSI_INST 0x15
#define RADIOLIB_SX126X_CMD_NOP 0x00
#define RADIOLIB_SX126X_CMD_CALIBRATE 0x89
#define RADIOLIB_SX126X_REG_RX_GAIN 0x08AC
#define RADIOLIB_SX126X_REG_RTC_CTRL 0x0902
#define RADIOLIB_SX126X_REG_EVENT_MASK 0x0944
#define RADIOLIB_SX126X_IRQ_RX_DONE 0x02
#define RADIOLIB_SX126X_IRQ_CRC_ERR 0x40
#define RADIOLIB_SX126X_IRQ_PREAMBLE_DETECTED 0x04
#define RADIOLIB_SX126X_IRQ_HEADER_VALID 0x10
#define RADIOLIB_SX126X_STANDBY_RC 0
#define RADIOLIB_SX126X_CALIBRATE_ALL 0x7F
#define SX126X_DIO2_AS_RF_SWITCH true
#define SX126X_REGISTER_PATCH 1
using S=AgcMaintenanceStep;
struct Transfer { std::string name;std::vector<uint8_t> command,data;bool wait,verify;uint32_t timeout; };
struct Module {
  struct { uint32_t timeout=777; } spiConfig;
  std::vector<Transfer> calls;
  unsigned fail_at=0;
  uint8_t read_value=0x94,raw_rssi=223;uint16_t irq=0;
  int16_t record(const char*name,std::vector<uint8_t> command={},std::vector<uint8_t> data={},bool wait=true,bool verify=true){
    calls.push_back({name,command,data,wait,verify,spiConfig.timeout});
    assert(spiConfig.timeout==50);
    return calls.size()==fail_at?-707:0;
  }
  int16_t SPIreadStream(const uint8_t*cmd,uint8_t len,uint8_t*data,size_t count,bool wait=true,bool verify=true){
    int16_t error=record("read",{cmd,cmd+len},{},wait,verify);
    for(size_t i=0;i<count;++i)data[i]=read_value;
    if(len==1&&cmd[0]==0x12){assert(count==2);data[0]=irq>>8;data[1]=irq&255;}
    if(len==1&&cmd[0]==0x15){assert(count==1);data[0]=raw_rssi;}
    return error;
  }
  int16_t SPIreadStream(uint16_t cmd,uint8_t*data,size_t count,bool wait=true,bool verify=true){
    uint8_t command=cmd;return SPIreadStream(&command,1,data,count,wait,verify);
  }
  int16_t SPIwriteStream(const uint8_t*cmd,uint8_t len,const uint8_t*data,size_t count,bool wait=true,bool verify=true){
    std::vector<uint8_t> bytes;if(count)bytes.assign(data,data+count);
    return record("write",{cmd,cmd+len},bytes,wait,verify);
  }
  int16_t SPIwriteStream(uint16_t cmd,const uint8_t*data,size_t count,bool wait=true,bool verify=true){
    uint8_t command=cmd;return SPIwriteStream(&command,1,data,count,wait,verify);
  }
};
struct CustomSX1262 {
  Module module;Module*mod=&module;bool busy=false,warm=false,dio2=false;float freqMHz=868.25f,image_freq=0;
  bool isChipBusy(){return busy;}
  int16_t standby(uint8_t mode=0){assert(mode==0);return mod->record("standby");}
  int16_t sleep(bool retain){warm=retain;return mod->record("sleep");}
  int16_t calibrateImage(float frequency){image_freq=frequency;return mod->record("image");}
  int16_t setDio2AsRfSwitch(bool value){dio2=value;return mod->record("dio2");}
  int16_t startReceive(){return mod->record("startRx");}
};
struct Wrapper {
  CustomSX1262 chip;CustomSX1262* _radio=&chip;
  bool _rx_ps_armed=false,_agc_gain_valid=false;uint8_t _agc_gain=0,_agc_patch=0;
  int16_t startReceiveMode(){return chip.mod->record("restoreRx");}
'''
    for signature in ('int16_t agcReadRegister(uint16_t address, uint8_t& value)',
                      'int16_t agcWriteRegister(uint16_t address, uint8_t value)',
                      'int16_t agcHardwareStep(AgcMaintenanceStep step, int16_t& value)'):
        code += signature + ' {\n' + body(sx, signature) + '\n}\n'
    code += r'''
};
unsigned checks=0;
#define CHECK(x) do{++checks;if(!(x)){std::fprintf(stderr,"line %d: %s\n",__LINE__,#x);return 1;}}while(0)
bool frame(const Transfer&t,const char*name,std::vector<uint8_t> command,std::vector<uint8_t> data={}){
  return t.name==name&&t.command==command&&t.data==data;
}
int main(){
  for(uint8_t gain:{0x94,0x96}){
    Wrapper r;int16_t value=0;r.chip.module.read_value=gain;
    CHECK(r.agcHardwareStep(S::ReadGain,value)==0);CHECK(r._agc_gain==gain);CHECK(r.chip.module.spiConfig.timeout==777);
    CHECK(frame(r.chip.module.calls[0],"read",{0x1D,0x08,0xAC}));r._agc_gain_valid=true;
    CHECK(r.agcHardwareStep(S::WriteGain,value)==0);CHECK(frame(r.chip.module.calls[1],"write",{0x0D,0x08,0xAC},{gain}));
    CHECK(r.chip.module.spiConfig.timeout==777);
  }
  {
    Wrapper r;int16_t value=0;CHECK(r.agcHardwareStep(S::WriteGain,value)==0);CHECK(r.chip.module.calls.empty());
    CHECK(r.chip.module.spiConfig.timeout==777);
    r._rx_ps_armed=true;r.chip.busy=true;CHECK(r.agcHardwareStep(S::Probe,value)==AGC_MAINTENANCE_DEFER);
    CHECK(r.chip.module.calls.empty());CHECK(r.chip.module.spiConfig.timeout==777);
  }
  for(uint16_t irq:{0x0000,0x0004,0x0010,0x0002,0x0040,0x0016}){
    Wrapper r;int16_t value=-1;r.chip.module.irq=irq;
    CHECK(r.agcHardwareStep(S::Probe,value)==0);
    CHECK(value==((irq&0x42)?AGC_MAINTENANCE_RX_READY:((irq&0x14)?AGC_MAINTENANCE_RX_ACTIVITY:0)));
    CHECK(frame(r.chip.module.calls[0],"read",{0x12}));CHECK(r.chip.module.spiConfig.timeout==777);
  }
  {
    Wrapper r;int16_t value=0;r._rx_ps_armed=true;r.chip.module.read_value=0xA4;
    CHECK(r.agcHardwareStep(S::Suspend,value)==0);CHECK(r.chip.module.calls.size()==4);
    CHECK(frame(r.chip.module.calls[0],"standby",{}));
    CHECK(frame(r.chip.module.calls[1],"write",{0x0D,0x09,0x02},{0}));
    CHECK(frame(r.chip.module.calls[2],"read",{0x1D,0x09,0x44}));
    CHECK(frame(r.chip.module.calls[3],"write",{0x0D,0x09,0x44},{0xA6}));
    CHECK(r.chip.module.spiConfig.timeout==777);
  }
  {
    Wrapper r;int16_t value=0;r.chip.module.read_value=0x42;
    CHECK(r.agcHardwareStep(S::ReadPatch,value)==0);CHECK(r.agcHardwareStep(S::WritePatch,value)==0);
    CHECK(frame(r.chip.module.calls[0],"read",{0x1D,0x08,0xB5}));
    CHECK(frame(r.chip.module.calls[1],"write",{0x0D,0x08,0xB5},{0x43}));
    CHECK(r.chip.module.spiConfig.timeout==777);
  }
  {
    Wrapper r;int16_t value=0;CHECK(r.agcHardwareStep(S::Calibrate,value)==0);
    CHECK(frame(r.chip.module.calls[0],"write",{0x89},{0x7F}));
    CHECK(!r.chip.module.calls[0].wait&&!r.chip.module.calls[0].verify);
    CHECK(r.chip.module.spiConfig.timeout==777);
    CHECK(r.agcHardwareStep(S::WaitCalibration,value)==0);CHECK(r.chip.module.calls[1].wait&&r.chip.module.calls[1].verify);
    CHECK(r.agcHardwareStep(S::Sample,value)==0);CHECK(value==-111);CHECK(frame(r.chip.module.calls[2],"read",{0x15}));
  }
  for(float frequency:{433.775f,868.25f,915.0f}){
    Wrapper r;int16_t value=0;r.chip.freqMHz=frequency;
    CHECK(r.agcHardwareStep(S::Image,value)==0);CHECK(r.chip.image_freq==frequency);CHECK(r.chip.module.spiConfig.timeout==777);
  }
  for(S step:{S::ReadGain,S::Suspend,S::Sleep,S::Wake,S::RecoveryWake,S::Calibrate,S::WaitCalibration,S::Image,
              S::Dio2,S::WriteGain,S::ReadPatch,S::WritePatch,S::StartRx,S::Sample,S::RestoreRx,S::Probe}){
    Wrapper success;int16_t value=0;success._rx_ps_armed=true;success._agc_gain_valid=true;
    CHECK(success.agcHardwareStep(step,value)==0);CHECK(success.chip.module.spiConfig.timeout==777);
    if(step==S::Sleep)CHECK(success.chip.warm);
    if(step==S::Dio2)CHECK(success.chip.dio2);
    if(step==S::Wake||step==S::RecoveryWake){
      CHECK(frame(success.chip.module.calls[0],"write",{0}));
      CHECK(!success.chip.module.calls[0].wait&&!success.chip.module.calls[0].verify);
    }
    for(unsigned failure=1;failure<=success.chip.module.calls.size();++failure){
      Wrapper fault;fault._rx_ps_armed=true;fault._agc_gain_valid=true;fault.chip.module.fail_at=failure;
      CHECK(fault.agcHardwareStep(step,value)==-707);CHECK(fault.chip.module.spiConfig.timeout==777);
      CHECK(fault.chip.module.calls.size()==failure);
    }
  }
  {
    Wrapper r;int16_t value=0;CHECK(r.agcHardwareStep(S::Idle,value)==RADIOLIB_ERR_UNSUPPORTED);
    CHECK(r.chip.module.spiConfig.timeout==777);CHECK(r.chip.module.calls.empty());
  }
  std::printf("AGC production SX1262 transport: %u checks PASS\n",checks);
}
'''
    compile_run(code)


def main():
    common = (ROOT / 'src/helpers/radiolib/RadioLibWrappers.cpp').read_text(encoding='utf-8')
    header = (ROOT / 'src/helpers/radiolib/RadioLibWrappers.h').read_text(encoding='utf-8')
    sx = (ROOT / 'src/helpers/radiolib/CustomSX1262Wrapper.h').read_text(encoding='utf-8')
    assert '_nf_calib_active || _agc_status.active' in body(header, 'bool isRxPowerSavingCalibrationActive()')
    assert 'if (_agc_status.active) return true;' in body(header, 'bool isReceiving()')
    assert 'abortAgcMaintenanceForRadioChange();' in body(sx, 'virtual void powerOff()')
    for signature in ('void RadioLibWrapper::idle()', 'void RadioLibWrapper::powerOff()',
                      'void RadioLibWrapper::prepareForRadioConfig()', 'bool RadioLibWrapper::setRxPowerSaving('):
        assert 'abortAgcMaintenanceForRadioChange();' in body(common, signature)
    assert 'if (agcOwnsHardware())' in body(sx, 'float getCurrentRSSI()')
    assert 'if (agcOwnsHardware())' in body(sx, 'bool isReceivingPacket()')
    assert 'agcOwnsHardware()' in body(common, 'float RadioLibWrapper::getLastRSSI()')
    assert 'agcOwnsHardware()' in body(common, 'float RadioLibWrapper::getLastSNR()')
    code = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <vector>
#include <algorithm>
#include "AgcMaintenance.h"
#define NRF52_PLATFORM 1
#define STATE_IDLE 0
#define STATE_RX 1
#define STATE_TX_WAIT 3
#define STATE_INT_READY 16
#define RADIOLIB_ERR_NONE 0
#define RADIOLIB_ERR_UNSUPPORTED -1
#define NUM_NOISE_FLOOR_SAMPLES 64
#define NF_CALIB_SETTLE_MS 20
#define NF_CALIB_MAX_SAMPLE_ATTEMPTS 256
#define MESH_DEBUG_PRINTLN(...) do {} while(0)
// Inject an ISR at an exact production read of the volatile state byte.
struct IRQState {
  uint8_t value=STATE_RX; unsigned reads=0, inject_read=0;
  operator uint8_t(){if(++reads==inject_read){value|=STATE_INT_READY;inject_read=0;}return value;}
  IRQState& operator=(uint8_t next){value=next;reads=0;return *this;}
  IRQState& operator|=(uint8_t bits){value|=bits;return *this;}
} state;
uint32_t tick=1000, primask=0;
bool inject_irq_on_lock=false;
uint32_t millis() { return tick; }
uint32_t __get_PRIMASK() { return primask; }
void __disable_irq() { primask=1; if(inject_irq_on_lock){state|=STATE_INT_READY;inject_irq_on_lock=false;} }
void __set_PRIMASK(uint32_t saved) { primask=saved; }
void setFlag() { state |= STATE_INT_READY; }
static void setStatePreservingIRQ(uint8_t next) {
''' + body(common, 'static void setStatePreservingIRQ(') + r'''
}
struct Board { int tx=0; void onBeforeTransmit(){++tx;} void onAfterTransmit(){} };
struct Chip {
  int sent=0, read=0; bool fail_tx=false;
  int startTransmit(uint8_t*,int){++sent;return fail_tx?-8:0;}
  int getPacketLength(){return 3;}
  float getSNR(){return 9;}
  float getRSSI(){return -90;}
  int readData(uint8_t*,int){++read;return 0;}
};
using S=AgcMaintenanceStep;
struct Radio {
  AgcMaintenanceStep _agc_step=S::Idle;
  AgcMaintenanceStatus _agc_status={false,0,0,0,0,0};
  uint32_t _agc_started=0,_agc_step_at=0,_agc_sample_at=0;
  uint16_t _agc_samples=0,_agc_sample_attempts=0;
  int32_t _agc_sum=0;
  bool _agc_gain_valid=false,_agc_touched=false,_agc_cancelled=false,_agc_restoring=false,_agc_restore_pending=false;
  bool supported=true,_config_valid=true,_nf_calib_active=false,_rx_ps_armed=false,_rx_ps_enabled=false;
  uint32_t _rx_ps_eff_rx_us=0,_rx_ps_eff_sleep_us=0,_nf_last_calib=0;
  int16_t _noise_floor=-105; unsigned _num_floor_samples=64; int32_t _floor_sample_sum=0;
  bool busy=false,defer=false,packet=false,inject_after_suspend=false,inject_after_sample=false;
  int probe_value=0,post_suspend_value=0,sample=-112,fail_count=0,probes=0,rxstarts=0;
  S fail_step=S::Idle;
  std::vector<S> calls;
  Board board; Board* _board=&board; Chip chip; Chip* _radio=&chip;
  bool _last_metrics_valid=false; float _last_snr=0,_last_rssi=0;
  unsigned n_recv=0,n_recv_errors=0;
  bool supportsAgcMaintenance()const{return supported;}
  bool isChipBusy(){return busy;}
  bool isPacketReady(){return true;}
  bool isReceivingPacket(){return packet;}
  void stopReceiveDutyCycle(){_rx_ps_armed=false;}
  void idle(){state=STATE_IDLE;}
  int startReceiveMode(){++rxstarts;_rx_ps_armed=_rx_ps_enabled;return 0;}
  void requestRestartRecv(){setStatePreservingIRQ(STATE_IDLE);}
  bool agcOwnsHardware()const {
''' + body(header, 'bool agcOwnsHardware() const') + r'''
  }
  bool isReceiving() {
''' + body(header, 'bool isReceiving() override') + r'''
  }
  bool isChannelActive(){return false;}
  int16_t agcHardwareStep(S step,int16_t& value) {
    calls.push_back(step);
    if(step==S::Suspend && inject_after_suspend) state|=STATE_INT_READY;
    if(step==S::Sample && inject_after_sample) state|=STATE_INT_READY;
    if(step==fail_step && fail_count){--fail_count;return -707;}
    if(step==S::Probe) {
      ++probes;
      if(defer)return AGC_MAINTENANCE_DEFER;
      value=probe_value;
      if(!calls.empty() && calls.size()>1 && calls[calls.size()-2]==S::Suspend) value=post_suspend_value;
    }
    if(step==S::Sample)value=sample;
    if(step==S::RestoreRx){++rxstarts;_rx_ps_armed=_rx_ps_enabled;}
    return 0;
  }
'''
    signatures = (
        ('bool', 'requestAgcMaintenance', ''), ('void', 'finishAgcMaintenance', 'bool preserve_rx'),
        ('void', 'cancelAgcMaintenance', ''), ('void', 'abortAgcMaintenanceForRadioChange', ''),
        ('void', 'serviceAgcMaintenance', ''), ('void', 'startRecv', ''),
        ('int', 'recvRaw', 'uint8_t* bytes, int sz'),
        ('bool', 'startSendRaw', 'const uint8_t* bytes, int len'),
    )
    for result, name, args in signatures:
        declaration = args.replace('bool preserve_rx', 'bool preserve_rx = false')
        code += f'  {result} {name}({declaration}) {{\n' + body(common, f'{result} RadioLibWrapper::{name}(') + '\n  }\n'
    code += r'''
};
unsigned checks=0;
#define CHECK(x) do{++checks;if(!(x)){std::fprintf(stderr,"line %d: %s\n",__LINE__,#x);return 1;}}while(0)
void advance(Radio& r,unsigned ms=1){tick+=ms;r.serviceAgcMaintenance();}
void run(Radio& r,unsigned limit=600){for(unsigned i=0;r._agc_status.active && i<limit;++i)advance(r);}
void until(Radio& r,S target){for(unsigned i=0;r._agc_status.active && r._agc_step!=target && i<500;++i)advance(r);assert(r._agc_step==target);}
unsigned count(Radio& r,S step){return std::count(r.calls.begin(),r.calls.end(),step);}
int main(){
  {
    Radio r;CHECK(!r._agc_status.active);r.supported=false;CHECK(!r.requestAgcMaintenance());
    r.supported=true;r._config_valid=false;CHECK(!r.requestAgcMaintenance());r._config_valid=true;
    state=STATE_TX_WAIT;CHECK(!r.requestAgcMaintenance());state=STATE_RX|STATE_INT_READY;CHECK(!r.requestAgcMaintenance());
    state=STATE_RX;r._nf_calib_active=true;CHECK(!r.requestAgcMaintenance());r._nf_calib_active=false;
    CHECK(r.requestAgcMaintenance());CHECK(r.calls.empty());CHECK(!r.requestAgcMaintenance());CHECK(r.isReceiving());
    run(r);CHECK(!r._agc_status.active);CHECK(r._agc_status.completed==1);CHECK(r._agc_status.failures==0);
    CHECK(r._noise_floor==-112);CHECK(count(r,S::Sample)==64);CHECK(count(r,S::Image)==1);CHECK(count(r,S::RestoreRx)==1);
  }
  {
    Radio r;state=STATE_RX;r._rx_ps_enabled=r._rx_ps_armed=true;r.defer=true;
    CHECK(r.requestAgcMaintenance());advance(r);CHECK(r.calls.size()==1);CHECK(r._rx_ps_armed);
    r.defer=false;run(r);CHECK(r._rx_ps_armed);CHECK(r._agc_status.completed==1);
  }
  for(int value:{AGC_MAINTENANCE_RX_ACTIVITY,AGC_MAINTENANCE_RX_READY}){
    Radio r;state=STATE_RX;r.probe_value=value;CHECK(r.requestAgcMaintenance());run(r);
    CHECK(count(r,S::Suspend)==0);CHECK(r._agc_status.cancellations==1);
    if(value==AGC_MAINTENANCE_RX_READY)CHECK(state&STATE_INT_READY);
  }
  for(int value:{AGC_MAINTENANCE_RX_ACTIVITY,AGC_MAINTENANCE_RX_READY}){
    Radio r;state=STATE_RX;r.post_suspend_value=value;CHECK(r.requestAgcMaintenance());run(r);
    CHECK(count(r,S::Sleep)==0);CHECK(r._agc_status.cancellations==1);
    if(value==AGC_MAINTENANCE_RX_READY)CHECK(state&STATE_INT_READY);
    else CHECK(count(r,S::StartRx)==1);
  }
  {
    Radio r;state=STATE_RX;CHECK(r.requestAgcMaintenance());until(r,S::Sleep);state|=STATE_INT_READY;advance(r);
    CHECK(!r._agc_status.active);CHECK(count(r,S::Sleep)==0);CHECK(state&STATE_INT_READY);
  }
  {
    Radio r;state=STATE_RX;CHECK(r.requestAgcMaintenance());r.inject_after_suspend=true;run(r);
    CHECK(count(r,S::Sleep)==0);CHECK(state&STATE_INT_READY);
  }
  {
    Radio r;state=STATE_RX;CHECK(r.requestAgcMaintenance());r.inject_after_suspend=true;r.fail_step=S::Suspend;r.fail_count=1;run(r);
    CHECK(r._agc_status.failures==1);CHECK(r._agc_status.last_error==-707);
  }
  {
    Radio r;state=STATE_RX;r._rx_ps_enabled=true;CHECK(r.requestAgcMaintenance());until(r,S::Sampling);
    CHECK(!r.agcOwnsHardware());CHECK(r._noise_floor==-105);r.probe_value=AGC_MAINTENANCE_RX_ACTIVITY;advance(r);
    CHECK(!r._agc_status.active);CHECK(r._agc_restore_pending);CHECK(count(r,S::RestoreRx)==0);CHECK(r._noise_floor==-105);
  }
  {
    Radio r;state=STATE_RX;CHECK(r.requestAgcMaintenance());until(r,S::Sampling);r.inject_after_sample=true;advance(r,20);
    CHECK(state&STATE_INT_READY);uint8_t data[3]={};CHECK(r.recvRaw(data,3)==3);CHECK(r.chip.read==1);
    CHECK(!r._agc_status.active);CHECK(r._agc_restore_pending);
  }
  {
    Radio r;state=STATE_RX;CHECK(r.requestAgcMaintenance());until(r,S::Sampling);
    state.reads=0;state.inject_read=3;uint8_t data[3]={};
    CHECK(r.recvRaw(data,3)==0);CHECK(state&STATE_INT_READY);CHECK(r.rxstarts==0);
    CHECK(r.recvRaw(data,3)==3);CHECK(!r._agc_status.active);CHECK(r.chip.read==1);
  }
  for(S step:{S::ReadGain,S::Suspend,S::Sleep,S::Wake,S::Calibrate,S::WaitCalibration,S::Image,
              S::Dio2,S::WriteGain,S::ReadPatch,S::WritePatch,S::StartRx,S::Sample,S::RestoreRx}){
    Radio r;state=STATE_RX;r.fail_step=step;r.fail_count=1;CHECK(r.requestAgcMaintenance());run(r);
    CHECK(!r._agc_status.active);CHECK(r._agc_status.failures==1);CHECK(r._agc_status.last_error==-707);
    if(step!=S::ReadGain && step!=S::Sample)CHECK(count(r,S::RecoveryWake)==1);
    if(step==S::Calibrate || step==S::WaitCalibration || step==S::Image)CHECK(count(r,S::Image)>=1);
  }
  {
    Radio r;state=STATE_RX;r.fail_step=S::Image;r.fail_count=99;CHECK(r.requestAgcMaintenance());run(r);
    CHECK(!r._agc_status.active);CHECK(r._agc_status.failures==1);CHECK(count(r,S::Image)==2);
  }
  {
    Radio r;state=STATE_RX;CHECK(r.requestAgcMaintenance());until(r,S::WaitCalibration);r.busy=true;
    advance(r,49);CHECK(r._agc_step==S::WaitCalibration);advance(r,2);CHECK(r._agc_step==S::RecoveryWake);
    r.busy=false;run(r);CHECK(r._agc_status.last_error==AGC_MAINTENANCE_TIMEOUT);CHECK(count(r,S::Image)==1);
  }
  {
    Radio r;state=STATE_RX;CHECK(r.requestAgcMaintenance());r.defer=true;advance(r,1600);
    CHECK(!r._agc_status.active);CHECK(count(r,S::Sleep)==0);CHECK(r._agc_status.failures==1);
  }
  {
    Radio r;state=STATE_RX;CHECK(r.requestAgcMaintenance());until(r,S::WaitCalibration);
    advance(r,1600);run(r);CHECK(!r._agc_status.active);CHECK(count(r,S::Image)==1);CHECK(r._agc_status.failures==1);
  }
  {
    Radio r;state=STATE_RX;r.sample=0;CHECK(r.requestAgcMaintenance());run(r);
    CHECK(!r._agc_status.active);CHECK(count(r,S::Sample)==256);CHECK(r._noise_floor==-105);
  }
  {
    Radio r;state=STATE_RX;tick=0xfffffff0UL;CHECK(r.requestAgcMaintenance());run(r);
    CHECK(r._agc_status.completed==1);CHECK(r._agc_status.failures==0);
  }
  for(S target:{S::ReadGain,S::Sleep,S::WaitCalibration,S::Sampling}){
    Radio r;state=STATE_RX;CHECK(r.requestAgcMaintenance());until(r,target);r.cancelAgcMaintenance();run(r);
    CHECK(!r._agc_status.active);CHECK(r._agc_status.cancellations==1);CHECK(r._agc_status.completed==0);
    if(target==S::WaitCalibration)CHECK(count(r,S::Image)==1);
  }
  for(S target:{S::ReadGain,S::Sleep,S::WaitCalibration,S::Sampling}){
    Radio r;state=STATE_RX;CHECK(r.requestAgcMaintenance());until(r,target);uint8_t data[3]={};
    CHECK(r.startSendRaw(data,3));CHECK(!r._agc_status.active);CHECK(state==STATE_TX_WAIT);CHECK(r.chip.sent==1);
    if(target==S::WaitCalibration)CHECK(count(r,S::Image)==1);
  }
  {
    Radio r;state=STATE_RX;CHECK(r.requestAgcMaintenance());until(r,S::Sleep);uint8_t data[3]={};
    unsigned calls=r.calls.size();CHECK(r.recvRaw(data,3)==0);CHECK(r.calls.size()==calls);CHECK(r.chip.read==0);
    r.startRecv();CHECK(r.rxstarts==0);CHECK(r.isReceiving());
  }
  {
    state=STATE_RX;primask=1;setStatePreservingIRQ(STATE_IDLE);CHECK(primask==1);
    primask=0;state=STATE_RX;inject_irq_on_lock=true;setStatePreservingIRQ(STATE_IDLE);
    CHECK(primask==0);CHECK(state==STATE_INT_READY);
    state=STATE_TX_WAIT;setStatePreservingIRQ(STATE_IDLE);CHECK(state==STATE_TX_WAIT);
  }
  std::printf("AGC production controller: %u checks PASS\n",checks);
}
'''
    compile_run(code)
    transport_test(sx)


if __name__ == '__main__':
    main()
