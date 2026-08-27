# GPU_RUNTIME_AUDIT.md
# GPU Availability and Utilization Audit
# ======================================

## HARDWARE

| Component | Status |
|-----------|--------|
| GPU Model | NVIDIA GeForce RTX 3050 6GB Laptop GPU |
| VRAM | 6GB |
| CUDA Driver | Available (nvidia-smi functional) |
| CUDA Python | ❌ NOT available |
| PyTorch | 2.13.0+cpu (CPU-only build) |

## CURRENT KIO COMPUTE ARCHITECTURE

| Component | Inference Type | Local/Remote | GPU Useful? |
|-----------|---------------|-------------|-------------|
| LLM conversation | API (Gemini/Groq/OpenRouter) | Remote | ❌ No |
| LLM classification | Deterministic regex/rules | Local | ❌ No |
| Media search | API (YouTube Data API) | Remote | ❌ No |
| Media playback | Browser (YouTube web) | Remote | ❌ No |
| Web retrieval | API (Exa/Tavily/DDG) | Remote | ❌ No |
| Identity dataset | Deterministic lookup | Local | ❌ No |
| Pragmatics analysis | Deterministic NLP | Local | ❌ No |
| Intent classification | Deterministic rules | Local | ❌ No |
| Context intelligence | Deterministic rules | Local | ❌ No |
| Semantic graph | SQLite | Local | ❌ No |
| Browser automation | WebSocket/CDP | Local | ❌ No |
| Telegram polling | API | Remote | ❌ No |

## GPU WORKLOAD ASSESSMENT

### What COULD benefit from GPU
1. **Local embedding model** — if KIO used local embeddings for semantic similarity
2. **Local reranking model** — if KIO reranked search results locally
3. **Local small LLM** — if KIO used a local 7B/13B model for classification
4. **Local speech-to-text** — if KIO used Whisper for voice input
5. **Local text-to-speech** — if KIO used local TTS

### What KIO ACTUALLY uses
- **All inference is API-based** (remote LLM providers)
- **All classification is deterministic** (regex/rules)
- **No local ML models are loaded**
- **No PyTorch operations in production code**

### VRAM feasibility (6GB)
- Whisper large-v3: ~3GB → ✅ Feasible
- 7B model (Q4 quantized): ~4GB → ✅ Feasible
- 13B model (Q4 quantized): ~7GB → ❌ Exceeds VRAM
- Embedding model (BGE-small): ~500MB → ✅ Feasible
- Reranking model (cross-encoder): ~500MB → ✅ Feasible

## GPU ACCELERATION RECOMMENDATION

### CPU Path (CURRENT — recommended to keep)
- All inference via API
- Deterministic classification
- No local GPU workload
- **Status: WORKING, no change needed**

### GPU Path (OPTIONAL — if voice/LLM features added)
- Install CUDA-enabled PyTorch (when needed)
- Local Whisper for voice-to-text
- Local small LLM for classification fallback
- Local embeddings for semantic search
- **Status: NOT NEEDED until voice features are added**

### Hybrid Path (RECOMMENDED for future)
- API inference for conversation (high quality)
- Local GPU for voice-to-text (low latency)
- Local GPU for embeddings (privacy + speed)
- CPU fallback for all GPU operations
- **Status: ARCHITECTURE READY — no GPU code in production**

## IMPACT ON HARDCODE AUDIT

**GPU status: NOT APPLICABLE to hardcoding reduction**

KIO's hardcoding issues are in:
- Phrase lists → no GPU needed
- Routing logic → no GPU needed
- Response generation → API-based, no GPU needed
- Media behavior → browser-based, no GPU needed

GPU acceleration would only be relevant if KIO adds:
- Voice input/output
- Local LLM fallback
- Local embedding/reranking

**Recommendation: Document GPU availability for future reference. Do not install CUDA PyTorch until a concrete GPU workload is identified.**
