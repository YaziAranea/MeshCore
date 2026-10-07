#!/usr/bin/env python3
"""Guard the public release identity, complete board set and publication boundary."""

from pathlib import Path
import unittest
from unittest.mock import patch

from package_smartui_release import (
    ARCHIVE_NAME, ASSET_COUNT, BOARD_NAMES, DISTRIBUTION, ESP_ENVS, ESP_PAIRS,
    FIRMWARE_NAMES, NOTES_NAME, NRF_ENVS, PUBLICATION, TAG, VERSION,
    firmware_metadata, input_files, validate_release_notes,
)


ROOT = Path(__file__).resolve().parents[1]


class PublicReleasePolicyTests(unittest.TestCase):
    def test_one_public_version_for_seven_boards_and_eleven_images(self):
        self.assertEqual((VERSION, TAG), ("0.15", "smartui-0.15"))
        self.assertEqual(DISTRIBUTION, "public")
        self.assertEqual(PUBLICATION, {
            "draft": False, "prerelease": False, "make_latest": True,
            "repository": "YaziAranea/MeshCore", "visibility": "public",
        })
        self.assertEqual(len(NRF_ENVS) + len(ESP_ENVS), 7)
        self.assertEqual(len(set(FIRMWARE_NAMES)), 11)
        self.assertEqual(ASSET_COUNT, 19)
        from prune_superseded_helper_assets import TAG as cleanup_tag
        self.assertEqual(cleanup_tag, TAG)
        self.assertTrue(all("_UI_0.15" in name for name in FIRMWARE_NAMES))
        self.assertEqual(ARCHIVE_NAME, "SmartUI_0.15_all-boards.zip")
        self.assertEqual(NOTES_NAME, "RELEASE_NOTES_SmartUI_0.15_RU.md")
        self.assertIn("Smart UI 0.15", (ROOT / NOTES_NAME).read_text(encoding="utf-8"))
        validate_release_notes((ROOT / NOTES_NAME).read_text(encoding="utf-8"))
        build_info = (ROOT / "src/helpers/SmartUiBuildInfo.h").read_text(encoding="utf-8")
        self.assertIn('#define SMARTUI_VERSION "0.15"', build_info)

    def test_public_title_and_firmware_spelling_require_exact_version(self):
        for title in ("# Smart UI 0.15 — release", "# SmartUI 0.15"):
            validate_release_notes(title)
        for title in ("", "Smart UI 0.11", "SmartUI 0.150", "Smart UI 0.15.1",
                      "SmartUI 0.15 RELEASE_FINALIZATION"):
            with self.subTest(title=title), self.assertRaises(ValueError):
                validate_release_notes(title)

    def test_all_release_profiles_use_the_public_marker(self):
        for board in ("heltec_t096", "heltec_t114", "promicro", "heltec_v3",
                      "heltec_v4", "heltec_wireless_paper", "heltec_v4_r8"):
            with self.subTest(board=board):
                source = (ROOT / "variants" / board / "platformio.ini").read_text(encoding="utf-8")
                self.assertIn('SMARTUI_RELEASE_LABEL=\'"0.15"\'', source)
                self.assertIn("SmartUI 0.15", source)
                self.assertNotIn("SmartUI 0.06-test.2", source)
                self.assertNotIn("PRIVATE_RELAY", source)

    def test_publication_requires_explicit_public_target_and_all_checks(self):
        workflow = (ROOT / ".github/workflows/smartui-ci.yml").read_text(encoding="utf-8")
        publish = workflow.split("  publish-public-release:", 1)[1]
        for guard in ("github.repository == 'YaziAranea/MeshCore'",
                      "github.event.repository.private == false",
                      "github.event_name == 'workflow_dispatch'",
                      "inputs.publish_experimental",
                      "github.ref == 'refs/heads/smartui-0.15'",
                      "needs: release-gate"):
            self.assertIn(guard, publish)
        self.assertIn('.full_name == "YaziAranea/MeshCore" and .private == false and .visibility == "public"', publish)
        self.assertEqual(publish.count("          check_public_target\n"), 2)
        self.assertLess(publish.index("          check_public_target\n"), publish.index('tag="smartui-0.15"'))
        self.assertLess(publish.rindex("          check_public_target\n"), publish.index('gh release edit "$tag"'))
        self.assertIn("--prerelease=false", publish)
        self.assertIn("--latest=true", publish)
        self.assertIn('test "$latest_tag" = "$tag"', publish)
        self.assertIn('test "$final_tag_sha" = "$GITHUB_SHA"', publish)
        self.assertIn('assert len(local) == 19', publish)
        for test in ("test_contact_persistence.py", "test_paper_shutdown_v007.py",
                     "test_release_source_guard.py", "test_public_release_policy.py",
                     "test_device_settings.py", "test_adc_calibration_service.py", "test_headless_runtime.py",
                     "test_periodic_agc_ui.py", "test_periodic_agc.py",
                     "test_agc_maintenance.py", "test_smartui_cli.py", "test_fem_prefs.py",
                     "test_smartui_console_commands.py",
                     "test_smartui_developer_kit.py", "test_heltec_v4_r8_profile.py",
                     "test_prune_superseded_helper_assets.py"):
            self.assertIn("python tools/" + test, workflow)
        for profile in ("SmartUI_ProMicro_headless", "SmartUI_Paper_headless"):
            self.assertIn("- " + profile, workflow)
        self.assertIn("node --test tools/usb-helper/test_ui.js", workflow)
        self.assertIn('python tools/prune_superseded_helper_assets.py "$release_json"', publish)
        self.assertLess(publish.index('gh release upload "$tag"'), publish.index('python tools/prune_superseded_helper_assets.py'))
        self.assertLess(publish.index('python tools/prune_superseded_helper_assets.py'), publish.index('assert local.keys() == assets.keys()'))
        self.assertIn("python -B -m unittest discover -s tools/smartui-cli/tests -v", workflow)
        for archived in ("python tools/test_smartui_api.py", "python tools/test_smartui_sync_api.py",
                         "discover -s tools/smartui-api/tests"):
            self.assertNotIn(archived, workflow)

    def test_companion_cli_claims_v14_without_remote_execution_or_c9(self):
        mesh = (ROOT / "examples/companion_radio/MyMesh.cpp").read_text(encoding="utf-8")
        header = (ROOT / "examples/companion_radio/MyMesh.h").read_text(encoding="utf-8")
        self.assertIn("#define FIRMWARE_VER_CODE 14", header)
        self.assertIn('vars.append("smartui_cli", "1")', mesh)
        self.assertNotIn('vars.append("smartui_api"', mesh)
        self.assertNotIn("handleSmartUiApiFrame(", mesh)
        self.assertNotIn("onCLICommandRecv(", mesh)
        package = (ROOT / "tools/package_smartui_release.py").read_text(encoding="utf-8")
        self.assertIn("cli_version=1", package)
        self.assertIn("companion_protocol_version=14, local_only=True", package)

    def test_display_free_source_profiles_keep_the_same_board_wiring(self):
        source = (ROOT / "platformio.smartui-headless.ini").read_text(encoding="utf-8")
        self.assertEqual(source.count("-D SMARTUI_HEADLESS=1"), 7)
        self.assertNotIn("-U DISPLAY_CLASS", source)
        self.assertNotIn("PRIVATE_RELAY", source)
        for profile in NRF_ENVS + ESP_ENVS:
            self.assertIn("extends = env:" + profile, source)

    def test_esp_profile_order_and_r8_identity_are_unambiguous(self):
        expected = (
            ("Heltec_v3_companion_radio_ble_smartui", "Heltec_V3_UI_0.15", "Heltec V3 OLED"),
            ("heltec_v4_3_companion_radio_ble_femon_smartui", "Heltec_V4.3_UI_0.15", "Heltec V4.3 OLED FEM ON"),
            ("Heltec_Wireless_Paper_companion_radio_ble_smartui_full", "Paper_UI_0.15", "Wireless Paper FULL"),
            ("heltec_v4_r8_companion_radio_ble_femon_smartui", "Heltec_V4_R8_UI_0.15", "Heltec V4 R8 OLED FEM ON"),
        )
        self.assertEqual(len(ESP_ENVS), len(ESP_PAIRS))
        self.assertEqual(len(BOARD_NAMES), len(NRF_ENVS) + len(ESP_ENVS))
        self.assertEqual(tuple(zip(ESP_ENVS, (pair.stem for pair in ESP_PAIRS), BOARD_NAMES[3:])), expected)
        self.assertEqual(len({pair.marker for pair in ESP_PAIRS}), 4)
        workflow = (ROOT / ".github/workflows/smartui-ci.yml").read_text(encoding="utf-8")
        matrix = workflow.split("  build-esp32:", 1)[1].split("    steps:", 1)[0]
        self.assertEqual(matrix.count("          - board:"), 4)
        for environment, stem, board in expected:
            self.assertEqual(matrix.count("environment: " + environment + "\n"), 1)
            self.assertEqual(matrix.count("stem: " + stem + "\n"), 1)
            for suffix in ("-merged.bin", "-update.bin"):
                metadata = firmware_metadata(stem + suffix, "0" * 40)
                self.assertEqual((metadata["environment"], metadata["board"]), (environment, board))

    def test_incomplete_environment_mapping_cannot_silently_truncate_zip(self):
        with patch("package_smartui_release.ESP_ENVS", ESP_ENVS[:-1]):
            with self.assertRaisesRegex(ValueError, "release profile mappings"):
                input_files(Path("unused-build-directory"))


if __name__ == "__main__":
    unittest.main()
