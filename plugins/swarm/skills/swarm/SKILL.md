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

## Locate Support Files

Before doing anything else, locate two directories and store them for use throughout the session.

### SKILL_DIR — built-in files (behaviors and default personas)

These files ship with the skill and may be replaced when the skill updates.

1. Use the Glob tool to check whether `~/.claude/skills/swarm/behaviors/` exists.
   - If yes: `SKILL_DIR = ~/.claude/skills/swarm`
2. If not found, read `~/.claude/plugins/installed_plugins.json`. Find the entry whose key starts with `swarm@` and use its `installPath` value with `/skills/swarm` appended.
   - Example: `installPath = C:\Users\...\plugins\cache\wildmason\swarm\1.0.0` → `SKILL_DIR = <installPath>/skills/swarm`
3. If neither location yields files, stop and print:
   ```
   /swarm support files not found.
   Install the skill locally at ~/.claude/skills/swarm/ or via plugin:
     /plugin marketplace add wildmason/claude-plugins
     /plugin install swarm@wildmason
   ```

### USER_DIR — user-owned files (custom personas and scratch space)

Always `~/.claude/swarm/` — never touched by skill updates.

Create it on first run if it doesn't exist:
```bash
mkdir -p ~/.claude/swarm/personas ~/.claude/swarm/.context
```

Files the user places in `USER_DIR/personas/` will be loaded alongside the built-in personas and are never overwritten by updates.

## Startup Guard

1. **Agent teams availability.** If the `Teammates` tool is missing or non-functional, print and stop:
   ```
   /swarm requires agent teams to be enabled.
   Add "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" to the env block in your settings.json and restart Claude Code.
   ```

2. **No existing team.** If an agent team is already active in this session, print and stop:
   ```
   A swarm is already active in this session. Finish or cancel the current swarm before starting a new one.
   ```

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

When a mode is inferred, announce it:
```
Inferred mode: <mode> (from target: "<target>")
```

### Help Text

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
  /swarm implement docs/specs/auth-redesign.md
  /swarm debug "login fails silently after token refresh"
  /swarm research "MV3 service worker caching strategies"
  /swarm src/auth/              (infers: review)
  /swarm "why is login broken"  (infers: debug)
