# Root-Cause Report: Async/Sync Boundary Regressions

## Overview

This report details the root causes of async/sync boundary regressions leading to coroutine objects propagating through `ConversationResponder`, `KnowledgeResolver`, and `RetrievalIntelligenceRouter`, and clarifies changes in LLM routing.

## 1. `knowledge_router.py` No Longer Exists

**Finding:** The file `knowledge_router.py` no longer exists.
**Explanation:** The functionality previously housed in `knowledge_router.py` has been moved to `mini_kio/knowledge/retrieval_router.py`. The primary class responsible for knowledge routing within this file is `RetrievalIntelligenceRouter`, which includes a comment `# Renamed from KnowledgeRouter`, confirming this refactoring.

## 2. `_ask_gemini` Routing Changes

**Finding:** `_ask_gemini` no longer directly routes through `llm_router.ask_llm` as an `await`able call.
**Explanation:** The function `_ask_gemini` (located in `mini_kio/llm/conversation_responder.py`) has been redefined to call `ask_llm_sync` instead of directly `await`ing `llm_router.ask_llm`.

**`mini_kio/llm/conversation_responder.py`:**
```python
def _ask_gemini(user_text: str, system_prompt: Optional[str] = None) -> Optional[str]:
    return ask_llm_sync(user_text, system_prompt=system_prompt)
```

`ask_llm_sync` (defined in `mini_kio/llm/llm_ops.py`) acts as a synchronous wrapper around the asynchronous `llm_router.ask_llm`. It achieves this by explicitly managing the asynchronous execution within a synchronous context using `asyncio.run_coroutine_threadsafe` or `asyncio.run`.

**`mini_kio/llm/llm_ops.py`:**
```python
def ask_llm_sync(...) -> Optional[str]:
    # ...
    try:
        loop = asyncio.get_running_loop()
        future = asyncio.run_coroutine_threadsafe(
            ask_llm(prompt, timeout=timeout, max_tokens=max_tokens),
            loop
        )
        content = future.result(timeout=timeout + 5.0)
    except RuntimeError:
        try:
            content = asyncio.run(ask_llm(prompt, timeout=timeout, max_tokens=max_tokens))
        # ...
    return sanitized if sanitized else None
```

**Impact:** While `_ask_gemini` ultimately still utilizes `llm_router.ask_llm`, the introduction of `ask_llm_sync` forces a synchronous blocking execution of what is an asynchronous operation. This can lead to performance bottlenecks and prevent proper integration within an `async` event loop if `_ask_gemini` itself is intended to be part of an `async` workflow. Callers of `_ask_gemini` are expecting a synchronous `Optional[str]`.

## 3. Async/Sync Boundary Regressions Leading to Coroutine Propagation

### Affected Functions and Return Type Changes:

#### a. `RetrievalIntelligenceRouter.route` and `RetrievalIntelligenceRouter.route_freshness`

**Location:** `mini_kio/knowledge/retrieval_router.py`
**Change:** These methods are now `async def` functions, explicitly returning coroutine objects.
- `async def route(self, query: str) -> LLMResponse`
- `async def route_freshness(self, query: str) -> Optional[MultiSourceResult]`
**Previous State (Inferred):** Given the nature of the regression, it's highly probable these methods were previously synchronous, returning `LLMResponse` or `Optional[MultiSourceResult>` directly.

### Callers Expecting Synchronous Values:

#### a. `KnowledgeResolver.resolve`

**Location:** `mini_kio/resolvers/knowledge_resolver.py`
**Definition:** `def resolve(self, text: str, state: SessionState, trace: TraceContext) -> Optional[str]`
**Issue:** This method is synchronous but calls the asynchronous methods of `RetrievalIntelligenceRouter` without `await`.

- **Call to `self._router.route_freshness`:**
  ```python
  res = self._router.route_freshness(text)
  ```
  **Expected:** `Optional[MultiSourceResult]`
  **Actual:** `res` receives a coroutine object. `KnowledgeResolver.resolve` then attempts to process `res` as if it were the resolved value (e.g., `if res:` or `isinstance(res, str)`), which will lead to runtime errors or incorrect logic as `res` is an unawaited coroutine.

- **Call to `self._router.route`:**
  ```python
  wiki = self._router.route(text)
  ```
  **Expected:** `LLMResponse`
  **Actual:** `wiki` receives a coroutine object. `KnowledgeResolver.resolve` then processes `wiki` as if it were the resolved value (e.g., `if wiki:`), and then attempts to return this coroutine object as `Optional[str]`, violating its own type hint.

**Impact:** `KnowledgeResolver.resolve` improperly propagates coroutine objects, expecting them to be synchronous return values from `RetrievalIntelligenceRouter`.

#### b. `ConversationResponder.generate`

**Location:** `mini_kio/llm/conversation_responder.py`
**Definition:** `def generate(...) -> str`
**Issue:** This method is synchronous and calls the synchronous `KnowledgeResolver.resolve`, which, as identified above, is already propagating coroutine objects.

- **Calls to `self._knowledge_resolver.resolve`:**
  ```python
  res = self._knowledge_resolver.resolve(pending.query, self._state, trace)
  # ...
  if res: # This 'if' check will pass for a coroutine object
      self._state.mark_pending_executed()
      return self._finalize_response(text, res, trace) # 'res' is a coroutine
  # ...
  reply = self._knowledge_resolver.resolve(text, self._state, trace)
  # ...
  is_knowledge_failure = not reply or (isinstance(reply, str) and "couldn't find" in reply.lower())
  ```
  **Expected:** `Optional[str]`
  **Actual:** `res` (and `reply`) receive coroutine objects from `KnowledgeResolver.resolve`. `ConversationResponder.generate` then proceeds to treat these coroutine objects as strings (e.g., `isinstance(reply, str)`, `in reply.lower()`), leading to `TypeError` or `AttributeError` at runtime.

**Impact:** `ConversationResponder.generate` receives and incorrectly processes coroutine objects, leading to severe runtime errors and the propagation of unawaited asynchronous operations up the call stack.

## Conclusion

The core of the async/sync boundary regression lies in the transition of key knowledge retrieval logic (`RetrievalIntelligenceRouter.route` and `route_freshness`) to asynchronous functions without corresponding `await` calls in their synchronous callers (`KnowledgeResolver.resolve`). This propagates unawaited coroutine objects, which are then mishandled by upstream synchronous components like `ConversationResponder.generate` that expect concrete string values. Additionally, `_ask_gemini`'s use of a synchronous wrapper (`ask_llm_sync`) for an asynchronous LLM call introduces blocking behavior, potentially impacting overall performance and responsiveness.