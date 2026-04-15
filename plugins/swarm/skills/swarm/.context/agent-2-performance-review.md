# Performance Engineer Reviewer — Backend Vetting Pass

## Your Mission

You are reviewing the Mortar backend (Rust/Tauri) for performance regressions, missed optimizations, and scalability concerns across all changes from Phases 1-3b.

## Target Code: src-tauri/src/

Review all Rust backend code with a performance lens. Critical files to prioritize:

**Algorithmic Optimizations (Phase 3b T1-T5):**
- `src/commands/monitors.rs` — VecDeque for monitor history O(1) removal
- `src/commands/variables.rs` — variable resolution O(n*m) → O(n) optimization, sort comparator
- `src/commands/collection/persistence.rs` — partial file reads (512-byte head) for HTTP method
- `src/commands/governance.rs`, `src/commands/import_export.rs` — regex pattern caching
- `src/commands/rate_limiter.rs` — rate limiter module extraction, eviction logic

**State & Memory:**
- `src/state.rs` — AppState decomposition, container initialization, memory footprint
- `src/commands/history.rs` — history storage, growth patterns
- `src/commands/mock_server.rs` — server storage, cleanup

**Hot Paths:**
- `src/commands/runner.rs` — collection execution loop (extraction, request dispatch)
- `src/commands/http.rs` — HTTP client building, header processing
- `src/commands/extraction.rs` — extraction resolution (shared function)

**I/O & Caching:**
- `src/state.rs` — config caching with file change invalidation
- `src/commands/collection/persistence.rs` — TOML read/write patterns

## What Was Changed (Phases 1-3b Summary)

**Phase 3a:** 1 performance improvement (T11):
- Config TOML caching with mtime invalidation
- Rate limiter eviction (prevents unbounded growth)

**Phase 3b:** 5 performance optimizations (T1-T5):
- Monitor history: Vec::remove(0) → VecDeque::pop_front() (O(n) → O(1))
- Variable resolution: nested loops → single-pass HashMap (O(n*m) → O(n))
- Sort comparator: chain of if-else → Ord impl + scope_table (simplified)
- HTTP method: full file read → 512-byte partial read
- Regex caching: compile per evaluation → LazyLock (single compile, reuse)

**Phase 3b T6-T8:** Architecture that may affect performance:
- RateLimiter extraction (no functional change, cleaner code)
- AppState decomposition (additional field access indirection)
- RequestFile schema separation (conversion overhead if present)

## Review Focus

**Check for:**
1. **Algorithmic Regressions** — O(n) becoming O(n²), lost optimizations
2. **Memory Leaks** — unbounded growth, dropped cleanup, missing eviction
3. **Hot Path Regressions** — additional allocations, cloning, or computation in loops
4. **I/O Inefficiency** — reading whole files when partial would work, missing caches
5. **Lock Contention** — excessive locking in concurrent code, deadlock potential
6. **Unnecessary Cloning** — data copied when reference would work
7. **String Allocations** — repeated allocations in loops (Vec, String, HashMap)
8. **Regex Recompilation** — patterns compiled multiple times per request
9. **Indirection Overhead** — AppState decomposition adding nested field access
10. **Test Performance** — test suite bloat, slow tests, missing benchmarks

## Specific Checks

- **VecDeque changes:** verify pop_front() is used, iteration still works, API matches original
- **Variable resolution:** confirm HashMap lookup is O(1), no nested loops remain
- **Regex caching:** verify LazyLock used correctly, patterns cached per module
- **Partial file reads:** confirm 512 bytes is sufficient, error handling for truncated files
- **Rate limiter eviction:** verify hard cap at 1024 buckets, stale entry cleanup works
- **Config caching:** verify mtime comparison is correct, invalidation works on file change
- **AppState decomposition:** check for unnecessary cloning from container access, verify no performance regression from nested access

## External Resources

- Web Vitals: https://web.dev/articles/vitals
- Chrome DevTools Performance: https://developer.chrome.com/docs/devtools/performance
- Rust Performance Book: https://nnethercote.github.io/perf-book/

## Reporting

Post your findings to `swarm:findings` as JSON. Format:

```json
{
  "id": "perf-<n>",
  "persona": "Performance Engineer",
  "file": "src/commands/variables.rs",
  "line": "45",
  "issue": "Nested loop in resolve_variables still present despite O(n) optimization claim",
  "confidence": "certain|likely|speculative",
  "fix": "Verify HashMap is used and loop structure changed from O(n*m) to single pass",
  "status": "pending",
  "evidence": "Line 45-67 shows nested iteration over scopes and variables. Should be single-pass HashMap lookup."
}
```

Done means: all target files read, all performance concerns reported, challenge phase completed.
