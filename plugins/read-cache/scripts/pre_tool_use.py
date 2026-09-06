#!/usr/bin/env python3
"""PreToolUse - deny a read whose bytes are provably already in the context.

Fail-open in every direction: any missing field, unreadable file, parse
miss or unexpected exception exits 0 and the tool call proceeds untouched.
A missed duplicate costs nothing; a false deny hides content from the agent.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import readcache_core as C  # noqa: E402


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def bump_stats(n_denies, bytes_saved):
    path = os.path.join(C.cache_dir(), "stats.json")
    s = C.load_cache(path)
    s["denies"] = int(s.get("denies") or 0) + n_denies
    s["bytes_saved"] = int(s.get("bytes_saved") or 0) + bytes_saved
    C.save_cache(path, s)


def targets_for(tool, ti):
    """[(raw_path, kind, payload)] this call would read, or None to stand down."""
    if tool == "Read":
        p = ti.get("file_path") or ""
        return [(p, "read", ti)] if p else None
    if tool in ("Bash", "PowerShell"):
        cmd = ti.get("command") or ""
        # Only deny when reading is ALL the command does - see core docstring.
        if not C.command_is_only_reads(cmd):
            return None
        parsed = C.parse_bash_reads(cmd)
        return [(p, "spec", spec) for p, spec in parsed] or None
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if C.disabled():
        return

    tool = data.get("tool_name") or ""
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return
    targets = targets_for(tool, ti)
    if not targets:
        return

    cwd = data.get("cwd") or ""
    cpath = C.cache_path(data.get("session_id"), data.get("agent_id"))
    cache = C.load_cache(cpath)

    updated, hits = {}, []
    for raw, kind, payload in targets:
        np = C.norm_path(raw, cwd)
        if not np or C.is_opaque(np):
            return
        fp = C.fingerprint_of(np)
        if fp is None:
            return                                  # let the tool report the error
        lc = C.line_count_of(np)
        span = C.read_span(payload, lc) if kind == "read" else C.resolve_spec(payload, lc)
        if span is None:
            return
        before = len((cache.get(np) or {}).get("denied") or {})
        decision, reason, entry = C.evaluate(cache.get(np), fp, span)
        if entry is not None:
            updated[np] = (entry, before)
        if decision != "deny":
            # A single non-duplicate target releases the whole call. Persist only
            # entries whose deny counter shrank (a change or an honoured insist);
            # never persist a bump that did not result in a deny.
            for k, (e, b) in updated.items():
                if len(e.get("denied") or {}) <= b:
                    cache[k] = e
            C.save_cache(cpath, cache)
            return
        # `np` is case-folded for keying; show the name the caller actually used.
        hits.append((np, span, (cache.get(np) or {}).get("ts") or "",
                     os.path.basename(raw.replace("\\", "/").rstrip("/")) or raw))

    for k, (e, _b) in updated.items():
        cache[k] = e
    C.save_cache(cpath, cache)

    saved = sum(C.span_bytes(np, span) for np, span, _, _ in hits)
    bump_stats(len(hits), saved)

    what = "; ".join("%s lines %d-%d" % (name, s[0], s[1]) for _, s, _, name in hits)
    when = hits[0][2][11:19] if len(hits[0][2]) >= 19 else "earlier"
    reason = (
        "read-cache: %s already in this context (read at %s; unchanged since "
        "- same mtime and size). Re-reading re-inserts ~%s tokens that stay in "
        "the window for the rest of the session. Scroll up to the earlier result "
        "instead. If you genuinely need it again, issue the identical call once "
        "more and the cache will stand aside."
        % (what, when, format(max(1, saved // 4), ","))
    )
    deny(reason)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass          # fail-open: never block a tool call because of a hook bug
    sys.exit(0)
