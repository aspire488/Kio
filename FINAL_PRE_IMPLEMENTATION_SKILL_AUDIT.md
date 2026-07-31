# KIO Engineering Playbook — Final Pre-Implementation Skill Audit

## 1. Complete Skill Catalogue (40 SKILL.md files)

### .agent-skills/ (30 — 24 standalone + 6 ponytail)

| # | Skill | File | Purpose | Phase |
|---|-------|------|---------|-------|
| 1 | api-and-interface-design | .agent-skills/api-and-interface-design/SKILL.md | Contract-first API design, error responses, Hyrum's Law | Design |
| 2 | browser-testing-with-devtools | .agent-skills/browser-testing-with-devtools/SKILL.md | Chrome DevTools MCP for live browser testing | Verify |
| 3 | build-and-distribution | .agent-skills/build-and-distribution/SKILL.md | Build config, distribution pipelines, multi-platform | Ship |
| 4 | ci-cd-and-automation | .agent-skills/ci-cd-and-automation/SKILL.md | Quality gate pipeline (lint→type→test→build→integration→e2e) | Ship |
| 5 | code-review-and-quality | .agent-skills/code-review-and-quality/SKILL.md | Five-axis review: correctness, readability, arch, security, perf | Verify |
| 6 | code-simplification | .agent-skills/code-simplification/SKILL.md | Preserve behavior, reduce complexity, eliminate dead code | Implement |
| 7 | context-engineering | .agent-skills/context-engineering/SKILL.md | Context hierarchy: rules→docs→source→errors→history | All |
| 8 | debugging-and-error-recovery | .agent-skills/debugging-and-error-recovery/SKILL.md | Stop-the-line, triage checklist, root cause before fix | Debug |
| 9 | deprecation-and-migration | .agent-skills/deprecation-and-migration/SKILL.md | Code is liability, remove > maintain, migration plans | Maintain |
| 10 | documentation-and-adrs | .agent-skills/documentation-and-adrs/SKILL.md | ADRs for arch decisions, document why not what | Design |
| 11 | doubt-driven-development | .agent-skills/doubt-driven-development/SKILL.md | Adversarial fresh-context review before non-trivial decisions | Design |
| 12 | frontend-ui-engineering | .agent-skills/frontend-ui-engineering/SKILL.md | Component tree, state co-location, progressive enhancement | Implement |
| 13 | git-workflow-and-versioning | .agent-skills/git-workflow-and-versioning/SKILL.md | Trunk-based git, atomic commits, .gitignore | All |
| 14 | idea-refine | .agent-skills/idea-refine/SKILL.md | Divergent→convergent idea sharpening | Design |
| 15 | incremental-implementation | .agent-skills/incremental-implementation/SKILL.md | Thin vertical slices, test-verify-commit cycles | Implement |
| 16 | interview-me | .agent-skills/interview-me/SKILL.md | One-question-at-a-time intent extraction before planning | Design |
| 17 | observability-and-instrumentation | .agent-skills/observability-and-instrumentation/SKILL.md | Define "working" before instrumenting, 3-pillar telemetry | Verify |
| 18 | performance-optimization | .agent-skills/performance-optimization/SKILL.md | Measure before optimize, 80/20 bottleneck targeting | Optimize |
| 19 | planning-and-task-breakdown | .agent-skills/planning-and-task-breakdown/SKILL.md | Decompose into small verifiable tasks with checkpoints | Plan |
| 20 | security-and-hardening | .agent-skills/security-and-hardening/SKILL.md | Threat model first, STRIDE per boundary, dependency review | Design |
| 21 | shipping-and-launch | .agent-skills/shipping-and-launch/SKILL.md | Pre-launch checklist, monitoring, rollback, staged rollout | Ship |
| 22 | source-driven-development | .agent-skills/source-driven-development/SKILL.md | Framework decisions backed by official docs, not memory | Design |
| 23 | spec-driven-development | .agent-skills/spec-driven-development/SKILL.md | Gated workflow: specify→plan→tasks→implement | Plan |
| 24 | test-driven-development | .agent-skills/test-driven-development/SKILL.md | RED→GREEN→REFACTOR, Prove-It pattern for bugs | Implement |
| 25 | using-agent-skills | .agent-skills/using-agent-skills/SKILL.md | Meta-skill: discover/invoke right skill by phase | All |
| 26 | observability-cost-optimization | .agent-skills/observability-cost-optimization/SKILL.md | Sampling, pre-aggregation, cost budgeting for telemetry | Optimize |
| 27 | observability-runbooks | .agent-skills/observability-runbooks/SKILL.md | Runbook structure, alert response, incident playbooks | Verify |
| 28 | prompt-engineering | .agent-skills/prompt-engineering/SKILL.md | Structured prompting for code generation | All |
| 29 | stress-testing | .agent-skills/stress-testing/SKILL.md | Load/soak/stress testing methodologies | Verify |
| 30 | documentation-specialist | .agent-skills/documentation-specialist/SKILL.md | Doc generation, API docs, user guides | Ship |

