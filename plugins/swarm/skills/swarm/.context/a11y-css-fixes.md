# Agent Briefing: A11y CSS Fixes

You are fixing accessibility CSS issues across the Helm frontend. **You may ONLY edit `.css` files.** Do not touch `.html` or `.ts` files — other agents own those.

Working directory: `C:\Users\Matt\Documents\development\@wildmason\helm`

## Design System Rule
This project uses the Aegis design system. All colors MUST use `--wm-*` CSS custom properties. Never hardcode hex values. Use `mcp__aegis__search` to look up tokens if unsure.

## Fixes to Apply

### 1. Replace `color: white` with `var(--wm-color-accent-text)` on accent backgrounds

**wcag-1:** `ui/src/app/features/shell/commit-list/commit-list.component.css` — `.cl-filter-active-badge` change `color: white` to `color: var(--wm-color-accent-text)`

**wcag-2:** Same file — `.cl-multiselect-bar` change `color: white` to `color: var(--wm-color-accent-text)`

**wcag-3:** `ui/src/app/features/shell/diff-viewer/diff-viewer.component.css` — Multiple elements with `color: white` on accent backgrounds: `.dv-load-image-btn`, `.dv-toggle-btn--active`, `.dv-stage-hunk-btn`, `.dv-slider-icon`. Change all to `color: var(--wm-color-accent-text)`. Exception: `.dv-slider-label` on `rgba(0,0,0,0.6)` background can keep white. `.dv-discard-hunk-btn` on danger background — use `color: var(--wm-color-accent-text)` or check if a danger-text token exists.

**wcag-4:** `ui/src/app/features/shell/file-status/file-status-list.component.css` — `.stash-action-bar` change `color: white` to `color: var(--wm-color-accent-text)`

### 2. Replace hardcoded hex colors with design tokens

**wcag-5:** `ui/src/app/features/shell/git-log-modal/git-log-modal.component.css` — `.status-chip.ok` replace `background: #1a3a1a; color: #6fcf97` with `background: color-mix(in srgb, var(--wm-color-success) 15%, var(--wm-bg-base)); color: var(--wm-color-success)`. `.status-chip.fail` replace `background: #3a1a1a; color: #eb5757` with `background: color-mix(in srgb, var(--wm-color-danger) 15%, var(--wm-bg-base)); color: var(--wm-color-danger)`. `.output-pre.stderr` replace `color: #c08080` with `color: var(--wm-color-danger)`.

**wcag-7:** `ui/src/app/features/shell/undo-history/undo-history.component.css` — `.btn-dialog-confirm` replace `color: #000` with `color: var(--wm-text-primary)`. Not perfect but safer than hardcoded black.

**wcag-11:** `ui/src/app/features/shell/bisect/bisect-banner.component.css` — `.bisect-good-btn` and `.bisect-bad-btn` replace `color: var(--wm-bg-base)` with `color: white` (semantic buttons on green/red backgrounds — white is reliably contrast-safe on both).

**wcag-20:** `ui/src/app/features/shell/conflict-banner/conflict-banner.component.css` — `.banner-btn` replace `background: rgba(0, 0, 0, 0.2)` with `background: color-mix(in srgb, var(--wm-bg-base) 25%, transparent)`.

### 3. Fix focus indicator suppression

**kb-6:** `ui/src/app/shared/components/context-menu/context-menu.component.css` — Change `.ctx-menu-item:focus { outline: none; }` to `.ctx-menu-item:focus:not(:focus-visible) { outline: none; }`.

**kb-7:** `ui/src/app/features/shell/pr/pr-detail-panel.component.css` — For `.edit-title-input`, `.edit-body-textarea`, `.comment-textarea` that have `outline: none`, add `:focus-visible` styles: `border-color: var(--wm-color-accent); box-shadow: 0 0 0 1px var(--wm-color-accent);`

**kb-8:** `ui/src/app/features/shell/issues/issue-detail-panel.component.css` — Same fix as kb-7 for the same class names.

**kb-9:** `ui/src/app/features/shell/pr/pr-review-form.component.css` — `.review-textarea` add `:focus-visible` style with accent border.

### 4. Fix icon opacity contrast

**wcag-13:** `ui/src/app/features/shell/commit-list/commit-list.component.css` — `.cl-signed-icon` remove `opacity: 0.7`, `.cl-not-pushed-icon` remove `opacity: 0.8`. The `--wm-text-muted` token is already designed for low-emphasis visibility.

### 5. Add prefers-reduced-motion media queries

**wcag-12:** Add `@media (prefers-reduced-motion: reduce)` blocks to every CSS file that contains `transition` or `animation` properties. At minimum these files:
- `ui/src/app/shared/components/context-menu/context-menu.component.css`
- `ui/src/app/features/shell/changelog/changelog-modal.component.css`
- `ui/src/app/features/shell/commit-list/commit-list.component.css`
- `ui/src/app/features/shell/shell.component.css`
- `ui/src/app/features/shell/branch-sidebar/branch-sidebar.component.css`
- `ui/src/app/features/shell/file-status/file-status-list.component.css`
- `ui/src/app/features/shell/git-log-modal/git-log-modal.component.css`

For each, search for `transition` and `animation` properties and add a media query block that sets `transition: none !important; animation: none !important;` on the relevant selectors. Use a single `@media` block at the end of each file.

## Verification

After all edits, run: `cd ui && node_modules/.bin/ng build --configuration=development 2>&1 | tail -10`

Then commit all CSS files with message: `fix(a11y): CSS contrast tokens, focus indicators, and reduced-motion`

## Rules
- ONLY edit .css files
- Read each file before editing
- Use Aegis MCP to verify token names if unsure
- Do NOT add features or refactor — only fix the specific issues listed
