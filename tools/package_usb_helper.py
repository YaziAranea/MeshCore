#!/usr/bin/env python3
"""Build the dependency-free, offline SmartUI USB helper and deterministic ZIP."""
from pathlib import Path
import argparse
import hashlib
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/usb-helper"
HTML_NAME = "SmartUI_USB_Helper_1.9.html"
ZIP_NAME = "SmartUI_USB_Helper_1.9.zip"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def render():
    html = (SOURCE / "index.html").read_text(encoding="utf-8")
    for part in ("core", "firmware", "api", "presets", "app", "dashboard"):
        marker = f"/* SMARTUI_HELPER_{part.upper()} */"
        if html.count(marker) != 1:
            raise ValueError(f"Expected exactly one {part} marker")
        script = (SOURCE / f"{part}.js").read_text(encoding="utf-8")
        if re.search(r"</script", script, re.I):
            raise ValueError("Inline script must not contain a closing HTML script tag")
        html = html.replace(marker, script)
    if re.search(r"<(?:script|link|iframe)\b[^>]*(?:src|href)\s*=", html, re.I):
        raise ValueError("Offline helper must not load external resources")
    if "connect-src 'none'" not in html:
        raise ValueError("Missing offline network policy")
    return html.encode("utf-8")


def package(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    html = render()
    payloads = {
        HTML_NAME: html,
        "README_RU.md": (SOURCE / "README_RU.md").read_bytes(),
        "PRESETS_SOURCE_RU.md": (SOURCE / "PRESETS_SOURCE_RU.md").read_bytes(),
        "docs/CONSOLE_COMMANDS_RU.md": (ROOT / "docs/CONSOLE_COMMANDS_RU.md").read_bytes(),
        "docs/SMARTUI_CLI_RU.md": (ROOT / "docs/SMARTUI_CLI_RU.md").read_bytes(),
        "tools/smartui-cli/README.md": (ROOT / "tools/smartui-cli/README.md").read_bytes(),
        "tools/usb-helper/PRESETS_SOURCE_RU.md": (SOURCE / "PRESETS_SOURCE_RU.md").read_bytes(),
        "LICENSE": (ROOT / "LICENSE").read_bytes(),
        "screenshots/settings-desktop.png": (SOURCE / "screenshots/settings-desktop.png").read_bytes(),
        "screenshots/settings-mobile.png": (SOURCE / "screenshots/settings-mobile.png").read_bytes(),
        "screenshots/dashboard-desktop.png": (SOURCE / "screenshots/dashboard-desktop.png").read_bytes(),
        "screenshots/dashboard-mobile.png": (SOURCE / "screenshots/dashboard-mobile.png").read_bytes(),
        "screenshots/city-desktop.png": (SOURCE / "screenshots/city-desktop.png").read_bytes(),
        "screenshots/city-mobile.png": (SOURCE / "screenshots/city-mobile.png").read_bytes(),
        "screenshots/adc-service-desktop.png": (SOURCE / "screenshots/adc-service-desktop.png").read_bytes(),
        "screenshots/adc-service-mobile.png": (SOURCE / "screenshots/adc-service-mobile.png").read_bytes(),
        "screenshots/console-desktop.png": (SOURCE / "screenshots/console-desktop.png").read_bytes(),
        "screenshots/console-mobile.png": (SOURCE / "screenshots/console-mobile.png").read_bytes(),
    }
    checksums = "".join(f"{digest(raw)}  {name}\n" for name, raw in sorted(payloads.items()))
    payloads["SHA256SUMS.txt"] = checksums.encode("ascii")
    html_path = output / HTML_NAME
    zip_path = output / ZIP_NAME
    if html_path.exists() or zip_path.exists():
        raise ValueError("Refusing to overwrite an existing helper artifact")
    html_path.write_bytes(html)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw, compresslevel=9)
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(payloads)
        for name, raw in payloads.items():
            assert archive.read(name) == raw
    return html_path, zip_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    for artifact in package(args.output):
        print(f"{artifact.name}: {artifact.stat().st_size} bytes; SHA256 {digest(artifact.read_bytes())}")