```

## Team Size Limits

**Hard cap: 6 concurrent teammates across all modes.**

| Mode | Typical | Maximum | Rationale |
|------|---------|---------|-----------|
| Review | 3 | 6 | 3 initial reviewers + up to 2 additional + 1 fix agent |
| Implement | 2–5 | 6 | 1 agent per module or file group |
| Debug | 3–5 | 6 | 1 agent per hypothesis |
| Research | 3–4 | 6 | 1 agent per facet |

If a task warrants more than 6 agents, **phase them**: complete one batch before spawning the next.
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
| Fix agents | **sonnet** | Mechanical application of described fixes |

Always specify the model explicitly when spawning. Never fall back to the default.

## Launch Sequence (Phase 1)

### Step 1 — Load Behavioral Profile

Read the behavioral profile for the selected mode:

```
SKILL_DIR/behaviors/review.md      (review mode)
SKILL_DIR/behaviors/implement.md   (implement mode)
SKILL_DIR/behaviors/debug.md       (debug mode)
SKILL_DIR/behaviors/research.md    (research mode)
```

The profile defines the collaboration protocol, phase structure, and reporting format. Its full content must be embedded in every spawn prompt.

### Step 2 — Load Personas

Load the persona catalogue for the selected mode from two sources and merge them:

1. **Built-in catalogue:** `SKILL_DIR/personas/<mode-type>.md`
   - `reviewers.md`, `implementers.md`, `debuggers.md`, or `researchers.md`
2. **User catalogue:** `USER_DIR/personas/<mode-type>.md` (load if it exists — skip silently if not)

Treat both files as one combined catalogue. Personas from the user file are fully equivalent to built-in personas.

### Step 3 — Select or Create Personas

Evaluate which personas from the merged catalogue match the task's domain, technology stack, and problem space.

- **Good matches exist:** Select the most relevant and assign one per teammate.
- **No good match:** Create a new persona inline:
  1. Choose a descriptive name (e.g. "GraphQL Schema Specialist")
  2. Write a 2–3 sentence description of the persona's expertise and perspective
  3. Use web search to find 2–4 authoritative reference URLs for the domain
  4. **Append the new persona to `USER_DIR/personas/<mode-type>.md`** — this ensures it persists across skill updates. Create the file if it doesn't exist yet, using the same format as the built-in catalogues.

A mix of built-in and user personas is fine.

### Step 4 — Create Session Log Directory

```bash
mkdir -p docs/swarm
```

### Step 5 — Create the Agent Team

Use the `Teammates` tool to create a new team named `<mode>-swarm-<short-slug>`.

### Step 6 — Build the Task List

Construct the task list with dependencies per the mode-specific protocol defined later in this document.

### Step 7 — Spawn Teammates

Every spawn prompt **must** include:

1. **Full behavioral profile content** — the entire content read in Step 1. Copy it verbatim. Do not reference the file path.

2. **Persona assignment:**
   ```
   ## Your Persona
   **Name:** <name>
   **Description:** <description>
   **References:**
   - <url>
   ```

3. **Target/task context** — exact file paths, directory scopes, error messages, or spec excerpts as needed.

4. **Findings output instructions:**
   ```
   ## Findings Output

   Your agent name is: <YOUR-AGENT-NAME>

   When you complete your primary task, include your full structured findings
   as the final content of your task completion output using the JSON format
   defined in your behavioral profile. The lead will collect your findings
   and distribute them to all agents before the challenge phase begins.
   ```

5. **Mode-specific collaboration instructions** from the behavioral profile, tailored to the agent's role.

6. **Constraints:**
   ```
   ## Constraints
   You must NOT spawn subagents or sub-teams. All work must be done directly by you.
   ```

7. **Tool access:**
   ```
   ## Tool Access
   You have access to all standard tools: Read, Edit, Bash, WebFetch, WebSearch,
   and SendMessage for direct teammate communication.
   ```

### Step 8 — Handle Long Spawn Prompts

If a spawn prompt exceeds approximately 4000 words:

1. Write the full context to `USER_DIR/.context/<teammate-name>.md`
2. Use a short spawn prompt instead:
   ```
   Before starting any work, read your full briefing from:
   ~/.claude/swarm/.context/<teammate-name>.md
   ```

### Step 9 — Track Agent Roster

Maintain the roster in your conversation context:

```json
[
  {
    "name": "<agent-name>",
    "persona": "<persona-name>",
    "model": "<opus|sonnet>",
    "role": "<reviewer|implementer|debugger|researcher|fix-agent>",
    "assigned_tasks": ["<task-id-1>"]
  }
]
```

### Step 10 — Announce to User

```
Spawned <mode> swarm: <agent-1-name> (<persona>), <agent-2-name> (<persona>), ...
```

---

## Monitoring (Phase 2)

### Primary Signal: TaskCompleted Hooks

On each `TaskCompleted` event:
1. Check which tasks are now complete
2. Determine current phase
3. If a phase transition is ready, collect findings from completed task outputs and prepare for the next phase

### Findings Collection at Phase Transitions

When all tasks in a phase complete and the next phase requires agents to see each other's work:

1. Use `TaskOutput` to read each agent's completed task output and extract findings JSON
2. Consolidate all findings into a single array
3. Send each agent a `SendMessage` with the full consolidated findings before their next task begins

### Phase Transitions

Task dependencies drive phase transitions automatically. The lead's role is to observe, detect problems, and intervene only when something goes wrong.

### Debate/Challenge Termination

Agents self-terminate by marking their challenge task complete when they have finished. The lead does not cut off debate.

### Stall Detection

Use `TeammateIdle` hooks. If an agent goes idle without completing their task:
1. Check in to understand the situation
2. Help unblock (provide missing context, clarify requirements)
3. Reassign if stuck, or escalate to the user

### Polling Fallback

If hooks are not triggering, poll the task list every 30–60 seconds.

### Status Updates

One line per phase transition. Examples by mode:

- **Review:** "Reviewers analyzing code..." → "Collecting findings. Challenge phase starting..." → "Challenge settled. Dispatching fix agent." → "Writing report."
- **Implement:** "Agents claiming modules..." → "Agent-1 done. Agent-2 still working..." → "Verification running..." → "Writing session log."
- **Debug:** "Investigating hypotheses..." → "Collecting evidence. Challenge starting..." → "Root cause identified. Writing reproduction test."
- **Research:** "Exploring facets..." → "Distributing findings for cross-pollination..." → "Synthesis complete. Writing report."

---

## Completion (Phase 3)

### Step 1 — Verify All Tasks Complete

Confirm every task is completed before proceeding.

### Step 2 — Gather Final Output

Use `TaskOutput` to read each agent's last completed task output and extract the findings JSON. Merge into a single unified array.

### Step 3 — Shut Down Teammates

Send each teammate a `SendMessage` asking them to shut down gracefully.

### Step 4 — Clean Up the Team

Use the `Teammates` tool to destroy the team. Collect token usage before doing so.

### Step 5 — Collect Token Usage Summary

Build a table from all agents' final output `<usage>` blocks:

```
| Agent | Model | Tasks | Tokens | Avg/Task |
|-------|-------|-------|--------|----------|
| agent-1 | opus | 2 | 119,094 | 59,547 |
| **TOTAL** | | **2** | **119,094** | **59,547** |
```

### Step 6 — Write Session Log

```
docs/swarm/YYYY-MM-DD-<mode>-<target-slug>.md
```

Append `-002.md`, `-003.md` etc. if the file already exists.

```markdown
# Swarm: <mode> — <target description>

