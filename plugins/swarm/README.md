# swarm

Multi-agent swarm orchestration for Claude Code. Spawns a coordinated team of specialist agents to tackle code review, implementation, debugging, or research — each mode uses a distinct collaboration protocol tuned for the task type.

## Requirements

- Claude Code v2.1.32+
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` environment variable
- `swarm` MCP server configured (for mailbox-based agent coordination)

## Installation

```
/plugin install swarm@wildmason/claude-plugins
```

## Usage

```
/swarm [mode] [target]
```

| Mode | Protocol | Use when |
|------|----------|----------|
| `review` | Adversarial | You want independent perspectives that challenge each other |
| `implement` | Cooperative | You have a plan and want parallel execution across modules |
| `debug` | Competitive | Agents race competing hypotheses to find the root cause |
| `research` | Convergent | Parallel exploration that synthesises into a unified recommendation |

### Examples

```
/swarm review src/auth/
/swarm implement plan.md
/swarm debug "login fails after password reset"
/swarm research "best approach for offline-first sync"
```

## How it works

Each invocation:

1. Reads the behavioral profile for the chosen mode
2. Selects specialist personas from the persona catalogue
3. Initialises shared mailbox state
4. Spawns up to 6 parallel teammate agents
5. Monitors completion, handles stalls, and enforces iteration caps
6. Gathers outputs, shuts down the team, and writes a session log

Context files in `.context/` contain pre-generated prompts for specialist roles (accessibility, security, performance, Angular, Rust, etc.) that are loaded when those agents are assigned.

## Author

[Wildmason](https://wildmason.dev) — matt@wildmason.dev
