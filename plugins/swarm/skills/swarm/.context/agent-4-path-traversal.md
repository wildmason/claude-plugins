# Agent-4: Path Traversal Validation on Reads — T6

## Task Assignment

**T6: Fix Missing Path Traversal Validation on Read Operations**

## Overview

Several read-only file operations lack path traversal validation, while write/delete operations all validate correctly. This is an inconsistency that should be fixed for defense-in-depth, even though the practical risk in Tauri (local user) is lower than write operations.

## Files You Own

- `src/commands/collection/handlers.rs` — multiple read commands need validation

## What to Do

### 1. Identify operations needing validation

These operations lack `reject_path_traversal()` checks:
- `read_request()` — line 83
- `list_requests()` — line 77
- `read_environment()` — line 236
- `list_environments()` — line 231
- `read_collection_config()` — line 241

These operations DO have validation (correct pattern):
- `write_request()` — line 89
- `delete_request()` — line 100
- `save_text_file()` — filesystem.rs
- `read_text_file()` — filesystem.rs

### 2. Add validation to read operations

For each operation, add at the start (before any file access):
```rust
reject_path_traversal(&path)?;
```

Reference the `security.rs:reject_path_traversal()` function which blocks:
- `../` sequences
- Absolute paths
- Drive letters (Windows)
- Other path traversal patterns

### 3. Example fix

Before:
```rust
#[tauri::command]
async fn read_request(path: String) -> Result<...> {
    inner_read_request(&path).await
}
```

After:
```rust
#[tauri::command]
async fn read_request(path: String) -> Result<...> {
    reject_path_traversal(&path)?;
    inner_read_request(&path).await
}
```

Apply same pattern to all 5 operations.

### 4. Add tests

Create tests verifying path traversal is blocked:
- **test_read_request_blocks_path_traversal** — reject `../../../etc/passwd`
- **test_list_requests_blocks_path_traversal** — reject traversal attempts
- **test_read_environment_blocks_path_traversal** — reject traversal
- **test_list_environments_blocks_path_traversal** — reject traversal
- **test_read_collection_config_blocks_path_traversal** — reject traversal
- **test_valid_relative_paths_still_work** — verify legitimate paths like `collections/my-collection/requests/get.toml` work

Test both Unix-style (`../`) and Windows-style (`..\..\`) path traversal.

## Success Criteria

✅ All read operations validate paths before filesystem access
✅ Path traversal attempts rejected with clear error
✅ Valid relative paths still work
✅ Consistency with write/delete operations
✅ All tests pass
✅ Code committed
✅ CWE-22 (Path Traversal) mitigated

## Estimated Time

90 minutes

## Dependencies

None — independent work

## Testing Instructions

Run: `cargo test --lib` — verify all tests pass including new path traversal tests
