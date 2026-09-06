# read-cache

Stops Claude Code from re-reading files it already has.

## Why

A transcript only grows. Every file a tool reads is pasted into the context
and stays there until compaction, and the whole transcript is re-sent on
every turn. Reading the same unchanged file twice does not cost tokens once
— it costs context-window space for the rest of the session, and brings the
next compaction forward.

Measured across five weeks of real Claude Code transcripts on this machine
(1,251 sessions, 78.7 Mchars of tool output):

| | |
|---|---|
| File reading, share of main-thread tool output | **51%** |
| Duplicate `Read` calls (same file, same session) | 1,440 calls, **8.3%** of all tool output |
| Duplicate Bash file-reads | 2,114 calls, 6.4% of all tool output |

Roughly one tool call in twenty-five was re-reading something already in
context.

## What it does

Before a `Read`, `cat`, `sed -n`, `head` or `tail` runs, a hook asks two
questions: have we already read this file in this context, and has it
changed since? If it is already there and unchanged, the call is denied and
replaced with a one-line pointer to the earlier result.

Nothing is summarised and nothing is lost. Unlike a cheap-model delegation
scheme, a deny is only ever issued when the identical bytes are provably
still in the transcript.

## Safety rules

The cost asymmetry drives every design choice: a missed duplicate is free,
a false deny hides content from the agent. So:

- **Range-aware.** `sed -n '1,50p' f` then `sed -n '80,120p' f` are
  different reads. Only a span already fully covered is denied.
- **Fingerprinted.** Any change to mtime or size invalidates the entry, so
  an edited file always re-reads.
- **Truncation-aware.** A bare `Read` stops at 2,000 lines, so it records
  lines 1–2000 of a 9,000-line file, not the whole thing. Bash output past
  the truncation limit is not recorded at all.
- **Never blocks a command that does more than read.** `cat a.ts && cargo
  build` is always allowed; denying it would cancel the build. So is
  `cat a.ts | grep foo`, whose output is not the file.
- **Subagents get their own cache.** A subagent has a fresh context window,
  so the parent's reads are not in it.
- **Cleared on compaction.** After a compact the cached content is gone from
  the context, so every entry is dropped.
- **Never a hard block.** Repeating a denied read immediately gets it
  through. The cache can cost at most one cheap round-trip.
- **Fail-open.** Any missing field, unreadable file, parse miss or hook bug
  exits 0 and the call proceeds untouched.

## Install

```bash
claude plugin marketplace add wildmason/claude-plugins
claude plugin install read-cache@wildmason
```

Needs `python` on `PATH`. No other dependencies.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `READCACHE_DISABLE` | unset | `1` makes every hook an instant no-op |
| `READCACHE_DIR` | `~/.claude/read-cache` | Where per-session caches live |

## Measuring it

```bash
python scripts/stats.py
```

Reports duplicate reads blocked, context bytes not spent, and live caches.

## Tests

```bash
python -m unittest discover -s tests
```

106 tests: 78 on the decision core, 28 driving the real hook scripts over
stdin against files on disk.
