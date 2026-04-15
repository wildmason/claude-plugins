# Agent-2: SSRF DNS Rebinding Fix — T2

## Task Assignment

**T2: Fix SSRF Bypass via DNS Rebinding on Redirects**

## Overview

The redirect callback in HTTP handling uses string-based domain checking instead of DNS resolution, vulnerable to DNS rebinding attacks. An attacker can set up a domain that resolves to a public IP initially, then rebind to 127.0.0.1 for the redirect.

## Files You Own

- `src/commands/http.rs` — SSRF redirect validation fix (line 564)
- Reference: `src/commands/http.rs:368` — correct DNS resolution implementation

## What to Do

### 1. Understand the vulnerability

Line 368 correctly uses DNS resolution:
```rust
is_private_network_url_resolved(&url)
```

But line 564 in the redirect callback uses string-based checking:
```rust
is_private_network_url(attempt.url().as_str())
```

The string-based check cannot detect DNS rebinding because it only looks at the domain name, not the actual IP it resolves to.

### 2. Fix the redirect callback

Replace line 564 to use DNS resolution:
```rust
// Option 1: Call is_private_network_url_resolved() for redirect target
if let Ok(is_private) = is_private_network_url_resolved(attempt.url().as_str()) {
    if is_private {
        return Err(MortarError::Security("Redirect target is private network".to_string()));
    }
}

// Option 2: Pre-resolve and check the target IP
```

The recommended approach is Option 1 — use the same `is_private_network_url_resolved()` function that already works for initial requests.

### 3. Handle DNS resolution failures

If DNS resolution fails (unknown host), decide on behavior:
- Option A: Block redirect (safer, might break some legitimate redirects)
- Option B: Allow redirect (same as current behavior, less safe)

Recommend Option A for security — if we can't verify the target is public, don't redirect.

### 4. Add tests

Create tests verifying:
- **test_redirect_to_localhost_blocked** — redirect to 127.0.0.1 rejected
- **test_redirect_to_private_ips_blocked** — redirects to 10.x, 172.16.x, 192.168.x rejected
- **test_redirect_to_public_ip_allowed** — valid public IP redirects work
- **test_redirect_to_public_domain_allowed** — valid public domain redirects work
- **test_dns_rebinding_attack_blocked** — domain that rebinds from public to private is blocked

## Success Criteria

✅ Redirect targets validated via DNS resolution
✅ Private network addresses blocked (including 127.0.0.1)
✅ Public redirects still work
✅ No regression in valid redirect handling
✅ Tests added and passing
✅ Code committed
✅ CWE-918 (SSRF) mitigated

## Estimated Time

120 minutes

## Dependencies

None — independent work

## Testing Instructions

Run: `cargo test --lib` to verify all tests pass

Consider manual testing with a local redirect server to verify DNS rebinding protection works.
