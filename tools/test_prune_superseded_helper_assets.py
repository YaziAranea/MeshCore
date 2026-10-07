"""Publication cleanup tests use fake metadata/files and never call GitHub."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from prune_superseded_helper_assets import cleanup_plan, NEW_NAMES, OLD_NAMES, TAG


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bundle = Path(self.tmp.name)
        self.release = {"tag_name": TAG, "draft": True, "assets": []}
        for i, name in enumerate(sorted(NEW_NAMES) + [f"asset-{n}" for n in range(17)]):
            data = name.encode()
            (self.bundle / name).write_bytes(data)
            self.release["assets"].append({"id": i + 1, "name": name, "state": "uploaded", "size": len(data), "digest": "sha256:" + hashlib.sha256(data).hexdigest()})
        self.release["assets"].extend({"id": 100+i, "name": name} for i, name in enumerate(sorted(OLD_NAMES)))

    def test_only_two_known_old_helpers_after_all_replacements_verified(self):
        planned = cleanup_plan(self.release, self.bundle, "a"*40)
        self.assertEqual({name for name, _ in planned}, OLD_NAMES)

    def test_rejects_unknown_extra_missing_duplicate_or_unverified_replacement(self):
        for mutate in (
            lambda r: r["assets"].append({"name": "user-backup.zip", "id": 900}),
            lambda r: r["assets"].pop(0),
            lambda r: r["assets"].append(r["assets"][0]),
            lambda r: r["assets"][0].update(digest="sha256:bad"),
            lambda r: r["assets"][0].update(state="starter"),
            lambda r: r["assets"][0].update(size=0),
            lambda r: r.update(draft=False),
            lambda r: r.update(tag_name="smartui-0.13"),
            lambda r: r["assets"][-1].update(id=-1),
        ):
            with self.subTest(mutate=mutate):
                release = copy.deepcopy(self.release)
                mutate(release)
                with self.assertRaises(ValueError):
                    cleanup_plan(release, self.bundle, "a"*40)

    def test_requires_explicit_expected_commit(self):
        for expected in ("", "x"*40, "a"*39):
            with self.assertRaises(ValueError):
                cleanup_plan(self.release, self.bundle, expected)

    def test_empty_replacement_rejected_before_any_cleanup(self):
        asset = self.release["assets"][0]
        (self.bundle / asset["name"]).write_bytes(b"")
        asset.update(size=0, digest="sha256:" + hashlib.sha256(b"").hexdigest())
        with self.assertRaises(ValueError):
            cleanup_plan(self.release, self.bundle, "a"*40)

    def test_rerun_without_obsolete_assets_is_noop(self):
        self.release["assets"] = self.release["assets"][:19]
        self.assertEqual(cleanup_plan(self.release, self.bundle, ""), [])


if __name__ == "__main__":
    unittest.main()
