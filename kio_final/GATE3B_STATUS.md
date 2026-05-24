# Gate 3B Status: Safe Intent Extraction

## Overview
Gate 3B implements the transformation of probabilistic LLM output into validated structured intents. This phase ensures that all LLM-derived instructions are treated as UNTRUSTED INPUT and subjected to rigorous, deterministic validation before they can reach the execution boundary.

## Intent Containment Guarantees
- **Isolation:** LLM outputs are parsed in a sandboxed classification layer (`IntentClassifier`) that has no access to system operators or runtime side-effects.
- **Model Separation:** Intents are represented by strict dataclasses (`ExtractedIntent`), preventing property injection or arbitrary payload carriage.
- **Trust Boundary:** The execution boundary (`execution_boundary.py`) now explicitly asserts that only validated intents may be dispatched.

## Validation Guarantees
- **Deterministic Rejection:** Any intent matching forbidden actions (e.g., `shutdown`, `rm`) or forbidden targets (e.g., `explorer.exe`, `registry`) is rejected.
- **Structural Integrity:** Executable intents must have both a clear action and a clear target; ambiguous or multi-target payloads are blocked.
- **Pattern Matching:** Detection of shell injection patterns (`;`, `&`, `|`, etc.) in both action and target fields.
- **Immutable Results:** Validation results never "repair" dangerous intents; they only mark them as unsafe and record errors.

## Runtime Authority Separation Doctrine
- **No Direct Routing:** The LLM cannot directly invoke operators. It can only propose a structure.
- **Explicit Handoff:** Transformation from "Proposed Intent" to "Executable Action" requires a discrete validation step that the LLM cannot bypass.
- **Zero-Authority Extraction:** The extraction and classification logic has zero runtime authority.

## Explicit Non-Goals
- **Autonomous Planning:** This phase does not allow the LLM to chain multiple actions or self-correct.
- **Real Execution:** No live execution of extracted intents was performed during Gate 3B validation.
- **Memory Systems:** No persistent storage of intents or context-aware intent refinement.

## Remaining Risks
- **Heuristic Limitations:** Natural language heuristics may misclassify complex phrasing; JSON-based extraction is the preferred high-fidelity path.
- **Target Aliasing:** While common system targets are blocked, clever aliasing or obfuscation in LLM output remains a theoretical risk managed by subsequent runtime checks.

## Validation Results
- **Compile Validation:** All Gate 3B modules passed `py_compile`.
- **Mocked Regression:** All test cases passed in `tests/gate3/test_intent_extraction.py`.
