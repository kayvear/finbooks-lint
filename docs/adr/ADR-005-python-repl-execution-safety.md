# ADR-005: python_repl Execution Safety — Sandboxing Agent-Generated Code for Production

**Status:** Proposed
**Date:** 2026-03-22
**Deciders:** Krish
**Linked ADR:** [ADR-001 — Agent Tool Boundary](ADR-001-agent-architecture-hybrid.md)

---

## Context

ADR-001 established a dual-mode agent architecture. The `hybrid` mode is more
valuable than `fixed` for production use because the agent can detect unanticipated
data quality issues, adapt to layout variation, and reason about anomalies that no
pre-built rule would catch. `fixed` mode can only find what its tools were coded to
find — which is a ceiling on detection quality.

Hybrid mode works by having the agent write Python comparison code at runtime and
execute it via a `python_repl` tool. This raises a question: is it safe to run
LLM-generated code in a production environment, and if so, how?

---

## How python_repl Works

### Why it exists as a tool rather than using Bash

The agent already has access to a `Bash` tool through Claude Code. It could run
Python via `bash python3 -c "..."`. The `python_repl` MCP tool exists instead
because it provides a **persistent execution namespace** — variables set in one
call are available in the next, exactly like an interactive Python session. This
allows the agent to load data once, inspect it, and iteratively build comparison
logic without re-loading everything on each call. It also gives us a clean
extraction point for the `result` variable that the agent is instructed to set
at the end, and eliminates the shell escaping surface that Bash introduces.

### Where the code actually runs

The generated code does **not** run inside Claude or the Anthropic API. The
execution chain is:

```
Your application process (PID A)
  └─ claude-agent-sdk spawns Claude Code CLI subprocess (PID B)
       └─ CLI calls Anthropic API → Claude decides to call python_repl("breaks = ...")
       └─ CLI sends the tool call back to the SDK via local IPC
  └─ SDK routes tool call to our @tool handler
       └─ exec("breaks = ...", namespace)   ← runs in PID A, your process
```

The MCP protocol is purely a transport. Execution is local, in your process, with
full access to everything that process can access.

### The actual threat

The agent (Claude) is not adversarial — it is well-behaved and writes sensible
comparison code. The realistic risks are:

1. **Hallucinated destructive code** — agent accidentally writes `import os; os.remove(...)`
2. **Accidental data leakage** — code logs sensitive values to a file or external endpoint
3. **Runaway computation** — infinite loop or memory explosion on large inputs

---

## Options

### Option A — Unrestricted exec (current, dev-only)

No restrictions. Full Python access inside the application process.

**Appropriate for:** Local development, CI with no customer data.
**Not appropriate for:** Any environment processing real financial data.

---

### Option B — AST allow-list visitor (in-process, no dependencies)

Parse the code as an abstract syntax tree before executing and reject any
operation not on an explicit allow-list (blocked: file I/O, network, subprocess,
dangerous builtins).

**Pros:** Zero dependencies, fast, fully in-process.
**Cons:** Known escape paths exist that bypass AST checks via Python's object
model (`__class__`, `__bases__`, etc.). Maintaining a comprehensive block-list
is an ongoing arms race. Not sufficient as a sole defence.

**Verdict:** Useful as a first-pass filter. Not sufficient alone.

---

### Option C — RestrictedPython (in-process, proven library)

