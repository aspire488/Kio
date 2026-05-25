# FORBIDDEN PATTERNS — DO NOT IMPLEMENT

These patterns are banned from the KIO codebase. AI-assisted edits that
introduce any FORBIDDEN pattern must be rejected at code review.

## CATEGORY: Architecture

- AGI/AGI-adjacent systems (world models, recursive self-improvement)
- Agent swarms or multi-agent coordination
- Autonomous self-modification of runtime code
- LangChain, LlamaIndex, or any orchestration framework
- Any new async event loop or message bus beyond asyncio

## CATEGORY: Memory

- Unbounded conversation history storage (no eviction policy)
- Vector databases or embedding-based retrieval
- Self-modifying memory systems
- Cumulative context windows without eviction
- Persistent SQL-backed memory systems before Gate 5 approval

## CATEGORY: Execution

- runtime.py rewrites or re-architecture
- Operator authority bypass (calling subprocess outside operators)
- Uncontrolled browser automation (no headless, no Playwright/Selenium)
- Shell injection vectors (shell=True, eval, exec on user input)

## CATEGORY: Process

- Repo-wide refactors or renames
- Concurrent multi-agent edits to same files
- Premature UI rewrites (GUI, web dashboard, TUI)
- Any cloud dependency or external API that becomes required
- Feature additions without corresponding tests

## Enforcement

- Code review gate: diff must be checked against this list before merge
