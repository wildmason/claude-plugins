#!/usr/bin/env python3
"""PreCompact / SessionEnd - drop this session's cache.

Compaction rewrites the transcript and discards the tool results it
summarises. After it runs, the cached file contents are no longer in the
context, so every entry must be forgotten or the next read would be denied
against content that no longer exists.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import readcache_core as C  # noqa: E402


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    sid = data.get("session_id")
    if not sid:
        return
    prefix = os.path.basename(C.cache_path(sid, "main")).rsplit("__", 1)[0] + "__"
    d = C.cache_dir()
    try:
        names = os.listdir(d)
    except Exception:
        return
    for name in names:
        if name.startswith(prefix) and name.endswith(".json"):
            try:
                os.remove(os.path.join(d, name))
            except Exception:
                pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
