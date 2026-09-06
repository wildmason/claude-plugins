#!/usr/bin/env python3
"""Replay Spotify's `shunt` policy over the same transcripts as replay.py.

`read-cache` was measured to destruction and found wanting. `shunt` was
rejected on inference. That asymmetry is what this script removes: it
simulates shunt's actual rule against real history and reports what it would
have done, on the same denominator.

The rule, as described at
https://engineering.atspotify.com/2026/9/portal-by-spotify-cut-my-claude-code-token-usage-by-90 :

  A PreToolUse hook on `Read` blocks any read longer than SHUNT_MIN_LINES
  (350 by default) and routes it to a `bulk-read` skill, which sends the
  file to a cheap model and returns "structured bullets only". A second
  mode, `code-write`, generates boilerplate straight to disk.

What is simulated
-----------------
* Every `Read` whose result exceeds the line threshold becomes a delegation.
  Saving is the result's bytes times the compression ratio.
* Each delegation is then classified by what the session did next with that
  file, which is the part the article concedes it cannot handle:
  a summary carries no line numbers, so a delegated read followed by an edit
  to the same file left the agent still needing the real thing.
* Reported separately for the main thread and for subagents, because a
  subagent's context is already isolated from the main window.
* A `--with-bash` variant extends the same rule to shell file reads, which
  shunt does not do. That tests whether the interception point, rather than
  the idea, is the limiting factor.

What is NOT simulated, and why
------------------------------
* `code-write`. Generated code that goes straight to disk leaves no trace in
  the transcript. Its opportunity is sized separately by `write_volume()`,
  which measures the assistant output that currently flows through Write and
  Edit tool inputs - that is the ceiling on what code-write could move to a
  cheap model.
* Answer quality. This measures bytes moved, not whether the cheap model's
  bullets were good enough. The article concedes one miss (a thread-safety
  bug). Nothing here contradicts or confirms that.
* Second-order behaviour. A blocked `Read` may push the agent to `cat` the
  file instead, or to read it in sub-threshold slices. Both would erase
  savings and neither is visible in transcripts recorded without the hook.

Usage:
    python replay_shunt.py --days 35
    python replay_shunt.py --days 35 --thresholds 200,350,500,1000
    python replay_shunt.py --days 35 --compression 0.9,0.7,0.5 --with-bash
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

LATENCY_S = 20.0          # article states 10-30 s per delegation


# ---------------------------------------------------------------- pure bits
def span_lines(span):
    """Lines a read returned, from its observed span."""
    if not span:
        return 0
    return max(0, int(span[1]) - int(span[0]) + 1)


def is_delegable(lines, threshold):
    """shunt's whole trigger: a read longer than the line threshold."""
    return lines >= threshold


def classify(read_seq, path, lane_edits):
    """What the session did with this file after a delegated read.

    'needed-exact' means an edit to the same file followed. A bullet summary
    carries no line numbers, so the agent would still have had to obtain the
    real content - the delegation added a round trip instead of removing one.
    """
    return "needed-exact" if any(e > read_seq for e in lane_edits.get(path, ())) else "summary-sufficed"


def savings(nbytes, compression):
    """Bytes removed from the context, and bytes the summary adds back."""
    kept = int(round(nbytes * (1.0 - compression)))
    return nbytes - kept, kept


# -------------------------------------------------------------- the harness
class ShuntReplay(object):
    def __init__(self, threshold, with_bash=False):
        self.threshold = threshold
        self.with_bash = with_bash
        self.read_bytes = 0            # denominator: all file-read bytes seen
        self.read_calls = 0
        self.deleg = collections.Counter()        # lane_kind -> count
        self.deleg_bytes = collections.Counter()  # lane_kind -> bytes
        self.outcome = collections.Counter()      # outcome -> count
        self.outcome_bytes = collections.Counter()
        self.by_tool = collections.Counter()
        self.top = collections.Counter()

    def run_file(self, path_jsonl):
        with open(path_jsonl, encoding="utf-8", errors="replace") as fh:
            self._consume(fh)

    def _consume(self, fh):
        pending = {}
        seq = 0
        reads = []                                  # (seq, lane, path, lines, bytes, tool)
        edits = collections.defaultdict(lambda: collections.defaultdict(list))
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
                if tool in R.MUTATORS:
                    p = C.norm_path(ti.get("file_path") or "", cwd)
                    if p:
                        edits[lane][p].append(seq)
                    continue
                text = R.result_text(b.get("content"))
                if not C.response_ok(text):
                    continue

                if tool == "Read":
                    p = C.norm_path(ti.get("file_path") or "", cwd)
                    sp = R.numbered_span(text)
                    if not p or C.is_opaque(p) or not sp:
                        continue
                    reads.append((seq, lane, p, span_lines(sp), len(text), "Read"))
                elif self.with_bash and tool in ("Bash", "PowerShell"):
                    cmd = ti.get("command") or ""
                    if not C.command_is_only_reads(cmd) or C.looks_truncated(text):
                        continue
                    items = C.parse_bash_reads(cmd)
                    if len(items) != 1:
                        continue
                    p = C.norm_path(items[0][0], cwd)
                    if not p or C.is_opaque(p):
                        continue
                    n = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
                    reads.append((seq, lane, p, n, len(text), "Bash"))

        for seq_, lane, p, lines, nbytes, tool in reads:
            self.read_calls += 1
            self.read_bytes += nbytes
            if not is_delegable(lines, self.threshold):
                continue
            kind = "main" if lane == "main" else "subagent"
            self.deleg[kind] += 1
            self.deleg_bytes[kind] += nbytes
            self.by_tool[tool] += nbytes
            out = classify(seq_, p, edits[lane])
            self.outcome[out] += 1
            self.outcome_bytes[out] += nbytes
            self.top[os.path.basename(p)] += nbytes

    # -- derived -------------------------------------------------------
    @property
    def deleg_total_bytes(self):
        return sum(self.deleg_bytes.values())

    @property
    def deleg_total(self):
        return sum(self.deleg.values())


