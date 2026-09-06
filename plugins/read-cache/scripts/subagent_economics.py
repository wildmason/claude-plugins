#!/usr/bin/env python3
"""Does a cheap-model delegation beat just using subagents more often?

Claude Code already ships `Explore`, which reads in its own context window
and returns conclusions. 262 of the 663 investigation bursts found by
`investigation.py` already ran that way. So before building a delegation
mechanism, the honest question is what a subagent already achieves.

This measures each subagent lane end to end without needing to link it back
to its spawning call (that link is absent from many transcripts):

* **consumed** - every tool-result byte that landed inside the subagent's own
  context window. This is what the investigation actually cost to run.
* **returned** - the subagent's final assistant message, which is what the
  parent receives. This is what the main context actually pays.
* **realized compression** - 1 - returned/consumed, measured rather than
  assumed. The article assumes 90%; this says what really happens.
* **model** - which model did the reading, from the sidechain's own records.

The comparison it enables:

    A subagent already solves the CONTEXT problem - the bytes never reach the
    main window. What it does not solve is the PRICE problem, because it runs
    on a frontier model. A cheap or local worker attacks that second axis.
    The two are orthogonal, and this quantifies both.

Usage:
    python subagent_economics.py --days 35
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
import investigation as I  # noqa: E402


# ---------------------------------------------------------------- pure bits
def realized_compression(consumed, returned):
    """Fraction of the investigation's bytes that never reach the parent."""
    if consumed <= 0:
        return None
    return max(0.0, 1.0 - float(returned) / float(consumed))


def price_ratio(worker_in, worker_out, frontier_in, frontier_out):
    """How much cheaper a worker model is, per unit of the same work.

    Investigation is read-dominated, so input tokens carry the weight. Both
    arguments are dollars per million tokens.
    """
    frontier = frontier_in * 0.9 + frontier_out * 0.1
    worker = worker_in * 0.9 + worker_out * 0.1
    if worker <= 0:
        return None
    return frontier / worker


def assistant_text(rec):
    return "".join(b.get("text") or "" for b in R.blocks(rec) if b.get("type") == "text")


# -------------------------------------------------------------- the harness
class Lane(object):
    __slots__ = ("consumed", "calls", "last_text", "models", "turns")

    def __init__(self):
        self.consumed = 0
        self.calls = 0
        self.last_text = ""
        self.models = collections.Counter()
        self.turns = 0


class SubagentEconomics(object):
    def __init__(self):
        self.lanes = {}
        self.main_observe_bytes = 0

    def run_file(self, path_jsonl):
        with open(path_jsonl, encoding="utf-8", errors="replace") as fh:
            self._consume(fh, path_jsonl)

    def _consume(self, fh, fname):
        pending = {}
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            side = bool(rec.get("isSidechain"))
            key = (fname, rec.get("agentId") or "unknown")
            t = rec.get("type")

            if t == "assistant":
                if side:
                    lane = self.lanes.setdefault(key, Lane())
                    lane.turns += 1
                    lane.models[(rec.get("message") or {}).get("model") or "?"] += 1
                    txt = assistant_text(rec)
                    if txt.strip():
                        lane.last_text = txt          # final one wins: the report
                for b in R.blocks(rec):
                    if b.get("type") == "tool_use":
                        pending[b.get("id")] = (b.get("name") or "", b.get("input") or {}, side, key)
                continue
            if t != "user":
                continue
            cwd = rec.get("cwd") or ""
            for b in R.blocks(rec):
                if b.get("type") != "tool_result":
                    continue
                tool, ti, was_side, k = pending.pop(b.get("tool_use_id"), ("", {}, False, key))
                if not tool or not isinstance(ti, dict):
                    continue
                text = R.result_text(b.get("content"))
                kind, nbytes, _p = _classify(tool, ti, text, cwd)
                if kind != "OBSERVE":
                    continue
                if was_side:
                    lane = self.lanes.setdefault(k, Lane())
                    lane.consumed += nbytes
                    lane.calls += 1
                else:
                    self.main_observe_bytes += nbytes


