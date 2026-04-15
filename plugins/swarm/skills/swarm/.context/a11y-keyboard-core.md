# Agent Briefing: A11y Keyboard Navigation — Core Widgets

You are implementing keyboard navigation fixes for the three most complex widgets in Helm. **You may ONLY edit `.ts` files in these directories:**
- `ui/src/app/features/shell/commit-list/commit-list.component.ts`
- `ui/src/app/features/shell/branch-sidebar/branch-sidebar.component.ts`
- `ui/src/app/features/shell/command-palette/command-palette.component.ts`

Also edit `.html` for branch-sidebar ONLY for `aria-setsize`/`aria-posinset` attributes (at-7).

Working directory: `C:\Users\Matt\Documents\development\@wildmason\helm`

## Fixes to Apply

### kb-4 / at-4: Commit list Arrow key navigation
**File:** `ui/src/app/features/shell/commit-list/commit-list.component.ts`

The commit list uses `role="listbox"` but each row is independently tabbable — no Arrow key navigation. The APG listbox pattern requires a single Tab stop with ArrowUp/ArrowDown moving the active item.

Read the existing `onCommitKeydown` handler and the component's focus management. Implement:
1. ArrowDown: move to next commit row (update selectedCommit or the focused index)
2. ArrowUp: move to previous commit row
3. Home: jump to first visible commit
4. End: jump to last visible commit
5. The scroll container should be the single Tab stop — individual rows should NOT be Tab stops

Look at how `branch-sidebar` implements roving tabindex (`focusedLocalIndex`, `onLocalItemKeydown`) for the pattern to follow. The commit list likely has a similar signal for tracking the focused/selected item.

Also fix at-4: add `role="presentation"` to the spacer div inside the virtual scroll container to fix the listbox → option ARIA ownership chain.

### kb-5: Branch tree Home/End/Left/Right arrow keys
**File:** `ui/src/app/features/shell/branch-sidebar/branch-sidebar.component.ts`

The tree view (`role="tree"`) already has ArrowUp/ArrowDown and Enter. Add:
1. **ArrowLeft:** If on an expanded folder → collapse it. If on a branch or collapsed folder → move focus to parent folder.
2. **ArrowRight:** If on a collapsed folder → expand it. If on an expanded folder → move focus to first child.
3. **Home:** Focus the first visible tree node.
4. **End:** Focus the last visible tree node.

Extend `onLocalItemKeydown` and `onRemoteItemKeydown`. Read the existing code first — the `localBranchTree` computed provides the flat node list. You need to find the parent folder for a given node by walking backwards in the list.

### at-7: Virtual scroll aria-setsize/posinset for remote branches
**File:** `ui/src/app/features/shell/branch-sidebar/branch-sidebar.component.html`
The remote branches tree uses CDK virtual scroll. Add `[attr.aria-setsize]="remoteBranchTree().length"` and `[attr.aria-posinset]="$index + 1"` to each `role="treeitem"` element in the remote branch virtual scroll.

### kb-2 / kb-3 / at-6: Command palette focus trap + return focus
**File:** `ui/src/app/features/shell/command-palette/command-palette.component.ts`

The command palette has `aria-modal="true"` but no focus trap and doesn't return focus on close.

1. **Focus trap:** In the keydown handler, intercept Tab. If Shift+Tab and focus is on first focusable element → move to last. If Tab and focus is on last focusable element → move to first. The only focusable elements should be the search input and the result list items.

2. **Return focus:** Store `document.activeElement as HTMLElement` when `open()` is called. In `close()`, after setting visible to false, call `this.previousFocus?.focus()`.

Read the existing component code first to understand the open/close lifecycle.

## Verification

After all edits, run: `cd ui && node_modules/.bin/ng build --configuration=development 2>&1 | tail -10`

Then commit with message: `fix(a11y): Arrow key navigation for commit list, branch tree, and command palette focus trap`

## Rules
- Read each file thoroughly before editing
- Follow existing patterns in the codebase
- Do NOT edit .css files — another agent owns those
- Do NOT add features or refactor beyond the specific fixes
- These are complex widgets — be careful with the keyboard interaction models
