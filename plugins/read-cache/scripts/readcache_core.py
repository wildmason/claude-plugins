"""readcache_core - decision logic for the read-cache hook.

The premise: a Claude Code transcript only grows. Every file a tool reads is
pasted into the context and stays there until compaction, and the whole
transcript is re-sent on every turn. Reading the same unchanged file twice
therefore does not cost tokens once - it costs context-window space for the
rest of the session, and brings the next compaction forward.

This module decides whether a read is a genuine duplicate. It never
summarises and never drops information: a DENY is only ever issued when the
identical bytes are provably already in the transcript.

Design rules that the tests pin down:

* Range-aware. `sed -n '1,50p' f` then `sed -n '80,120p' f` are different
  reads, not duplicates. Only a span already fully covered is denied.
* Fingerprinted. Any change to mtime or size invalidates the entry, so an
  edited file always re-reads. (An Edit changes mtime, so this covers edits
  for free.)
* Truncation-aware. A bare Read stops at DEFAULT_READ_LIMIT lines, so it
  records lines 1..2000 of a 9000-line file - not the whole file.
* Never a hard block. Repeating a denied read immediately gets it through
  (`insist`). The cache can cost at most one cheap round-trip.
* Conservative parsing. Anything ambiguous in a Bash command is left alone.
  A missed duplicate is free; a false deny hides content from the agent.
"""
import json
import os
import re

# Claude Code's Read tool stops after this many lines when no limit is given.
DEFAULT_READ_LIMIT = 2000

# Bash tool results are truncated near this length. Output at or past it may
# be missing the tail of the file, so it must not be recorded as a full read.
BASH_TRUNCATION_CHARS = 30000

# Per-session cap on tracked files. Oldest touch is evicted first.
MAX_ENTRIES = 2000

HEAD_TAIL_DEFAULT = 10

# Files whose Read result is not line-addressable text.
OPAQUE_EXTS = frozenset((
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tif", ".tiff",
    ".pdf", ".ipynb", ".mp3", ".mp4", ".mov", ".wav", ".zip", ".gz", ".tar",
    ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf", ".otf",
))

READ_CMDS = frozenset(("cat", "bat", "head", "tail", "sed"))

_SED_RANGE = re.compile(r"^(\d+),(\d+)p$")
_SED_ONE = re.compile(r"^(\d+)p$")
_NUM_FLAG = re.compile(r"^-(\d+)$")
_DRIVE = re.compile(r"^[A-Za-z]:")
_GLOBBY = re.compile(r"[*?\[\]]")


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
def _is_abs(p):
    return p.startswith("/") or p.startswith("\\") or bool(_DRIVE.match(p))


def norm_path(path, cwd=None):
    """Canonical cache key for a file path. Case-folded on Windows."""
    if not path:
        return ""
    p = path.strip().strip('"').strip("'").replace("\\", "/")
    if p.startswith("//?/"):
        p = p[4:]
    if cwd and not _is_abs(p):
        p = cwd.strip().replace("\\", "/").rstrip("/") + "/" + p
    p = os.path.normpath(p).replace("\\", "/")
    if os.name == "nt":
        p = p.lower()
    return p


def is_opaque(path):
    """True when a Read of this file is not line-addressable text."""
    return os.path.splitext(path or "")[1].lower() in OPAQUE_EXTS


def line_count_of(path, max_bytes=20 * 1024 * 1024):
    """Line count of a local file, or None when it cannot be counted cheaply.

    Reads from local disk. Costs no tokens - it never enters the transcript.
    """
    try:
        if os.path.getsize(path) > max_bytes:
            return None
        n = 0
        with open(path, "rb") as fh:
            for _ in fh:
                n += 1
        return n
    except Exception:
        return None


def fingerprint_of(path):
    """[mtime_ns, size], or None when the file cannot be stat'd."""
    try:
        st = os.stat(path)
        return [st.st_mtime_ns, st.st_size]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# span arithmetic
