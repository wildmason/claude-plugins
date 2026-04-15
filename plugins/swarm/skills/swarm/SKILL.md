---
name: swarm
description: Use when the user invokes /swarm to orchestrate a multi-agent team for code review, implementation, debugging, or research. Requires CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS to be enabled.
---

# /swarm — Multi-Agent Team Orchestration

Orchestrate a team of parallel agents to tackle code review, implementation, debugging, or research. Each of the 4 modes uses a distinct collaboration protocol tuned for the task type:

| Mode | Protocol | Description |
|------|----------|-------------|
| `review` | Adversarial | Multi-perspective code review with independent reviewers who challenge each other's findings |
| `implement` | Cooperative | Parallel implementation from a plan or spec, with agents owning distinct modules |
| `debug` | Competitive | Competing-hypothesis investigation where agents independently pursue different theories |
| `research` | Convergent | Parallel exploration of facets that synthesises into a unified recommendation |

Built on Claude Code's experimental agent teams feature — agents are full peers that can read files, run commands, and coordinate through shared context.

## Prerequisites

- Claude Code v2.1.32 or later
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` set to `"1"` in settings.json `env` block
- Swarm mailbox MCP server registered (`mcp__swarm__mailbox_state` tool available)

## Startup Guard

Before doing any work, perform these checks in order:

1. **Agent teams availability.** Verify that agent teams are available in the current session. This feature requires the `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` environment variable to be set. If agent teams are not available (the `Teammates` tool is missing or non-functional), print the following message and stop:

   ```
   /swarm requires agent teams to be enabled.
   Add "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" to the env block in your settings.json and restart Claude Code.
   ```

2. **No existing team.** Check whether an agent team is already active in this session. Agent teams supports one team per session. If a team is already running, print the following message and stop:

   ```
   A swarm is already active in this session. Finish or cancel the current swarm before starting a new one.
   ```

3. **Mailbox MCP available.** Verify that the `mcp__swarm__mailbox_state` tool is available. If not, print the following message and stop:

   ```
   /swarm requires the swarm mailbox MCP server. Ensure "swarm" is configured in mcpServers in your settings.json.
   ```

If all checks pass, proceed to invocation parsing.

## Invocation Parsing

### Syntax

```
/swarm <mode> <target>     # explicit mode
/swarm <target>            # inferred mode
/swarm                     # help text
```

### Mode Resolution

1. Parse the first argument after `/swarm`.
2. If it matches one of `review`, `implement`, `debug`, or `research` exactly, use that as the mode. Everything after the mode keyword is the target.
3. If the first argument does not match a mode keyword, infer the mode from the target:
   - **File path or "current changeset"** → `review`
   - **Path containing `specs/` or `plans/`** → `implement`
   - **Problem statement** (phrases like "why does...", "users report...", "X is broken", "fails when...") → `debug`
   - **Question** (phrases like "how should we...", "best practices for...", "what are the options for...") → `research`
   - **Genuinely ambiguous** → ask the user which mode to use before proceeding.
4. If no arguments are provided, print the help text below and stop.

When a mode is inferred, announce the inference to the user before proceeding:
```
Inferred mode: <mode> (from target: "<target>")
```

### Help Text

When invoked with no arguments, print this verbatim:

```
/swarm — Multi-Agent Team Orchestration

Modes:
  review <target>      Adversarial multi-perspective code review
  implement <target>   Parallel implementation from a plan or spec
  debug <target>       Competing-hypothesis investigation
  research <target>    Parallel exploration and synthesis

Target can be a file path, "current changeset", a spec path, or a freeform description.

Examples:
  /swarm review src/auth/
  /swarm implement docs/superpowers/specs/2026-03-24-auth-redesign.md
  /swarm debug "login fails silently after token refresh"
  /swarm research "MV3 service worker caching strategies"
  /swarm src/auth/              (infers: review)
  /swarm "why is login broken"  (infers: debug)
