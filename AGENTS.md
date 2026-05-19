<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Kio** (1234 symbols, 2097 relationships, 108 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Kio/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Kio/clusters` | All functional areas |
| `gitnexus://repo/Kio/processes` | All execution flows |
| `gitnexus://repo/Kio/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |
| Work in the Cluster_11 area (23 symbols) | `.claude/skills/generated/cluster-11/SKILL.md` |
| Work in the Cluster_7 area (15 symbols) | `.claude/skills/generated/cluster-7/SKILL.md` |
| Work in the Kio_final area (13 symbols) | `.claude/skills/generated/kio-final/SKILL.md` |
| Work in the Cluster_5 area (12 symbols) | `.claude/skills/generated/cluster-5/SKILL.md` |
| Work in the Cluster_6 area (12 symbols) | `.claude/skills/generated/cluster-6/SKILL.md` |
| Work in the Cluster_16 area (12 symbols) | `.claude/skills/generated/cluster-16/SKILL.md` |
| Work in the Plugins area (12 symbols) | `.claude/skills/generated/plugins/SKILL.md` |
| Work in the Cluster_4 area (11 symbols) | `.claude/skills/generated/cluster-4/SKILL.md` |
| Work in the Cluster_9 area (10 symbols) | `.claude/skills/generated/cluster-9/SKILL.md` |
| Work in the Cluster_31 area (9 symbols) | `.claude/skills/generated/cluster-31/SKILL.md` |
| Work in the Cluster_8 area (8 symbols) | `.claude/skills/generated/cluster-8/SKILL.md` |
| Work in the Cluster_10 area (8 symbols) | `.claude/skills/generated/cluster-10/SKILL.md` |
| Work in the Cluster_30 area (8 symbols) | `.claude/skills/generated/cluster-30/SKILL.md` |
| Work in the Cluster_18 area (7 symbols) | `.claude/skills/generated/cluster-18/SKILL.md` |
| Work in the Cluster_37 area (7 symbols) | `.claude/skills/generated/cluster-37/SKILL.md` |
| Work in the Cluster_20 area (6 symbols) | `.claude/skills/generated/cluster-20/SKILL.md` |
| Work in the Cluster_22 area (6 symbols) | `.claude/skills/generated/cluster-22/SKILL.md` |
| Work in the Cluster_24 area (6 symbols) | `.claude/skills/generated/cluster-24/SKILL.md` |
| Work in the Cluster_35 area (6 symbols) | `.claude/skills/generated/cluster-35/SKILL.md` |
| Work in the Cluster_21 area (5 symbols) | `.claude/skills/generated/cluster-21/SKILL.md` |

<!-- gitnexus:end -->