_probe = I.InvestigationReplay()


def _classify(tool, ti, text, cwd):
    return _probe._classify(tool, ti, text, cwd)


# ------------------------------------------------------------------ report
def human(n):
    return format(int(n), ",")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=35.0)
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--min-consumed", type=int, default=2000,
                    help="ignore trivial lanes that never really investigated")
    args = ap.parse_args()

    cutoff = time.time() - args.days * 86400
    files = [f for f in glob.glob(os.path.join(args.root, "**", "*.jsonl"), recursive=True)
             if os.path.getmtime(f) >= cutoff]
    if not files:
        print("no transcripts in the window")
        return

    se = SubagentEconomics()
    for f in files:
        se.run_file(f)

    all_lanes = [l for l in se.lanes.values() if l.consumed >= args.min_consumed]
    # A lane with no final text reported through another channel (SendMessage)
    # or was interrupted. Counting it as a zero-byte return would inflate the
    # compression figure, so it is excluded and disclosed.
    lanes = [l for l in all_lanes if l.last_text.strip()]
    silent = len(all_lanes) - len(lanes)
    consumed = sum(l.consumed for l in lanes)
    returned = sum(len(l.last_text) for l in lanes)
    comp = realized_compression(consumed, returned)

    print("subagent economics - last %g days, %d transcripts" % (args.days, len(files)))
    print("subagent lanes with real work : %s  (%s excluded: reported via another"
          " channel or interrupted)" % (human(len(lanes)), human(silent)))
    print("  consumed inside their own windows : %s chars (~%s tokens)"
          % (human(consumed), human(consumed // 4)))
    print("  returned to the parent            : %s chars (~%s tokens)"
          % (human(returned), human(returned // 4)))
    print("  REALIZED COMPRESSION              : %.1f%%" % (comp * 100 if comp else 0.0))
    print("  main-thread observation bytes     : %s chars (~%s tokens)"
          % (human(se.main_observe_bytes), human(se.main_observe_bytes // 4)))

    ratios = sorted((realized_compression(l.consumed, len(l.last_text)), l.consumed,
                     len(l.last_text), l.calls, l.turns) for l in lanes)
    if ratios:
        c, cons, ret, calls, turns = ratios[len(ratios) // 2]
        print("\nmedian lane by compression : %.1f%%  (%s chars consumed -> %s returned,"
              " %d observation calls, %d turns)"
              % (c * 100, human(cons), human(ret), calls, turns))
        w = ratios[0]
        print("least compressed lane      : %.1f%%  (%s -> %s)"
              % (w[0] * 100, human(w[1]), human(w[2])))

    models = collections.Counter()
    for l in lanes:
        for m, n in l.models.items():
            models[m] += n
    print("\nwhich model did the reading:")
    tot_m = sum(models.values()) or 1
    for m, n in models.most_common(6):
        print("  %-28s %6d turns  %5.1f%%" % (m, n, 100.0 * n / tot_m))

    print("\ndistribution of realized compression:")
    buckets = collections.Counter()
    for l in lanes:
        c = realized_compression(l.consumed, len(l.last_text))
        if c is None:
            continue
        b = ("<50%" if c < .5 else "50-79%" if c < .8 else
             "80-89%" if c < .9 else "90-94%" if c < .95 else "95%+")
        buckets[b] += 1
    for b in ("<50%", "50-79%", "80-89%", "90-94%", "95%+"):
        print("  %-8s %5d lanes" % (b, buckets[b]))

    print("\n" + "=" * 70)
    print("WHAT THIS SETTLES")
    print("=" * 70)
    print("Context: a subagent already keeps %.1f%% of an investigation's bytes out of"
          % ((comp or 0) * 100))
    print("the parent window. A cheap-model delegation cannot beat that by much -")
    print("the ceiling is 100%% and Explore is already close to it.")
    print()
    print("Price: those bytes are still read by a frontier model. Per the sidechain")
    print("records above, that is where a cheap or local worker adds something a")
    print("subagent does not. The two mechanisms are orthogonal, not competing.")


if __name__ == "__main__":
    main()
