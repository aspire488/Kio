# PERSONALITY_AND_IDENTITY_REPORT.md

## Symptom
- "Tell me something about yourself" → LLM fabrication: *"I'm a bit of a tech enthusiast…"*
- "Do you enjoy football?" / "Messi or Ronaldo?" → fabricated human opinions/preferences.

## Root Cause
1. **Prompt-driven fabrication.** `_chat_converse`'s system prompt in
   `mini_kio/core/pipeline/__init__.py` explicitly commanded the LLM to "have your own taste
   and perspective, like a friend", "express likes and dislikes directly", and
   "NEVER say 'I don't have personal feelings', 'as an AI'". This directly contradicts the
   KIO doctrine (Freedom of Mind, Governance of Action — companion, not human).
   The canonical `KIO_character_knowledge.py` is clean; the corruption came from the prompt.
2. **Identity escape.** `identity_dataset.py` triggers included "tell me about yourself" but
   not "tell me **something** about yourself"; substring phase requires the trigger to be a
   contiguous substring, so the variant fell through to the opinion/converse classifier → LLM.

## Fix
1. **Prompt rewritten** to the doctrine stance: short-first (1-2 sentences + expand offer),
   reasoned *analytical* opinions grounded in KIO's design philosophy, honest that KIO has no
   body/senses/emotions/personal taste — never claim personal experience of music/film/sport,
   discuss analytically. This is doctrine-compliant: KIO may express opinions, but must not
   invent human lived experience.
2. **Identity triggers expanded** with the escaping variants:
   "tell me something/a bit/a little/more about yourself".

## Verification
```
pipeline.run("Tell me something about yourself") → canonical KIO identity answer (deterministic)
pipeline.run("Who are you")                      → canonical KIO identity answer
classify("What do you think about AI?")          → identity (opinions_ai entry)
classify("Do you enjoy football?")               → conversation/converse (LLM, now honest prompt)
```

## Design Intent (matches doctrine §2, §20)
Opinion questions are NOT suppressed — they route to the LLM with a prompt that permits
reasoned analysis while forbidding invented human experience. Deterministic identity answers
take precedence for all self-description queries.
