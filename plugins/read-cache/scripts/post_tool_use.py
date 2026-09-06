#!/usr/bin/env python3
"""PostToolUse - record a read whose result actually landed in the context.

Recording happens here rather than in PreToolUse so that a failed, denied or
truncated read is never mistaken for content the agent holds.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import readcache_core as C  # noqa: E402


def response_text(resp):
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        for k in ("stdout", "content", "text", "file"):
            v = resp.get(k)
            if isinstance(v, str):
                return v
            if isinstance(v, dict) and isinstance(v.get("content"), str):
                return v["content"]
    return ""


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
    resp = data.get("tool_response")
    if not C.response_ok(resp):
        return

    cwd = data.get("cwd") or ""
    ts = data.get("timestamp") or __import__("datetime").datetime.now().isoformat(timespec="seconds")

    if tool == "Read":
        raw = ti.get("file_path") or ""
        if not raw:
            return
        items = [(raw, "read", ti)]
    elif tool in ("Bash", "PowerShell"):
        cmd = ti.get("command") or ""
        # Same gate as the deny path: only when the output IS the file verbatim.
        if not C.command_is_only_reads(cmd):
            return
        if C.looks_truncated(response_text(resp)):
            return                                  # tail of the file never arrived
        items = [(p, "spec", spec) for p, spec in C.parse_bash_reads(cmd)]
    else:
        return
    if not items:
        return

    cpath = C.cache_path(data.get("session_id"), data.get("agent_id"))
    cache = C.load_cache(cpath)
    changed = False
    for raw, kind, payload in items:
        np = C.norm_path(raw, cwd)
        if not np or C.is_opaque(np):
            continue
        fp = C.fingerprint_of(np)
        if fp is None:
            continue
        lc = C.line_count_of(np)
        span = C.read_span(payload, lc) if kind == "read" else C.resolve_spec(payload, lc)
        if span is None:
            continue
        C.record(cache, np, fp, span, ts)
        changed = True
    if changed:
        C.save_cache(cpath, cache)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
