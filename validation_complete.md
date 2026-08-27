# KIO P1.2 Guard-Set Live Telegram Validation

- Date: 2026-08-05T16:11:07
- Mode: ATTACH to running runtime (PID unchanged, no restart)
- Restart count: 0
- Guard set: G1 media / G2 transport / G3 forget passthroughs, G4 'again',
  G5 pronoun resolution + last_target fallback, S1/S2 continuation & affirmative
  markers (newly-live surface), plus 7 context-bleed scenarios (C-04 set).
- Result: 22/25 PASS, 2 FAIL, 1 PARTIAL

- G1/media_play_jazz: PASS (6.49s) Error: Couldn't play jazz on YouTube
- G2/transport_pause: PASS (2.25s) No media to pause
- G2/transport_resume: PASS (2.24s) No media to resume
- G3/forget_passthrough: FAIL (2.24s) Error: I don't remember anything about my name
- G4/prime_play_trailer: PASS (6.44s) Error: Couldn't play interstellar trailer on YouTube
- G4/again_repeat: FAIL (2.26s) No media to resume
- G5/prime_open_youtube: PASS (4.33s) Opened Youtube in Chrome
- G5/pronoun_close_it: PASS (6.4s) Closed chrome::open_url::https://www.youtube.com::youtube. Primary browser proce
- G5/prime_search_interstellar: PASS (2.25s) Searched: Interstellar
- G5/pronoun_who_directed: PASS (6.44s) You're talking about Christopher
- S1/continue_tell_more: PASS (4.35s) Christopher Nolan directed the movie Interstellar, a science fiction film that e
- S2/affirmative_go_ahead: PASS (4.41s) Couldn't play Interstellar official trailer on YouTube
- S2/affirmative_yes: PASS (2.45s) Christopher Nolan is known for his complex and thought-provoking storytelling, a
- S2/affirmative_okay: PASS (2.25s) Noted
- BLEED1/prime_interstellar: PASS (8.61s) Hey there! Interstellar actually started
- BLEED1/resolve_who_directed: PASS (4.32s) Oh, you mean Christopher Nolan! He
- BLEED2/prime_fifa: PASS (6.42s) Hey there! Spain actually won the FIFA
- BLEED2/resolve_who_scored: PASS (6.46s) 📍 FIFA World Cup scored Spain 1-0 Argentina | World Cup 2026 report and highligh
- BLEED3/prime_the_bear: PASS (10.61s) Error: Couldn't play the bear on YouTube
- BLEED3/resolve_who_created: PASS (6.53s) 📍 The Bear creator Christopher Storer Christopher Storer (born 1980 or 1981) is 
- BLEED4/cross_domain_knowledge: PASS (6.43s) Hey there! Quantum entanglement is basically a
- BLEED5/pronoun_no_bleed: PARTIAL (6.43s) 📍 Quantum Entanglement biography history Entanglement and experiment, part 1: Be
- BLEED6/prime_youtube2: PASS (4.36s) Opened Youtube in Chrome
- BLEED6/explicit_new_overrides: PASS (2.28s) Searched: pasta recipes
- BLEED6/resolve_close_it: PASS (2.34s) Closed Pasta recipes tab

Runtime left running per protocol (exactly one runtime).
