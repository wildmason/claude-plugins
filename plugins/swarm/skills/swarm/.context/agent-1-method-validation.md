# Agent-1: HTTP Method Validation Fix — T1

## Task Assignment

**T1: Fix HTTP Method Validation Bypass in Runner & Monitors**

## Overview

The runner and monitors accept arbitrary HTTP methods (TRACE, CONNECT) without calling `validate_method()`, bypassing security controls present in the main `send_request()` path. This needs to be fixed in both execution paths.

## Files You Own

- `src/commands/runner.rs` — HTTP method validation in collection runner
- `src/commands/monitors.rs` — HTTP method validation in monitor execution
- Reference only: `src/commands/http.rs` — see how `validate_method()` is implemented

## What to Do

### 1. Add validation to runner.rs

Line 291 currently creates a reqwest Method directly:
```rust
reqwest::Method::from_bytes(req.method.as_bytes())
```

Add validation before this:
```rust
if !crate::commands::http::validate_method(&req.method) {
    return Err(MortarError::Validation(format!("Invalid HTTP method: {}", &req.method)));
}
let method = reqwest::Method::from_bytes(req.method.as_bytes())?;
```

### 2. Add validation to monitors.rs

Line 167 has the same issue — direct method creation without validation:
```rust
let method = reqwest::Method::from_bytes(req_file.method.as_bytes())?;
```

Add the same validation check before this line.

### 3. Reference implementation

Check `http.rs:507` to see how `validate_method()` is called in the main path:
```rust
if !crate::commands::http::validate_method(&method) {
    return Err(MortarError::Validation(...));
}
```

The function blocks TRACE and CONNECT methods per CWE-749 (Exposed Dangerous Method).

### 4. Add tests

Create tests in both files:
- **test_runner_rejects_trace_method** — verify TRACE rejected
- **test_runner_rejects_connect_method** — verify CONNECT rejected
- **test_monitor_rejects_trace_method** — verify TRACE rejected in monitors
- **test_monitor_rejects_connect_method** — verify CONNECT rejected in monitors
- **test_valid_methods_still_work** — verify GET, POST, PUT, DELETE all work

## Success Criteria

✅ Runner rejects TRACE/CONNECT with validation error
✅ Monitors rejects TRACE/CONNECT with validation error
✅ All existing tests pass
✅ No behavioral change for valid methods
✅ Tests added and passing
✅ Code committed

## Estimated Time

90 minutes

## Dependencies

None — this is independent work

## Testing Instructions

Run: `cargo test --lib` — all tests should pass, including new ones