### ponytail sub-family (.agent-skills/ponytail/skills/)

| # | Skill | Purpose | Phase |
|---|-------|---------|-------|
| 31 | ponytail | Laziest correct solution, ladder (YAGNI→stdlib→native→deps→1line→min) | Implement |
| 32 | ponytail-review | Diff review for unnecessary complexity | Verify |
| 33 | ponytail-audit | Repo-wide bloat scan | Maintain |
| 34 | ponytail-debt | Harvest ponytail: comments into ledger | Maintain |
| 35 | ponytail-help | Quick reference card | All |
| 36 | ponytail-gain | Scoreboard: less code, less cost, more speed | Inform |

### .claude/skills/gitnexus/ (6)

| # | Skill | Purpose | Phase |
|---|-------|---------|-------|
| 37 | gitnexus-cli | Index/analyze/context Cypher query commands | All |
| 38 | gitnexus-debugging | query+context+trace debugging pattern | Debug |
| 39 | gitnexus-exploring | Understanding code with query+clusters+process | Explore |
| 40 | gitnexus-impact-analysis | Blast radius before editing | Implement |
| 41 | gitnexus-refactoring | Safe rename/extract/split with dependency mapping | Implement |
| 42 | gitnexus-guide | Tool/resource/schema reference | All |

### Other locations (3)

| # | Skill | Location | Purpose | Phase |
|---|-------|----------|---------|-------|
| 43 | karpathy-guidelines | .config/opencode/skills/ | Think before coding, surgical changes, Goal-Driven Exec | All |
| 44 | learn | .hermes/skills/ | Search/install/rate agent skills from agentskill.sh | All |
| 45 | review-skill / agentskill-sh-review-skill | .hermes/skills/ + .agents/skills/ | SKILL.md quality review on 10 dimensions | All |

---

## 2. Categorised Capability Matrix

| Capability | Skills |
|------------|--------|
| **Planning & Spec** | spec-driven-development, planning-and-task-breakdown, interview-me, idea-refine |
| **Design & Architecture** | api-and-interface-design, documentation-and-adrs, security-and-hardening, source-driven-development, doubt-driven-development |
| **Implementation** | incremental-implementation, test-driven-development, code-simplification, frontend-ui-engineering, ponytail, gitnexus-impact-analysis, gitnexus-refactoring |
| **Verification** | code-review-and-quality, browser-testing-with-devtools, observability-and-instrumentation, ponytail-review, stress-testing, observability-runbooks |
| **Debugging** | debugging-and-error-recovery, gitnexus-debugging |
| **Optimisation** | performance-optimization, observability-cost-optimization |
| **Shipping** | ci-cd-and-automation, shipping-and-launch, build-and-distribution |
| **Maintenance** | deprecation-and-migration, ponytail-audit, ponytail-debt |
| **Meta/Cross-cutting** | using-agent-skills, context-engineering, git-workflow-and-versioning, prompt-engineering, karpathy-guidelines, learn, review-skill, gitnexus-exploring, gitnexus-cli, gitnexus-guide, ponytail-help, documentation-specialist |

---

## 3. Top 20 Constant-Use Skills (every session)