# ---------------------------------------------------------------------------
def merge_span(spans, span):
    """Union `span` into `spans`. Returns a sorted list of disjoint tuples.

    Adjacent spans coalesce: lines 1-50 plus 51-100 is one 1-100 range.
    """
    items = [(int(a), int(b)) for a, b in (spans or [])]
    if span:
        items.append((int(span[0]), int(span[1])))
    items.sort()
    out = []
    for a, b in items:
        if out and a <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def covers(spans, span):
    """True only when a single recorded span fully contains `span`."""
    if not span:
        return False
    a, b = int(span[0]), int(span[1])
    for s in spans or ():
        if int(s[0]) <= a and b <= int(s[1]):
            return True
    return False


def read_span(tool_input, line_count):
    """The line range a Read tool call will actually return, or None."""
    ti = tool_input if isinstance(tool_input, dict) else {}
    try:
        start = max(1, int(ti.get("offset") or 1))
    except (TypeError, ValueError):
        start = 1
    try:
        limit = int(ti.get("limit") or 0) or DEFAULT_READ_LIMIT
    except (TypeError, ValueError):
        limit = DEFAULT_READ_LIMIT
    if line_count is not None:
        if line_count <= 0 or start > line_count:
            return None
    end = start + limit - 1
    if line_count is not None:
        end = min(end, line_count)
    return (start, end)


def resolve_spec(spec, line_count):
    """Turn a parsed Bash read spec into a concrete line span, or None."""
    if not spec:
        return None
    kind = spec[0]
    if kind == "full":
        if line_count is None or line_count <= 0:
            return None
        return (1, line_count)
    if kind == "head":
        n = max(1, int(spec[1]))
        return (1, n if line_count is None else min(n, line_count))
    if kind == "tail":
        if line_count is None or line_count <= 0:
            return None
        n = max(1, int(spec[1]))
        return (max(1, line_count - n + 1), line_count)
    if kind == "lines":
        a, b = int(spec[1]), int(spec[2])
        if line_count is not None:
            if a > line_count:
                return None
            b = min(b, line_count)
        if b < a:
            return None
        return (a, b)
    return None


# ---------------------------------------------------------------------------
# Bash command parsing
# ---------------------------------------------------------------------------
def _split_top(command):
    """Split a command line into (chain_index, segment) honouring quotes.

    Chains break on ; && || and newline. Within a chain, only the first
    pipeline stage can read a file - later stages filter stdin.
    """
    segs, buf, chain, quote = [], [], 0, None
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            buf.append(ch)
            i += 1
            continue
        two = command[i:i + 2]
        if two in ("&&", "||"):
            segs.append((chain, "".join(buf)))
            buf = []
            chain += 1
            i += 2
            continue
        if ch in ";\n":
            segs.append((chain, "".join(buf)))
            buf = []
            chain += 1
            i += 1
            continue
        if ch == "|":
            segs.append((chain, "".join(buf)))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    segs.append((chain, "".join(buf)))
    return segs


def _tokens(segment):
    """Split a segment into words, keeping backslashes intact.

    POSIX-mode shlex treats `\\` as an escape, which mangles Windows paths
    (`C:\\repo\\a.ts` becomes `C:repoa.ts`). Non-POSIX mode keeps them, at
    the cost of leaving quotes on the tokens - stripped here.
    """
    import shlex
    try:
        lex = shlex.shlex(segment, posix=False)
        lex.whitespace_split = True
        lex.commenters = ""
        toks = list(lex)
    except Exception:
        return []
    out = []
    for t in toks:
        if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
            t = t[1:-1]
        out.append(t)
    return out


