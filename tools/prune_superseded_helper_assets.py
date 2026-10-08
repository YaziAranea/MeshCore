"""Guard SmartUI 0.16 assets; prune only known replaced Helper 1.8 hotfix files."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = "YaziAranea/MeshCore"
TAG = "smartui-0.16"
OLD_NAMES = {"SmartUI_USB_Helper_1.8.html", "SmartUI_USB_Helper_1.8.zip"}
NEW_NAMES = {"SmartUI_USB_Helper_2.0.html", "SmartUI_USB_Helper_2.0.zip"}


def cleanup_plan(release, bundle, expected_commit):
    local = {p.name: p for p in Path(bundle).iterdir() if p.is_file()}
    assets = {a["name"]: a for a in release["assets"]}
    if release.get("tag_name") != TAG or len(local) != 19 or len(assets) != len(release["assets"]):
        raise ValueError("Unexpected release identity, bundle size or duplicate assets")
    extra = set(assets) - set(local)
    if extra - OLD_NAMES or set(local) - set(assets):
        raise ValueError("Unknown extra or missing release assets; refusing cleanup")
    # Verify every replacement before removing even a known obsolete file.
    for name, path in local.items():
        asset = assets[name]
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if path.stat().st_size <= 0 or asset.get("state") != "uploaded" or asset.get("size") != path.stat().st_size or asset.get("digest") != digest:
            raise ValueError("Unverified replacement: " + name)
    if not extra:
        return []
    if not release.get("draft") or not re.fullmatch(r"[0-9a-f]{40}", expected_commit or "") or not NEW_NAMES <= set(local):
        raise ValueError("Cleanup requires a hidden same-page hotfix and both new helper files")
    for name in extra:
        if not isinstance(assets[name].get("id"), int) or assets[name]["id"] <= 0:
            raise ValueError("Invalid obsolete asset ID")
    return [(name, assets[name]["id"]) for name in sorted(extra)]


def main():
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise ValueError("Cleanup is restricted to the public repository")
    release = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    expected = os.environ.get("EXPECTED_RELEASE_COMMIT", "")
    planned = cleanup_plan(release, "release", expected)
    if not planned:
        print("No superseded Helper assets")
        return
    repo = json.loads(subprocess.check_output(["gh", "api", "repos/" + REPO], text=True))
    if repo.get("private") or repo.get("visibility") != "public" or repo.get("full_name") != REPO:
        raise ValueError("Repository visibility changed; refusing cleanup")
    tag = json.loads(subprocess.check_output(["gh", "api", f"repos/{REPO}/git/ref/tags/{TAG}"], text=True))
    if tag["object"]["sha"] != expected:
        raise ValueError("Release tag changed; refusing cleanup")
    for name, asset_id in planned:
        subprocess.run(["gh", "api", "--method", "DELETE", f"repos/{REPO}/releases/assets/{asset_id}"], check=True)
        print("Replaced obsolete asset: " + name)


if __name__ == "__main__":
    main()
