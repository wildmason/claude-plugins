# Agent Briefing: A11y ARIA Fixes — Right Side Components

You are fixing accessibility ARIA/HTML issues in the right-side and shared components of the Helm frontend. **You may ONLY edit HTML files in these directories:**
- `ui/src/app/shared/components/toast-container/`
- `ui/src/app/shared/components/prompt-modal/`
- `ui/src/app/shared/components/context-menu/` (HTML only)
- `ui/src/app/features/shell/diff-viewer/` (HTML only)
- `ui/src/app/features/shell/commit-list/` (HTML only)
- `ui/src/app/features/shell/commit-detail/` (HTML only)
- `ui/src/app/features/shell/toolbar/` (HTML only)
- `ui/src/app/features/shell/repo-tabs/` (HTML only)
- `ui/src/app/features/shell/file-status/` (HTML only — file-tree.component.html)
- `ui/src/app/features/shell/stash-sidebar/` (HTML only)
- `ui/src/app/features/shell/command-palette/` (HTML only)
- `ui/src/app/features/shell/range-diff/range-diff.component.ts` (inline styles only)

Working directory: `C:\Users\Matt\Documents\development\@wildmason\helm`

## Fixes to Apply

### at-1 / wcag-15: Toast container role conflict
**File:** `ui/src/app/shared/components/toast-container/toast-container.component.html`
The container has both `aria-live="assertive"` and `role="status"` which conflict. Change to `role="log" aria-live="polite"` on the container. Then on individual toast divs, add `role="alert"` for error toasts only (check the toast type/severity). If the template iterates over toasts, conditionally apply `[attr.role]="toast.type === 'error' ? 'alert' : 'status'"` on each toast div.

### at-2: Prompt modal input labels
**File:** `ui/src/app/shared/components/prompt-modal/prompt-modal.component.html`
Find the `<textarea>` and `<input>` elements (around line 4-22). Add `[attr.aria-label]="title()"` to both.

### at-10 / at-19: Diff viewer split pane labels + line semantics
**File:** `ui/src/app/features/shell/diff-viewer/diff-viewer.component.html`
Find the split view panes (around line 469-470). Add `aria-label="Old file content"` to the left pane and `aria-label="New file content"` to the right pane.

### wcag-14: Stage/Discard Lines aria-labels with hunk context
**File:** `ui/src/app/features/shell/diff-viewer/diff-viewer.component.html`
Find the "Stage N Lines" and "Discard N Lines" buttons (around line 362-381). Add hunk context to their aria-labels: `[attr.aria-label]="'Stage ' + selectionCount(vh.index) + ' selected lines in hunk: ' + vh.hunk.header"` and similarly for discard.

### wcag-23: Diff viewer line numbers — replace opacity-40
**File:** `ui/src/app/features/shell/diff-viewer/diff-viewer.component.html`
Find all elements using the `opacity-40` Tailwind class for line numbers (around lines 409, 413, 486, 530). Replace `opacity-40` with a CSS class or inline style using `color: var(--wm-text-muted)`. You can add a class like `dv-line-num` and the CSS agent will style it, OR just replace `opacity-40` with `text-[var(--wm-text-muted)]` if Tailwind arbitrary values are supported, OR remove `opacity-40` and add `style="color: var(--wm-text-muted)"`.

### wcag-22: Command palette category — replace opacity-40
**File:** `ui/src/app/features/shell/command-palette/command-palette.component.html`
Find the category text (around line 36) using `opacity-40`. Replace with a class using `color: var(--wm-text-muted)` or inline `style="color: var(--wm-text-muted)"`.

### wcag-24: Context menu shortcut text — replace opacity-40
**File:** `ui/src/app/shared/components/context-menu/context-menu.component.html`
Find the keyboard shortcut text (around line 25) using `opacity-40`. Replace with `style="color: var(--wm-text-muted)"` or equivalent.

### wcag-9: CI status dots — add shape differentiation
**File:** `ui/src/app/features/shell/commit-list/commit-list.component.html`
Find the CI status dot (around line 246-250). The dot is an 8x8 circle whose color indicates status. Add a tiny icon or shape distinction: use `lucide-icon` with `Check` for success, `X` for failure, `Clock` for pending — at size 8-10. Keep the existing `aria-label`.

### at-17: Working tree row aria-label
**File:** `ui/src/app/features/shell/commit-list/commit-list.component.html`
Find the working tree pseudo-row (around line 161-187). Add a combined `aria-label` like `[attr.aria-label]="'Working directory: ' + (workingTreeStatus()?.staged?.length || 0) + ' staged, ' + (workingTreeStatus()?.unstaged?.length || 0) + ' unstaged'"`.

### wcag-6: Toolbar fail dot — add text alternative
**File:** `ui/src/app/features/shell/toolbar/toolbar.component.html`
Find the git-log fail dot. It has `aria-hidden="true"` but no text alternative exists on the parent. Add an `aria-label` on the parent button that conditionally includes the failure state, e.g.: `[attr.aria-label]="'Git log' + (lastOpFailed() ? ' — last operation failed' : '')"`.

### wcag-18: Repo tab decorative icons
**File:** `ui/src/app/features/shell/repo-tabs/repo-tabs.component.html`
Find the `lucide-icon` inside tab buttons (around line 45-50). Add `aria-hidden="true"` to the icon since the button already has an `aria-label`.

### at-14: AI explanation live region
**File:** `ui/src/app/features/shell/commit-detail/commit-detail.component.html`
Find the AI explanation section (around line 48-69). Wrap the explanation container in an `aria-live="polite"` region so screen readers announce when the explanation loads.

### at-15: File tree aria-label
**File:** `ui/src/app/features/shell/file-status/file-tree.component.html`
Add an `aria-label` to the root cdk-tree element. Drive it from the component's sectionType input, e.g.: `[attr.aria-label]="sectionType === 'staged' ? 'Staged files' : 'Unstaged files'"`. Read the component TS to find the exact input name.

### at-13: Stash form focus management
**File:** `ui/src/app/features/shell/stash-sidebar/stash-sidebar.component.html`
When the stash form appears, the message input should receive focus. Add a template reference on the input and use `autofocus` or add a ViewChild that focuses it when visible.

### wcag-8: Range diff hardcoded line colors
**File:** `ui/src/app/features/shell/range-diff/range-diff.component.ts`
Find the hardcoded `rgba(52,211,153,0.12)` and `rgba(248,113,113,0.12)` in inline styles (around line 72-73). Replace with `color-mix(in srgb, var(--wm-diff-added) 12%, transparent)` and `color-mix(in srgb, var(--wm-diff-deleted) 12%, transparent)`.

## Verification

After all edits, run: `cd ui && node_modules/.bin/ng build --configuration=development 2>&1 | tail -10`

Then commit with message: `fix(a11y): ARIA roles, labels, live regions, and contrast for right-side components`

## Rules
- Read each file before editing
- Do NOT edit .css files — another agent owns those
- Do NOT edit .ts files except range-diff.component.ts for inline styles and stash-sidebar for focus
- Do NOT add features or refactor — only fix the specific issues listed
