# Agent-6: OpenAPI Import Body Size Cap — T8

## Task Assignment

**T8: Fix import_openapi_url Unbounded Response Body**

## Overview

The `import_openapi_url()` function fetches remote OpenAPI specs without a response body size limit. The main HTTP path caps at 10MB; remote OpenAPI import doesn't, creating a resource exhaustion vulnerability.

## Files You Own

- `src/commands/import_export.rs` — import_openapi_url function (line 480-501)
- Reference: `src/commands/http.rs` — MAX_BODY_BYTES constant and body size limiting logic (lines 441-448)

## What to Do

### 1. Understand the gap

Current implementation at line 498:
```rust
let content = resp.text().await?;
```

This reads the entire response body into memory without any limit. A malicious/compromised URL could return multi-gigabyte data causing OOM.

Main HTTP path prevents this with streaming and byte counter (see http.rs:441-448).

### 2. Add body size limit

Define a reasonable limit for OpenAPI specs (e.g., 50MB — generous for legitimate specs):

```rust
const MAX_OPENAPI_IMPORT_SIZE: u64 = 50 * 1024 * 1024; // 50MB
```

### 3. Implement size checking

Option A: Check content-length before reading:
```rust
if let Some(content_length) = resp.content_length() {
    if content_length > MAX_OPENAPI_IMPORT_SIZE {
        return Err(MortarError::Data("OpenAPI spec too large".to_string()));
    }
}
let content = resp.text().await?;
```

Option B: Stream and accumulate with byte counter:
```rust
let mut buffer = Vec::new();
let mut stream = resp.bytes_stream();
while let Some(chunk) = stream.next().await {
    let chunk = chunk?;
    buffer.extend_from_slice(&chunk);
    if buffer.len() > MAX_OPENAPI_IMPORT_SIZE as usize {
        return Err(MortarError::Data("OpenAPI spec too large".to_string()));
    }
}
let content = String::from_utf8(buffer)?;
```

**Recommended:** Option A is simpler and sufficient (most servers set content-length).

### 4. Error handling

Return appropriate error:
```rust
MortarError::Data(format!("OpenAPI spec exceeds {} MB limit",
    MAX_OPENAPI_IMPORT_SIZE / (1024 * 1024)))
```

### 5. Add tests

Create tests verifying:
- **test_import_small_openapi** — small spec (<1MB) imports successfully
- **test_import_large_valid_openapi** — large but valid spec (5MB) imports successfully
- **test_import_oversized_openapi** — oversized response (>limit) rejected with error
- **test_import_malicious_content_length** — response claiming huge content-length rejected

## Success Criteria

✅ Response body size limited to reasonable cap (50MB)
✅ Malicious/oversized responses rejected with clear error
✅ Legitimate imports unaffected
✅ Tests added and passing
✅ Code committed
✅ CWE-400 (Resource Exhaustion) mitigated

## Estimated Time

75 minutes

## Dependencies

None — independent work

## Testing Instructions

Run: `cargo test --lib` — verify all tests pass
Manual test: Create a test server that returns oversized response and verify import fails appropriately
