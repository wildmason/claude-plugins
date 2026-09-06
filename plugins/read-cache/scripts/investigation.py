#!/usr/bin/env python3
"""Size the real proposition: delegate an INVESTIGATION, not a file.

Matt's framing, which is a better hypothesis than the one `shunt` implements:

    "I need to know how function foo is used and where it's called from"
    ... spend quota on multiple file reads ...

The waste is not one big read. It is a burst of reads and searches whose only
durable product is an ANSWER - "foo is called from these three files, it takes
these params, it does X and Y". Every byte of every file in that burst lands
in the context permanently and is re-sent every turn afterwards, but the value
extracted is a paragraph. A cheap or local model could do the reading and
tracing and hand back the paragraph.

An **investigation** here is a maximal run of consecutive observation calls
(Read, Grep, Glob, shell file-reads) inside one context window, broken by any
mutation, by a non-observing command such as a build or a test, or by a
compaction.

It counts as **delegable** when the session never edited any file the burst
looked at. That is the evidence that the burst produced understanding rather
than a change - and it is the honest test, because a summary carries no line
numbers, so a burst that fed an edit could not have been delegated.

Bursts already running inside a subagent are reported separately: that work is
already off the main context window, so it is not new opportunity.

Usage:
    python investigation.py --days 35
    python investigation.py --days 35 --min-calls 2 --compression 0.9,0.7
"""
import argparse
import collections
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import readcache_core as C  # noqa: E402
import replay as R  # noqa: E402

OBSERVE_TOOLS = ("Read", "Grep", "Glob")
ANSWER_CHARS = 1500        # what a structured answer costs to bring back
LATENCY_S = 20.0           # the article's stated 10-30 s per delegation


# ---------------------------------------------------------------- pure bits
class Burst(object):
    __slots__ = ("calls", "nbytes", "paths", "start", "lane", "tools", "by_path", "anon_bytes")

    def __init__(self, lane, start):
        self.calls = 0
        self.nbytes = 0
        self.paths = set()
        self.start = start
        self.lane = lane
        self.tools = collections.Counter()
        self.by_path = collections.Counter()   # bytes attributable to each file
        self.anon_bytes = 0                    # Grep/Glob output: no single file

    def add(self, tool, nbytes, path):
        self.calls += 1
        self.nbytes += nbytes
        self.tools[tool] += 1
        if path:
            self.paths.add(path)
            self.by_path[path] += nbytes
        else:
            self.anon_bytes += nbytes

    def label(self):
        names = sorted(os.path.basename(p) for p in self.paths)
        if not names:
            return "(search only)"
        head = ", ".join(names[:3])
        return head + (" +%d" % (len(names) - 3) if len(names) > 3 else "")


def burst_is_delegable(burst, lane_edits):
    """True when nothing the burst looked at was edited later in that window.

    An edit to an inspected file means the session needed exact line numbers,
    which a summary cannot supply.
    """
    for p in burst.paths:
        if any(e > burst.start for e in lane_edits.get(p, ())):
            return False
    return True


def delegable_bytes(burst, lane_edits):
    """Bytes inside a burst that came from files the session never edited.

    The all-or-nothing rule disqualifies a whole burst if any inspected file
    is later edited, which is too strict for the real proposition: answering
    "where is foo called from" reads many files to inform a change in one.
    Per-file attribution keeps the untouched files as genuine investigation.

    Search output (Grep/Glob) is always attributable - a grep result is not
    line-addressable, so it can never be the thing an edit needed.
    """
    n = burst.anon_bytes
    for p, b in burst.by_path.items():
        if not any(e > burst.start for e in lane_edits.get(p, ())):
            n += b
    return n


def size_bucket(calls):
    if calls <= 4:
        return "3-4 calls"
    if calls <= 9:
        return "5-9 calls"
    if calls <= 19:
        return "10-19 calls"
    return "20+ calls"


def net_saving(gross_bytes, n_bursts, compression, answer_chars=ANSWER_CHARS):
    """Bytes removed, after paying for one answer per delegated burst."""
    return max(0, int(gross_bytes * compression) - n_bursts * answer_chars)


