#!/usr/bin/env python3
"""Source-bound V3 addon QA; no hardware or whole-firmware execution claim.

The original five-board release assets stay immutable. V3 adds its own
128x64 fixtures using the same checked-in glyph tables/geometry helpers,
but with the actual V3 capability flags: no GPS/FEM or sound group.
"""
from __future__ import annotations

import argparse
import configparser
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import shutil

from PIL import Image

from simulate_smartui_ps17_qa import (
    Frame, make_profiles, make_matrix, render_keyboard,
    render_target, render_send_confirmation,
)
from simulate_v4_3_oled_qa import clock_scene, ble_pin_scene
from simulate_oled_128x64 import STYLES
from simulate_dev2_settings import root_menu, auxiliary, help_labels

ROOT = Path(__file__).resolve().parents[1]
ENV = "env:Heltec_v3_companion_radio_ble_smartui"


def source_contract() -> dict:
    """Resolve local V3 build_flags references before checking last-wins defines."""
    path = ROOT / "variants/heltec_v3/platformio.ini"
    source = path.read_text(encoding="utf-8")
    config = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";",))
    config.read_string(source)
    assert ENV in config, f"missing V3 addon: {ENV}"
    def expand(section: str, key: str, stack=()):
        ref = (section,key)
        assert ref not in stack, f"cyclic V3 configuration: {ref}"
        # Common esp32/sensor flags are outside this file. The decisive UI
        # overrides are explicit in the V3 environment and checked below.
        if section not in config: return ""
        value=config[section].get(key)
        if value is None:
            parent=config[section].get("extends","").strip()
            if parent and parent not in config: parent="env:"+parent
            return expand(parent,key,stack+(ref,)) if parent else ""
        return re.sub(r"\$\{([^{}]+)\.([a-z_]+)\}",
                      lambda m: expand(m[1],m[2],stack+(ref,)),value)
    flags=expand(ENV,"build_flags")
    unflags=expand(ENV,"build_unflags")
    pattern=r"-([DU])\s*([A-Z][A-Z0-9_]*)(?:=([^\s]+))?"
    removed=set(re.findall(pattern,unflags))
    macros={}
    for operation,name,value in re.findall(pattern,flags):
        if (operation,name,value) in removed: continue
        if operation=="U": macros.pop(name,None)
        else: macros[name]=value or "1"
    expected={"HELTEC_LORA_V3":"1","DISPLAY_CLASS":"SSD1306Display",
              "UI_V4_3_OLED_PROFILE":"1","UI_QUICK_REPLY_KEYBOARD":"1",
              "UI_COMPACT_SETTINGS_MENU":"1","UI_SMART_B11_EXTRAS":"1",
              "UI_UNREAD_DIRECT_ONLY":"1","UI_ADC_MULTIPLIER_PAGE":"1",
              "UI_BLE_PIN_PAGE":"1","BLE_PIN_PERSIST_RANDOM":"1",
              "UI_SOUND_SETTINGS_GROUP":"0","UI_PHONE_GPS":"0",
              "UI_TONE_FALLBACK_TO_ALERT":"0","PIN_USER_BTN":"0"}
    for name,value in expected.items():
        assert macros.get(name)==value, f"V3 {name}: {macros.get(name)} != {value}"
    assert ("D","ENV_INCLUDE_GPS","1") in removed and macros.get("ENV_INCLUDE_GPS")=="0"
    assert not any(name in macros for name in ("PIN_GPS_RX","PIN_GPS_TX","PIN_GPS_EN","BLE_DEBUG_LOGGING"))
    assert not any(name in macros for name in ("PIN_MSG_TONE","PIN_BUZZER","PIN_VIBRATION","RADIO_FEM_RXGAIN"))
    header=(ROOT/"src/helpers/ui/SSD1306Display.h").read_text(encoding="utf-8")
    driver=(ROOT/"src/helpers/ui/SSD1306Display.cpp").read_text(encoding="utf-8")
    assert "defined(HELTEC_LORA_V3)" in header and "DisplayDriver(128, 64)" in header
    assert "#if SSD1306_COMPACT_STYLE_PROFILE\n  return 5;" in driver
    for name,advance,bold in STYLES:
        assert f'"{name} {advance}x8"' in driver
    return {"environment":ENV,"dimensions":[128,64],"styles":[s[0] for s in STYLES],
            "gps":False,"fem":False,"buzzer":False,
            "configuration_sha256":hashlib.sha256(source.encode()).hexdigest(),
            "scope":"V3-local flag interpolation + explicit UI overrides; not a full PlatformIO/C++ preprocessor"}


def image_frame(profile,name,image,errors):
    frame=Frame(profile,name,True)
    frame.image=image.convert("RGB")
    frame.violations.extend(errors)
    return frame


