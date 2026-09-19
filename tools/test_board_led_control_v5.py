"""Host regression test for the SmartUI V5 onboard-LED master switch.

The harness compiles the production BoardLedControl implementation and the
actual TX callback bodies for each public SmartUI board family.  Arduino GPIO
and FEM operations are recorded by small host stubs.  This is not an RF or
electrical hardware test.
"""

from pathlib import Path
import re
import shutil
import subprocess

from test_notify_pins_v4 import UI as NOTIFY_UI, board_defines, build_harness


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "qa_outputs/board-led-control-v5"


def function(source: str, signature: str) -> str:
    """Return one complete C++ function, including nested blocks."""
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for pos in range(brace, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    raise AssertionError(f"unterminated function: {signature}")


def run_cpp(code: str, stem: str) -> str:
    assert re.fullmatch(r"[a-z0-9_-]+", stem)
    OUT.mkdir(parents=True, exist_ok=True)
    cpp = OUT / f"{stem}.cpp"
    cpp.write_text(code, encoding="utf-8")
    native = shutil.which("g++")
    linux_out = None if native else subprocess.check_output(
        ["wsl", "--exec", "wslpath", "-a", str(OUT.resolve())], text=True
    ).strip()
    compiler = [native] if native else ["wsl", "--exec", "g++"]
    source_path = str(cpp) if native else f"{linux_out}/{cpp.name}"
    binary = str(OUT / stem) if native else f"{linux_out}/{stem}"
    result = subprocess.run(
        compiler + ["-std=c++17", "-O2", "-Wall", "-Wextra", source_path, "-o", binary],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    return subprocess.check_output(
        [binary] if native else ["wsl", "--exec", binary],
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def board_led_control_source() -> str:
    source = (ROOT / "src/helpers/BoardLedControl.cpp").read_text(encoding="utf-8")
    return source.replace('#include "BoardLedControl.h"', "")


def harness(class_name: str, methods: str, pin: int, on: int, off: int, fem: bool) -> str:
    if "::" not in methods:
        methods = methods.replace(" override", "")
        declaration = f"class {class_name} {{ public:\n"
        if fem:
            declaration += "  Fem loRaFEMControl;\n"
        declaration += methods + "\n};\n"
        definitions = ""
    else:
        declaration = f"class {class_name} {{ public:\n"
        if fem:
            declaration += "  Fem loRaFEMControl;\n"
        declaration += "  void onBeforeTransmit();\n  void onAfterTransmit();\n};\n"
        definitions = methods

    fem_asserts = r'''
  assert(board.loRaFEMControl.tx == expected_tx);
  assert(board.loRaFEMControl.rx == expected_rx);
''' if fem else ""
    fem_counts = "int expected_tx=0, expected_rx=0;" if fem else ""
    fem_before = "++expected_tx;" if fem else ""
    fem_after = "++expected_rx;" if fem else ""
    fem_label = ", FEM preserved" if fem else ""

    return rf'''
#include <cassert>
#include <cstdio>
#include <vector>
#include <utility>
#include <cstdint>
#define HIGH 1
#define LOW 0
#define P_LORA_TX_LED {pin}
static std::vector<std::pair<int,int>> gpio;
static void digitalWrite(int pin, int value) {{ gpio.push_back({{pin, value}}); }}
struct Fem {{
  int tx=0, rx=0;
  void setTxModeEnable() {{ ++tx; }}
  void setRxModeEnable() {{ ++rx; }}
}};
{board_led_control_source()}
{declaration}
{definitions}
static void expectLast(int value) {{
  assert(!gpio.empty());
  assert(gpio.back().first == P_LORA_TX_LED);
  assert(gpio.back().second == value);
}}
int main() {{
  {class_name} board;
  {fem_counts}

  assert(meshcoreBoardLedsEnabled()); // production default remains ON
  meshcoreSetBoardLedsEnabled(true);
  gpio.clear(); board.onBeforeTransmit(); {fem_before}
  assert(gpio.size() == 1); expectLast({on});
  {fem_asserts}

  // Turning the master off during an active TX must still end safely OFF.
  meshcoreSetBoardLedsEnabled(false);
  gpio.clear(); board.onAfterTransmit(); {fem_after}
  assert(gpio.size() == 1); expectLast({off});
  {fem_asserts}

  // A new TX while disabled must explicitly keep the onboard LED OFF.
  gpio.clear(); board.onBeforeTransmit(); {fem_before}
  assert(gpio.size() == 1); expectLast({off});
  {fem_asserts}

  // Re-enabling during that TX must not make its finish edge illuminate it.
  meshcoreSetBoardLedsEnabled(true);
  gpio.clear(); board.onAfterTransmit(); {fem_after}
  assert(gpio.size() == 1); expectLast({off});
  {fem_asserts}

  std::printf("PASS {class_name} TX LED master, safe finish{fem_label}\n");
}}
'''


def profile_pin(path: str, expected: int) -> None:
    source = (ROOT / path).read_text(encoding="utf-8")
    match = re.search(r"(?m)^\s*-D\s+P_LORA_TX_LED=(\d+)\s*$", source)
    assert match and int(match[1]) == expected, f"unexpected TX LED pin in {path}"


def notification_policy_harness(source: str, flags: dict, external_pin: int) -> str:
    """Use the production notification handler to prove master/external policy."""
    return build_harness(source, flags) + rf'''
int main() {{
  UITask task;
  task.muted=false;
  task.board_leds=false;

  task._msg_alert_pin=PIN_LED;
  io.clear(); task.triggerMsgAlert();
  assert(io.size()==1);
  assert(io.back().pin==PIN_LED && io.back().value!=PIN_MSG_ALERT_ACTIVE);

  // The board master must not suppress an independently selected external LED.
  task._msg_alert_pin={external_pin};
  io.clear(); task.triggerMsgAlert();
  assert(lights({external_pin})==1);

  task.board_leds=true;
  task._msg_alert_pin=PIN_LED;
  io.clear(); task.triggerMsgAlert();
  assert(lights(PIN_LED)==1);
  std::printf("PASS notification master suppresses onboard only; external GPIO remains active\n");
}}
'''


def main() -> None:
    t114_path = ROOT / "variants/heltec_t114/T114Board.h"
    t096_path = ROOT / "variants/heltec_t096/T096Board.cpp"
    esp32_path = ROOT / "src/helpers/ESP32Board.h"
    v4_path = ROOT / "variants/heltec_v4/HeltecV4Board.cpp"

    t114 = t114_path.read_text(encoding="utf-8")
    t096 = t096_path.read_text(encoding="utf-8")
    esp32 = esp32_path.read_text(encoding="utf-8")
    v4 = v4_path.read_text(encoding="utf-8")
    callbacks = {
        "t114": (
            "T114Board",
            function(t114, "void onBeforeTransmit() override") + "\n" +
            function(t114, "void onAfterTransmit() override"),
            35, 0, 1, False,
        ),
        "t096": (
            "T096Board",
            function(t096, "void T096Board::onBeforeTransmit()") + "\n" +
            function(t096, "void T096Board::onAfterTransmit()"),
            28, 1, 0, True,
        ),
        "v3": (
            "ESP32Board",
            function(esp32, "void onBeforeTransmit() override") + "\n" +
            function(esp32, "void onAfterTransmit() override"),
            35, 1, 0, False,
        ),
        "paper": (
            "ESP32Board",
            function(esp32, "void onBeforeTransmit() override") + "\n" +
            function(esp32, "void onAfterTransmit() override"),
            18, 1, 0, False,
        ),
        "v4_3": (
            "HeltecV4Board",
            function(v4, "void HeltecV4Board::onBeforeTransmit(void)") + "\n" +
            function(v4, "void HeltecV4Board::onAfterTransmit(void)"),
            35, 1, 0, True,
        ),
    }

    # Verify the public profile-to-callback mapping used by this host harness.
    profile_pin("variants/heltec_t114/platformio.ini", 35)
    profile_pin("variants/heltec_t096/platformio.ini", 28)
    profile_pin("variants/heltec_v3/platformio.ini", 35)
    profile_pin("variants/heltec_wireless_paper/platformio.ini", 18)
    profile_pin("variants/heltec_v4/platformio.ini", 35)
    assert "public HeltecV3Board" in (ROOT / "variants/heltec_wireless_paper/target.h").read_text(encoding="utf-8")
    assert "public ESP32Board" in (ROOT / "variants/heltec_v3/HeltecV3Board.h").read_text(encoding="utf-8")

    # ProMicro has no LoRa TX LED callback.  Its independent Bluefruit timer
    # must be disabled before Bluefruit.begin() constructs/starts that timer,
    # and only for the published SmartUI build.
    ble = (ROOT / "src/helpers/nrf52/SerialBLEInterface.cpp").read_text(encoding="utf-8")
    ble_begin = function(ble, "void SerialBLEInterface::begin")
    assert "#if defined(PROMICRO) && defined(SMARTUI_RELEASE_LABEL)" in ble_begin
    assert ble_begin.count("Bluefruit.autoConnLed(false);") == 1
    assert ble_begin.index("Bluefruit.autoConnLed(false);") < ble_begin.index("Bluefruit.begin();")
    assert "Advertising.stop" not in ble_begin and "Advertising.start" not in ble_begin
    promicro_profile = (ROOT / "variants/promicro/platformio.ini").read_text(encoding="utf-8")
    assert "-D PROMICRO" in promicro_profile and "-D SMARTUI_RELEASE_LABEL=" in promicro_profile

    # Ownership really passes to the existing UI: PIN_LED remains selectable
    # for notifications, and the board-LED master has an explicit OFF path.
    ui = (ROOT / "examples/companion_radio/ui-new/UITask.cpp").read_text(encoding="utf-8")
    promicro_pins = ui[ui.index("#if defined(PROMICRO)"):ui.index("#elif", ui.index("#if defined(PROMICRO)"))]
    apply_leds = function(ui, "void UITask::applyBoardLedsState()")
    assert "PIN_LED" in promicro_pins
    assert "setBoardLedPinOff(PIN_LED);" in apply_leds
    print("PASS ProMicro disables autonomous BLE LED before Bluefruit.begin; UI retains PIN_LED")

    notify_source = NOTIFY_UI.read_text(encoding="utf-8")
    notify_profiles = {
        "notify_promicro": ("promicro", "ProMicro_ra62_companion_radio_ble", 1),
        "notify_t114": ("heltec_t114", "Heltec_t114_companion_radio_ble", 0),
    }
    for stem, (board, env, external_pin) in notify_profiles.items():
        flags = board_defines(board, env)
        print(run_cpp(notification_policy_harness(notify_source, flags, external_pin), stem), end="")

    for stem, args in callbacks.items():
        class_name, methods, pin, on, off, fem = args
        # Each production callback gates only ON; finish remains unconditional OFF.
        assert "meshcoreBoardLedsEnabled()" in methods
        after_method = function(methods, "void onAfterTransmit") if "void onAfterTransmit" in methods else function(methods, f"void {class_name}::onAfterTransmit")
        assert "meshcoreBoardLedsEnabled()" not in after_method
        print(run_cpp(harness(class_name, methods, pin, on, off, fem), stem), end="")

    wrapper = (ROOT / "src/helpers/radiolib/RadioLibWrappers.cpp").read_text(encoding="utf-8")
    start_send = function(wrapper, "bool RadioLibWrapper::startSendRaw")
    finish_send = function(wrapper, "void RadioLibWrapper::onSendFinished")
    assert start_send.index("onBeforeTransmit()") < start_send.index("startTransmit")
    assert "onAfterTransmit()" in start_send  # immediate start error
    assert "onAfterTransmit()" in finish_send  # normal/interrupt completion
    print("PASS RadioLib finish and start-error paths force the board callback")
    print("PASS all 6 public SmartUI board profiles honor UI ownership of onboard LEDs")


if __name__ == "__main__":
    main()
