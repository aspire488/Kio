# KIO Media Provider Readiness Audit

**Date:** 2026-09-15  
**Scope:** Read-only audit of media capability across YAML templates, providers, and infrastructure.

---

## 1. YAML Templates Using `capability: media`

| Template ID | File | Media Actions Used |
|---|---|---|
| `media.content_repurpose` | `library/media/content_repurpose.yaml` | `publish`, `verify_posts` |
| `communication.voice_assistant` | `library/communication/voice_assistant.yaml` | `text_to_speech` |
| `files.drive_to_social` | `library/files/drive_to_social.yaml` | `transcode_variants` |
| `ai.image_generate` | `library/ai/image_generate.yaml` | `generate_image` |

**Total: 4 templates, 5 distinct media actions required.**

### Required Media Actions (Automation)

| Action | Template(s) | Purpose |
|---|---|---|
| `publish` | `media.content_repurpose` | Publish content to social platforms |
| `verify_posts` | `media.content_repurpose` | Verify published posts are live |
| `text_to_speech` | `communication.voice_assistant` | Synthesize voice from text reply |
| `transcode_variants` | `files.drive_to_social` | Resize/reformat media for target platforms |
| `generate_image` | `ai.image_generate` | Generate images from text prompts |

---

## 2. Existing Media Infrastructure

### 2a. step_runner.py `_ACTION_MAP` (lines 231–237)

All 7 media actions are mapped to `"execute_capability"`:

```python
("media", "transcribe"): "execute_capability",
("media", "generate_image"): "execute_capability",
("media", "process_video"): "execute_capability",
("media", "publish"): "execute_capability",
("media", "text_to_speech"): "execute_capability",
("media", "transcode_variants"): "execute_capability",
("media", "verify_posts"): "execute_capability",
```

**Status:** Routing is wired. All media automation actions route to `execute_capability` via the `app::cap::args` format.

### 2b. capability_resolver.py

```python
_CAPABILITY_TO_PROVIDER = { ..., "media": ["media"], ... }
_ALWAYS_AVAILABLE = frozenset({"workflow", "memory"})  # media NOT included
```

Blocking reason: `"Media provider not available"`.

**Status:** Resolver expects a registered provider named `"media"`. Since no such provider exists in the `ProviderRegistry`, `check_capabilities(["media"])` returns `{media: False}`. Any template listing `media` in `capabilities_required` will be **BLOCKED** at pre-flight check.

### 2c. status.py `_check_media()` (line 128–129)

```python
def _check_media(self) -> dict[str, Any]:
    return {"available": False, "reason": "Media provider not implemented"}
```

**Status:** Explicitly reports unavailable. No subsystem can satisfy this check.

### 2d. Operational Health (operational_health.py:161–164)

```python
existing = getattr(MediaManager, "_instance", None)
out["media"] = "ready" if existing is not None else "available"
```

**Status:** Reports "available" or "ready" if `MediaManager` singleton exists. This is for the playback subsystem, NOT the automation provider — different concern.

### 2e. ProviderRegistry

No provider with `id() == "media"` or `capabilities()` containing a `"media"` `ProviderCapability` is registered. The `get_provider("media")` call returns `None`.

**Status:** No automation media provider exists.

---

## 3. What Existing Media Code Actually Handles

The existing media subsystem is a **playback/transport controller**, not a content-processing automation provider.

| Component | Interface | Actions |
|---|---|---|
| `media.providers.MediaProvider` (ABC) | Playback control | `play`, `pause`, `resume`, `stop`, `next_track`, `previous_track`, `seek`, `volume`, `search`, `close`, `check_active` |
| `media.providers.YouTubeProvider` | YouTube playback | Same as above + YouTube API search |
| `media.providers.BrowserProvider` | Browser media control | Same as above + browser tab resolution |
| `media.providers.LocalMediaProvider` | Local file playback | Same as above + file playback |
| `core.media_contract.MediaProvider` (ABC) | Contract layer | `id`, `tier`, `supported_types`, `search`, `play`, `verify_playback`, `pause`, `resume`, `next_track`, `prev_track`, `set_volume`, `get_position`, `health` |
| `media.media_manager.MediaManager` | Orchestrator | `play()`, `pause()`, `resume()`, `stop()`, session management |
| `core.pipeline._exec_media` | Pipeline dispatch | Only handles `play` and `play_discovery` actions |