| Rank | Skill | Why |
|------|-------|-----|
| 1 | karpathy-guidelines | Ruled in AGENTS.md — always loaded. Think before coding, surgical changes. |
| 2 | ponytail | Ruled in AGENTS.md — always loaded full-level. Laziest correct solution. |
| 3 | context-engineering | Before any work, establish context hierarchy. |
| 4 | gitnexus-exploring | Understanding unfamiliar code. |
| 5 | gitnexus-impact-analysis | Before editing any symbol (AGENTS.md mandate). |
| 6 | incremental-implementation | Every feature: thin vertical slices. |
| 7 | using-agent-skills | Meta: discover which skill fits current phase. |
| 8 | code-simplification | Keep code simple as you write it. |
| 9 | git-workflow-and-versioning | Atomic commits, trunk-based. |
| 10 | planning-and-task-breakdown | Decompose work before starting. |
| 11 | test-driven-development | Red-green-refactor for all new logic. |
| 12 | debugging-and-error-recovery | Stop-the-line rule. |
| 13 | source-driven-development | Official docs over memory for framework decisions. |
| 14 | prompt-engineering | Structured prompts for code generation. |
| 15 | gitnexus-debugging | Trace bugs via knowledge graph. |
| 16 | gitnexus-refactoring | Safe rename/extract/split. |
| 17 | code-review-and-quality | Five-axis review before PR. |
| 18 | ponytail-review | Over-engineering check on diffs. |
| 19 | security-and-hardening | Threat model per boundary. |
| 20 | learn | Discover new skills when needed. |

---

## 4. Phase-Mapped Skill Invocation Guide

### DESIGN phase
1. interview-me → extract intent
2. idea-refine → sharpen concept
3. source-driven-development → research frameworks
4. doubt-driven-development → adversarial review
5. security-and-hardening → threat model
6. api-and-interface-design → contract-first
7. documentation-and-adrs → ADR for decision
8. spec-driven-development → write spec

### PLAN phase
1. spec-driven-development → gated tasks
2. planning-and-task-breakdown → decompose
3. gitnexus-exploring → understand affected code
4. gitnexus-impact-analysis → blast radius

### IMPLEMENT phase
1. gitnexus-impact-analysis → verify blast radius before edit
2. ponytail → laziest correct solution
3. karpathy-guidelines → surgical change, think first
4. test-driven-development → RED→GREEN→REFACTOR
5. incremental-implementation → thin slice, test, commit
6. code-simplification → reduce complexity during writing
7. gitnexus-refactoring → if renaming/extracting
8. frontend-ui-engineering → if UI work
9. git-workflow-and-versioning → atomic commits

### VERIFY phase
1. code-review-and-quality → five-axis review
2. ponytail-review → over-engineering check
3. browser-testing-with-devtools → live browser testing
4. observability-and-instrumentation → define "working"
5. stress-testing → load testing if applicable
6. observability-runbooks → runbook for new features

### DEBUG phase
1. debugging-and-error-recovery → stop, triage, root cause
2. gitnexus-debugging → trace via knowledge graph

### OPTIMISE phase
1. performance-optimization → measure first, 80/20
2. observability-cost-optimization → cost reduction

### SHIP phase
1. ci-cd-and-automation → quality gates
2. build-and-distribution → build config
3. shipping-and-launch → pre-launch checklist
4. documentation-specialist → docs generation

### MAINTAIN phase
1. deprecation-and-migration → remove or migrate
2. ponytail-audit → periodic bloat scan
3. ponytail-debt → harvest ponytail: comments into ledger

---

## 5. Pre-PR Checklist (must-run before every PR)

- [ ] gitnexus-impact-analysis on every changed symbol
- [ ] karpathy-guidelines: verify surgical change (not scope creep)
- [ ] ponytail-review: over-engineering check on diff
- [ ] code-review-and-quality: five-axis review
- [ ] test-driven-development: RED→GREEN passed
- [ ] incremental-implementation: verify one thin slice per commit
- [ ] gitnexus-refactoring: confirm safe rename/extract if applicable
- [ ] git-workflow-and-versioning: atomic commits, meaningful messages

---

## 6. Pre-Release Checklist (before any release)

