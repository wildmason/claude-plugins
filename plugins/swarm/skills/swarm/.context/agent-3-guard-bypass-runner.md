# Agent-3: Security Guard Bypass in Runner — T3

## Task Assignment

**T3: Fix Security Guard Bypass in Runner**

## Overview

The collection runner builds its own HTTP client without rate limiting, body size caps, or redirect SSRF protection. It bypasses all the security guards present in the main `send_request()` path. This needs to be refactored to reuse the protected HTTP path.

## Files You Own

- `src/commands/runner.rs` — HTTP client building and request execution (lines 221-224, 277-310)
- Reference: `src/commands/http.rs` — see `send_protected_http_request()` implementation

## What to Do

### 1. Analyze the gap

Current runner implementation at lines 221-224 builds a plain reqwest client:
```rust
let client = reqwest::Client::builder()
    .timeout(Duration::from_secs(timeout_secs))
    .build()?;
```

Missing guards:
- ❌ Rate limiting via RateLimiter
- ❌ 10MB body size cap
- ❌ Redirect SSRF protection
- ❌ Retry-After handling

Main `send_request()` path uses `send_protected_http_request()` which enforces all these.

### 2. Refactor to reuse protected HTTP logic

**Strategy:** Refactor runner to call the shared protected HTTP path.

Steps:
1. Extract the HTTP request building/sending logic from runner
2. Call `send_protected_http_request()` instead of building raw client
3. Pass request config to the protected path
4. Preserve per-request client config options (TLS, proxy, cookie jar settings)

OR create a new helper function in http.rs that both send_request and runner can call:
```rust
async fn execute_http_request(
    client: &reqwest::Client,
    method: Method,
    url: &str,
    rate_limiter: &RateLimiter,
    // ... other params
) -> Result<Response>
```

**Recommended:** Option 1 — refactor to call `send_protected_http_request()` with appropriate request parameters

### 3. Implementation details

- Ensure rate limiter is passed and checked before making request
- Ensure response body is capped at MAX_BODY_BYTES (10MB)
- Ensure Retry-After handling is applied
- Ensure redirect SSRF protection is applied (it's in the redirect callback)
- Maintain backward compatibility with collection runner behavior

### 4. Add tests

Create tests verifying guards are enforced in runner:
- **test_runner_respects_rate_limit** — request blocked when rate limit exceeded
- **test_runner_response_capped_at_10mb** — oversized response rejected
- **test_runner_respects_retry_after** — runner pauses when Retry-After header present
- **test_collection_execution_respects_rate_limits** — full collection execution respects rate limits

## Success Criteria

✅ Runner uses same security guards as send_request
✅ Rate limiting enforced in runner
✅ Body size cap enforced (10MB)
✅ Redirect SSRF protection applied
✅ Retry-After handling applied
✅ All tests pass (existing + new)
✅ Code committed

## Estimated Time

180 minutes (includes refactoring and testing)

## Dependencies

**After T1** — T1's method validation should be complete first so runner validates methods before this refactor

## Testing Instructions

Run: `cargo test --lib` — all tests should pass
Manual test: Run a collection with rate limiting enabled and verify requests are spaced appropriately