def _spec_from_tokens(toks):
    """(spec, operand) for a recognised read command, else (None, None)."""
    cmd = toks[0]
    rest = toks[1:]

    if cmd in ("cat", "bat"):
        ops = [t for t in rest if not t.startswith("-")]
        return (("full",), ops[0]) if len(ops) == 1 else (None, None)

    if cmd in ("head", "tail"):
        n, ops, i = None, [], 0
        while i < len(rest):
            t = rest[i]
            if t in ("-f", "--follow", "-F"):
                return (None, None)          # streaming, not a bounded read
            m = _NUM_FLAG.match(t)
            if m:
                n = int(m.group(1))
            elif t in ("-n", "--lines"):
                i += 1
                if i >= len(rest):
                    return (None, None)
                try:
                    n = int(rest[i].lstrip("+"))
                except ValueError:
                    return (None, None)
            elif t.startswith("-n"):
                try:
                    n = int(t[2:])
                except ValueError:
                    return (None, None)
            elif t.startswith("-"):
                return (None, None)          # unknown flag: stay conservative
            else:
                ops.append(t)
            i += 1
        if len(ops) != 1:
            return (None, None)
        return ((cmd, n if n is not None else HEAD_TAIL_DEFAULT), ops[0])

    if cmd == "sed":
        if "-i" in rest or any(t.startswith("--in-place") for t in rest):
            return (None, None)              # a write, not a read
        if "-n" not in rest:
            return (None, None)
        ops = [t for t in rest if not t.startswith("-")]
        if len(ops) != 2:
            return (None, None)
        script, operand = ops
        m = _SED_RANGE.match(script)
        if m:
            return (("lines", int(m.group(1)), int(m.group(2))), operand)
        m = _SED_ONE.match(script)
        if m:
            return (("lines", int(m.group(1)), int(m.group(1))), operand)
        return (None, None)

    return (None, None)


def parse_bash_reads(command):
    """Extract [(path, spec)] for the file reads a shell command performs.

    Deliberately narrow. Substitutions, heredocs, redirections, globs and
    multi-file operands all disable parsing, because a wrong entry here
    becomes a false DENY later.
    """
    if not command or not isinstance(command, str):
        return []
    if "$(" in command or "`" in command or "<<" in command:
        return []

    out, base, seen_chain = [], None, set()
    for chain, seg in _split_top(command):
        raw = seg.strip()
        if not raw:
            continue
        first_in_chain = chain not in seen_chain
        seen_chain.add(chain)

        toks = _tokens(raw)
        if not toks:
            continue
        if toks[0] == "sudo":
            toks = toks[1:]
            if not toks:
                continue
        if toks[0] == "cd" and len(toks) >= 2:
            base = toks[1]
            continue
        if not first_in_chain:
            continue                          # downstream of a pipe: filters stdin
        if toks[0] not in READ_CMDS:
            continue
        if ">" in raw or "<" in raw:
            continue                          # redirection: not a plain read

        spec, operand = _spec_from_tokens(toks)
        if not spec or not operand or _GLOBBY.search(operand):
            continue
        path = operand
        if base and not _is_abs(path):
            path = base.replace("\\", "/").rstrip("/") + "/" + path
        out.append((path, spec))
    return out


# ---------------------------------------------------------------------------
# decision + recording
# ---------------------------------------------------------------------------
def evaluate(entry, fp, span):
    """Decide one read. Returns (decision, reason, updated_entry).

    `decision` is "allow" or "deny". The caller must persist `updated_entry`
    so the insist counter survives to the next call.
    """
    if entry is None:
        return ("allow", "not read yet in this session", None)
    if list(entry.get("fp") or []) != list(fp or []):
        e = dict(entry)
        e["denied"] = {}
        return ("allow", "file changed on disk since the cached read", e)
    if not covers(entry.get("spans") or [], span):
        return ("allow", "requested range was not previously read", entry)

    key = "%d-%d" % (span[0], span[1])
    denied = dict(entry.get("denied") or {})
    e = dict(entry)
    if denied.get(key, 0) >= 1:
        denied.pop(key, None)
        e["denied"] = denied
        return ("allow", "re-read insisted on; cache stood aside", e)
    denied[key] = denied.get(key, 0) + 1
    e["denied"] = denied
    return ("deny", "already in context and unchanged on disk", e)


