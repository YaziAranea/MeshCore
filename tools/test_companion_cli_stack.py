#!/usr/bin/env python3
"""Regression checks for the ARM stack report guard (no cross-compiler needed)."""
import contextlib
import io
import unittest

import check_companion_cli_stack as stack


class ConsoleStackBudgetTest(unittest.TestCase):
    def records(self, wrapper=48, scalar=264, quick=208):
        sizes = {stack.CONSOLE_WRAPPER: wrapper,
                 stack.CONSOLE_BRANCHES[0]: scalar,
                 stack.CONSOLE_BRANCHES[1]: quick}
        return [(name, sizes.get(name, 0), "static") for name in stack.BUDGETS]

    def check(self, records):
        with contextlib.redirect_stdout(io.StringIO()):
            stack.check_budgets(records)

    def test_exact_nested_budget(self):
        self.check(self.records(wrapper=64, scalar=320, quick=320))

    def test_individually_valid_frames_can_overflow_together(self):
        for branch in ("scalar", "quick"):
            with self.subTest(branch=branch):
                with self.assertRaisesRegex(RuntimeError, "Nested CLI stack regression"):
                    self.check(self.records(wrapper=64, **{branch: 321}))

    def test_missing_helper_cannot_hide_inlining(self):
        for branch in stack.CONSOLE_BRANCHES:
            with self.subTest(branch=branch):
                records = [record for record in self.records() if record[0] != branch]
                with self.assertRaisesRegex(RuntimeError, "Missing production stack record"):
                    self.check(records)

    def test_largest_clone_frame_is_counted(self):
        records = self.records(wrapper=64)
        records.append((stack.CONSOLE_BRANCHES[0] + " [clone]", 321, "static"))
        with self.assertRaisesRegex(RuntimeError, "Nested CLI stack regression"):
            self.check(records)

    def test_unbounded_helper_rejected(self):
        records = self.records()
        records.append((stack.CONSOLE_BRANCHES[1] + " [clone]", 8, "dynamic"))
        with self.assertRaisesRegex(RuntimeError, "Unbounded/dynamic stack frame"):
            self.check(records)


if __name__ == "__main__":
    unittest.main()
