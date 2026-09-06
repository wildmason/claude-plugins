"""Tests for the read-cache decision core.

Every test here exercises logic that can produce a WRONG decision: a false
DENY (the agent loses content it does not actually have) or a missed DENY
(duplicate content re-enters the context). Nothing asserts a hardcoded
constant back at itself.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import readcache_core as C


# --------------------------------------------------------------------------
# span arithmetic - the guard against false denies on partial reads
# --------------------------------------------------------------------------
class TestSpans(unittest.TestCase):
    def test_merge_adjacent_spans_into_one(self):
        self.assertEqual(C.merge_span([(1, 50)], (51, 100)), [(1, 100)])

    def test_merge_overlapping_spans(self):
        self.assertEqual(C.merge_span([(1, 50), (200, 300)], (40, 210)), [(1, 300)])

    def test_merge_keeps_disjoint_spans_separate(self):
        self.assertEqual(C.merge_span([(1, 50)], (80, 120)), [(1, 50), (80, 120)])

    def test_merge_is_order_independent(self):
        a = C.merge_span(C.merge_span([], (80, 120)), (1, 50))
        b = C.merge_span(C.merge_span([], (1, 50)), (80, 120))
        self.assertEqual(a, b)

    def test_covers_true_for_subrange(self):
        self.assertTrue(C.covers([(1, 200)], (50, 60)))

    def test_covers_false_when_span_extends_past_end(self):
        self.assertFalse(C.covers([(1, 200)], (150, 260)))

    def test_covers_false_when_span_starts_before(self):
        self.assertFalse(C.covers([(50, 200)], (1, 60)))

    def test_covers_false_across_a_gap(self):
        # 51..79 was never read; asking for 40..90 must be allowed through.
        self.assertFalse(C.covers([(1, 50), (80, 120)], (40, 90)))

    def test_covers_true_when_gap_was_later_filled(self):
        spans = C.merge_span([(1, 50), (80, 120)], (51, 79))
        self.assertTrue(C.covers(spans, (40, 90)))


# --------------------------------------------------------------------------
# Read tool input -> span
# --------------------------------------------------------------------------
class TestReadSpan(unittest.TestCase):
    def test_bare_read_of_short_file_covers_whole_file(self):
        self.assertEqual(C.read_span({}, line_count=120), (1, 120))

    def test_bare_read_of_long_file_is_capped_at_the_tool_limit(self):
        # A Read with no limit stops at DEFAULT_READ_LIMIT lines. Claiming the
        # whole 9000-line file is in context would cause a false DENY later.
        self.assertEqual(C.read_span({}, line_count=9000), (1, C.DEFAULT_READ_LIMIT))

    def test_offset_and_limit_are_honoured(self):
        self.assertEqual(C.read_span({"offset": 100, "limit": 50}, line_count=9000), (100, 149))

    def test_limit_is_clamped_to_end_of_file(self):
        self.assertEqual(C.read_span({"offset": 100, "limit": 500}, line_count=180), (100, 180))

    def test_offset_zero_is_treated_as_line_one(self):
        self.assertEqual(C.read_span({"offset": 0, "limit": 10}, line_count=900), (1, 10))

    def test_offset_past_end_of_file_yields_no_span(self):
        self.assertIsNone(C.read_span({"offset": 500}, line_count=100))

    def test_unknown_line_count_still_produces_a_span(self):
        self.assertEqual(C.read_span({"offset": 10, "limit": 5}, line_count=None), (10, 14))


# --------------------------------------------------------------------------
# Bash command parsing - conservative by design
# --------------------------------------------------------------------------
class TestBashParsing(unittest.TestCase):
    def parse(self, cmd):
        return C.parse_bash_reads(cmd)

    def test_plain_cat_is_a_full_read(self):
        self.assertEqual(self.parse("cat src/main.rs"), [("src/main.rs", ("full",))])

    def test_sed_range_is_a_line_span(self):
        self.assertEqual(self.parse("sed -n '20,80p' a.ts"), [("a.ts", ("lines", 20, 80))])

    def test_sed_single_line(self):
        self.assertEqual(self.parse("sed -n '42p' a.ts"), [("a.ts", ("lines", 42, 42))])

    def test_head_with_dash_n(self):
        self.assertEqual(self.parse("head -n 30 a.ts"), [("a.ts", ("head", 30))])

    def test_head_with_bare_number_flag(self):
        self.assertEqual(self.parse("head -30 a.ts"), [("a.ts", ("head", 30))])

    def test_tail_needs_the_file_length_to_resolve(self):
        self.assertEqual(self.parse("tail -n 5 a.ts"), [("a.ts", ("tail", 5))])

    def test_cd_prefix_rebases_the_relative_path(self):
        self.assertEqual(self.parse("cd /repo/ui && cat src/app.ts"),
                         [("/repo/ui/src/app.ts", ("full",))])

    def test_downstream_pipeline_stages_are_not_file_reads(self):
        # `head` here filters cargo's output; it reads no file.
        self.assertEqual(self.parse("cargo test 2>&1 | head -50"), [])

    def test_first_stage_of_a_pipeline_is_still_a_file_read(self):
        self.assertEqual(self.parse("cat a.ts | grep foo"), [("a.ts", ("full",))])

    def test_redirection_disables_parsing(self):
        # `cat a.ts > b.ts` writes; treating it as a read risks a stale cache.
        self.assertEqual(self.parse("cat a.ts > b.ts"), [])

    def test_command_substitution_disables_parsing(self):
        self.assertEqual(self.parse("cat $(ls)"), [])

    def test_backtick_substitution_disables_parsing(self):
        self.assertEqual(self.parse("cat `ls`"), [])

    def test_glob_operand_is_skipped(self):
        self.assertEqual(self.parse("cat src/*.ts"), [])

    def test_multiple_operands_are_skipped(self):
        self.assertEqual(self.parse("cat a.ts b.ts"), [])

    def test_tail_follow_is_not_a_bounded_read(self):
        self.assertEqual(self.parse("tail -f server.log"), [])

    def test_quoted_path_with_spaces(self):
        self.assertEqual(self.parse('cat "my file.ts"'), [("my file.ts", ("full",))])

    def test_unrelated_command_yields_nothing(self):
        self.assertEqual(self.parse("cargo build --release"), [])

    def test_heredoc_body_is_not_parsed_as_commands(self):
        # A heredoc that happens to contain `cat x.ts` is data, not a read.
        self.assertEqual(self.parse("python - <<'EOF'\ncat a.ts\nEOF"), [])

    def test_multiple_reads_in_one_chain(self):
        self.assertEqual(self.parse("cat a.ts && sed -n '1,5p' b.ts"),
                         [("a.ts", ("full",)), ("b.ts", ("lines", 1, 5))])

    def test_sed_with_extra_script_forms_is_skipped(self):
        # Substitution, not a range read.
        self.assertEqual(self.parse("sed -n 's/a/b/p' a.ts"), [])

    def test_sed_in_place_is_a_write_not_a_read(self):
        self.assertEqual(self.parse("sed -i '1,5d' a.ts"), [])


class TestResolveSpec(unittest.TestCase):
    def test_full_resolves_to_whole_file(self):
        self.assertEqual(C.resolve_spec(("full",), 400), (1, 400))

    def test_head_is_clamped_to_file_length(self):
        self.assertEqual(C.resolve_spec(("head", 900), 120), (1, 120))

    def test_tail_counts_back_from_the_end(self):
        self.assertEqual(C.resolve_spec(("tail", 10), 100), (91, 100))

    def test_tail_larger_than_file_is_the_whole_file(self):
        self.assertEqual(C.resolve_spec(("tail", 500), 100), (1, 100))

    def test_lines_beyond_end_are_clamped(self):
        self.assertEqual(C.resolve_spec(("lines", 90, 400), 120), (90, 120))

    def test_lines_entirely_past_end_yield_no_span(self):
        self.assertIsNone(C.resolve_spec(("lines", 300, 400), 120))

    def test_unknown_length_leaves_full_unresolvable(self):
        self.assertIsNone(C.resolve_spec(("full",), None))


# --------------------------------------------------------------------------
# the decision itself
# --------------------------------------------------------------------------
FP = [111, 2048]


def entry(spans, fp=None, denied=None):
    return {"fp": list(fp or FP), "spans": [list(s) for s in spans],
            "denied": denied or {}, "ts": "2026-09-06T00:00:00"}


class TestEvaluate(unittest.TestCase):
    def test_unseen_file_is_allowed(self):
        d, _, _ = C.evaluate(None, FP, (1, 100))
        self.assertEqual(d, "allow")

    def test_repeat_of_covered_span_is_denied(self):
        d, reason, _ = C.evaluate(entry([(1, 200)]), FP, (1, 200))
        self.assertEqual(d, "deny")
        self.assertIn("unchanged", reason.lower())

    def test_subrange_of_a_covered_span_is_denied(self):
        d, _, _ = C.evaluate(entry([(1, 200)]), FP, (30, 60))
        self.assertEqual(d, "deny")

    def test_changed_mtime_forces_a_reread(self):
        d, reason, _ = C.evaluate(entry([(1, 200)]), [222, 2048], (1, 200))
        self.assertEqual(d, "allow")
        self.assertIn("changed", reason.lower())

    def test_changed_size_forces_a_reread(self):
        d, _, _ = C.evaluate(entry([(1, 200)]), [111, 4096], (1, 200))
        self.assertEqual(d, "allow")

    def test_uncovered_range_is_allowed(self):
        d, _, _ = C.evaluate(entry([(1, 200)]), FP, (300, 400))
        self.assertEqual(d, "allow")

    def test_partially_covered_range_is_allowed(self):
        d, _, _ = C.evaluate(entry([(1, 200)]), FP, (150, 400))
        self.assertEqual(d, "allow")

    def test_insisting_after_a_deny_gets_through(self):
        # Escape hatch: the cache must never be able to hard-block the agent.
        e = entry([(1, 200)])
        d1, _, e = C.evaluate(e, FP, (1, 200))
        self.assertEqual(d1, "deny")
        d2, reason, e = C.evaluate(e, FP, (1, 200))
        self.assertEqual(d2, "allow")
        self.assertIn("insist", reason.lower())

    def test_insist_counter_resets_after_it_is_honoured(self):
        e = entry([(1, 200)])
        _, _, e = C.evaluate(e, FP, (1, 200))     # deny
        _, _, e = C.evaluate(e, FP, (1, 200))     # allow (insisted)
        d, _, _ = C.evaluate(e, FP, (1, 200))     # back to denying
        self.assertEqual(d, "deny")

    def test_insist_counter_is_per_span_not_global(self):
        e = entry([(1, 200)])
        _, _, e = C.evaluate(e, FP, (1, 50))      # deny span A
        d, _, _ = C.evaluate(e, FP, (60, 90))     # span B must still deny
        self.assertEqual(d, "deny")

    def test_changed_file_clears_stale_insist_counters(self):
        e = entry([(1, 200)], denied={"1-200": 1})
        _, _, e2 = C.evaluate(e, [999, 2048], (1, 200))
        self.assertEqual(e2["denied"], {})


class TestRecord(unittest.TestCase):
    def test_recording_a_new_file_creates_an_entry(self):
        cache = {}
        C.record(cache, "a.ts", FP, (1, 100), "T")
        self.assertEqual(cache["a.ts"]["spans"], [[1, 100]])

    def test_recording_merges_into_existing_spans(self):
        cache = {}
        C.record(cache, "a.ts", FP, (1, 100), "T")
        C.record(cache, "a.ts", FP, (101, 150), "T")
        self.assertEqual(cache["a.ts"]["spans"], [[1, 150]])

    def test_recording_after_a_change_discards_the_old_spans(self):
        cache = {}
        C.record(cache, "a.ts", FP, (1, 100), "T")
        C.record(cache, "a.ts", [999, 1], (5, 20), "T")
        self.assertEqual(cache["a.ts"]["spans"], [[5, 20]])
        self.assertEqual(cache["a.ts"]["fp"], [999, 1])

    def test_cache_is_bounded_and_evicts_oldest_first(self):
        cache = {}
        for i in range(C.MAX_ENTRIES + 25):
            C.record(cache, "f%d.ts" % i, FP, (1, 10), "T%05d" % i)
        self.assertLessEqual(len(cache), C.MAX_ENTRIES)
        self.assertIn("f%d.ts" % (C.MAX_ENTRIES + 24), cache)   # newest survives
        self.assertNotIn("f0.ts", cache)                        # oldest evicted


class TestSkipRules(unittest.TestCase):
    def test_images_and_pdfs_are_never_cached(self):
        for p in ("shot.png", "a.JPG", "doc.pdf", "nb.ipynb", "x.webp"):
            self.assertTrue(C.is_opaque(p), p)

    def test_source_files_are_cached(self):
        for p in ("a.rs", "b.ts", "c.md", "d.html", "e.go"):
            self.assertFalse(C.is_opaque(p), p)

    def test_truncated_bash_output_must_not_be_recorded(self):
        self.assertTrue(C.looks_truncated("x" * 40 + "\n<truncated>"))
        self.assertTrue(C.looks_truncated("y" * (C.BASH_TRUNCATION_CHARS + 10)))
        self.assertFalse(C.looks_truncated("short and complete"))

    def test_error_response_must_not_be_recorded(self):
        self.assertFalse(C.response_ok({"is_error": True}))
        self.assertFalse(C.response_ok("Error: ENOENT: no such file or directory, open 'x'"))
        self.assertTrue(C.response_ok("     1\tfn main() {}"))


class TestNormPath(unittest.TestCase):
    def test_relative_paths_resolve_against_cwd(self):
        self.assertEqual(C.norm_path("src/a.ts", "/repo"), C.norm_path("/repo/src/a.ts", None))

    def test_separators_are_normalised(self):
        self.assertEqual(C.norm_path("C:\\repo\\src\\a.ts", None),
                         C.norm_path("C:/repo/src/a.ts", None))

    def test_dot_segments_collapse(self):
        self.assertEqual(C.norm_path("/repo/ui/../src/a.ts", None),
                         C.norm_path("/repo/src/a.ts", None))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestOnlyReads(unittest.TestCase):
    """A Bash command may only be denied when reading is ALL it does.
    Denying `cat a.ts && cargo build` would cancel the build."""

    def test_single_read_is_only_reads(self):
        self.assertTrue(C.command_is_only_reads("cat a.ts"))

    def test_cd_prefix_is_allowed(self):
        self.assertTrue(C.command_is_only_reads("cd /repo && sed -n '1,20p' a.ts"))

    def test_two_reads_are_only_reads(self):
        self.assertTrue(C.command_is_only_reads("cat a.ts && head -5 b.ts"))

    def test_read_chained_with_a_build_is_not(self):
        self.assertFalse(C.command_is_only_reads("cat a.ts && cargo build"))

    def test_read_piped_into_a_filter_is_not(self):
        # The grep output is not the file; denying would lose the filtered result.
        self.assertFalse(C.command_is_only_reads("cat a.ts | grep foo"))

    def test_echo_alongside_a_read_is_not(self):
        self.assertFalse(C.command_is_only_reads("echo hi; cat a.ts"))

    def test_empty_command_is_not(self):
        self.assertFalse(C.command_is_only_reads(""))

    def test_unparseable_read_is_not(self):
        self.assertFalse(C.command_is_only_reads("cat a.ts b.ts"))


class TestSpanBytes(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.d = tempfile.mkdtemp()
        self.f = os.path.join(self.d, "sample.txt")
        with open(self.f, "w", encoding="utf-8", newline="\n") as fh:
            for i in range(1, 11):
                fh.write("line%02d\n" % i)
        self.per_line = len("line01\n")   # 7 bytes incl newline

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d, ignore_errors=True)

    def test_counts_only_the_requested_lines(self):
        self.assertEqual(C.span_bytes(self.f, (1, 3)), 3 * self.per_line)

    def test_counts_a_middle_span(self):
        self.assertEqual(C.span_bytes(self.f, (4, 6)), 3 * self.per_line)

    def test_span_past_end_counts_what_exists(self):
        self.assertEqual(C.span_bytes(self.f, (9, 99)), 2 * self.per_line)

    def test_missing_file_is_zero_not_an_error(self):
        self.assertEqual(C.span_bytes(os.path.join(self.d, "nope.txt"), (1, 5)), 0)
