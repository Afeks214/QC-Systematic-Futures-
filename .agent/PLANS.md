# ExecPlan Standard

Every major repository change uses a living ExecPlan that a new contributor can execute without relying on chat history. The plan must be updated while work is in progress and reconciled before completion.

Each ExecPlan contains these sections:

1. **Purpose** — the user-visible outcome and explicit non-goals.
2. **Current repository state** — what exists, what is missing, and whether Git, LEAN, credentials, and network access are available.
3. **Source documents** — authoritative files, verified official sources, hashes when available, and conflict order.
4. **Assumptions** — only assumptions that cannot affect correctness; each marked with its verification path.
5. **Exact file changes** — every file to create or modify and the functions/classes it owns.
6. **Milestones** — ordered, independently verifiable subsystems with stopping conditions.
7. **Verification commands** — exact commands and expected evidence, including commands that may remain `NOT_EXECUTED`.
8. **Acceptance criteria** — observable pass/fail conditions tied to the active task.
9. **Blockers** — unresolved facts, missing permissions/data/runtime, and the work each blocker prevents.
10. **Progress log** — dated checklist entries updated after every major subsystem and validation pass.
11. **Decision log** — material choices, alternatives, evidence, consequences, and reopen conditions.
12. **Final reconciliation** — planned versus delivered files, executed versus unexecuted checks, deviations, remaining blockers, and readiness decision.

Plans use explicit status labels: `PENDING`, `IN_PROGRESS`, `COMPLETE`, `BLOCKED`, `NOT_VERIFIED`, and `NOT_EXECUTED`. A check is never marked complete from inspection alone when the plan requires execution.
