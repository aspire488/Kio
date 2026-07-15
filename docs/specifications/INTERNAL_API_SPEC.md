# INTERNAL API Specification

This document outlines the public interfaces that make up the **KIO Internal API**.  All adapters and external components must implement these protocols; no runtime logic lives here.

## Modules

- **browser.py** – `BrowserFacade` protocol for navigation, clicking, and text extraction.
- **workspace.py** – `Workspace` protocol for basic file‑system operations.
- **execution.py** – `ExecutionEngine` protocol for task submission and cancellation.
- **provider.py** – `Provider` protocol for generic service calls (LLM, storage, etc.).
- **communication.py** – `Communicator` protocol for channel‑based messaging.
- **voice.py** – `VoiceRuntime` protocol for audio capture and synthesis.
- **avatar.py** – `AvatarRuntime` protocol for rendering and updating avatars.
- **agent.py** – `AgentRuntime` protocol for managing autonomous agents.

All protocols are deliberately minimal, exposing only the essential operations required by the KIO architecture. Implementations may add richer semantics internally but must conform to these signatures.

---

*pony Tail: The spec purposefully omits concrete error‑type hierarchies and advanced configuration. Add richer definitions only when a concrete use‑case demands them.*