```

## Team Size Limits

**Hard cap: 6 concurrent teammates across all modes.** This applies to the total number of agents active at any given time, regardless of role.

| Mode | Typical | Maximum | Rationale |
|------|---------|---------|-----------|
| Review | 3 | 6 | 3 initial reviewers + up to 2 additional + 1 fix agent |
| Implement | 2–5 | 6 | 1 agent per module or file group |
| Debug | 3–5 | 6 | 1 agent per hypothesis |
| Research | 3–4 | 6 | 1 agent per facet |

If a task warrants more than 6 agents, **phase them**: complete one batch before spawning the next. Announce phasing to the user:
```
This task requires more agents than the 6-agent limit. Running in phases — batch 1 of N starting now.
```

## Model Selection

| Role | Model | Rationale |
|------|-------|-----------|
| Reviewers (all modes) | **opus** | Domain expertise, nuanced analysis |
| Implementers | **opus** | Complex code generation, architectural judgment |
| Debuggers | **opus** | Hypothesis reasoning, evidence evaluation |
| Researchers | **opus** | Synthesis, critical thinking |
| Fix agents | **sonnet** | Mechanical application of described fixes — cheaper and faster |

All teammates are spawned with an explicit model parameter. Never fall back to the default model — always specify the model from this table based on the agent's role.

## Launch Sequence (Phase 1)

Execute these steps in order after invocation parsing and startup checks pass.

### Step 1 — Load Behavioral Profile

Read the behavioral profile for the selected mode from:

```
~/.claude/skills/swarm/behaviors/<mode>.md
```

Mode-to-file mapping:

| Mode | File |
|------|------|
| `review` | `review.md` |
| `implement` | `implement.md` |
| `debug` | `debug.md` |
| `research` | `research.md` |

The behavioral profile defines the collaboration protocol, phase structure, and agent interaction rules for the mode. Its full content will be embedded in every spawn prompt.

### Step 2 — Load Personas

Read the persona catalogue for the selected mode from:

```
~/.claude/skills/swarm/personas/<mode-type>.md
```

Mode-to-file mapping:

| Mode | File |
|------|------|
| `review` | `reviewers.md` |
| `implement` | `implementers.md` |
| `debug` | `debuggers.md` |
| `research` | `researchers.md` |

Each persona file contains named personas with descriptions and reference URLs that give the agent a specialist perspective.

### Step 3 — Select or Create Personas

Evaluate which personas from the catalogue match the task's domain, technology stack, and problem space.

- **Good matches exist:** Select the most relevant personas and assign one per teammate. Not every persona in the file needs to be used — pick the ones that bring the most value to this specific task.
- **No good match exists:** Create a new persona on the spot:
  1. Choose a descriptive name (e.g. "GraphQL Schema Specialist", "iOS Memory Profiler")
  2. Write a 2–3 sentence description of the persona's expertise and perspective
  3. Use web search to find 2–4 authoritative reference URLs relevant to the persona's domain (documentation, style guides, best-practice articles)
  4. Append the new persona to the persona file following the existing format
  5. No user approval is needed — this is a living document

A mix of existing and newly created personas is fine. The goal is the best team for the task, not strict reuse.

### Step 4 — Clear Previous Session State

Reset the swarm mailbox state to a clean slate by writing empty values to all swarm keys:

```
mcp__swarm__mailbox_state(key: "swarm:session", value: "")
mcp__swarm__mailbox_state(key: "swarm:synthesis", value: "")
mcp__swarm__mailbox_state(key: "swarm:agent_roster", value: "")
```

Also clear any per-agent findings keys from a previous session. For each agent name in the previous roster (if any), clear `swarm:findings:<agent-name>`.

This ensures no stale data from a previous swarm session bleeds into the new one.

### Step 5 — Initialize Session State

Write the new session configuration to `swarm:session`:

```json
{
  "mode": "<review|implement|debug|research>",
  "target": "<the target string from invocation>",
  "iteration": 0,
  "phase": "launch",
  "team_name": "<mode>-swarm-<short-slug>"
}
```

The `team_name` should be a short, descriptive identifier. Example: `review-swarm-auth-module`, `debug-swarm-login-failure`.

### Step 6 — Create Session Log Directory

Ensure the `docs/swarm/` directory exists in the current working directory:

```bash
mkdir -p docs/swarm
```

This is where the session log will be written at completion.

### Step 7 — Create the Agent Team

Use the `Teammates` tool to create a new team with the `team_name` from step 5. This is the container that all spawned agents will belong to.

### Step 8 — Build the Task List

Construct the task list with dependencies according to the mode-specific orchestration protocol (defined in the mode-specific sections later in this document). The task list defines what work each agent does and in what order. Tasks have dependency relationships that control phase transitions — a task cannot start until all its dependencies are complete.

### Step 9 — Spawn Teammates

Spawn each teammate using the `Teammates` tool. Every spawn prompt **must** include all of the following:

1. **Full behavioral profile content** — copy the entire content of the behavioral profile file (from step 1) into the spawn prompt. Do not reference the file path — the agent must have the content directly.

2. **Persona assignment** — the assigned persona's name, full description, and all reference URLs. Example:
   ```
   ## Your Persona
   **Name:** Security Auditor
   **Description:** You approach code with a security-first mindset. You look for injection vectors, auth bypass, data exposure, and unsafe defaults. You reference OWASP guidelines and CWE classifications.
   **References:**
   - https://owasp.org/www-project-top-ten/
   - https://cwe.mitre.org/top25/archive/2024/2024_top25_list.html
   ```

3. **Target/task context** — file paths to review, problem descriptions, spec content, or whatever the agent needs to understand what it is working on. Be specific: include exact file paths, directory scopes, error messages, or relevant excerpts.

4. **Mailbox MCP instructions** — include the following block in every spawn prompt, replacing `<YOUR-AGENT-NAME>` with the agent's actual name:

   ```
   ## Mailbox MCP — Persistent State

   You have access to `mcp__swarm__mailbox_state` for persistent key-value state.
   This is a get/set tool, NOT a channel/queue.

   **IMPORTANT — Per-Agent Findings Keys:**
   Each agent writes findings to its OWN namespaced key to prevent write races.

   - WRITE your findings to: `swarm:findings:<YOUR-AGENT-NAME>`
   - READ other agents' findings from: `swarm:findings:<other-agent-name>`
     (check `swarm:agent_roster` for the list of agent names)
   - READ session config from: `swarm:session`

   Example (if your name is "perf-engineer"):
   - Write: mcp__swarm__mailbox_state(key: "swarm:findings:perf-engineer", value: "<json>")
   - Read your own: mcp__swarm__mailbox_state(key: "swarm:findings:perf-engineer")
   - Read another's: mcp__swarm__mailbox_state(key: "swarm:findings:concurrency-reviewer")

   **Rules:**
   - ONLY write to YOUR OWN findings key — never write to another agent's key
   - To challenge another agent's finding, message them directly; they update their own key
   - Do NOT use `mailbox_post`, `mailbox_take`, or `mailbox_clear` — those are reserved for /review-swarm
   ```

5. **Mode-specific collaboration instructions** — what the agent should do with its findings, how to interact with teammates (challenge, collaborate, compete, converge), and what phase structure to follow. This comes from the behavioral profile but should be tailored to the agent's specific role in the team.

6. **Teammate constraints** — include this verbatim:
   ```
   ## Constraints
   You must NOT spawn subagents or sub-teams. All work must be done directly by you.
   This ensures your findings and messages are visible to all other teammates.
   ```

7. **Tool access** — include this verbatim:
   ```
   ## Tool Access
   You have access to all standard tools: Read, Edit, Bash, WebFetch, WebSearch, and the mailbox MCP state tool. Use them as needed for your work.
   ```

### Step 10 — Handle Long Spawn Prompts

If a spawn prompt exceeds approximately 4000 words, do not try to fit it all into the spawn call. Instead:

1. Write the full context to `~/.claude/skills/swarm/.context/<teammate-name>.md`
2. In the spawn prompt, include only a brief role summary and this instruction:
   ```
   Before starting any work, read your full briefing from:
   ~/.claude/skills/swarm/.context/<teammate-name>.md
   ```

This keeps spawn calls within token limits while still giving each agent full context.

### Step 11 — Write Agent Roster

Write the agent roster to `swarm:agent_roster` as a JSON array:

```json
[
  {
    "name": "<agent-name>",
    "persona": "<persona-name>",
    "model": "<opus|sonnet>",
    "role": "<reviewer|implementer|debugger|researcher|fix-agent>",
    "assigned_tasks": ["<task-id-1>", "<task-id-2>"]
  }
]
```

This allows any agent (or the lead) to look up who is on the team and what they are responsible for.

### Step 12 — Announce to User

Print a summary to the user confirming the swarm is live:

```
Spawned <mode> swarm: <agent-1-name> (<persona>), <agent-2-name> (<persona>), ...
```

Example:
```
Spawned review swarm: agent-1 (Security Auditor), agent-2 (Performance Analyst), agent-3 (API Design Critic)
```

Launch is complete. Transition to the monitoring phase.

---

## Monitoring (Phase 2)

The lead agent monitors the swarm during execution and drives phase transitions. This phase begins immediately after launch and continues until all tasks are complete.

### Primary Signal: TaskCompleted Hooks

`TaskCompleted` hooks are the primary monitoring mechanism. When a teammate marks a task as complete, the hook fires and the lead receives a notification. On each `TaskCompleted` event, the lead:

1. Checks the overall task list state to see which tasks are now complete
2. Determines the current phase based on which task groups are done
3. Identifies whether the next phase can begin (all dependencies for the next set of tasks are satisfied)
4. If a phase transition occurs, updates `swarm:session` with the new phase and iteration count

### Phase Transitions

Phase transitions are driven by task dependencies, not by time or manual intervention.

- Each task in the task list has zero or more dependencies (other task IDs that must complete first)
- When all of a task's dependencies are complete, that task is unblocked and available for a teammate to claim
- Teammates self-claim unblocked tasks — the lead does not need to explicitly assign them
- When all tasks in a logical phase complete, the swarm naturally transitions to the next phase

The lead does not need to orchestrate every transition — the dependency graph handles sequencing. The lead's role is to observe, detect problems, and intervene only when something goes wrong.

### Debate/Challenge Termination

In adversarial and competitive modes, agents challenge each other's work. Termination of these debate rounds is defined by task completion, not by message volume:

- Each agent has a "challenge" task in the task list
- An agent marks their challenge task complete when they have finished reviewing and responding to other agents' work
- The challenge phase is over when **all** challenge tasks are marked complete
- The lead does not cut off debate early — agents self-terminate by completing their tasks

### Stall Detection

Use `TeammateIdle` hooks as the stall detection signal. If a teammate goes idle (stops producing output) without having completed their assigned task:

1. The lead checks in with the idle teammate to understand the situation
2. If the teammate is blocked on something, the lead helps unblock (provides missing context, clarifies requirements, etc.)
3. If the teammate is stuck in a loop or has failed, the lead reassigns the task to another teammate or handles it directly
4. If reassignment is not possible (all teammates busy), the lead escalates to the user with a status report

### Polling Fallback

If `TaskCompleted` or `TeammateIdle` hooks are not available or not triggering reliably, the lead falls back to periodic polling:

- Poll the task list state every 30–60 seconds
- Compare the current state to the previous poll to detect progress or stalls
- Apply the same phase transition and stall detection logic as the hook-based approach

### Status Updates

The lead surfaces brief, informative updates to the user at each phase transition. These should be concise — one line per transition. Examples by mode:

**Review mode:**
- "Reviewers analyzing code independently..."
- "Initial review complete. Agents entering challenge phase..."
- "Challenge phase settled. N findings survived scrutiny. Dispatching fix agent."
- "All fixes verified. Writing report."

**Implement mode:**
- "Implementation agents claiming modules..."
- "Agent-1 completed auth module. Agent-2 still working on routing..."
- "All modules implemented. Running integration verification..."
- "Integration clean. Writing session log."

**Debug mode:**
- "Investigators pursuing independent hypotheses..."
- "Round 1 complete. 2 hypotheses eliminated, 1 promising lead."
- "Root cause identified. Writing reproduction test..."
- "Reproduction test passes. Fix verified."

**Research mode:**
- "Researchers exploring assigned facets..."
- "Exploration complete. Beginning cross-pollination..."
- "Synthesis underway. Merging findings into recommendations..."
- "Recommendations finalized. Writing report."

Do not flood the user with updates on every minor event — only phase transitions and significant milestones.

---

## Completion (Phase 3)

When all tasks are complete, the lead executes the completion sequence.

### Step 1 — Verify All Tasks Complete

Check the task list one final time to confirm every task is in a completed state. If any tasks are still pending or in-progress, return to monitoring — do not proceed with completion until everything is done.

### Step 2 — Gather Final Output

Read the accumulated results from the mailbox:

- `swarm:findings:<agent-name>` — each agent's findings in their own namespaced key. Read `swarm:agent_roster` for the list of agent names, then read each agent's findings key and merge them into a single array.
- `swarm:synthesis` — the synthesized summary (if the mode produces one)

These contain the raw material for the session log and user-facing summary.

### Step 3 — Shut Down Teammates

Ask each teammate to shut down gracefully. Teammates should complete any final writes to the mailbox before exiting.

### Step 4 — Clean Up the Team

Use the `Teammates` tool to clean up / destroy the team. This releases all resources associated with the agent team.

**Note:** Collect token usage from all agents' final outputs before cleaning up the team, as their output data will still be accessible at this point.

### Step 5 — Collect Token Usage Summary

Aggregate token usage data from all agents:

1. Read `swarm:agent_roster` to get agent list with model information
2. From each agent's final output `<usage>` block, extract `total_tokens`
3. Build a table with columns: Agent | Model | Tasks | Tokens | Avg/Task
4. Calculate totals for all rows
5. Format as a clean, aligned markdown table

**Table format example:**
```
| Agent | Model | Tasks | Tokens | Avg/Task |
|-------|-------|-------|--------|----------|
| agent-1-http-perf | opus | 2 | 119,094 | 59,547 |
| agent-2-ssrf-runner | opus | 2 | 93,637 | 46,819 |
| **TOTAL** | | **4** | **212,731** | **53,183** |
```

Display this table to the user immediately before the written summary (see Step 6).

### Step 6 — Write Session Log

Write a session log to `docs/swarm/` using this naming convention:

```
docs/swarm/YYYY-MM-DD-<mode>-<target-slug>.md
```

Where `<target-slug>` is a short, filesystem-safe slug derived from the target (e.g., `auth-module`, `login-failure`, `caching-strategies`). Keep it under 40 characters. Lowercase, hyphens only, no special characters.

**If the file already exists** (e.g., multiple swarm runs on the same target in one day), append a counter: `-002.md`, `-003.md`, etc.

**Session log format:**

```markdown
# Swarm: <mode> — <target description>