[RestrictedPython](https://restrictedpython.readthedocs.io/) is a 20-year-old
library (used in production by Zope/Plone) that compiles Python through a
restricted AST transformer. It intercepts all attribute access, blocks disallowed
imports, and neuters dangerous builtins. An explicit allow-list controls exactly
which modules and builtins the code may use (`json`, `math`, arithmetic, iteration
— all that the comparison code needs).

**Pros:** Battle-tested against adversarial Python. In-process, so the persistent
namespace is preserved. Single dependency.
**Cons:** Some legitimate patterns need explicit allow-listing. Not a formal
security guarantee — Zope's threat model differs from ours. Adds ~2ms compile step.

**Verdict:** Best fit for production environments without container infrastructure.

---

### Option D — Subprocess with OS resource limits

Each `python_repl` call spawns a child process. Code and data are passed via
stdin; results come back on stdout. Before executing, the child process applies
hard OS-level resource limits: CPU time cap, memory ceiling, maximum open file
descriptors (set to 4, making file I/O impossible), and no subprocess spawning.
These limits are enforced by the kernel — they cannot be exceeded even if the code
tries.

**Pros:** True OS-level enforcement. Works without any Python sandboxing library.
`RLIMIT_NOFILE=4` makes accidental file writes effectively impossible.
**Cons:** 50–100ms subprocess startup overhead per call. The persistent namespace
is lost — the agent must write a single self-contained script each call rather
than building state incrementally. Linux-only.

**Verdict:** Strongest practical isolation for bare-metal or VM Linux deployments.
Requires a prompt/workflow change (single-script model).

---

### Option E — Long-running sidecar microservice

A dedicated Python execution container runs alongside the main application as a
sidecar. The `python_repl` tool sends code and data to it over a Unix socket or
HTTP; the sidecar executes and returns results. The sidecar container has no
network, a read-only filesystem, hard memory and CPU limits, and a seccomp
syscall profile blocking file access, subprocess spawning, and networking.

**Pros:** Syscall-level enforcement by the OS kernel. Container can be killed and
restarted independently. Network completely absent. Works natively in Kubernetes.
**Cons:** Meaningful infrastructure: container orchestration, service discovery,
health checks, socket management. Persistent namespace lost (stateless calls).

**Verdict:** Appropriate if the platform grows to serve external users or
multi-tenant workloads. Overkill for an internal, single-tenant tool.

---

### Option F — Ephemeral Docker container per validation run

One Docker container is spun up per PDF validation run (not per `python_repl`
call). The container hosts the Python process that maintains the persistent
namespace for that run. When the run finishes, the container is killed.

The key difference from Option E (long-running sidecar) is the lifecycle:
containers are ephemeral and per-run, not shared across runs. Container flags
include: no network, read-only filesystem, memory/CPU limits, no new privileges,
unprivileged user.

**Startup cost:** 150–400ms per container on a modern Linux host with a
pre-pulled image. This is a one-time cost per run, not per call. For a 10-PDF
batch, that is 10 container starts. A **pre-warmed pool** (N idle containers
waiting on Unix sockets) reduces effective latency to socket round-trip (~1ms).

**Persistent namespace:** Fully preserved within a run. No workflow change vs
current implementation.

**Pros:** True container isolation with persistent namespace. Network absent.
Pre-warmed pool eliminates cold-start latency. Works in Kubernetes.
**Cons:** Requires Docker or containerd on the host. Pre-warmed pool adds a pool
manager component. Data volumes must not be mounted into the container.

**Verdict:** Best option when Docker is available. Preserves persistent namespace
while adding process and network isolation. Recommended upgrade from Option C.

---

### Option G — Minimal virtual environment subprocess

A Python virtual environment isolates installed packages but provides **no
execution sandbox**. The stdlib (`os`, `socket`, `subprocess`, `http`) is always
available regardless of what is installed in the venv.

The value of a **minimal venv** (stdlib only, no third-party packages) is
narrower: it prevents the agent from importing main-application packages
(`anthropic`, `requests`, `pandas`) to make outbound API calls or access data
in unexpected ways. This closes a specific exfiltration risk at zero cost.

A minimal venv alone does nothing for syscall-level isolation. It is only
meaningful when layered on top of Option D (subprocess + OS resource limits),
where it adds package import isolation as defence-in-depth.

**Pros:** Zero runtime cost. Eliminates third-party import surface. Works on any OS.
**Cons:** Not a standalone sandbox. stdlib threats remain. Persistent namespace
lost (subprocess boundary). Venv must be maintained across Python version upgrades.

**Verdict:** Not a standalone option. A worthwhile cheap layer on top of Option D.

---

## Decision

### Tiered upgrade path

No single option fits all environments. The correct choice depends on what
infrastructure is available:

| Tier | Deployment context | Option | Persistent namespace? |
|---|---|---|---|
| 0 — Dev | Local, no customer data | A — unrestricted | ✅ Yes |
| 1 — Prod, Python only | VM / bare-metal, no Docker | C + B as pre-filter | ✅ Yes |
| 2 — Prod, Docker available | VM or k8s with containerd | F — ephemeral container (pre-warmed) | ✅ Yes |
| 3 — Prod, max isolation | Multi-tenant / external-facing | D + G — subprocess + RLIMIT + minimal venv | ❌ Single-script |
| 4 — Enterprise k8s | gVisor / Firecracker available | E — sidecar + kernel sandbox | ❌ Stateless |

### Phase 2b decision — Tier 1

**Option C (RestrictedPython)** is adopted as the default production execution
policy. Rationale: lowest-friction path — one dependency, no infrastructure changes,
persistent namespace preserved, sufficient for internal first-party data.

**Option B (AST visitor)** runs as a cheap pre-filter before RestrictedPython to
catch obvious violations and produce clearer error messages.

**Option F** is the recommended next step when Docker becomes available in the
deployment environment. It preserves the persistent namespace with no workflow
change while adding true process and network isolation.

**Option D + G** is the fallback when Docker is unavailable but stronger isolation
than RestrictedPython is required.

### Execution policy is controlled by an environment variable

```
FINBOOKS_REPL_POLICY=unrestricted   # Tier 0 — dev default
FINBOOKS_REPL_POLICY=restricted     # Tier 1 — RestrictedPython (prod default)
FINBOOKS_REPL_POLICY=container      # Tier 2 — Docker container pool
FINBOOKS_REPL_POLICY=subprocess     # Tier 3 — subprocess + RLIMIT + minimal venv
```

---

## Consequences

**Positive:**
- Hybrid mode can run safely in production environments processing real customer data
- The agent's open-ended detection capability — the primary value of hybrid mode — is
  preserved at every tier; only the execution boundary changes
- A clear no-big-bang upgrade path exists as infrastructure matures

**Negative / trade-offs:**
- Tier 1 (RestrictedPython) requires explicit allow-listing of any builtins the agent uses; the system prompt must constrain the agent to `json` and `math` only
- Tier 2 (Docker) requires container infrastructure and a pool manager
- Tiers 3+ lose the persistent namespace; the system prompt and agent workflow must change to a single-script model per call
- `FINBOOKS_REPL_POLICY` must be explicitly set in each deployment environment

---

## Alternatives Not Adopted at Phase 2b

| Option | Disposition |
|---|---|
| Option A in production | Rejected — unacceptable with real customer data |
| Option B alone | Pre-filter only — known escape paths via Python object model |
| Option E as default | Deferred — overkill for current single-tenant use |
| PyPy sandbox | Deprecated in modern PyPy — not viable |
| Fixed mode only in production | Rejected — open-ended agent detection is the core production value |