def record(cache, path, fp, span, ts):
    """Merge a completed read into the cache, evicting the oldest if full."""
    e = cache.get(path)
    if e is None or list(e.get("fp") or []) != list(fp or []):
        e = {"fp": list(fp or []), "spans": [], "denied": {}, "ts": ts}
    e["spans"] = [list(s) for s in merge_span(e.get("spans") or [], span)]
    e["ts"] = ts
    cache[path] = e
    while len(cache) > MAX_ENTRIES:
        oldest = min(cache, key=lambda k: cache[k].get("ts") or "")
        cache.pop(oldest, None)
    return cache


# ---------------------------------------------------------------------------
# tool-response sanity
# ---------------------------------------------------------------------------
_ERROR_MARKERS = ("error:", "enoent", "eacces", "no such file",
                  "permission denied", "<tool_use_error>")


def response_ok(resp):
    """False when a tool response indicates the content never landed."""
    if isinstance(resp, dict):
        if resp.get("is_error") or resp.get("isError"):
            return False
        txt = ""
        for k in ("stdout", "content", "text", "file"):
            v = resp.get(k)
            if isinstance(v, str):
                txt += v
        if not txt:
            return True
    elif isinstance(resp, str):
        txt = resp
    else:
        return True
    head = txt.lstrip()[:200].lower()
    return not any(m in head for m in _ERROR_MARKERS)


def looks_truncated(text):
    """True when a Bash result may be missing the tail of the file."""
    if not isinstance(text, str):
        return False
    if len(text) >= BASH_TRUNCATION_CHARS:
        return True
    tail = text[-400:].lower()
    return "<truncated>" in tail or "output truncated" in tail


# ---------------------------------------------------------------------------
# cache file I/O
# ---------------------------------------------------------------------------
def cache_dir():
    return os.environ.get("READCACHE_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude", "read-cache")


def cache_path(session_id, agent_id=None):
    """One cache per context. A subagent has its own window, so its reads
    must never be deduplicated against the main thread's."""
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id or "unknown"))[:80]
    aid = re.sub(r"[^A-Za-z0-9_.-]", "_", str(agent_id or "main"))[:40]
    return os.path.join(cache_dir(), "%s__%s.json" % (sid, aid))


def load_cache(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cache(path, cache):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def disabled():
    return os.environ.get("READCACHE_DISABLE", "") == "1"


def command_is_only_reads(command):
    """True when reading files is ALL a shell command does.

    A Bash call may only be denied under this condition. `cat a.ts && cargo
    build` reads a duplicate file but also runs a build; denying it would
    cancel the build. `cat a.ts | grep foo` returns filtered output, not the
    file, so it is not a duplicate either.
    """
    if not command or not isinstance(command, str):
        return False
    if "$(" in command or "`" in command or "<<" in command:
        return False
    found, seen_chain = False, set()
    for chain, seg in _split_top(command):
        raw = seg.strip()
        if not raw:
            continue
        first_in_chain = chain not in seen_chain
        seen_chain.add(chain)
        toks = _tokens(raw)
        if not toks:
            return False
        if toks[0] == "sudo":
            toks = toks[1:]
        if not toks:
            return False
        if toks[0] == "cd" and len(toks) >= 2:
            continue
        if not first_in_chain or toks[0] not in READ_CMDS:
            return False
        if ">" in raw or "<" in raw:
            return False
        spec, operand = _spec_from_tokens(toks)
        if not spec or not operand or _GLOBBY.search(operand):
            return False
        found = True
    return found


def span_bytes(path, span):
    """Byte size of a line span on disk. Used to report what a DENY saved.

    Reads locally, so it costs no tokens. Returns 0 when unreadable.
    """
    if not span:
        return 0
    a, b = int(span[0]), int(span[1])
    total = 0
    try:
        with open(path, "rb") as fh:
            for i, line in enumerate(fh, 1):
                if i < a:
                    continue
                if i > b:
                    break
                total += len(line)
    except Exception:
        return 0
    return total