**Date:** YYYY-MM-DD
**Mode:** <mode>
**Protocol:** <adversarial | cooperative | competitive | convergent>
**Iterations:** N

## Token Usage
| Agent | Model | Tasks | Tokens | Avg/Task |
...

## Team
| Agent | Persona | Model | Tasks Completed |
...

## Summary
<2–5 sentences>

## Findings / Output
<mode-specific>

## Unresolved Items
<anything deferred to the user>
```

### Step 7 — Present Summary to User

- Token usage table
- Mode and target
- Agent count
- Key findings (top 3–5)
- Path to session log
- Unresolved items

---

## Iteration Safety

| Mode | Cap | Trigger |
|------|-----|---------|
| Review | 15 rounds | Pause and ask user to continue |
| Implement | Stall detection | Pause if task list unchanged across 3 checks or no `TaskCompleted` for 5+ minutes |
| Debug | 2 rounds | Pause if all hypotheses disproven after 2 full rounds |
| Research | Stall detection | Synthesize whatever exists if no tasks complete for 5+ minutes post-explore |

When pausing, provide: what triggered it, current state, options, and a recommendation.

---

## Mode-Specific Orchestration Protocols

---

### Review Mode (Adversarial)

**Goal:** Independent reviewers challenge each other's findings, producing battle-tested results.

#### Phase 1 — Independent Review

1. Select 3 reviewer personas from the merged catalogue matching the target's domain and risk profile.
2. Spawn 3 reviewer teammates (opus) with the full review behavioral profile, their persona, and the target context.
3. Task list:
   - 1 `review` task per reviewer (independent, parallel)
   - 1 `challenge` task per reviewer (depends on ALL 3 `review` tasks)
4. Reviewers analyze independently and mark their `review` task complete with findings JSON in the output.

#### Phase 2 — Challenge

5. When all `review` tasks complete, collect each reviewer's findings via `TaskOutput` and consolidate.
6. Send each reviewer a `SendMessage`:
   > "All initial reviews complete. Challenge phase beginning. Here are all agents' findings: [consolidated JSON]. For each finding you disagree with, message that reviewer directly via SendMessage. Defend your own findings with evidence. If convinced you were wrong, mark the finding as `retracted`. Mark your challenge task complete with your updated findings in the output."
7. Reviewers challenge each other via `SendMessage` and mark `challenge` tasks complete with updated findings.

#### Phase 3 — Settlement and Fixes

8. Collect updated findings via `TaskOutput` and merge into the final settled array.
9. For any findings with confidence `certain` or `likely` and status `pending`:
   - Spawn a fix agent (sonnet) with fix instructions derived from the findings
   - After fixes, create `re-review` tasks for original reviewers to verify
10. Repeat until clean or the 15-round cap is reached.

#### Confidence Levels

| Level | Action |
|-------|--------|
| `certain` | Auto-fixed by fix agent |
| `likely` | Auto-fixed by fix agent |
| `speculative` | Surfaced to user — not auto-fixed |

---

### Implement Mode (Cooperative)

**Goal:** Parallel implementation with explicit file ownership and interface contracts.

#### Phase 1 — Decomposition and Assignment

1. Read the spec/plan and decompose into independent tasks.
2. Assign file ownership — each file belongs to exactly one agent. Designate shared file owners for barrel exports, type defs, config files.
3. Select implementer personas from the merged catalogue.
4. Spawn teammates (opus) with the full implement behavioral profile, their persona, task context, and file ownership annotations.

#### Phase 2 — Parallel Implementation

5. Agents self-claim tasks and work in parallel on owned files.
6. Interface changes are broadcast to affected teammates via `SendMessage`.
7. Shared file changes are requested via `SendMessage` to the file owner.
8. Lead monitors for blocked agents and reassigns if stuck.

#### Phase 3 — Verification

9. Run verification commands when all implementation tasks complete.
10. Assign fix tasks to the owning agent if verification fails.
11. Run `git diff --name-only` to confirm no file was modified by multiple agents.
12. Repeat until clean or escalate.

---

### Debug Mode (Competitive)

**Goal:** Competing hypotheses investigated independently, then challenged with evidence.

#### Phase 1 — Hypothesis Generation

1. Generate 3–5 competing hypotheses from the problem description. Each must be specific and testable.
2. Select debugger personas matched to each hypothesis's domain.
3. Spawn 1 agent (opus) per hypothesis with the full debug behavioral profile, their persona, the problem, and their assigned hypothesis.
4. Task list:
   - 1 `investigate` task per agent (independent, parallel)
   - 1 `challenge` task per agent (depends on ALL `investigate` tasks)

#### Phase 2 — Independent Investigation

5. Agents investigate and mark `investigate` tasks complete with their evidence JSON in the output.

#### Phase 3 — Challenge

6. Collect all evidence via `TaskOutput` and consolidate.
7. Send each agent a `SendMessage`:
   > "Investigation complete. Challenge phase beginning. Here is all agents' evidence: [consolidated JSON]. Exchange counter-evidence via SendMessage. Mark your challenge task complete with your updated verdict in the output."
8. Agents exchange evidence and mark `challenge` tasks complete.

#### Phase 4 — Resolution

9. Collect updated verdicts via `TaskOutput` and evaluate survivors:
   - **One survivor:** Agent writes a minimal reproduction test. Ask user: "Root cause identified: [summary]. Fix now or report findings?"
   - **Multiple survivors:** Report all with a recommendation.
   - **Zero survivors:** Generate new hypotheses and run a second round. If zero after 2 rounds, pause for user input.

---

### Research Mode (Convergent)

**Goal:** Parallel facet exploration converging into unified recommendations.

#### Phase 1 — Facet Decomposition

1. Decompose the question into 3–4 distinct facets, each exploring a different dimension.
2. Select researcher personas from the merged catalogue.
3. Spawn 1 agent (opus) per facet with the full research behavioral profile, their persona, the question, and their assigned facet.
4. Task list:
   - 1 `explore` task per agent (independent, parallel)
   - 1 `synthesize` task per agent (depends on ALL `explore` tasks)

#### Phase 2 — Independent Exploration

5. Agents explore and mark `explore` tasks complete with their findings JSON in the output.

#### Phase 3 — Cross-Pollination and Synthesis

6. Collect all findings via `TaskOutput` and consolidate.
7. Send each agent a `SendMessage`:
   > "Exploration complete. Cross-pollination beginning. Here are all agents' findings: [consolidated JSON]. Message agents via SendMessage to resolve disagreements. Mark your synthesize task complete with refined findings in the output."
8. Agents message each other and mark `synthesize` tasks complete.

#### Phase 4 — Final Report

9. Collect synthesized findings via `TaskOutput` and merge. Assemble the final report:
   - **Recommendations** — ranked by confidence and feasibility
   - **Trade-offs** — costs and gains per option
   - **Unresolved disagreements** — both positions presented
   - **Evidence sources** — links and references from research
