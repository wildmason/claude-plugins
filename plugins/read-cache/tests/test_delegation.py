"""Tests for the two delegation harnesses.

These are measurement instruments used to accept or reject a design, so the
risk is a confidently wrong number. The rules that decide whether bytes count
as delegable are what get exercised here.
"""
import collections
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import investigation as I  # noqa: E402
import replay_shunt as S  # noqa: E402
import subagent_economics as SE  # noqa: E402


# ---------------------------------------------------------------------------
# shunt's own rule
# ---------------------------------------------------------------------------
class TestShuntRule(unittest.TestCase):
    def test_lines_come_from_the_observed_span_not_a_count(self):
        self.assertEqual(S.span_lines((500, 799)), 300)

    def test_missing_span_is_zero_lines(self):
        self.assertEqual(S.span_lines(None), 0)

    def test_threshold_is_inclusive(self):
        self.assertTrue(S.is_delegable(350, 350))
        self.assertFalse(S.is_delegable(349, 350))

    def test_a_later_edit_means_the_summary_was_not_enough(self):
        edits = {"/a.ts": [40]}
        self.assertEqual(S.classify(10, "/a.ts", edits), "needed-exact")

    def test_an_earlier_edit_does_not_disqualify(self):
        # The edit happened before this read, so it says nothing about whether
        # a summary would have sufficed afterwards.
        edits = {"/a.ts": [5]}
        self.assertEqual(S.classify(10, "/a.ts", edits), "summary-sufficed")

    def test_an_edit_to_a_different_file_does_not_disqualify(self):
        self.assertEqual(S.classify(10, "/a.ts", {"/b.ts": [40]}), "summary-sufficed")

    def test_savings_split_into_removed_and_summary(self):
        removed, kept = S.savings(1000, 0.9)
        self.assertEqual((removed, kept), (900, 100))
        self.assertEqual(removed + kept, 1000)

    def test_zero_compression_saves_nothing(self):
        removed, kept = S.savings(1000, 0.0)
        self.assertEqual(removed, 0)
        self.assertEqual(kept, 1000)


# ---------------------------------------------------------------------------
# the investigation steelman
# ---------------------------------------------------------------------------
def burst(lane="main", start=10, items=()):
    b = I.Burst(lane, start)
    for tool, nbytes, path in items:
        b.add(tool, nbytes, path)
    return b


class TestBurst(unittest.TestCase):
    def test_bytes_are_attributed_per_file(self):
        b = burst(items=[("OBSERVE", 100, "/a.ts"), ("OBSERVE", 50, "/a.ts"),
                         ("OBSERVE", 70, "/b.ts")])
        self.assertEqual(b.by_path["/a.ts"], 150)
        self.assertEqual(b.by_path["/b.ts"], 70)
        self.assertEqual(b.nbytes, 220)

    def test_search_output_has_no_owning_file(self):
        b = burst(items=[("OBSERVE", 90, None)])
        self.assertEqual(b.anon_bytes, 90)
        self.assertEqual(b.paths, set())

    def test_label_lists_files_and_counts_the_overflow(self):
        b = burst(items=[("OBSERVE", 1, "/x/%d.ts" % i) for i in range(5)])
        self.assertIn("+2", b.label())

    def test_label_of_a_pure_search_burst(self):
        self.assertEqual(burst(items=[("OBSERVE", 5, None)]).label(), "(search only)")


class TestStrictRule(unittest.TestCase):
    def test_untouched_burst_is_delegable(self):
        b = burst(items=[("OBSERVE", 100, "/a.ts")])
        self.assertTrue(I.burst_is_delegable(b, {}))

    def test_one_later_edit_disqualifies_the_whole_burst(self):
        b = burst(items=[("OBSERVE", 100, "/a.ts"), ("OBSERVE", 100, "/b.ts")])
        self.assertFalse(I.burst_is_delegable(b, {"/b.ts": [99]}))

    def test_an_edit_before_the_burst_does_not_disqualify(self):
        b = burst(start=50, items=[("OBSERVE", 100, "/a.ts")])
        self.assertTrue(I.burst_is_delegable(b, {"/a.ts": [10]}))


class TestPerFileAttribution(unittest.TestCase):
    """The fairer rule: keep the untouched files inside a mixed burst."""

    def test_only_the_edited_file_is_excluded(self):
        b = burst(items=[("OBSERVE", 100, "/a.ts"), ("OBSERVE", 300, "/b.ts")])
        self.assertEqual(I.delegable_bytes(b, {"/a.ts": [99]}), 300)

    def test_search_bytes_always_count(self):
        # A grep result is not line-addressable, so it can never be the thing
        # an edit needed.
        b = burst(items=[("OBSERVE", 100, "/a.ts"), ("OBSERVE", 40, None)])
        self.assertEqual(I.delegable_bytes(b, {"/a.ts": [99]}), 40)

    def test_nothing_edited_means_everything_counts(self):
        b = burst(items=[("OBSERVE", 100, "/a.ts"), ("OBSERVE", 300, "/b.ts")])
        self.assertEqual(I.delegable_bytes(b, {}), 400)

    def test_the_fair_rule_is_never_stricter_than_the_all_or_nothing_rule(self):
        b = burst(items=[("OBSERVE", 100, "/a.ts"), ("OBSERVE", 300, "/b.ts")])
        for edits in ({}, {"/a.ts": [99]}, {"/a.ts": [99], "/b.ts": [99]}):
            strict = b.nbytes if I.burst_is_delegable(b, edits) else 0
            self.assertGreaterEqual(I.delegable_bytes(b, edits), strict)