**Date:** YYYY-MM-DD
**Mode:** <review | implement | debug | research>
**Protocol:** <adversarial | cooperative | competitive | convergent>
**Iterations:** N

## Token Usage

| Agent | Model | Tasks | Tokens | Avg/Task |
|-------|-------|-------|--------|----------|
| ... | ... | ... | ... | ... |
| **TOTAL** | | | | |

## Team
| Agent | Persona | Model | Tasks Completed |
|-------|---------|-------|-----------------|
| ... | ... | ... | ... |

## Summary
<Mode-specific summary of what was accomplished>

## Findings / Output
<Review: findings table with confidence + resolution>
<Implement: list of files created/modified per agent>
<Debug: root cause analysis + reproduction test>
<Research: recommendations with trade-offs>

## Unresolved Items
<Anything deferred to the user>
```

Fill in the template with actual data from the session. The summary should be 2–5 sentences. Findings/output should be as detailed as the mode warrants. Unresolved items should list anything the swarm could not resolve or that requires user decision.

### Step 7 — Present Summary to User

Print a concise summary to the user that includes:

- Token usage summary table (from Step 5)
- What mode was run and on what target
- How many agents participated
- Key findings or outcomes (top 3–5 items)
- Path to the full session log
- Any unresolved items that need user attention

Example:
```
## Token Usage

