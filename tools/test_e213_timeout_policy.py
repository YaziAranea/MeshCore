#!/usr/bin/env python3
"""Static + timing-model regression for Wireless Paper BUSY recovery policy."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/helpers/ui/E213Display.cpp").read_text(encoding="utf-8")
HEADER = (ROOT / "src/helpers/ui/E213Display.h").read_text(encoding="utf-8")
GUARD = (ROOT / "src/helpers/ui/E213BusyGuard.h").read_text(encoding="utf-8")
CONFIG = (ROOT / "variants/heltec_wireless_paper/platformio.ini").read_text(encoding="utf-8")


def flag(name: str) -> int:
    match = re.search(rf"-D {name}=(\d+)(?:UL)?", CONFIG)
    assert match, f"missing {name}"
    return int(match.group(1))


def elapsed(now: int, started: int, budget: int) -> bool:
    return budget > 0 and ((now - started) & 0xFFFFFFFF) >= budget


def main() -> None:
    wait = flag("E213_BUSY_TIMEOUT_MILLIS")
    init = flag("E213_INIT_BUDGET_MILLIS")
    frame = flag("E213_FRAME_BUDGET_MILLIS")
    retry = flag("E213_RETRY_DELAY_MILLIS")
    retry_max = flag("E213_RETRY_MAX_DELAY_MILLIS")
    assert 0 < wait <= frame <= init < 0x80000000
    assert 0 < retry <= retry_max < 0x80000000
    assert "-D E213_KEEP_SHARED_VEXT_ON=1" in CONFIG

    assert SOURCE.count("_guard->keepWaiting(millis(), started)") == 2
    assert SOURCE.count("delay(1);  // Block loopTask") == 2
    assert "keepWaiting(millis(), started)) return;\n      yield();" not in SOURCE
    assert "digitalRead(DISP_BUSY) == LOW" in SOURCE
    assert "digitalRead(DISP_BUSY) == HIGH" in SOURCE
    assert "if (!finishOperation()) return;" in SOURCE
    finish = SOURCE.index("if (!finishOperation()) return;", SOURCE.index("void E213Display::endFrame"))
    commit = SOURCE.index("last_display_crc_value = crc", finish)
    assert finish < commit
    assert "_has_display_crc = false;" in SOURCE[SOURCE.index("void E213Display::failOperation"):commit]
    assert "#if !E213_KEEP_SHARED_VEXT_ON\n  powerOff();" in SOURCE
    assert "if (!_isOn || !_init || display == NULL) return;" in SOURCE
    assert "(uint32_t)(now - started) >= budget" in GUARD
    assert "(int32_t)(now - _retry_at_millis) >= 0" in SOURCE
    assert "_retry_pending && retryReady(millis())" in SOURCE
    assert "_retry_delay_millis *= 2;" in SOURCE
    assert "_retry_delay_millis = E213_RETRY_MAX_DELAY_MILLIS;" in SOURCE
    for api in ("lastError()", "hasPendingRetry()", "lastOperationMillis()",
                "retryAfterMillis()", "clearError()"):
        assert api in HEADER

    # Same unsigned-difference rule used by E213BusyGuard: exact deadline and
    # wraparound both expire, one tick before either deadline does not.
    start = 0xFFFFFF00
    assert not elapsed((start + wait - 1) & 0xFFFFFFFF, start, wait)
    assert elapsed((start + wait) & 0xFFFFFFFF, start, wait)
    assert elapsed((start + frame) & 0xFFFFFFFF, start, frame)

    dependency = re.search(
        r"heltec-eink-modules/archive/([0-9a-f]{40})\.zip", CONFIG)
    assert dependency and dependency.group(1) == "9207eb6ab2b96f66298e0488740218c17b006af7"
    print(
        f"[PASS] E213 policy: wait={wait}ms frame={frame}ms init={init}ms "
        f"retry={retry}..{retry_max}ms; both BUSY polarities bounded; CRC commit after success; shared VEXT retained"
    )
    print("Static source contract + wrap timing model; firmware compile/hardware fault injection separate.")


if __name__ == "__main__":
    main()
