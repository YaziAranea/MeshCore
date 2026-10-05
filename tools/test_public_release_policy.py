#!/usr/bin/env python3
"""Guard the public release identity, complete board set and publication boundary."""

from pathlib import Path
import unittest

from package_smartui_release import (
    ARCHIVE_NAME, DISTRIBUTION, ESP_ENVS, FIRMWARE_NAMES, NOTES_NAME, NRF_ENVS,
    PUBLICATION, TAG, VERSION,
)


ROOT = Path(__file__).resolve().parents[1]


class PublicReleasePolicyTests(unittest.TestCase):
    def test_one_public_version_for_six_boards_and_nine_images(self):
        self.assertEqual((VERSION, TAG), ("0.08", "smartui-0.08"))
        self.assertEqual(DISTRIBUTION, "public")
        self.assertEqual(PUBLICATION, {
            "draft": False, "prerelease": False, "make_latest": True,
            "repository": "YaziAranea/MeshCore", "visibility": "public",
        })
        self.assertEqual(len(NRF_ENVS) + len(ESP_ENVS), 6)
        self.assertEqual(len(set(FIRMWARE_NAMES)), 9)
        self.assertTrue(all("_UI_0.08" in name for name in FIRMWARE_NAMES))
        self.assertEqual(ARCHIVE_NAME, "SmartUI_0.08_all-boards.zip")
        self.assertEqual(NOTES_NAME, "RELEASE_NOTES_SmartUI_0.08_RU.md")
        self.assertIn("SmartUI 0.08", (ROOT / NOTES_NAME).read_text(encoding="utf-8"))
        build_info = (ROOT / "src/helpers/SmartUiBuildInfo.h").read_text(encoding="utf-8")
        self.assertIn('#define SMARTUI_VERSION "0.08"', build_info)

    def test_all_release_profiles_use_the_public_marker(self):
        for board in ("heltec_t096", "heltec_t114", "promicro", "heltec_v3",
                      "heltec_v4", "heltec_wireless_paper"):
            with self.subTest(board=board):
                source = (ROOT / "variants" / board / "platformio.ini").read_text(encoding="utf-8")
                self.assertIn('SMARTUI_RELEASE_LABEL=\'"0.08"\'', source)
                self.assertIn("SmartUI 0.08", source)
                self.assertNotIn("SmartUI 0.06-test.2", source)
                self.assertNotIn("PRIVATE_RELAY", source)

    def test_publication_requires_explicit_public_target_and_all_checks(self):
        workflow = (ROOT / ".github/workflows/smartui-ci.yml").read_text(encoding="utf-8")
        publish = workflow.split("  publish-public-release:", 1)[1]
        for guard in ("github.repository == 'YaziAranea/MeshCore'",
                      "github.event.repository.private == false",
                      "github.event_name == 'workflow_dispatch'",
                      "inputs.publish_experimental",
                      "github.ref == 'refs/heads/smartui-0.08'",
                      "needs: release-gate"):
            self.assertIn(guard, publish)
        self.assertIn('.full_name == "YaziAranea/MeshCore" and .private == false and .visibility == "public"', publish)
        self.assertEqual(publish.count("          check_public_target\n"), 2)
        self.assertLess(publish.index("          check_public_target\n"), publish.index('tag="smartui-0.08"'))
        self.assertLess(publish.rindex("          check_public_target\n"), publish.index('gh release edit "$tag"'))
        self.assertIn("--prerelease=false", publish)
        self.assertIn("--latest=true", publish)
        self.assertIn('test "$latest_tag" = "$tag"', publish)
        self.assertIn('test "$final_tag_sha" = "$GITHUB_SHA"', publish)
        self.assertIn('assert len(local) == 16', publish)
        for test in ("test_contact_persistence.py", "test_paper_shutdown_v007.py",
                     "test_release_source_guard.py", "test_public_release_policy.py",
                     "test_device_settings.py", "test_headless_runtime.py"):
            self.assertIn("python tools/" + test, workflow)
        for profile in ("SmartUI_ProMicro_headless", "SmartUI_Paper_headless"):
            self.assertIn("- " + profile, workflow)
        self.assertIn("node --test tools/usb-helper/test_ui.js", workflow)

    def test_display_free_source_profiles_keep_the_same_board_wiring(self):
        source = (ROOT / "platformio.smartui-headless.ini").read_text(encoding="utf-8")
        self.assertEqual(source.count("-D SMARTUI_HEADLESS=1"), 6)
        self.assertNotIn("-U DISPLAY_CLASS", source)
        self.assertNotIn("PRIVATE_RELAY", source)
        for profile in NRF_ENVS + ESP_ENVS:
            self.assertIn("extends = env:" + profile, source)


if __name__ == "__main__":
    unittest.main()