| Agent | Model | Tasks | Tokens | Avg/Task |
|-------|-------|-------|--------|----------|
| agent-1 | opus | 3 | 145,230 | 48,410 |
| agent-2 | opus | 2 | 98,550 | 49,275 |
| **TOTAL** | | **5** | **243,780** | **48,756** |

---

Review swarm complete — 3 reviewers analyzed src/auth/

Key findings:
1. [Critical] SQL injection in buildQuery() — fixed by fix agent
2. [High] Token refresh race condition — fixed by fix agent
3. [Medium] Missing rate limiting on /api/login — deferred (needs design decision)

Full report: docs/swarm/2026-03-24-review-auth.md
1 item needs your attention (see Unresolved Items).
```

---

## Iteration Safety

Each mode has a safety cap to prevent runaway loops. When a cap is hit, the lead **pauses** and asks the user whether to continue. The lead does not silently terminate — it always explains what happened and what the options are.

| Mode | Cap | Trigger |
|------|-----|---------|
| Review | 15 review/challenge rounds | Lead pauses and asks user to continue. A "round" is one full cycle of review + challenge across all agents. If 15 rounds complete without convergence, something is wrong — the agents may be in a disagreement loop. |
| Implement | Stall detection | If the task list is unchanged across 3 consecutive `TaskCompleted` checks, or if no `TaskCompleted` fires for 5+ minutes, the lead pauses and reports status to the user. This catches cases where agents are silently failing or stuck in retry loops. |
| Debug | 2-round hypothesis limit | If all hypotheses are disproven after 2 full rounds of investigation, the lead pauses and asks the user for input. The user may have context that narrows the search space. Continuing to guess without new information wastes resources. |
| Research | Stall detection | If no tasks complete for 5+ minutes after all explore tasks are done, the lead synthesizes whatever findings exist and presents them to the user rather than waiting indefinitely. Partial results are better than no results. |

When pausing, the lead provides:

1. What triggered the pause (which cap was hit)
2. Current state of the swarm (what has been completed, what is in progress)
3. Options for the user: continue with the current approach, adjust parameters, or stop the swarm
4. The lead's recommendation (if it has one)

Example pause message:
```
⏸ Review swarm paused — 15 challenge rounds completed without convergence.

