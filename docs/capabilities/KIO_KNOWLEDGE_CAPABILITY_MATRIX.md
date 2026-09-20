# KIO Knowledge Capability Matrix

**Date:** 2026-09-11  
**Phase:** 2 — Knowledge/Search  
**Total Capabilities:** 63 (none deleted, reduced, merged, or replaced)

## Phase 2 Impact: Templates Now Fully Executable

| # | Template ID | Category | YAML Action | Execution Path | Status |
|---|------------|----------|-------------|----------------|--------|
| 1 | ai.enrich_records | ai | `knowledge: batch_lookup` | KnowledgeProvider → web_search | **FULLY EXECUTABLE** |
| 2 | data.api_poll_to_store | data | `knowledge: paginated_get` | KnowledgeProvider → paginated_get | **FULLY EXECUTABLE** |
| 3 | data.webhook_to_store | data | `knowledge: verify_hmac` | KnowledgeProvider → verify_hmac | **FULLY EXECUTABLE** |
| 4 | monitoring.website_uptime | monitoring | `knowledge: healthcheck` | KnowledgeProvider → healthcheck | **FULLY EXECUTABLE** |
| 5 | research.youtube_summary | research | `knowledge: list_new_videos` | KnowledgeProvider → list_new_videos (DDG fallback) | **FULLY EXECUTABLE** |

## Phase 2 Impact: Previously Blocked Now Resolved

| # | Template ID | Category | YAML Action | Status |
|---|------------|----------|-------------|--------|
| 1 | monitoring.rss_news_monitor | monitoring | `knowledge: read_feeds` | **RESOLVED** (feedparser installed) |

## Still Blocked

| # | Template ID | Category | YAML Action | Blocker |
|---|------------|----------|-------------|---------|
| 1 | ai.rag_answer | ai | `knowledge: vector_search` | No vector DB installed (chromadb/qdrant) |

## 8 Knowledge Actions — Provider Contract

| Action | Input | Output | Category | Timeout | RAM |
|--------|-------|--------|----------|---------|-----|
| `web_search` | query (str) | {result, source} | READ | 10s | 10MB |
| `fetch_url` | url (str) | {content, content_length} | READ | 15s | 10MB |
| `fetch_wikipedia` | query (str) | {summary, source} | READ | 10s | 5MB |
| `healthcheck` | url (str) | {status_code, healthy, response_ms} | READ | 15s | 5MB |
| `list_new_videos` | sources (list) | {videos, count} | READ | 15s | 10MB |
| `read_feeds` | feeds (list) | {items, count} | READ | 15s | 10MB |
| `paginated_get` | url (str) | {items, count, pages_fetched} | READ | 30s | 10MB |
| `verify_hmac` | payload, secret, signature | {valid, computed_hash} | READ | 1s | 1MB |

## StepRunner Action Map (Knowledge)

| (capability, action) | boundary_action |
|----------------------|-----------------|
| (knowledge, web_search) | web_search |
| (knowledge, fetch_url) | fetch_url |
| (knowledge, fetch_wikipedia) | fetch_wikipedia |
| (knowledge, healthcheck) | healthcheck |
| (knowledge, list_new_videos) | list_new_videos |
| (knowledge, read_feeds) | read_feeds |
| (knowledge, paginated_get) | paginated_get |
| (knowledge, verify_hmac) | verify_hmac |
| (knowledge, query) | web_search (fallback) |
| (knowledge, search) | web_search (fallback) |
| (knowledge, retrieve) | fetch_url (fallback) |
| (knowledge, batch_lookup) | web_search (fallback) |
| (knowledge, multi_scan) | web_search (fallback) |

## Security Classification

All 8 knowledge actions: **READ** — no data mutation, no deletion, no credential access.

## 63 Count Preserved

No templates deleted, reduced, merged, or replaced. All 63 YAML templates remain in `automation/library/`.