def write_volume(files):
    """Assistant output currently spent writing code through Write/Edit inputs.

    This is the ceiling on what shunt's `code-write` mode could move to a
    cheap model. It never appears in a tool RESULT, which is why the read
    simulation cannot see it.
    """
    total = collections.Counter()
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("type") != "assistant":
                    continue
                for b in R.blocks(rec):
                    if b.get("type") != "tool_use":
                        continue
                    name = b.get("name") or ""
                    ti = b.get("input") or {}
                    if not isinstance(ti, dict):
                        continue
                    if name == "Write":
                        total["Write"] += len(ti.get("content") or "")
                    elif name in ("Edit", "MultiEdit"):
                        total["Edit"] += len(ti.get("new_string") or "")
    return total


# ------------------------------------------------------------------ report
def human(n):
    return format(int(n), ",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=35.0)
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--thresholds", default="350")
    ap.add_argument("--compression", default="0.9")
    ap.add_argument("--with-bash", action="store_true")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    cutoff = time.time() - args.days * 86400
    files = [f for f in glob.glob(os.path.join(args.root, "**", "*.jsonl"), recursive=True)
             if os.path.getmtime(f) >= cutoff]
    if not files:
        print("no transcripts in the window")
        return

    thresholds = [int(x) for x in args.thresholds.split(",")]
    compressions = [float(x) for x in args.compression.split(",")]

    print("shunt replay - last %g days, %d transcripts%s"
          % (args.days, len(files), "  (Read + Bash)" if args.with_bash else "  (Read only, as shipped)"))

    runs = {}
    for th in thresholds:
        r = ShuntReplay(th, with_bash=args.with_bash)
        for f in files:
            r.run_file(f)
        runs[th] = r

    base = runs[thresholds[0]]
    print("file reads seen: %s calls, %s chars\n" % (human(base.read_calls), human(base.read_bytes)))

    print("%-10s %9s %14s %9s %12s" % ("threshold", "delegated", "bytes", "share", "latency"))
    for th in thresholds:
        r = runs[th]
        share = 100.0 * r.deleg_total_bytes / max(r.read_bytes, 1)
        mins = r.deleg_total * LATENCY_S / 60.0
        print("%-10s %9s %14s %8.1f%% %9.0f min" %
              ("%d lines" % th, human(r.deleg_total), human(r.deleg_total_bytes), share, mins))

    r = runs[thresholds[0]]
    print("\nat %d lines - where the delegable bytes sit:" % thresholds[0])
    for kind in ("main", "subagent"):
        b = r.deleg_bytes[kind]
        print("  %-24s %9s calls %14s chars  %5.1f%% of all read bytes"
              % (kind, human(r.deleg[kind]), human(b), 100.0 * b / max(r.read_bytes, 1)))

    print("\nwhat happened after each delegated read:")
    for out in ("summary-sufficed", "needed-exact"):
        n, b = r.outcome[out], r.outcome_bytes[out]
        pct = 100.0 * b / max(r.deleg_total_bytes, 1)
        print("  %-24s %9s calls %14s chars  %5.1f%% of delegated"
              % (out, human(n), human(b), pct))

    print("\nnet effect on the main thread, summary-sufficed only:")
    main_ok = r.outcome_bytes["summary-sufficed"] * (
        r.deleg_bytes["main"] / max(r.deleg_total_bytes, 1))
    for c in compressions:
        saved, kept = savings(main_ok, c)
        share = 100.0 * saved / max(r.read_bytes, 1)
        print("  compression %.0f%%  ->  %14s chars saved  (%.1f%% of all read bytes, ~%s tokens)"
              % (c * 100, human(saved), share, human(saved // 4)))

    print("\ntop delegated files:")
    for name, n in r.top.most_common(args.top):
        print("  %-46s %12s" % (name[:46], human(n)))

    wv = write_volume(files)
    print("\ncode-write opportunity (not simulated above - assistant output, not tool results):")
    for k in ("Write", "Edit"):
        print("  %-24s %14s chars  (~%s tokens of generation)" % (k, human(wv[k]), human(wv[k] // 4)))


if __name__ == "__main__":
    main()