Status: Agents 1 and 3 are in a loop disagreeing on whether the auth middleware ordering is a real issue.

Options:
1. Continue for 5 more rounds
2. Force convergence (accept majority position)
3. Stop and report current findings

Recommendation: Option 2 — the disagreement is on a subjective style issue, not a correctness bug.
```

---

## Mode-Specific Orchestration Protocols

The following sections define the detailed orchestration protocol for each mode. These protocols are referenced by Step 8 of the Launch Sequence (Build the Task List) and drive the phase structure, task dependencies, and agent interactions for the entire swarm session.

---

### Review Mode (Adversarial)

**Goal:** Multi-perspective code review where independent reviewers challenge each other's findings, producing battle-tested results with high confidence.

#### Phase 1 — Independent Review

1. Lead analyzes the target (file paths, changeset, module), then selects 3 reviewer personas from `~/.claude/skills/swarm/personas/reviewers.md` that best match the target's domain and risk profile.
2. Lead spawns 3 reviewer teammates (opus) — each receives the full behavioral profile from `~/.claude/skills/swarm/behaviors/review.md`, their assigned persona, and the target context.
3. Lead creates the task list:
   - 1 `review` task per reviewer (independent, no dependencies) — these run in parallel
   - 1 `challenge` task per reviewer (depends on ALL 3 `review` tasks completing)
4. Reviewers analyze the code independently. Each reviewer posts their findings to their own `swarm:findings:<agent-name>` key using the findings schema defined in the behavioral profile, then marks their `review` task complete.

#### Phase 2 — Challenge

5. When all `review` tasks complete, `challenge` tasks unblock. Lead broadcasts to all teammates:

   > "All initial reviews complete. Challenge phase: read each other's findings from their `swarm:findings:<agent-name>` keys (check `swarm:agent_roster` for agent names). For each finding you disagree with, message that reviewer directly. Update your OWN findings in your own key — mark retracted findings as `retracted` and add supporting evidence to defended findings. Mark your challenge task complete when done."

6. Reviewers read each other's findings, send direct messages to challenge or request clarification, and update their own findings accordingly. Each reviewer marks their `challenge` task complete when they have finished all challenges and updates.

#### Phase 3 — Settlement and Fixes

7. When all `challenge` tasks complete, lead reads each agent's `swarm:findings:<agent-name>` key and merges them into a unified findings array for the settled state.
8. If fixes are needed (any findings with confidence `certain` or `likely` and status `pending`):
   - Lead spawns a fix agent teammate (sonnet) with fix instructions derived from the findings. The fix agent applies the mechanical fixes and marks its task complete.
   - After the fix agent completes, lead creates `re-review` tasks for the original reviewers to verify the fixes are correct and complete.
9. Repeat the review-challenge-fix cycle until clean (no actionable findings remain) or the iteration cap is reached (15 rounds).

#### Confidence Levels

| Level | Meaning | Action |
|-------|---------|--------|
| `certain` | Demonstrably incorrect behavior, provable bug, or clear violation | Auto-fixed by fix agent |
| `likely` | Strong evidence of a problem but not 100% provable from static analysis | Auto-fixed by fix agent |
| `speculative` | Possible issue, subjective concern, or style preference | Surfaced to the user — not auto-fixed |

---

### Implement Mode (Cooperative)

**Goal:** Parallel implementation from a plan or spec, with agents owning distinct modules and coordinating through explicit file ownership and interface contracts.

#### Phase 1 — Decomposition and Assignment

1. Lead reads the spec/plan, decomposes it into independent implementation tasks. Each task should represent a coherent unit of work (a module, a feature slice, a service, etc.).
2. Lead identifies file ownership:
   - **Owned files:** Each file is assigned to exactly one agent. Only that agent may edit it. This prevents merge conflicts.
   - **Shared files:** Files that multiple agents need to modify (barrel exports, type definitions, `package.json`, config files, shared test fixtures). Lead assigns one agent as the "shared file owner" for each shared file. Other agents message the shared file owner when they need changes to that file.
3. Lead selects implementer personas from `~/.claude/skills/swarm/personas/implementers.md` based on the work domain (frontend, backend, test, infrastructure, etc.).
4. Lead spawns teammates (opus) — each receives the full behavioral profile from `~/.claude/skills/swarm/behaviors/implement.md`, their assigned persona, and detailed task context including file ownership annotations.
5. Lead creates the task list with dependencies and file ownership annotations. Tasks that depend on shared interfaces being defined first have explicit dependencies on the interface-defining task.

#### Phase 2 — Parallel Implementation

6. Teammates self-claim tasks from the shared list as they complete work. Agents work in parallel on their owned files.
7. When an agent defines or changes a shared interface or contract (e.g., a TypeScript interface, an API schema, a shared type), they message all affected teammates to communicate the change.
8. When an agent needs a change to a shared file they do not own, they message the shared file owner with the specific change needed. The shared file owner applies the change.
9. Lead monitors for blocked teammates and reassigns work if someone is stuck. Lead also watches for dependency violations (an agent editing a file they do not own).

#### Phase 3 — Verification

10. When all implementation tasks complete, lead runs verification commands (`npm test`, `npm run build`, `ng test`, or whatever is appropriate for the project).
11. If verification fails, lead analyzes the failure, assigns fix tasks to the appropriate agent (based on file ownership), and teammates resolve.
12. **Post-completion conflict check:** Lead runs `git diff --name-only` and verifies no file was modified by multiple agents. If conflicts are detected, lead assigns a merge/resolution task to the shared file owner for those files.
13. Repeat verification until clean or escalate to the user if fixes are not converging.

---

### Debug Mode (Competitive)

**Goal:** Competing-hypothesis investigation where agents independently pursue different theories about a bug's root cause, then challenge each other's evidence to find the truth.

#### Phase 1 — Hypothesis Generation

1. Lead analyzes the problem description (error messages, reproduction steps, user report), then generates 3–5 competing hypotheses about the root cause. Each hypothesis should be specific and testable — not vague categories.
2. Lead selects debugger personas from `~/.claude/skills/swarm/personas/debuggers.md` matched to each hypothesis's domain (e.g., a concurrency specialist for a race condition hypothesis, a data flow analyst for a state management hypothesis).
3. Lead spawns 1 teammate (opus) per hypothesis — each receives the full behavioral profile from `~/.claude/skills/swarm/behaviors/debug.md`, their assigned persona, the problem description, and their specific hypothesis to investigate.
4. Lead creates the task list:
   - 1 `investigate` task per agent (independent, no dependencies) — these run in parallel
   - 1 `challenge` task per agent (depends on ALL `investigate` tasks completing)

#### Phase 2 — Independent Investigation

5. Agents investigate independently — reading code, checking logs, writing test scripts, adding instrumentation. Each agent's goal is to prove or disprove their assigned hypothesis. Agents mark their `investigate` task complete with an evidence summary posted to their own `swarm:findings:<agent-name>` key.

#### Phase 3 — Challenge

6. When all `investigate` tasks complete, `challenge` tasks unblock. Lead broadcasts to all teammates:

   > "Investigation complete. Challenge phase: share your evidence and try to disprove each other's hypotheses. Message each other directly with counter-evidence. Mark your challenge task complete when done."

7. Agents review each other's evidence, send direct messages with counter-evidence or supporting evidence, and update their findings. Each agent marks their `challenge` task complete when done.

#### Phase 4 — Resolution

8. Lead evaluates surviving hypotheses (those not disproven during the challenge phase):

   - **One survivor:** The winning agent writes a minimal reproduction test that demonstrates the root cause. Lead asks the user: "Root cause identified: [summary]. Fix it now, or report findings?"
   - **Multiple survivors:** Lead asks surviving agents to present their strongest evidence. Lead reports all surviving hypotheses to the user with a recommendation. If the evidence suggests the root cause is a combination of factors, the lead notes this.
   - **Zero survivors:** Lead generates new hypotheses informed by the accumulated evidence from round 1 and spawns a second round. If zero hypotheses survive after 2 rounds, the lead pauses for user input — the problem may require information the agents cannot access.

---

### Research Mode (Convergent)

**Goal:** Parallel exploration of distinct facets of a question, converging into a unified set of recommendations with trade-offs and evidence.

#### Phase 1 — Facet Decomposition

1. Lead decomposes the research question into 3–4 distinct facets or angles. Each facet should explore a meaningfully different dimension of the question (e.g., for "MV3 caching strategies": performance characteristics, API compatibility, offline behavior, migration complexity).
2. Lead selects researcher personas from `~/.claude/skills/swarm/personas/researchers.md` that match each facet's domain.
3. Lead spawns 1 teammate (opus) per facet — each receives the full behavioral profile from `~/.claude/skills/swarm/behaviors/research.md`, their assigned persona, the research question, and their specific facet to explore.
4. Lead creates the task list:
   - 1 `explore` task per agent (independent, no dependencies) — these run in parallel
   - 1 `synthesize` task per agent (depends on ALL `explore` tasks completing)

#### Phase 2 — Independent Exploration

5. Agents explore independently — codebase analysis first (reading existing code, configs, dependencies), then web search for external knowledge (documentation, blog posts, benchmarks, best practices). Each agent posts their findings to their own `swarm:findings:<agent-name>` key and marks their `explore` task complete.

#### Phase 3 — Cross-Pollination and Synthesis

6. When all `explore` tasks complete, `synthesize` tasks unblock. Lead broadcasts to all teammates:

   > "Exploration complete. Share your findings with each other. Identify overlaps, flag disagreements, and work toward synthesis. Mark your synthesize task complete when done."

7. Agents read each other's findings, message each other to resolve disagreements, identify common themes, and refine their analysis in light of other facets. Each agent marks their `synthesize` task complete when done.

#### Phase 4 — Final Report

8. Lead reads each agent's `swarm:findings:<agent-name>` key and merges them, then reads `swarm:synthesis` for the converged state. Lead assembles the final report with:
   - **Recommendations** — ranked by confidence and feasibility
   - **Trade-offs** — what each option costs and what it gains
   - **Unresolved disagreements** — areas where agents could not reach consensus, with both positions presented
   - **Evidence sources** — links and references discovered during research
