# Capability Authority Matrix (C‑5)

| Capability | Canonical KIO Provider | External Authority | Decision | Confidence |
|-----------|-----------------------|--------------------|----------|------------|
| MCP Runtime | `mcp_runtime/` (self) | Self (Opencode) | KEEP | High |
| Document conversion (MD↔HTML) | `MarkItDownProvider` (adapter) | MarkItDown library | KEEP | High |
| Web extraction | `ScraplingAdapter` (thin delegator) | Scrapling library | MODIFY | Medium |
| Browser automation | Playwright provider (`mini_kio/browser_runtime/`) | Browser‑Use (candidate) | KEEP (per ADR) | Medium |
| Computer‑use | `CUAProvider` (adapter) | CUA library | KEEP | High |

*Stubs (Reference Only)*: `AgentReachAdapter`, `AgenticInboxAdapter`, `ShepherdAdapter`, `LibreChatAdapter`, `VTuberAdapter`, `OpenWorkAdapter`, `Crawl4AIAdapter`.
