"""Tests for the transcript replay harness.

The replay is a measurement instrument, so the risk is a number that is
confidently wrong: mis-parsed spans, leaking one context window's reads into
another, or ignoring the events that invalidate a cached read.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import replay as R  # noqa: E402


class TestNumberedSpan(unittest.TestCase):
    def test_parses_a_cat_n_style_result(self):
        self.assertEqual(R.numbered_span("     1\tfn main() {\n     2\t}\n"), (1, 2))

    def test_uses_the_real_offsets_not_a_count(self):
        # An offset read starts at line 500; a naive line count would say 1-3.
        self.assertEqual(R.numbered_span("   500\ta\n   501\tb\n   502\tc\n"), (500, 502))

    def test_ignores_unnumbered_trailing_notes(self):
        text = "     7\tuse std;\n     8\t\n<system-reminder>be careful</system-reminder>"
        self.assertEqual(R.numbered_span(text), (7, 8))

    def test_plain_output_has_no_span(self):
        self.assertIsNone(R.numbered_span("just some shell output\n"))

    def test_non_string_is_safe(self):
        self.assertIsNone(R.numbered_span(None))


class TestLane(unittest.TestCase):
    def test_main_thread_records(self):
        self.assertEqual(R.lane_of({"isSidechain": False}), "main")

    def test_each_subagent_gets_its_own_lane(self):
        a = R.lane_of({"isSidechain": True, "agentId": "a1"})
        b = R.lane_of({"isSidechain": True, "agentId": "a2"})
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, "main")

    def test_falls_back_to_the_spawning_tool_id(self):
        got = R.lane_of({"isSidechain": True, "sourceToolAssistantUUID": "t9"})
        self.assertIn("t9", got)


class TestResultText(unittest.TestCase):
    def test_joins_content_blocks(self):
        self.assertEqual(R.result_text([{"type": "text", "text": "a"},
                                        {"type": "text", "text": "b"}]), "ab")

    def test_passes_a_plain_string_through(self):
        self.assertEqual(R.result_text("x"), "x")


class TestCompactBoundary(unittest.TestCase):
    def test_recognises_the_boundary_record(self):
        self.assertTrue(R.is_compact_boundary({"type": "system", "subtype": "compact_boundary"}))

    def test_other_system_records_are_not_boundaries(self):
        self.assertFalse(R.is_compact_boundary({"type": "system", "subtype": "turn_duration"}))


# ---------------------------------------------------------------------------
# end-to-end over a synthetic transcript
# ---------------------------------------------------------------------------
def asst(tid, name, tool_input, sidechain=False, agent=None):
    r = {"type": "assistant", "isSidechain": sidechain,
         "message": {"content": [{"type": "tool_use", "id": tid,
                                  "name": name, "input": tool_input}]}}
    if agent:
        r["agentId"] = agent
    return r


def res(tid, text, sidechain=False, agent=None, cwd="/repo"):
    r = {"type": "user", "cwd": cwd, "isSidechain": sidechain,
         "message": {"content": [{"type": "tool_result", "tool_use_id": tid,
                                  "content": text}]}}
    if agent:
        r["agentId"] = agent
    return r


BODY = "".join("%6d\tline %d\n" % (i, i) for i in range(1, 21))


class TestReplayEndToEnd(unittest.TestCase):
    def run_records(self, records, allow_insist=True):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                for r in records:
                    fh.write(json.dumps(r) + "\n")
            rp = R.Replay(allow_insist=allow_insist)
            rp.run_file(path, "proj")
            return rp
        finally:
            os.remove(path)

    def test_a_single_read_saves_nothing(self):
        rp = self.run_records([asst("1", "Read", {"file_path": "/repo/a.ts"}), res("1", BODY)])
        self.assertEqual(rp.denies, 0)
        self.assertEqual(rp.reads, 1)

    def test_a_repeat_read_is_counted_as_a_saving(self):
        rp = self.run_records([
            asst("1", "Read", {"file_path": "/repo/a.ts"}), res("1", BODY),
            asst("2", "Read", {"file_path": "/repo/a.ts"}), res("2", BODY),
        ])
        self.assertEqual(rp.denies, 1)
        self.assertEqual(rp.saved, len(BODY))

    def test_an_edit_between_reads_cancels_the_saving(self):
        rp = self.run_records([
            asst("1", "Read", {"file_path": "/repo/a.ts"}), res("1", BODY),
            asst("2", "Edit", {"file_path": "/repo/a.ts"}), res("2", "ok"),
            asst("3", "Read", {"file_path": "/repo/a.ts"}), res("3", BODY),
        ])
        self.assertEqual(rp.denies, 0)

    def test_a_subagent_reading_the_same_file_is_not_a_duplicate(self):
        rp = self.run_records([
            asst("1", "Read", {"file_path": "/repo/a.ts"}), res("1", BODY),
            asst("2", "Read", {"file_path": "/repo/a.ts"}, sidechain=True, agent="a1"),
            res("2", BODY, sidechain=True, agent="a1"),
        ])
        self.assertEqual(rp.denies, 0)

    def test_compaction_resets_the_saving(self):
        rp = self.run_records([
            asst("1", "Read", {"file_path": "/repo/a.ts"}), res("1", BODY),
            {"type": "system", "subtype": "compact_boundary"},
            asst("2", "Read", {"file_path": "/repo/a.ts"}), res("2", BODY),
        ])
        self.assertEqual(rp.denies, 0)
        self.assertEqual(rp.compactions, 1)

    def test_disjoint_offset_reads_are_not_duplicates(self):
        top = "".join("%6d\tline %d\n" % (i, i) for i in range(1, 11))
        bottom = "".join("%6d\tline %d\n" % (i, i) for i in range(200, 211))
        rp = self.run_records([
            asst("1", "Read", {"file_path": "/repo/a.ts", "offset": 1, "limit": 10}), res("1", top),
            asst("2", "Read", {"file_path": "/repo/a.ts", "offset": 200, "limit": 11}),
            res("2", bottom),
        ])
        self.assertEqual(rp.denies, 0)

    def test_insist_hatch_lets_every_other_repeat_through(self):
        seq = [asst("1", "Read", {"file_path": "/repo/a.ts"}), res("1", BODY)]
        for i in range(2, 6):
            seq += [asst(str(i), "Read", {"file_path": "/repo/a.ts"}), res(str(i), BODY)]
        with_hatch = self.run_records(seq, allow_insist=True)
        without = self.run_records(seq, allow_insist=False)
        self.assertEqual(without.denies, 4)          # every repeat blocked
        self.assertLess(with_hatch.denies, without.denies)
        self.assertGreater(with_hatch.denies, 0)

    def test_repeat_bash_cat_is_counted(self):
        out = "line 1\nline 2\n"
        rp = self.run_records([
            asst("1", "Bash", {"command": "cat /repo/a.ts"}), res("1", out),
            asst("2", "Bash", {"command": "cat /repo/a.ts"}), res("2", out),
        ])
        self.assertEqual(rp.denies, 1)

    def test_bash_read_chained_with_a_build_is_never_counted(self):
        out = "line 1\nline 2\n"
        rp = self.run_records([
            asst("1", "Bash", {"command": "cat /repo/a.ts"}), res("1", out),
            asst("2", "Bash", {"command": "cat /repo/a.ts && cargo build"}), res("2", out),
        ])
        self.assertEqual(rp.denies, 0)

    def test_failed_reads_are_ignored(self):
        rp = self.run_records([
            asst("1", "Read", {"file_path": "/repo/a.ts"}),
            res("1", "Error: ENOENT: no such file or directory"),
            asst("2", "Read", {"file_path": "/repo/a.ts"}), res("2", BODY),
        ])
        self.assertEqual(rp.denies, 0)

    def test_savings_are_attributed_to_the_file_and_project(self):
        rp = self.run_records([
            asst("1", "Read", {"file_path": "/repo/a.ts"}), res("1", BODY),
            asst("2", "Read", {"file_path": "/repo/a.ts"}), res("2", BODY),
        ])
        self.assertEqual(rp.by_file["a.ts"], len(BODY))
        self.assertEqual(rp.by_project["proj"], len(BODY))
        self.assertEqual(rp.by_tool["Read"], len(BODY))


if __name__ == "__main__":
    unittest.main(verbosity=2)
