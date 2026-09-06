"""End-to-end tests for the hook shims.

These drive the real scripts over stdin/stdout exactly as Claude Code does,
against real files on disk. They cover the failure that actually matters:
a DENY issued when the content is NOT already in context.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
PRE = os.path.join(SCRIPTS, "pre_tool_use.py")
POST = os.path.join(SCRIPTS, "post_tool_use.py")
COMPACT = os.path.join(SCRIPTS, "on_compact.py")

SESSION = "sess-test-1"


class HookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache = os.path.join(self.tmp, "cache")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self.f = os.path.join(self.repo, "sample.ts")
        self.write_file(300)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_file(self, n, tag="a"):
        with open(self.f, "w", encoding="utf-8", newline="\n") as fh:
            for i in range(1, n + 1):
                fh.write("const %s%d = %d;\n" % (tag, i, i))

    def run_hook(self, script, payload, env_extra=None):
        env = dict(os.environ)
        env["READCACHE_DIR"] = self.cache
        env.pop("READCACHE_DISABLE", None)
        env.update(env_extra or {})
        p = subprocess.run([sys.executable, script], input=json.dumps(payload),
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    # -- helpers ---------------------------------------------------------
    def payload(self, tool, tool_input, event="PreToolUse", response=None, agent=None):
        d = {"session_id": SESSION, "hook_event_name": event, "cwd": self.repo,
             "tool_name": tool, "tool_input": tool_input}
        if response is not None:
            d["tool_response"] = response
        if agent:
            d["agent_id"] = agent
        return d

    def pre(self, tool, ti, agent=None, env=None):
        return self.run_hook(PRE, self.payload(tool, ti, agent=agent), env)

    def post(self, tool, ti, response, agent=None):
        return self.run_hook(POST, self.payload(tool, ti, "PostToolUse",
                                                response=response, agent=agent))

    def read_once(self, ti=None, agent=None):
        """Simulate a completed Read of the file."""
        ti = ti if ti is not None else {"file_path": self.f}
        self.post("Read", ti, "     1\tconst a1 = 1;", agent=agent)

    def assert_allowed(self, out):
        self.assertEqual(out, "", "expected the call to pass through, got: %s" % out)

    def assert_denied(self, out):
        self.assertTrue(out, "expected a deny payload, got nothing")
        data = json.loads(out)
        h = data["hookSpecificOutput"]
        self.assertEqual(h["hookEventName"], "PreToolUse")
        self.assertEqual(h["permissionDecision"], "deny")
        self.assertTrue(h["permissionDecisionReason"].strip())
        return h["permissionDecisionReason"]


class TestReadDedup(HookCase):
    def test_first_read_passes_through(self):
        self.assert_allowed(self.pre("Read", {"file_path": self.f}))

    def test_second_identical_read_is_denied(self):
        self.read_once()
        reason = self.assert_denied(self.pre("Read", {"file_path": self.f}))
        self.assertIn("sample.ts", reason)
        self.assertIn("unchanged", reason.lower())

    def test_denied_reason_names_the_line_range(self):
        self.read_once()
        reason = self.assert_denied(self.pre("Read", {"file_path": self.f}))
        self.assertIn("lines 1-300", reason)

    def test_insisting_immediately_after_a_deny_gets_through(self):
        self.read_once()
        self.assert_denied(self.pre("Read", {"file_path": self.f}))
        self.assert_allowed(self.pre("Read", {"file_path": self.f}))

    def test_editing_the_file_forces_a_fresh_read(self):
        self.read_once()
        self.assert_denied(self.pre("Read", {"file_path": self.f}))
        time.sleep(0.01)
        self.write_file(300, tag="b")          # same line count, different bytes
        self.assert_allowed(self.pre("Read", {"file_path": self.f}))

    def test_uncovered_range_passes_through(self):
        self.read_once({"file_path": self.f, "offset": 1, "limit": 50})
        self.assert_allowed(self.pre("Read", {"file_path": self.f, "offset": 200, "limit": 50}))

    def test_subrange_of_a_recorded_read_is_denied(self):
        self.read_once({"file_path": self.f, "offset": 1, "limit": 100})
        self.assert_denied(self.pre("Read", {"file_path": self.f, "offset": 20, "limit": 10}))

    def test_full_read_after_a_partial_read_passes_through(self):
        self.read_once({"file_path": self.f, "offset": 1, "limit": 50})
        self.assert_allowed(self.pre("Read", {"file_path": self.f}))

    def test_long_file_read_is_not_treated_as_complete(self):
        # 9000 lines; a bare Read returns only the first 2000. A later read of
        # line 5000 must not be denied.
        self.write_file(9000)
        self.read_once()
        self.assert_allowed(self.pre("Read", {"file_path": self.f, "offset": 5000, "limit": 20}))

    def test_missing_file_passes_through(self):
        self.assert_allowed(self.pre("Read", {"file_path": os.path.join(self.repo, "nope.ts")}))

    def test_images_are_never_denied(self):
        img = os.path.join(self.repo, "shot.png")
        with open(img, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
        self.post("Read", {"file_path": img}, "[image]")
        self.assert_allowed(self.pre("Read", {"file_path": img}))

    def test_failed_read_is_not_recorded(self):
        self.post("Read", {"file_path": self.f},
                  {"is_error": True, "content": "EACCES: permission denied"})
        self.assert_allowed(self.pre("Read", {"file_path": self.f}))


class TestBashDedup(HookCase):
    def cat(self):
        return {"command": "cat %s" % self.f, "description": "read it"}

    def test_second_cat_of_the_same_file_is_denied(self):
        self.post("Bash", self.cat(), "const a1 = 1;")
        self.assert_denied(self.pre("Bash", self.cat()))

    def test_cat_chained_with_a_build_is_never_denied(self):
        # Denying this would cancel the build. The read is a duplicate; the
        # command as a whole is not.
        self.post("Bash", self.cat(), "const a1 = 1;")
        self.assert_allowed(self.pre("Bash", {"command": "cat %s && cargo build" % self.f}))

    def test_cat_piped_into_grep_is_never_denied(self):
        self.post("Bash", self.cat(), "const a1 = 1;")
        self.assert_allowed(self.pre("Bash", {"command": "cat %s | grep a1" % self.f}))

    def test_disjoint_sed_slices_both_pass_through(self):
        self.post("Bash", {"command": "sed -n '1,50p' %s" % self.f}, "x")
        self.assert_allowed(self.pre("Bash", {"command": "sed -n '80,120p' %s" % self.f}))

    def test_repeat_of_the_same_sed_slice_is_denied(self):
        self.post("Bash", {"command": "sed -n '1,50p' %s" % self.f}, "x")
        self.assert_denied(self.pre("Bash", {"command": "sed -n '1,50p' %s" % self.f}))

    def test_slice_inside_an_earlier_cat_is_denied(self):
        self.post("Bash", self.cat(), "const a1 = 1;")
        self.assert_denied(self.pre("Bash", {"command": "sed -n '10,20p' %s" % self.f}))

    def test_truncated_output_is_not_recorded(self):
        self.post("Bash", self.cat(), "y" * 30050)
        self.assert_allowed(self.pre("Bash", self.cat()))

    def test_read_tool_and_bash_share_one_cache(self):
        self.read_once()
        self.assert_denied(self.pre("Bash", self.cat()))

    def test_unrelated_command_passes_through(self):
        self.assert_allowed(self.pre("Bash", {"command": "cargo build --release"}))


class TestIsolationAndSafety(HookCase):
    def test_subagent_cache_is_separate_from_the_main_thread(self):
        # A subagent has its own context window; the parent's reads are not
        # in it, so deduplicating across the boundary would hide content.
        self.read_once()
        self.assert_denied(self.pre("Read", {"file_path": self.f}))
        self.assert_allowed(self.pre("Read", {"file_path": self.f}, agent="agent-7"))

    def test_compaction_clears_the_cache(self):
        self.read_once()
        self.assert_denied(self.pre("Read", {"file_path": self.f}))
        self.run_hook(COMPACT, {"session_id": SESSION, "hook_event_name": "PreCompact"})
        self.assert_allowed(self.pre("Read", {"file_path": self.f}))

    def test_kill_switch_disables_denying(self):
        self.read_once()
        self.assert_allowed(self.pre("Read", {"file_path": self.f},
                                     env={"READCACHE_DISABLE": "1"}))

    def test_malformed_stdin_fails_open(self):
        env = dict(os.environ)
        env["READCACHE_DIR"] = self.cache
        p = subprocess.run([sys.executable, PRE], input="not json at all",
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout.strip(), "")

    def test_missing_tool_input_fails_open(self):
        out = self.run_hook(PRE, {"session_id": SESSION, "tool_name": "Read"})
        self.assertEqual(out, "")

    def test_other_tools_are_untouched(self):
        self.assert_allowed(self.pre("Edit", {"file_path": self.f, "old_string": "a"}))
        self.assert_allowed(self.pre("Grep", {"pattern": "a1"}))

    def test_stats_accumulate_on_a_deny(self):
        self.read_once()
        self.assert_denied(self.pre("Read", {"file_path": self.f}))
        with open(os.path.join(self.cache, "stats.json"), encoding="utf-8") as fh:
            s = json.load(fh)
        self.assertEqual(s["denies"], 1)
        self.assertGreater(s["bytes_saved"], 1000)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestDenyMessage(HookCase):
    def setUp(self):
        super().setUp()
        # A mixed-case name: the cache key is folded on Windows, the message
        # must still show the name the caller used.
        self.f = os.path.join(self.repo, "CommitList.ts")
        self.write_file(120)

    def test_message_preserves_the_original_filename_case(self):
        self.read_once()
        reason = self.assert_denied(self.pre("Read", {"file_path": self.f}))
        self.assertIn("CommitList.ts", reason)

    def test_message_reads_grammatically(self):
        self.read_once()
        reason = self.assert_denied(self.pre("Read", {"file_path": self.f}))
        self.assertIn("lines 1-120 already in this context", reason)

    def test_message_quantifies_the_saving(self):
        self.read_once()
        reason = self.assert_denied(self.pre("Read", {"file_path": self.f}))
        self.assertRegex(reason, r"~[\d,]+ tokens")