def scenes(profile,style):
    clock,errors=clock_scene(style,"",True)
    pin,pin_errors=ble_pin_scene(style,"Heltec V3")
    choices=["Шрифт","Bluetooth","Защита АКБ","Калибр. АКБ","Отмена"]
    return [
        ("clock",image_frame(profile,"V3 clock: no GPS",clock,errors)),
        ("ble-pin",image_frame(profile,"V3 BLE PIN",pin,pin_errors)),
        ("keyboard",render_keyboard(profile,desired=True,cursor=21)),
        ("keyboard-typing",render_keyboard(profile,desired=True,page=1,cursor=14)),
        ("target-home",render_target(profile,desired=True,count=3,cursor=0,kind="Контакты",
                    labels=["* Мария","Все контакты >","По букве >"])),
        ("target-initial",render_target(profile,desired=True,count=4,cursor=2,kind="Первая буква",
                    labels=["A","Е","Я","#"])),
        ("send-confirm",render_send_confirmation(profile)),
        ("settings",root_menu(profile)),
        ("favorites",auxiliary(profile,"Избранное 1",choices,1,"Выбрать",active=2)),
        ("adc-reset",auxiliary(profile,"Сброс ADC",["Отмена","Заводской коэф."],0,"Отмена")),
        ("controls",auxiliary(profile,"Управление",help_labels(),6,"Назад")),
    ]


def run(out: Path, docs: Path | None = None) -> dict:
    contract=source_contract()
    out.mkdir(parents=True,exist_ok=True)
    records=[]
    canonical=[]
    style_sheet=[]
    def record(profile,name,frame):
        records.append({"style":profile.profile,"case":name,"failures":list(frame.violations)})
    for base,style in zip(make_profiles()["OLED"],STYLES):
        profile=replace(base,board="Heltec V3")
        rendered=scenes(profile,style)
        for name,frame in rendered:
            record(profile,name,frame)
        if not canonical: canonical=rendered
        style_sheet.extend((f"V3 / {style[0]} / {name}",frame)
                           for name,frame in rendered if name in ("clock","send-confirm","settings"))
        for muted in (False,True):
            for valid,mv in ((True,4090),(False,0),(False,2700)):
                image,errors=clock_scene(style,"",muted,999999*3600+59*60,
                                         time_valid=valid,milli_volts=mv)
                record(profile,f"clock mute={muted} time={valid} mv={mv}",image_frame(profile,"clock",image,errors))
        for page in range(3):
            for cursor in (0,14,18,19,20,21,22,23):
                frame=render_keyboard(profile,desired=True,page=page,cursor=cursor)
                if frame.facts.get("action_hint"):
                    if not frame.facts.get("hint_full"): frame.violations.append("service instruction truncated")
                elif not (frame.facts.get("tail_ok") and frame.facts.get("caret")):
                    frame.violations.append("typed tail/caret missing")
                record(profile,f"keyboard page={page} cursor={cursor}",frame)
        for count,cursor in ((0,0),(1,0),(350,349),(350,350)):
            record(profile,f"target count={count} cursor={cursor}",render_target(profile,desired=True,count=count,cursor=cursor))
        for target_id in ("#A12F","CH40"):
            for selected in (False,True):
                frame=render_send_confirmation(profile,identity=target_id,send_selected=selected)
                if not frame.facts["identity_full"]: frame.violations.append("recipient short ID truncated")
                record(profile,f"confirm {target_id} send={selected}",frame)
        for cursor in range(7): record(profile,f"root cursor={cursor}",root_menu(profile,cursor))
    failures=[f"{r['style']}/{r['case']}: {e}" for r in records for e in r["failures"]]
    report={"source_contract":contract,"checks":len(records),"failed":len(failures),
            "failures":failures,"records":records,
            "limits":"Source-bound UI geometry, real bitmap glyphs and required-value assertions; not whole UITask execution, button timing, electrical or radio testing. Favourites screenshot is an illustrative subset of valid functions."}
    (out/"REPORT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    assert not failures, "\n".join(failures)
    make_matrix([(f"Heltec V3 / {name}",frame) for name,frame in canonical],
                out/"HELTEC_V3_SMARTUI_UI_MATRIX.png",columns=3)
    make_matrix(style_sheet,out/"HELTEC_V3_SMARTUI_FIVE_STYLES.png",columns=3)
    if docs:
        docs.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(out/"HELTEC_V3_SMARTUI_FIVE_STYLES.png",docs/"heltec-v3-five-styles.png")
    for name,frame in canonical:
        frame.image.save(out/f"heltec-v3-{name}-native.png")
        if docs:
            docs.mkdir(parents=True,exist_ok=True)
            frame.image.resize((512,256),Image.Resampling.NEAREST).save(docs/f"heltec-v3-{name}.png")
    print(f"Heltec V3 addon source-bound UI QA: {len(records)} passed, 0 failed")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir",type=Path,default=ROOT/"qa_outputs/v3-addon")
    parser.add_argument("--docs-dir",type=Path)
    args=parser.parse_args()
    run(args.out_dir,args.docs_dir)
