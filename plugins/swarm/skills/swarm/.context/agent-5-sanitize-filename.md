# Agent-5: sanitize_filename Empty String Fix — T7

## Task Assignment

**T7: Fix sanitize_filename Returning Empty String**

## Overview

The `sanitize_filename()` function can return an empty string for pathological inputs (all punctuation/symbols), leading to invalid filenames like `.toml`. This needs a fallback for edge cases.

## Files You Own

- `src/commands/import_export.rs` — sanitize_filename function and callers

## What to Do

### 1. Understand the issue

Current implementation:
```rust
fn sanitize_filename(name: &str) -> String {
    name
        .chars()
        .map(|c| if c.is_alphanumeric() || c == '-' || c == '_' || c == '.' { c } else { '_' })
        .collect::<String>()
        .trim_matches('_')
        .to_string()
}
```

Problem: For `sanitize_filename("!!!###")`:
1. All chars become `_`: `"___"`
2. trim_matches('_') removes all: `""`
3. Result: empty string

Usage: `format!("{}.toml", sanitize_filename(&name))` → `.toml` (invalid filename)

### 2. Fix by adding fallback

Modify `sanitize_filename()` to return a default when result is empty:

```rust
fn sanitize_filename(name: &str) -> String {
    let result = name
        .chars()
        .map(|c| if c.is_alphanumeric() || c == '-' || c == '_' || c == '.' { c } else { '_' })
        .collect::<String>()
        .trim_matches('_')
        .to_string();

    if result.is_empty() {
        "unnamed".to_string()
    } else {
        result
    }
}
```

Alternative: Use UUID for truly unique fallback:
```rust
if result.is_empty() {
    uuid::Uuid::new_v4().to_string()
} else {
    result
}
```

**Recommended:** Use `"unnamed"` for simplicity and UX clarity. If multiple files need this fallback, they'll still be distinguishable during import process.

### 3. Verify all callers

Callers of `sanitize_filename()`:
- `import_postman_items()` — line 236
- `import_insomnia()` — line 371
- `inner_import_openapi()` — line 451

All will automatically benefit from the fix since it's in the function definition.

### 4. Add tests

Create tests verifying:
- **test_sanitize_filename_all_punctuation** — `sanitize_filename("!!!###")` returns `"unnamed"`
- **test_sanitize_filename_all_underscores** — `sanitize_filename("___")` returns `"unnamed"`
- **test_sanitize_filename_valid_name** — `sanitize_filename("valid-name")` returns `"valid-name"`
- **test_sanitize_filename_mixed_input** — `sanitize_filename("test!!!name")` returns `"test___name"` (then trimmed)
- **test_import_with_pathological_name** — import with pathological name creates file with `"unnamed"` fallback name

## Success Criteria

✅ `sanitize_filename()` never returns empty string
✅ Pathological inputs get sensible fallback
✅ All imports succeed with edge-case names
✅ Tests added and passing
✅ Code committed
✅ CWE-20 (Improper Input Validation) mitigated

## Estimated Time

60 minutes

## Dependencies

None — independent work

## Testing Instructions

Run: `cargo test --lib` — verify all tests pass
Manual test: Try importing with filename like "!!!###" and verify it creates a file named "unnamed.toml"