# -------------------------------------------------------------- the harness
class InvestigationReplay(object):
    def __init__(self, min_calls=3):
        self.min_calls = min_calls
        self.observe_bytes = 0
        self.observe_calls = 0
        self.bursts = []            # (kind, calls, bytes, delegable, label)
        self.sizes = collections.Counter()
        self.size_bytes = collections.Counter()
        self.top = collections.Counter()
        self.tool_mix = collections.Counter()
        self.partial_bytes = 0        # per-file attribution, main thread
        self.partial_bursts = 0

    def run_file(self, path_jsonl):
        with open(path_jsonl, encoding="utf-8", errors="replace") as fh:
            self._consume(fh)

    def _flush(self, burst, edits):
        if burst is None or burst.calls < self.min_calls:
            return
        kind = "main" if burst.lane == "main" else "subagent"
        ok = burst_is_delegable(burst, edits[burst.lane])
        label = burst.label()
        self.bursts.append((kind, burst.calls, burst.nbytes, ok, label))
        self.sizes[size_bucket(burst.calls)] += 1
        self.size_bytes[size_bucket(burst.calls)] += burst.nbytes
        if kind == "main":
            part = delegable_bytes(burst, edits[burst.lane])
            if part > 0:
                self.partial_bytes += part
                self.partial_bursts += 1
        if ok and kind == "main":
            self.top[label] += burst.nbytes
            for t, n in burst.tools.items():
                self.tool_mix[t] += n

    def _classify(self, tool, ti, text, cwd):
        """(kind, bytes, path) for one tool result."""
        if tool in R.MUTATORS:
            return ("MUTATE", 0, C.norm_path(ti.get("file_path") or "", cwd))
        if tool == "Read":
            p = C.norm_path(ti.get("file_path") or "", cwd)
            if not p or C.is_opaque(p):
                return ("OTHER", 0, None)
            return ("OBSERVE", len(text), p)
        if tool in ("Grep", "Glob"):
            return ("OBSERVE", len(text), None)
        if tool in ("Bash", "PowerShell"):
            cmd = ti.get("command") or ""
            if C.command_is_only_reads(cmd):
                items = C.parse_bash_reads(cmd)
                p = C.norm_path(items[0][0], cwd) if len(items) == 1 else None
                return ("OBSERVE", len(text), p)
            return ("OTHER", 0, None)
        return ("OTHER", 0, None)

    def _consume(self, fh):
        pending, seq = {}, 0
        edits = collections.defaultdict(lambda: collections.defaultdict(list))
        events = []
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if R.is_compact_boundary(rec):
                seq += 1
                events.append((seq, None, "COMPACT", 0, None))
                continue
            t = rec.get("type")
            if t == "assistant":
                for b in R.blocks(rec):
                    if b.get("type") == "tool_use":
                        pending[b.get("id")] = (b.get("name") or "", b.get("input") or {},
                                                R.lane_of(rec))
                continue
            if t != "user":
                continue
            cwd = rec.get("cwd") or ""
            for b in R.blocks(rec):
                if b.get("type") != "tool_result":
                    continue
                tool, ti, lane = pending.pop(b.get("tool_use_id"), ("", {}, "main"))
                if not tool or not isinstance(ti, dict):
                    continue
                seq += 1
                text = R.result_text(b.get("content"))
                kind, nbytes, p = self._classify(tool, ti, text, cwd)
                if kind == "MUTATE" and p:
                    edits[lane][p].append(seq)
                events.append((seq, lane, kind, nbytes, p))

        open_burst = {}
        for seq_, lane, kind, nbytes, p in events:
            if kind == "COMPACT":
                for L in list(open_burst):
                    self._flush(open_burst.pop(L), edits)
                continue
            if kind == "OBSERVE":
                self.observe_bytes += nbytes
                self.observe_calls += 1
                cur = open_burst.get(lane)
                if cur is None:
                    cur = open_burst[lane] = Burst(lane, seq_)
                cur.add(kind, nbytes, p)
            elif lane in open_burst:
                self._flush(open_burst.pop(lane), edits)
        for L in list(open_burst):
            self._flush(open_burst.pop(L), edits)