**Overlap with automation requirements: 0%.** The existing providers handle media playback; the templates need content creation, transcription, image generation, video transcoding, publishing, and post verification — none of which exist in any media provider.

---

## 4. Per-Template Blocking Analysis

### Template: `media.content_repurpose`
- **Capabilities required:** `ai_reasoning`, `workflow`, `media`
- **Media actions:** `publish`, `verify_posts`
- **Other blocking capabilities:** None — `ai_reasoning` maps to `llm` provider (available), `workflow` is always available.
- **Media-only blocked:** Yes
- **Can any existing code handle these actions?** No. No provider implements `publish` or `verify_posts`.

### Template: `communication.voice_assistant`
- **Capabilities required:** `ai_reasoning`, `communication`, `media`
- **Media actions:** `text_to_speech`
- **Other blocking capabilities:** `ai_reasoning` (available via LLM), `communication` (available via telegram/discord).
- **Media-only blocked:** Yes (when `config.reply_voice == true`)
- **Can any existing code handle this action?** No. No provider implements `text_to_speech`. Note: the `transcribe` step uses `ai_reasoning`, not `media`, so transcription itself works.

### Template: `files.drive_to_social`
- **Capabilities required:** `filesystem`, `media`
- **Media actions:** `transcode_variants`
- **Other blocking capabilities:** `filesystem` (available).
- **Media-only blocked:** Yes
- **Can any existing code handle this action?** No. No provider implements `transcode_variants`.

### Template: `ai.image_generate`
- **Capabilities required:** `filesystem`, `media`
- **Media actions:** `generate_image`
- **Other blocking capabilities:** `filesystem` (available).
- **Media-only blocked:** Yes
- **Can any existing code handle this action?** No. No provider implements `generate_image`. (Note: there may be image generation code in the `media` package, but it is not wired as an `ExecutionProvider`.)

---

## 5. Gap Summary

| Automation Action | Provider Implementation | `ExecutionProvider` Registered | `ProviderRegistry` Entry | Status |
|---|---|---|---|---|
| `publish` | ❌ None | ❌ No | ❌ No | **Missing** |
| `verify_posts` | ❌ None | ❌ No | ❌ No | **Missing** |
| `text_to_speech` | ❌ None | ❌ No | ❌ No | **Missing** |
| `transcode_variants` | ❌ None | ❌ No | ❌ No | **Missing** |
| `generate_image` | ❌ None | ❌ No | ❌ No | **Missing** |
| `transcribe` | ⚠️ Routed via `ai_reasoning` | N/A | N/A | Routed elsewhere |
| `process_video` | ❌ None | ❌ No | ❌ No | **Missing** |

**Root cause:** The existing media subsystem is a playback transport layer. No `ExecutionProvider`-conformant media provider exists for content creation/processing actions. The step_runner correctly routes these actions to `execute_capability`, but the target provider is absent.

---

## 6. Recommendation

**Rating: C — Partial capability. Infrastructure exists but actions are unimplemented.**

**Rationale:**
- The routing layer (`step_runner._ACTION_MAP`, `capability_resolver`) is correctly wired for media actions
- The existing media subsystem handles playback/transport but has **zero overlap** with automation content-processing actions
- All 4 templates are **blocked exclusively by media** (no other missing capabilities)
- Building the missing `ExecutionProvider` is the single blocker — routing, resolution, and dispatch are ready

**Minimum viable path:** Create a `MediaAutomationProvider(ExecutionProvider)` that implements `execute(action, target, **kwargs)` for the 5 required actions, register it in `ProviderRegistry` with `ProviderCapability(name="media")`, and update `status._check_media()` to check for it.

**Estimated effort:** 1 provider class + 1 registration call. All 5 actions can delegate to existing libraries (ffmpeg for transcode, openai/whisper for TTS, OpenAI DALL-E/Stable Diffusion for image gen, social API clients for publish). No architecture changes needed.
