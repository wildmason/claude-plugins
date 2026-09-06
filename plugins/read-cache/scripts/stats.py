#!/usr/bin/env python3
"""Report what the read-cache has actually saved. Run it directly:

    python scripts/stats.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import readcache_core as C  # noqa: E402


def main():
    d = C.cache_dir()
    s = C.load_cache(os.path.join(d, "stats.json"))
    denies = int(s.get("denies") or 0)
    saved = int(s.get("bytes_saved") or 0)

    live, files, spans = 0, 0, 0
    try:
        for name in os.listdir(d):
            if not name.endswith(".json") or name == "stats.json":
                continue
            live += 1
            cache = C.load_cache(os.path.join(d, name))
            files += len(cache)
            spans += sum(len(e.get("spans") or []) for e in cache.values())
    except Exception:
        pass

    print("read-cache stats  (%s)" % d)
    print("  duplicate reads blocked : %s" % format(denies, ","))
    print("  context bytes not spent : %s  (~%s tokens)"
          % (format(saved, ","), format(saved // 4, ",")))
    print("  live caches             : %d  (%d files, %d spans)" % (live, files, spans))
    if denies:
        print("  average per block       : %s bytes" % format(saved // denies, ","))


if __name__ == "__main__":
    main()
