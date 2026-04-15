# Agent Briefing: A11y ARIA Fixes — Left Side Components

You are fixing accessibility ARIA/HTML issues in the left-side components of the Helm frontend. **You may ONLY edit files in these directories:**
- `ui/src/app/features/shell/branch-sidebar/` (HTML only)
- `ui/src/app/features/welcome/`
- `ui/src/app/features/settings/` (HTML only)
- `ui/src/app/features/shell/shell.component.html`
- `ui/src/app/features/shell/open-clone-dialog/` (HTML only)
- `ui/src/app/app.routes.ts` and `ui/src/app/app.component.ts`

Do NOT edit `.css` files or `.ts` files in branch-sidebar, settings, or open-clone-dialog — other agents own those.

Working directory: `C:\Users\Matt\Documents\development\@wildmason\helm`

## Fixes to Apply

### at-8 / wcag-10: Branch ahead/behind accessible text
**File:** `ui/src/app/features/shell/branch-sidebar/branch-sidebar.component.html`
Find the ahead/behind count spans (around line 234-239) that show arrow characters with numbers. Add an `aria-label` on the container that describes the counts, e.g.: `[attr.aria-label]="node.branch!.ahead + ' commits ahead, ' + node.branch!.behind + ' commits behind'"`. Hide the individual arrow spans with `aria-hidden="true"`.

### at-16: Stacked branches header — div[role=button] → native button
**File:** `ui/src/app/features/shell/branch-sidebar/branch-sidebar.component.html`
Find the stacked branches section header (around line 9-17) that uses `<div>` with `role="button"`. Replace with a native `<button>` element matching the pattern used by the Local branches section header. Keep all attributes and event handlers.

### at-11: Progress bar hidden when idle
**File:** `ui/src/app/features/shell/shell.component.html`
Find the global progress indicator (around line 16-30) with `role="progressbar"`. Add `[attr.aria-hidden]="!globalBusy()"` so screen readers ignore it when idle.

### at-18: Settings nav aria-current
**File:** `ui/src/app/features/settings/settings.component.html`
Find the settings sidebar nav buttons (around line 9-23). Add `[attr.aria-current]="activeSection() === sec.id ? 'page' : null"` to each nav button.

### wcag-16: Welcome group name input labels
**File:** `ui/src/app/features/welcome/welcome.component.html`
Find the create-group input (around line 55-60) — add `aria-label="New group name"`. Find the rename input (around line 87-93) — add `aria-label="Rename group"`.

### at-20: Welcome repo rows — nested interactives
**File:** `ui/src/app/features/welcome/welcome.component.html`
The repo row template (around line 178-250) uses `div[role="button"]` containing nested buttons (pin, remove, group select). This violates the button content model. Fix: change the outer div from `role="button"` to just a regular `<div>` (remove role="button"), and make the repo name/path area the clickable element with `role="button"` (or use an `<a>` or `<button>`). The pin, group-select, and remove buttons remain as siblings, not children of the clickable area. This may require restructuring — the click handler `(click)="openRecent(repo.path)"` needs to move to just the name/path area, not the outer container.

### at-12: Open-clone dialog accessible name
**File:** `ui/src/app/features/shell/open-clone-dialog/open-clone-dialog.component.html`
Add `title="Open or Clone Repository"` to the `<wm-dialog>` element (line 1).

### at-3: Route change announcement
**File:** `ui/src/app/app.routes.ts`
Add `title` property to each route: `{ path: 'welcome', title: 'Helm — Welcome', ... }` and `{ path: 'repo', title: 'Helm — Repository', ... }`. Angular's built-in TitleStrategy will update `document.title` on navigation, which screen readers detect.

### wcag-17: Theme swatch accessible names (verify)
**File:** `ui/src/app/features/settings/settings.component.html`
Check the theme swatch buttons (around line 50-69). Verify that each button's text content (the swatch-label span inside) is readable as the button's accessible name. If the lucide-icon or div structure obscures it, add `[attr.aria-label]="'Select theme: ' + t.name"`.

## Verification

After all edits, run: `cd ui && node_modules/.bin/ng build --configuration=development 2>&1 | tail -10`

Then commit with message: `fix(a11y): ARIA labels, roles, and route announcements for left-side components`

## Rules
- Read each file before editing
- Do NOT edit .css files — another agent owns those
- Do NOT edit .ts files in branch-sidebar, settings, or open-clone-dialog
- Do NOT add features or refactor — only fix the specific issues listed
