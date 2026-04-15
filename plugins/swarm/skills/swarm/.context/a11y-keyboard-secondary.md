# Agent Briefing: A11y Keyboard Navigation — Secondary Widgets

You are implementing keyboard navigation fixes for secondary widgets in Helm. **You may ONLY edit `.ts` and `.html` files in these directories:**
- `ui/src/app/features/shell/commit-panel/`
- `ui/src/app/features/shell/toolbar/toolbar.component.ts`
- `ui/src/app/features/shell/diff-viewer/diff-viewer.component.ts`
- `ui/src/app/features/shell/repo-tabs/repo-tabs.component.ts` and `.html`
- `ui/src/app/features/shell/file-status/file-tree.component.ts`
- `ui/src/app/features/shell/shell.component.ts`

Do NOT edit `.css` files or files in commit-list, branch-sidebar, or command-palette — other agents own those.

Working directory: `C:\Users\Matt\Documents\development\@wildmason\helm`

## Fixes to Apply

### at-5 / kb-16: Co-author combobox ARIA pattern
**File:** `ui/src/app/features/shell/commit-panel/commit-panel.component.html` and `.ts`

The co-author autocomplete input has no combobox ARIA pattern. Add:
- On the input: `role="combobox"`, `[attr.aria-expanded]="showCoAuthorDropdown() && filteredCommitters().length > 0"`, `aria-controls="coauthor-listbox"`, `aria-autocomplete="list"`
- On the dropdown div: `role="listbox"`, `id="coauthor-listbox"`
- On each suggestion: `role="option"`

Also ensure the existing `onCoAuthorKeydown` handler supports ArrowDown/ArrowUp to navigate suggestions and Enter to select.

### kb-15: Recent messages menu Arrow key navigation
**File:** `ui/src/app/features/shell/commit-panel/commit-panel.component.html` and `.ts`

The recent commit messages dropdown (role="menu" with role="menuitem" buttons) lacks Arrow key navigation. Add a `(keydown)` handler on the menu container that implements ArrowDown/ArrowUp to move focus between menuitem buttons, and Escape to close and return focus to the trigger button.

### kb-10: Toolbar dropdown menu Arrow key navigation
**File:** `ui/src/app/features/shell/toolbar/toolbar.component.ts`

The toolbar dropdown menus (Fetch, Pull, Push options) use wm-popover with role="menu". First check if `WmPopover` from Aegis handles keyboard navigation internally (use `mcp__aegis__search` for "popover keyboard"). If it does, no fix needed. If not, add a keydown handler that implements ArrowDown/ArrowUp/Escape for the menu items inside each popover.

### kb-11: Diff viewer keyboard hunk navigation
**File:** `ui/src/app/features/shell/diff-viewer/diff-viewer.component.ts`

The diff viewer has no keyboard mechanism to navigate between hunks. Add keyboard shortcuts: `n` for next hunk, `p` for previous hunk (or `]`/`[`). Make the diff scroll container focusable with `tabindex="0"`. When a hunk is navigated to, scroll it into view and optionally focus the Stage Hunk button.

Read the component to understand the hunk data structure first.

### kb-12: Repo tab close buttons — keyboard accessible
**File:** `ui/src/app/features/shell/repo-tabs/repo-tabs.component.html` and `.ts`

Tab close buttons have `tabindex="-1"` and `aria-hidden="true"`. Check if the existing `onTablistKeydown` handler supports Delete to close the focused tab (not just the active tab). If Delete only closes the active tab, fix it to close the focused tab. Then either:
(a) Keep close buttons hidden but ensure Delete works for any focused tab, OR
(b) Remove `aria-hidden` and `tabindex="-1"` to make close buttons focusable

Option (a) is cleaner if Delete already works correctly.

### kb-14: File tree keyboard model (verify)
**File:** `ui/src/app/features/shell/file-status/file-tree.component.ts`

Read the `onFolderKeydown` and `onFileKeydown` handlers. Verify they implement ArrowUp/ArrowDown/Left/Right/Home/End per the ARIA tree pattern. If missing, add them following the same pattern used in branch-sidebar (which another agent is fixing).

### kb-18: Drag-drop keyboard alternatives (verify)
Read the branch-sidebar context menu code. Verify that all actions achievable via drag-and-drop (merge onto branch, reorder) have keyboard-accessible equivalents in the context menu. The cherry-pick action is confirmed in the context menu. If merge-onto-branch via drag is NOT in the context menu, add it as a menu item: "Merge into [branch]...".

### kb-20: Focus management after state transitions
**File:** `ui/src/app/features/shell/shell.component.ts`

After major state transitions (repo switch via `currentRepo` effect, branch checkout), focus is not managed. Add focus restoration:
1. When `currentRepo` changes (around line 304), after resetting state, set focus to the commit list container or the first focusable element in the main content area.
2. This can be done by adding a `ViewChild` reference to the commit list and calling `.nativeElement.focus()` after the state reset.

Read the existing effect to understand the lifecycle first.

## Verification

After all edits, run: `cd ui && node_modules/.bin/ng build --configuration=development 2>&1 | tail -10`

Then commit with message: `fix(a11y): keyboard navigation for commit panel, toolbar, diff viewer, tabs, and focus management`

## Rules
- Read each file thoroughly before editing
- Follow existing patterns in the codebase
- Do NOT edit .css files — another agent owns those
- Do NOT edit files in commit-list, branch-sidebar, or command-palette — another agent owns those
- Use Aegis MCP to check WmPopover keyboard behavior before implementing kb-10
- For verification-only items (kb-14, kb-18), report what you found even if no fix is needed
