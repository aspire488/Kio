# External Dependency Authority Register (C‑5)

| Dependency | Purpose | KIO Owner | External Authority | Relationship | Runtime Status | Next Review Trigger | Last GitMCP Validation |
|------------|---------|-----------|--------------------|--------------|----------------|---------------------|------------------------|
| MarkItDown | Markdown ↔ HTML conversion | MarkItDownProvider | MarkItDown library | Wrapper | Active | On next upstream release | 2026‑07‑26 |
| Scrapling | Structured web extraction | ScraplingAdapter | Scrapling library | Wrapper | Active | On upstream API change | 2026‑07‑26 |
| Browser‑Use | AI‑driven browser automation (candidate) | – | Browser‑Use library | Reference/Candidate | Absent | When ADR revisited | 2026‑07‑26 |
| CUA | UI / desktop automation | CUAProvider | CUA library | Wrapper | Active | On CUA major version bump | 2026‑07‑26 |
| Agent‑Reach | Web reading / search | AgentReachAdapter | Agent‑Reach API | Reference | Stub | Deferred | 2026‑07‑26 |
| Agentic‑Inbox | Inbox routing | AgenticInboxAdapter | Agentic‑Inbox API | Reference | Stub | Deferred | 2026‑07‑26 |
| Shepherd | Distributed task scheduling | ShepherdAdapter | Shepherd server | Reference | Stub | Deferred | 2026‑07‑26 |
| LibreChat | Conversational UI | LibreChatAdapter | LibreChat backend | Reference | Stub | Deferred | 2026‑07‑26 |
| Open‑LLM‑VTuber | Voice / avatar interaction | VTuberAdapter | Open‑LLM‑VTuber | Reference | Stub | Deferred | 2026‑07‑26 |
| OpenWork | Workspace / session management | OpenWorkAdapter | OpenWork library | Reference | Stub | Deferred | 2026‑07‑26 |
| Crawl4AI | Large‑scale crawling | Crawl4AIAdapter | Crawl4AI service | Reference | Stub | Deferred | 2026‑07‑06 |
| Agency‑Swarm | Multi‑agent orchestration (reference) | – | Agency‑Swarm repo | Reference | Absent | When needed | 2026‑07‑26 |
| Awesome‑LLM‑Apps | Catalog of prompt‑ready apps (reference) | – | Awesome‑LLM‑Apps repo | Reference | Absent | When needed | 2026‑07‑26 |

*Notes*: Relationship indicates wrapper/reference. Runtime Status indicates Active, Stub, or Absent. Next Review Trigger ties validation to upstream changes or architectural decisions.