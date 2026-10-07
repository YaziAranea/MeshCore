#!/usr/bin/env python3
"""Run production companion radio transactions with deterministic hardware faults."""
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


def main():
    mesh = (ROOT / 'examples/companion_radio/MyMesh.cpp').read_text(encoding='utf-8')
    wrapper = (ROOT / 'src/helpers/radiolib/CustomSX1262Wrapper.h').read_text(encoding='utf-8')
    common = (ROOT / 'src/helpers/radiolib/RadioLibWrappers.cpp').read_text(encoding='utf-8')
    base = (ROOT / 'src/helpers/radiolib/RadioLibWrappers.h').read_text(encoding='utf-8')
    startup = (ROOT / 'examples/companion_radio/main.cpp').read_text(encoding='utf-8')
    header = (ROOT / 'examples/companion_radio/MyMesh.h').read_text(encoding='utf-8')
    # Startup is shared by non-SmartUI targets too. Its error discriminator
    # must not disappear when the optional connection selector is disabled.
    guards = []
    for line in header.splitlines():
        directive = line.strip()
        if directive.startswith(('#if ', '#ifdef ', '#ifndef ')):
            guards.append(directive)
        elif directive.startswith('#endif'):
            guards.pop()
        if 'bool isRadioStartupError() const' in line:
            assert not guards, f'radio startup getter hidden by {guards}'
            break
    else:
        raise AssertionError('missing shared radio startup error getter')
    failed_start = body(startup, 'if (!mesh_started)')
    radio_failure = body(failed_start, 'if (the_mesh.isRadioStartupError())')
    assert '"RADIO ERROR"' in radio_failure and 'halt();' in radio_failure
    assert failed_start.index('if (the_mesh.isRadioStartupError())') < failed_start.index('"IDENTITY ERROR"')
    assert 'factory' not in radio_failure.lower() and 'reset' not in radio_failure.lower()
    for signature in ('void RadioLibWrapper::startRecv()', 'void RadioLibWrapper::resetAGC()',
                      'void RadioLibWrapper::loop()', 'bool RadioLibWrapper::isChannelActive()',
                      'int RadioLibWrapper::recvRaw(', 'bool RadioLibWrapper::startSendRaw('):
        assert body(common, signature).strip().startswith('if (!_config_valid) return')
    assert 'setParams(freq, bw, sf, cr);' in body(base, 'virtual bool setParamsChecked(')
    boot = body(mesh, 'if (!setCompanionRadioParamsChecked(_prefs.freq, _prefs.bw, _prefs.sf, _prefs.cr))')
    code = r'''
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include "RXPowerSaving.h"
#include "LoRaConfigValidation.h"
#define MESH_DEBUG_PRINTLN(...) do {} while (0)
#define RADIOLIB_ERR_NONE 0
#define ERR_CODE_BAD_STATE 4
#define ERR_CODE_FILE_IO_ERROR 5
#define ERR_CODE_ILLEGAL_ARG 6
#define LORA_FREQ 868.0f
#define LORA_BW 125.0f
#define LORA_SF 9
#define LORA_CR 5
#define STATE_RX 1
#define STATE_TX_WAIT 3
int state=0;
struct Board {
  unsigned before=0,after=0;
  void onBeforeTransmit() { ++before; }
  void onAfterTransmit() { ++after; }
} board;
struct Chip {
  float frequency=868, bandwidth=125;
  uint8_t sf=9, cr=5; unsigned preamble=16, writes=0, transmissions=0;
  int fail_stage=0, failures=0; bool fail_all=false;
  int fail(int stage) {
    ++writes;
    if (fail_all) return -1;
    if (stage == fail_stage && failures > 0) { --failures; return -1; }
    return 0;
  }
  int setFrequency(float v) { if(fail(1))return -1;frequency=v;return 0; }
  int setSpreadingFactor(uint8_t v) { if(fail(2))return -1;sf=v;return 0; }
  int setBandwidth(float v) { if(fail(3))return -1;bandwidth=v;return 0; }
  int setCodingRate(uint8_t v) { if(fail(4))return -1;cr=v;return 0; }
  int setPreambleLength(unsigned v) { if(fail(5))return -1;preamble=v;return 0; }
  void setPreambleMillis(uint32_t) {}
  void setMaxPayloadMillis(uint32_t) {}
  int standby() { return 0; }
  int startTransmit(uint8_t*,int) { ++transmissions;return 0; }
} chip;
using CustomSX1262 = Chip;
struct PacketMillis { uint32_t preambleMillis=0, payloadMillis=0; };
struct TestRadio : RxPowerSavingControl {
  Chip* _radio=&chip;
  Board* _board=&board;
  bool _config_valid=true;
  bool _rx_ps_armed=false;
  uint8_t _preamble_sf=9;
  float cached_bandwidth=125;
  uint32_t applied_rx=0, applied_sleep=0;
  unsigned config_calls=0, rxps_calls=0, legacy_calls=0, receive_calls=0;
  void idle() { _radio->standby(); }
  bool agcOwnsHardware() const { return false; }
  void abortAgcMaintenanceForRadioChange() {}
  void stopReceiveDutyCycle() { _rx_ps_armed=false; }
  int startReceiveMode() { ++receive_calls;return 0; }
  void startRecv() {
''' + body(common, 'void RadioLibWrapper::startRecv()') + r'''
  }
  bool startSendRaw(const uint8_t* bytes,int len) {
''' + body(common, 'bool RadioLibWrapper::startSendRaw(') + r'''
  }
  static unsigned preambleLengthForSF(uint8_t sf) { return sf <= 8 ? 32 : 16; }
  PacketMillis calcMaxPacketMillis(uint8_t, float bw, uint8_t, unsigned) { cached_bandwidth=bw;return {}; }
  bool validateParams(float freq, float bw, uint8_t sf, uint8_t cr) const {
''' + body(wrapper, 'bool validateParams(') + r'''
  }
  bool setParamsChecked(float freq, float bw, uint8_t sf, uint8_t cr) {
    ++config_calls;
''' + body(wrapper, 'bool setParamsChecked(') + r'''
  }
  void setParams(float freq, float bw, uint8_t sf, uint8_t cr) {
    ++legacy_calls;
    assert(setParamsChecked(freq,bw,sf,cr));
  }
  bool setRxPowerSaving(bool, uint32_t rx, uint32_t sleep) override {
    ++rxps_calls;applied_rx=rx;applied_sleep=sleep;return true;
  }
} radio_driver;
static bool validateCompanionRadioParams(float freq, float bw, uint8_t sf, uint8_t cr) {
''' + body(mesh, 'static bool validateCompanionRadioParams(') + r'''
}
static bool setCompanionRadioParamsChecked(float freq, float bw, uint8_t sf, uint8_t cr) {
''' + body(mesh, 'static bool setCompanionRadioParamsChecked(') + r'''
}
static void applyCompanionRxPowerSaving(uint8_t sf, float bw) {
''' + body(mesh, 'static void applyCompanionRxPowerSaving(') + r'''
}
struct Prefs {
  float freq=868,bw=125; uint8_t sf=9,cr=5; bool repeat=false;
  bool isRepeatEn() { return repeat; }
  void setRepeatEn(bool v) { repeat=v; }
} _prefs, persisted;
bool save_ok=true, fail_after_save=false, _radio_startup_error=false; unsigned saves=0; int response=-1;
bool savePrefs() {
  ++saves;
  // Durable settings may only be attempted after all hardware steps succeeded.
  assert(radio_driver._config_valid);
  assert(chip.frequency == _prefs.freq && chip.bandwidth == _prefs.bw);
  assert(chip.sf == _prefs.sf && chip.cr == _prefs.cr);
  if(save_ok) persisted=_prefs;
  if(fail_after_save) chip.fail_all=true;
  return save_ok;
}
struct Store { bool savePrefs(const Prefs&) { return ::savePrefs(); } } store;
Store* _store=&store;
bool isValidClientRepeatFreq(uint32_t freq) { return freq == 869525; }
void writeErrFrame(int code) { response=code; }
void writeOKFrame() { response=0; }
void handle(uint8_t* cmd_frame, int len) {
''' + body(mesh, '} else if (cmd_frame[0] == CMD_SET_RADIO_PARAMS && len >= 11)') + r'''
}
bool boot() {
  if (!setCompanionRadioParamsChecked(_prefs.freq, _prefs.bw, _prefs.sf, _prefs.cr)) {
''' + boot + r'''
  }
  applyCompanionRxPowerSaving(_prefs.sf,_prefs.bw);
  return true;
}
void reset() {
  chip=Chip{};board=Board{};state=0;radio_driver=TestRadio{};_prefs=Prefs{};persisted=Prefs{};
  save_ok=true;fail_after_save=false;_radio_startup_error=false;saves=0;response=-1;
}
void request(uint32_t freq=915000,uint32_t bw=250000,uint8_t sf=10,uint8_t cr=7,uint8_t repeat=0) {
  uint8_t frame[12]={11};
  memcpy(frame+1,&freq,4);memcpy(frame+5,&bw,4);frame[9]=sf;frame[10]=cr;frame[11]=repeat;
  handle(frame,sizeof(frame));
}
void expect_old() {
  assert(_prefs.freq==868 && _prefs.bw==125 && _prefs.sf==9 && _prefs.cr==5 && !_prefs.repeat);
  assert(chip.frequency==868 && chip.bandwidth==125 && chip.sf==9 && chip.cr==5 && chip.preamble==16);
  assert(persisted.freq==868 && persisted.bw==125);
}
uint32_t floatBits(float value) {
  uint32_t bits;memcpy(&bits,&value,sizeof(bits));return bits;
}
float drift(float value,int ulps) {
  uint32_t bits=floatBits(value)+ulps;memcpy(&value,&bits,sizeof(value));return value;
}
int main() {
  struct Bandwidth { uint32_t hz;float khz; };
  const Bandwidth bandwidths[] = {
    {7800,7.8f},{10400,10.4f},{15600,15.6f},{20800,20.8f},{31250,31.25f},
    {41700,41.7f},{62500,62.5f},{125000,125.0f},{250000,250.0f},{500000,500.0f}
  };
  for(const auto& bw : bandwidths) {
    assert(validSX1262LoRaParams(868,bw.khz,9,5));
    assert(floatBits(companionBandwidthKHz(bw.hz))==floatBits(bw.khz));
    reset();request(868731,bw.hz,7,7);
    assert(response==0 && saves==1 && radio_driver._config_valid);
    assert(static_cast<uint32_t>(_prefs.freq*1000.0f+0.5f)==868731);
    assert(floatBits(_prefs.bw)==floatBits(bw.khz));
    assert(floatBits(persisted.bw)==floatBits(bw.khz));
    assert(floatBits(chip.bandwidth)==floatBits(bw.khz));
    assert(floatBits(radio_driver.cached_bandwidth)==floatBits(bw.khz));
    for(int ulps : {-3,-2,-1,0,1,2,3}) {
      const float old=drift(bw.khz,ulps);float canonical=0;
      const bool accepted=ulps>=-2 && ulps<=2;
      assert(canonicalSX1262Bandwidth(old,canonical)==accepted);
      assert(validSX1262LoRaParams(868,old,9,5)==accepted);
      if(accepted) {
        assert(floatBits(canonical)==floatBits(bw.khz));
        reset();assert(radio_driver.setParamsChecked(868,old,9,5));
        assert(floatBits(chip.bandwidth)==floatBits(bw.khz));
        assert(floatBits(radio_driver.cached_bandwidth)==floatBits(bw.khz));
      }
    }
#ifdef WRAPPER_CLASS
    for(int delta : {-1,1}) {
      reset();request(868731,bw.hz+delta,7,7);
      assert(response==ERR_CODE_ILLEGAL_ARG && saves==0 && chip.writes==0);
      expect_old();
    }
    for(int ulps : {-2,-1,1,2}) {
      // Saved pre-fix drift must neither force a factory preset nor break a
      // rollback. Driver and time-on-air cache receive the canonical value.
      const float old=drift(bw.khz,ulps);
      reset();_prefs.bw=old;persisted=_prefs;chip.bandwidth=bw.khz;
      assert(boot());
      assert(saves==0 && !_radio_startup_error && radio_driver._config_valid);
      assert(floatBits(chip.bandwidth)==floatBits(bw.khz));
      assert(floatBits(radio_driver.cached_bandwidth)==floatBits(bw.khz));
      for(int stage=0;stage<=5;++stage) {
        reset();_prefs.bw=old;persisted=_prefs;chip.bandwidth=bw.khz;
        if(stage) { chip.fail_stage=stage;chip.failures=1; }
        else save_ok=false;
        request();
        assert(response==(stage ? ERR_CODE_BAD_STATE : ERR_CODE_FILE_IO_ERROR));
        assert(saves==(stage ? 0U : 1U) && radio_driver._config_valid);
        assert(floatBits(_prefs.bw)==floatBits(old) && floatBits(persisted.bw)==floatBits(old));
        assert(floatBits(chip.bandwidth)==floatBits(bw.khz));
        assert(floatBits(radio_driver.cached_bandwidth)==floatBits(bw.khz));
        assert(_prefs.freq==868 && chip.frequency==868 && persisted.freq==868);
      }
    }
#endif
  }
  // Exact OMS migration reported for ProMicro, through binary CMD11 as well.
  reset();_prefs.freq=869.618f;_prefs.bw=62.5f;_prefs.sf=8;_prefs.cr=5;
  persisted=_prefs;chip.frequency=_prefs.freq;chip.bandwidth=_prefs.bw;chip.sf=8;chip.cr=5;
  request(868731,62500,7,7);
  assert(response==0 && saves==1 && chip.sf==7 && chip.cr==7);
  assert(floatBits(chip.bandwidth)==floatBits(62.5f));
  assert(floatBits(persisted.bw)==floatBits(62.5f));
  assert(!validCompanionLoRaParams(NAN,125,9,5));
  assert(!validCompanionLoRaParams(868,NAN,9,5));
  assert(!validCompanionLoRaParams(INFINITY,125,9,5));
  assert(!validCompanionLoRaParams(868,INFINITY,9,5));
  assert(!validSX1262LoRaParams(NAN,125,9,5));
  assert(!validSX1262LoRaParams(868,NAN,9,5));
  assert(!validSX1262LoRaParams(INFINITY,125,9,5));
  assert(!validSX1262LoRaParams(2400,125,9,5));
  assert(!validSX1262LoRaParams(868,126,9,5));
  assert(!validSX1262LoRaParams(868,300,9,5));
  assert(!validSX1262LoRaParams(868,125,4,5));
  assert(!validSX1262LoRaParams(868,125,9,9));
#ifdef WRAPPER_CLASS
  for(uint32_t frequency : {150000U,960000U}) {
    reset();request(frequency,62500,7,7);
    assert(response==0 && saves==1 && radio_driver._config_valid);
    assert(static_cast<uint32_t>(chip.frequency*1000.0f+0.5f)==frequency);
    assert(chip.frequency==_prefs.freq && chip.frequency==persisted.freq);
  }
  for(uint32_t frequency : {149999U,960001U}) {
    reset();request(frequency,62500,7,7);
    assert(response==ERR_CODE_ILLEGAL_ARG && saves==0 && chip.writes==0);
    expect_old();
  }
  for (uint32_t bw : {126000U,300000U,7000U,500001U}) {
    reset();request(868000,bw);
    assert(response==ERR_CODE_ILLEGAL_ARG && saves==0 && chip.writes==0);
    expect_old();
  }
  reset();request(2400000,125000);assert(response==ERR_CODE_ILLEGAL_ARG && saves==0 && chip.writes==0);
  reset();request(915000,250000,10,7,1);assert(response==ERR_CODE_ILLEGAL_ARG && saves==0 && chip.writes==0);
  for(int stage=1;stage<=5;++stage) {
    reset();chip.fail_stage=stage;chip.failures=1;request();
    assert(response==ERR_CODE_BAD_STATE && saves==0 && radio_driver._config_valid);
    expect_old();
  }
  reset();chip.fail_all=true;request();
  assert(response==ERR_CODE_BAD_STATE && saves==0 && !radio_driver._config_valid);
  const uint8_t message=1;
  assert(!radio_driver.startSendRaw(&message,1));radio_driver.startRecv();
  assert(chip.transmissions==0 && board.before==0 && radio_driver.receive_calls==0);
  chip.fail_all=false;request();assert(response==0 && radio_driver._config_valid);
  assert(radio_driver.startSendRaw(&message,1));radio_driver.startRecv();
  assert(chip.transmissions==1 && board.before==1 && radio_driver.receive_calls==1);
  reset();save_ok=false;request();
  assert(response==ERR_CODE_FILE_IO_ERROR && saves==1 && radio_driver._config_valid);expect_old();
  reset();save_ok=false;fail_after_save=true;request();
  assert(response==ERR_CODE_BAD_STATE && saves==1 && !radio_driver._config_valid);
  assert(_prefs.freq==868 && _prefs.bw==125 && persisted.freq==868 && persisted.bw==125);
  reset();_prefs.bw=300;_prefs.repeat=true;assert(boot());
  assert(saves==1 && chip.writes==5 && radio_driver._config_valid);expect_old();
  reset();_prefs.freq=NAN;assert(boot());expect_old();
  reset();_prefs.bw=300;save_ok=false;assert(boot());assert(saves==1);expect_old();
  reset();_prefs.bw=300;chip.fail_all=true;assert(!boot());
  assert(saves==0 && !radio_driver._config_valid && _radio_startup_error);
  for(int stage=1;stage<=5;++stage) {
    reset();_prefs.freq=915;_prefs.bw=250;chip.fail_stage=stage;chip.failures=1;
    assert(boot());assert(saves==1 && radio_driver._config_valid);expect_old();
  }
#endif
  reset();request();assert(response==0 && saves==1 && radio_driver._config_valid);
  assert(chip.frequency==915 && chip.bandwidth==250 && persisted.freq==915 && persisted.bw==250);
  uint32_t rx=0,sleep=0;
  assert(calcRxPowerSavingLevel(RX_POWERSAVING_BALANCED_LEVEL,10,250,16,&rx,&sleep));
#ifdef WRAPPER_CLASS
  assert(radio_driver.applied_rx==rx && radio_driver.applied_sleep==sleep);
  puts("PASS: SX1262 validation, five-stage SPI rollback, flash rollback, rollback failure, boot fallback, matching RXPS");
#else
  assert(radio_driver.legacy_calls==1);
  puts("PASS: non-RadioLib legacy setParams compatibility");
#endif
}
'''
    code = '#include <initializer_list>\n' + code
    with tempfile.TemporaryDirectory(prefix='smartui-radio-config-') as tmp:
        folder = Path(tmp)
        source = folder / 'test.cpp'
        source.write_text(code, encoding='utf-8')
        include = ROOT / 'src/helpers/radiolib'
        calculator = include / 'RXPowerSaving.cpp'
        for checked in (True, False):
            for optimization in ('-O2', '-Ofast'):
                flags = ['-std=c++14', '-Wall', '-Wextra', '-Werror', optimization]
                if checked:
                    flags.append('-DWRAPPER_CLASS=TestRadio')
                binary = folder / (('checked' if checked else 'legacy') + optimization)
                if shutil.which('g++'):
                    compile_cmd = ['g++', *flags, '-I', str(include), str(source), str(calculator), '-o', str(binary)]
                    run_cmd = [str(binary)]
                else:
                    compile_cmd = ['wsl', '--exec', 'g++', *flags, '-I', linux(include), linux(source), linux(calculator), '-o', linux(binary)]
                    run_cmd = ['wsl', '--exec', linux(binary)]
                print(f"companion radio {'checked' if checked else 'legacy'} {optimization}", flush=True)
                subprocess.run(compile_cmd, check=True, timeout=40)
                subprocess.run(run_cmd, check=True, timeout=10)


if __name__ == '__main__':
    main()