class TestNetSaving(unittest.TestCase):
    def test_each_delegation_pays_for_its_answer(self):
        self.assertEqual(I.net_saving(10000, 2, 0.9, answer_chars=1000), 7000)

    def test_a_burst_smaller_than_its_answer_saves_nothing(self):
        self.assertEqual(I.net_saving(500, 1, 0.9, answer_chars=1500), 0)

    def test_lower_compression_saves_less(self):
        a = I.net_saving(100000, 5, 0.9, answer_chars=1500)
        b = I.net_saving(100000, 5, 0.5, answer_chars=1500)
        self.assertGreater(a, b)


class TestSizeBucket(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(I.size_bucket(4), "3-4 calls")
        self.assertEqual(I.size_bucket(5), "5-9 calls")
        self.assertEqual(I.size_bucket(19), "10-19 calls")
        self.assertEqual(I.size_bucket(20), "20+ calls")


class TestClassifier(unittest.TestCase):
    """Which tool results start, extend or break an investigation."""

    def setUp(self):
        self.ir = I.InvestigationReplay()

    def kind(self, tool, ti, text="x" * 40):
        return self.ir._classify(tool, ti, text, "/repo")[0]

    def test_read_is_an_observation(self):
        self.assertEqual(self.kind("Read", {"file_path": "/repo/a.ts"}), "OBSERVE")

    def test_grep_is_an_observation(self):
        self.assertEqual(self.kind("Grep", {"pattern": "foo"}), "OBSERVE")

    def test_a_shell_file_read_is_an_observation(self):
        self.assertEqual(self.kind("Bash", {"command": "cat /repo/a.ts"}), "OBSERVE")

    def test_a_build_breaks_the_investigation(self):
        self.assertEqual(self.kind("Bash", {"command": "cargo build"}), "OTHER")

    def test_an_edit_breaks_the_investigation(self):
        self.assertEqual(self.kind("Edit", {"file_path": "/repo/a.ts"}), "MUTATE")

    def test_an_image_read_is_not_an_observation_of_text(self):
        self.assertEqual(self.kind("Read", {"file_path": "/repo/shot.png"}), "OTHER")


# ---------------------------------------------------------------------------
# subagent economics
# ---------------------------------------------------------------------------


class TestRealizedCompression(unittest.TestCase):
    def test_a_small_report_from_a_big_read_is_high_compression(self):
        self.assertAlmostEqual(SE.realized_compression(100000, 1000), 0.99, places=3)

    def test_returning_everything_is_no_compression(self):
        self.assertEqual(SE.realized_compression(500, 500), 0.0)

    def test_a_report_larger_than_the_reading_never_goes_negative(self):
        self.assertEqual(SE.realized_compression(100, 400), 0.0)

    def test_a_lane_that_read_nothing_has_no_ratio(self):
        self.assertIsNone(SE.realized_compression(0, 120))

    def test_a_silent_lane_must_not_be_read_as_perfect(self):
        # Guards the bug this measurement actually had: a lane that reported
        # through another channel looks like 100% compression and inflates
        # the aggregate. The harness excludes these; this pins the arithmetic
        # that made the inflation possible.
        self.assertEqual(SE.realized_compression(100000, 0), 1.0)


class TestPriceRatio(unittest.TestCase):
    def test_a_cheaper_worker_yields_a_ratio_above_one(self):
        r = SE.price_ratio(worker_in=0.8, worker_out=4.0, frontier_in=5.0, frontier_out=25.0)
        self.assertGreater(r, 1.0)

    def test_identical_pricing_is_parity(self):
        self.assertAlmostEqual(
            SE.price_ratio(5.0, 25.0, 5.0, 25.0), 1.0, places=6)

    def test_input_price_dominates_because_investigation_is_read_heavy(self):
        # Same output price, worker input 10x cheaper -> big ratio.
        cheap_in = SE.price_ratio(0.5, 25.0, 5.0, 25.0)
        cheap_out = SE.price_ratio(5.0, 2.5, 5.0, 25.0)
        self.assertGreater(cheap_in, cheap_out)

    def test_a_free_worker_has_no_finite_ratio(self):
        self.assertIsNone(SE.price_ratio(0.0, 0.0, 5.0, 25.0))


class TestAssistantText(unittest.TestCase):
    def test_takes_the_text_block_and_nothing_else(self):
        # A subagent record carries thinking and tool_use alongside its report.
        # Counting thinking as the returned report would understate compression.
        rec = {"message": {"content": [
            {"type": "thinking", "text": "internal reasoning"},
            {"type": "text", "text": "foo is called from a.ts and b.ts"},
            {"type": "tool_use", "id": "1", "name": "Read", "input": {}}]}}
        self.assertEqual(SE.assistant_text(rec), "foo is called from a.ts and b.ts")

    def test_a_record_with_no_content_is_empty(self):
        self.assertEqual(SE.assistant_text({"message": {}}), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