- [ ] ci-cd-and-automation: full pipeline green
- [ ] shipping-and-launch: run pre-launch checklist
- [ ] build-and-distribution: verify build artifacts
- [ ] security-and-hardening: dependency review, threat model pass
- [ ] stress-testing: load test results within thresholds
- [ ] observability-and-instrumentation: telemetry confirms "working"
- [ ] deprecation-and-migration: no stale code shipping
- [ ] documentation-specialist: docs updated

---

## 7. Duplicates & Overlaps (confirmed, no action needed)

| Skills | Overlap | Resolution |
|--------|---------|------------|
| review-skill + agentskill-sh-review-skill | Identical content | Same skill installed in two locations. Use either. |
| ponytail + code-simplification | Both reduce complexity | ponytail = laziness ladder, code-simplification = structural simplification. Complementary. |
| ponytail-review + code-review-and-quality | Both review diffs | ponytail-review focuses on over-engineering only; code-review-and-quality is full five-axis. Run both. |
| spec-driven-development + planning-and-task-breakdown | Both produce plans | spec-drove writes the spec; planning decomposes it. Run sequentially. |
| gitnexus-debugging + debugging-and-error-recovery | Both debug | gitnexus = knowledge graph trace; debugging = triage protocol. Complementary. |
| context-engineering + using-agent-skills + karpathy-guidelines | Meta-instructions all | context-engineering = file/context hierarchy; using-agent-skills = skill discovery; karpathy = thinking protocol. Non-overlapping. |

---

## 8. Skills Never Needed for KIO (excluded from Toolbox)

| Skill | Reason |
|-------|--------|
| observability-cost-optimization | No observability platform deployed; no telemetry cost to optimise. Revisit when KIO has production observability. |
| observability-runbooks | Same rationale — no runbooks to write until observability exists. |
| stress-testing | KIO is in pre-implementation; no production traffic to load test. Revisit before first major release. |
| build-and-distribution | No multi-platform distribution configured. Revisit when packaging for distribution. |
| documentation-specialist | Documentation will be written ad-hoc by the developer. Dedicated doc generation is premature. |
| ponytail-audit | Full-repo bloat scan is premature until KIO has substantial codebase. Revisit quarterly. |
| ponytail-debt | No ponytail: comments have been left yet. Revisit after first implementation phase. |
| learn | Agent skill management from agentskill.sh — not needed unless acquiring new skills. |
| review-skill / agentskill-sh-review-skill | SKILL.md quality review — these skill files are already audited. Only use if writing new skill files. |

---

## 9. KIO Engineering Toolbox (permanent subset)

These 23 skills form the permanent KIO Engineering Toolbox. All implementation work uses these exclusively.

### Always-On (loaded by AGENTS.md or active every session)
1. karpathy-guidelines
2. ponytail (full)
3. context-engineering
4. using-agent-skills
5. gitnexus-impact-analysis (mandated by AGENTS.md)
6. gitnexus-exploring
7. gitnexus-cli

### Design & Planning (invoke as needed)
8. interview-me
9. idea-refine
10. source-driven-development
11. doubt-driven-development
12. security-and-hardening
13. api-and-interface-design
14. documentation-and-adrs
15. spec-driven-development
16. planning-and-task-breakdown

### Implementation & Testing (invoke per task)
17. incremental-implementation
18. test-driven-development
19. code-simplification
20. gitnexus-refactoring

### Review & Debug (invoke per PR or per bug)
21. code-review-and-quality
22. ponytail-review
23. debugging-and-error-recovery
24. gitnexus-debugging

### Shipping (invoke per release)
25. ci-cd-and-automation
26. shipping-and-launch

### Cross-cutting
27. git-workflow-and-versioning
28. prompt-engineering
29. frontend-ui-engineering

---

## 10. Summary

- **40 skills audited** across 5 locations
- **29 retained** in KIO Engineering Toolbox
- **9 excluded** as premature (revisit post-launch)
- **2 duplicates** confirmed (review-skill, no action)
- **0 gaps** — all phases covered
- **Pre-PR checklist**: 8 items
- **Pre-release checklist**: 8 items
- **Phase map**: 8 phases with ordered invocation

This document supersedes all previous audit files. Implementation begins using the KIO Engineering Toolbox above.
