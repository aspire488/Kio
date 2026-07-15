# KIO V2 Overview

## KIO Executive

Central orchestrator that coordinates all runtimes, manages conversation flow, identity, personality, and supervises execution.

## AURA

Provides observation processing, long‑term memory, knowledge base, reasoning, planning, reflection, learning, world model, beliefs, goals, confidence, and continuity.

## Execution Fabric

Orchestrates task execution across runtimes, handling scheduling, dependency resolution, and resource allocation.

## Internal APIs

- **Adapter Registry** – Registers and resolves adapters for external repositories.
- **Observation Bus** – Publishes observations from AURA to KIO Executive and other consumers.
- **Provider System** – Routes provider calls (e.g., LLM, storage) through a unified interface.
- **BrowserFacade** – Abstracts browser interactions for the Execution Fabric.
- **Agent Runtime** – Hosts autonomous agents, managing their lifecycle.
- **Voice Runtime** – Handles voice input/output and coordination.
- **Avatar Runtime** – Manages avatar rendering and interaction pipelines.

## Infrastructure

- **MCP Runtime** – Micro‑container platform for service isolation (unchanged).
- **WorkflowEngine** – Executes defined workflows; remains untouched.

---

*ponytail: omitted exhaustive component diagrams – add when needed for stakeholder presentations.*