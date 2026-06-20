\# KIO Mandatory Engineering Workflow



Before any implementation:



Read:



\* AGENTS.md

\* CLAUDE.md

\* KIO Architecture v1.1

\* KIO Future Architecture Master

\* KIO Future Implementation Master



Then read:



.agent-skills/using-agent-skills/SKILL.md



Select applicable skills.



For debugging:



\* debugging-and-error-recovery

\* observability-and-instrumentation

\* doubt-driven-development

\* code-review-and-quality



For implementation:



\* spec-driven-development

\* planning-and-task-breakdown

\* incremental-implementation

\* test-driven-development

\* code-review-and-quality



For releases:



\* shipping-and-launch

\* performance-optimization

\* security-and-hardening



Required output before coding:



SKILLS SELECTED:



\* ...



Required output before declaring success:



EVIDENCE:



\* ...



VALIDATION:



\* ...



REGRESSION CHECK:



\* ...



ROLLBACK PLAN:



\* ...



For KIO, runtime validation means:



python -c "from mini\_kio.core.runtime import run\_runtime; run\_runtime()"



Pytest alone is insufficient.



Repository source code is the source of truth.



Do not trust previous reports.



Reproduce, trace, localize, fix, validate.