# ------------------------------------------------------------------ report
def human(n):
    return format(int(n), ",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=35.0)
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--min-calls", type=int, default=3)
    ap.add_argument("--compression", default="0.9,0.7,0.5")
    ap.add_argument("--answer-chars", type=int, default=ANSWER_CHARS)
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    cutoff = time.time() - args.days * 86400
    files = [f for f in glob.glob(os.path.join(args.root, "**", "*.jsonl"), recursive=True)
             if os.path.getmtime(f) >= cutoff]
    if not files:
        print("no transcripts in the window")
        return

    ir = InvestigationReplay(min_calls=args.min_calls)
    for f in files:
        ir.run_file(f)

    tot = ir.observe_bytes
    main_b = [b for b in ir.bursts if b[0] == "main"]
    main_ok = [b for b in main_b if b[3]]
    sub = [b for b in ir.bursts if b[0] == "subagent"]
    gross = sum(b[2] for b in main_ok)

    print("investigation replay - last %g days, %d transcripts, min %d calls per burst"
          % (args.days, len(files), args.min_calls))
    print("all observation output in window : %s calls, %s chars (~%s tokens)"
          % (human(ir.observe_calls), human(tot), human(tot // 4)))
    print()
    print("investigations found             : %s  (%s main thread, %s already in subagents)"
          % (human(len(ir.bursts)), human(len(main_b)), human(len(sub))))
    print("main, nothing later edited       : %s bursts, %s calls, %s chars = %.1f%% of observation bytes"
          % (human(len(main_ok)), human(sum(b[1] for b in main_ok)), human(gross),
             100.0 * gross / max(tot, 1)))
    print("main, something later edited     : %s bursts, %s chars  (not delegable)"
          % (human(len(main_b) - len(main_ok)),
             human(sum(b[2] for b in main_b if not b[3]))))

    print("\nburst size distribution (all lanes):")
    for k in ("3-4 calls", "5-9 calls", "10-19 calls", "20+ calls"):
        print("  %-14s %6s bursts %14s chars  %5.1f%%"
              % (k, human(ir.sizes[k]), human(ir.size_bytes[k]),
                 100.0 * ir.size_bytes[k] / max(tot, 1)))

    print("\nnet saving, each delegable burst returning a ~%s-char answer:" % human(args.answer_chars))
    for c in [float(x) for x in args.compression.split(",")]:
        saved = net_saving(gross, len(main_ok), c, args.answer_chars)
        print("  compression %3.0f%%  ->  %14s chars  (%5.1f%% of observation bytes, ~%s tokens)"
              % (c * 100, human(saved), 100.0 * saved / max(tot, 1), human(saved // 4)))
    print("  latency cost   : %s delegations x %gs = %.0f min"
          % (human(len(main_ok)), LATENCY_S, len(main_ok) * LATENCY_S / 60.0))

    print("\nper-file attribution (the fairer rule - untouched files inside every burst):")
    print("  %s main bursts hold %s chars from files never edited = %.1f%% of observation bytes"
          % (human(ir.partial_bursts), human(ir.partial_bytes),
             100.0 * ir.partial_bytes / max(tot, 1)))
    for c in [float(x) for x in args.compression.split(",")]:
        saved = net_saving(ir.partial_bytes, ir.partial_bursts, c, args.answer_chars)
        print("    compression %3.0f%%  ->  %14s chars  (%5.1f%% of observation bytes, ~%s tokens)"
              % (c * 100, human(saved), 100.0 * saved / max(tot, 1), human(saved // 4)))

    print("\nbiggest delegable investigations (main thread):")
    for label, n in ir.top.most_common(args.top):
        print("  %-52s %12s" % (label[:52], human(n)))


if __name__ == "__main__":
    main()
