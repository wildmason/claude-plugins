#!/usr/bin/env python3
"""Replay historical transcripts through the read-cache decision core.

Answers "what would this hook have saved?" without waiting for live sessions
to accumulate. It streams `~/.claude/projects/**/*.jsonl`, reconstructs each
Read / Bash file-read, and asks the real `readcache_core` what it would have
decided.

Two inputs the live hook takes from disk are taken from the transcript
instead, because the filesystem has moved on since:

* **Fingerprint** - a generation counter per path, bumped whenever the
  transcript shows an Edit or Write to it. That is what a changed mtime
  would have done. Limitation: an *external* change (another session, a
  build step, a git checkout) is invisible here, so replay under-counts
  invalidations and therefore slightly OVER-counts denies.
* **Line count** - learned from the lines a read actually returned. Unknown
  on the first sight of a file, which makes replay skip dedup it would have
  performed live, so this pushes the other way and UNDER-counts denies.

Both bounds are reported. Savings are the exact byte length of the result
that would not have entered the context.

Usage:
    python replay.py                 # last 7 days
    python replay.py --days 30
    python replay.py --days 7 --top 15 --project wildmason
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import readcache_core as C  # noqa: E402

NUMBERED = re.compile(r"^\s*(\d+)\t", re.M)
MUTATORS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
READERS = ("Read", "Bash", "PowerShell")


# ---------------------------------------------------------------- pure bits
def numbered_span(text):
    """(first, last) line numbers in a `cat -n` style Read result, else None."""
    if not isinstance(text, str):
        return None
    nums = [int(m) for m in NUMBERED.findall(text)]
    if not nums:
        return None
    return (min(nums), max(nums))


def lane_of(rec):
    """Which context window a record belongs to.

    A subagent has its own window, so its reads must not be deduplicated
    against the main thread's.
    """
    if rec.get("isSidechain"):
        return "agent:%s" % (rec.get("agentId") or rec.get("sourceToolAssistantUUID") or "unknown")
    return "main"


def blocks(rec):
    m = rec.get("message")
    if not isinstance(m, dict):
        return []
    c = m.get("content")
    return [b for b in c if isinstance(b, dict)] if isinstance(c, list) else []


def result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text") or "" for b in content if isinstance(b, dict))
    return ""


def is_compact_boundary(rec):
    return rec.get("type") == "system" and rec.get("subtype") == "compact_boundary"


# -------------------------------------------------------------- the replay
class Lane(object):
    __slots__ = ("cache", "gen", "lines")

    def __init__(self):
        self.cache = {}                       # path -> cache entry
        self.gen = collections.Counter()      # path -> mutation generation
        self.lines = {}                       # path -> best known line count

    def fp(self, path):
        return [self.gen[path], 0]


class Replay(object):
    def __init__(self, allow_insist=True):
        self.allow_insist = allow_insist
        self.denies = 0
        self.saved = 0
        self.reads = 0
        self.read_bytes = 0
        self.compactions = 0
        self.by_file = collections.Counter()
        self.by_project = collections.Counter()
        self.by_tool = collections.Counter()

    def decide(self, lane, path, span, nbytes, tool, project, display):
        entry = lane.cache.get(path)
        decision, _reason, updated = C.evaluate(entry, lane.fp(path), span)
        if decision == "deny" and not self.allow_insist:
            pass                                   # count it; do not persist the bump
        elif updated is not None:
            lane.cache[path] = updated
        if decision == "deny":
            self.denies += 1
            self.saved += nbytes
            self.by_file[display] += nbytes
            self.by_project[project] += nbytes
            self.by_tool[tool] += nbytes
            return "deny"
        C.record(lane.cache, path, lane.fp(path), span, "")
        return "allow"

    def run_file(self, path_jsonl, project):
        lanes = collections.defaultdict(Lane)
        pending = {}
        with open(path_jsonl, encoding="utf-8", errors="replace") as fh:
            self._consume(fh, lanes, pending, project)

    def _consume(self, fh, lanes, pending, project):
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue

            if is_compact_boundary(rec):
                self.compactions += 1
                lanes.clear()                      # cached content is gone from context
                continue

            t = rec.get("type")
            if t == "assistant":
                for b in blocks(rec):
                    if b.get("type") == "tool_use":
                        pending[b.get("id")] = (b.get("name") or "", b.get("input") or {},
                                                lane_of(rec))
                continue
            if t != "user":
                continue

            cwd = rec.get("cwd") or ""
            for b in blocks(rec):
                if b.get("type") != "tool_result":
                    continue
                tool, ti, lane_key = pending.pop(b.get("tool_use_id"), ("", {}, "main"))
                if not tool or not isinstance(ti, dict):
                    continue
                lane = lanes[lane_key]

                if tool in MUTATORS:
                    p = C.norm_path(ti.get("file_path") or "", cwd)
                    if p:
                        lane.gen[p] += 1           # stands in for a changed mtime
                    continue
                if tool not in READERS:
                    continue

                text = result_text(b.get("content"))
                if not C.response_ok(text):
                    continue
                self.handle_read(lane, tool, ti, cwd, text, project)

    def handle_read(self, lane, tool, ti, cwd, text, project):
        if tool == "Read":
            raw = ti.get("file_path") or ""
            if not raw:
                return
            items = [(raw, "read", ti)]
        else:
            cmd = ti.get("command") or ""
            if not C.command_is_only_reads(cmd):
                return
            if C.looks_truncated(text):
                return
            items = [(p, "spec", spec) for p, spec in C.parse_bash_reads(cmd)]
        if not items:
            return

        nbytes = len(text)
        share = max(1, nbytes // len(items))
        for raw, kind, payload in items:
            p = C.norm_path(raw, cwd)
            if not p or C.is_opaque(p):
                continue

            observed = numbered_span(text) if tool == "Read" else None
            if observed:
                lane.lines[p] = max(lane.lines.get(p, 0), observed[1])
            elif tool != "Read":
                n = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
                lane.lines[p] = max(lane.lines.get(p, 0), n)

            lc = lane.lines.get(p)
            span = (C.read_span(payload, lc) if kind == "read"
                    else C.resolve_spec(payload, lc))
            if span is None:
                span = observed
            if span is None:
                continue

            self.reads += 1
            self.read_bytes += share
            self.decide(lane, p, span, share, tool, project, os.path.basename(p))


# ------------------------------------------------------------------- report
def human(n):
    return format(int(n), ",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=7.0)
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--project", default="", help="substring filter on the project directory")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    import time
    cutoff = time.time() - args.days * 86400
    files = [f for f in glob.glob(os.path.join(args.root, "**", "*.jsonl"), recursive=True)
             if os.path.getmtime(f) >= cutoff and args.project in f]
    if not files:
        print("no transcripts in the window")
        return

    runs = {}
    for label, insist in (("with insist hatch", True), ("without insist hatch", False)):
        r = Replay(allow_insist=insist)
        for f in files:
            r.run_file(f, os.path.basename(os.path.dirname(f)))
        runs[label] = r

    lo = runs["with insist hatch"]
    hi = runs["without insist hatch"]

    print("read-cache replay - last %g days, %d transcripts, %d compactions"
          % (args.days, len(files), lo.compactions))
    print("file reads seen: %s calls, %s chars of context"
          % (human(lo.reads), human(lo.read_bytes)))
    print()
    print("%-22s %10s %14s %10s" % ("scenario", "blocked", "chars saved", "share"))
    for label in ("with insist hatch", "without insist hatch"):
        r = runs[label]
        share = 100.0 * r.saved / r.read_bytes if r.read_bytes else 0.0
        print("%-22s %10s %14s %9.1f%%" % (label, human(r.denies), human(r.saved), share))
    print()
    print("~%s to ~%s tokens of context not spent"
          % (human(lo.saved // 4), human(hi.saved // 4)))

    print("\ntop repeat-read files (chars saved, insist hatch on):")
    for name, n in lo.by_file.most_common(args.top):
        print("  %-46s %12s" % (name[:46], human(n)))

    print("\nby project:")
    for name, n in lo.by_project.most_common(8):
        print("  %-46s %12s" % (name[:46], human(n)))

    print("\nby tool:")
    for name, n in lo.by_tool.most_common():
        print("  %-46s %12s" % (name, human(n)))


if __name__ == "__main__":
    main()
