# GATE 2 ARCHITECTURE PLAN: DETERMINISTIC EXPANSION

**Version:** 2.0  
**Status:** DRAFT / PROPOSED  
**Scope:** Operator Maturity & Contextual Stability  

## 1. Core Philosophy
Gate 2 evolves KIO from a "reactive prototype" to a "reliable desktop operator." The architecture remains lightweight and deterministic, prioritizing runtime preservation over autonomy.

### Strict Non-Negotiables
- **No Autonomous Loops:** KIO only acts on explicit user triggers.
- **No Background Agency:** No "think-loops" or self-initiated tasks.
- **Bounded Resource Usage:** Memory must remain < 150MB RSS during idle.
- **Trace-Driven Integrity:** Every state change must be emitted as a normalized JSON trace.

## 2. Layered Architecture Evolution

### 2.1. The Intelligence Nucleus (Refinement)
- **Contextual Memory (Bounded):** Transition from flat `context_items` to a structured `ContextBuffer` (deque, maxlen=16). It stores the last N interactions to resolve simple anaphora (e.g., "close it" referring to the last opened app).
- **Conversational Fallback:** Controlled handoff to LLM for intent disambiguation ONLY, not for execution planning.

### 2.2. The Operator Layer (Strengthening)
- **Discovery Service:** Decouple "finding an app/file" from "executing it." Operators will use a lightweight `Registry` for common aliases and path resolution.
- **Process Tracking:** Operators will move toward PID-aware control to verify if an application actually launched or closed.

### 2.3. The Verification Layer (Expansion)
- **Outcome Verification:** Move beyond "did the function return?" to "did the system state change?" (e.g., checking if a process exists after `open_app`).
- **Diagnostic Probes:** Runtime-owned probes that can query system state without affecting execution flow.

## 3. Structural Components

| Component | Responsibility | Gate 2 Evolution |
| :--- | :--- | :--- |
| **Runtime** | State & Lifecycle | Integrity monitoring & watchdog integration. |
| **Boundary** | Side-effect Handoff | Multi-stage verification (Pre-check, Exec, Post-check). |
| **Memory** | Bounded State | Structured deque for interaction history (16-item cap). |
| **Operators** | System Interaction | Process-aware controls & safer discovery logic. |
| **Diagnostics** | Visibility | Real-time health scoring & event-stream normalization. |

## 4. Execution Flow: Deterministic Scaling
1. **Trigger:** User command via Telegram or Gesture.
2. **Resolve:** Command Parser maps intent using Alias Registry + Context Memory.
3. **Guard:** Execution Boundary checks category permissions and resource health.
4. **Execute:** Operator performs action (Process-aware).
5. **Verify:** Boundary runs post-execution diagnostic probe.
6. **Report:** Result returned to user; Trace emitted to log.

---
*Gate 2 must preserve Gate 1 stability by ensuring all new features are optional plugins to the core Nucleus.*
