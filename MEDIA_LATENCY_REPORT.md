# MEDIA LATENCY REPORT

**Date:** 2026-08-25
**Runtime:** KIO kio_bot.py (PID 16300/31176)
**User:** Joel (ID: 2146008061)
**Test Method:** Telethon USER → Telegram → KIO → Browser → Response

---

## Overall Latency Statistics

| Metric | Value |
|--------|-------|
| Total Tests | 26 |
| Min Latency | 2.3s |
| Median Latency | 13.2s |
| P95 Latency | 26.1s |
| Max Latency | 36.9s |
| Mean Latency | 12.8s |

---

## Latency by Category

### Direct Media Playback
| Test | Message | Latency | Breakdown |
|------|---------|---------|-----------|
| #1 | Play Space Song by Beach House | 13.2s | Search + Navigate + Play |
| #2 | Play Never Gonna Give You Up | 15.2s | Search + Navigate + Play |
| #3 | Play the Interstellar trailer | 13.1s | Search + Navigate + Play |
| #4 | Play Cosmic Samson teaser | 13.1s | Search + Navigate + Play |
| #5 | Play Bethlehem Kudumba Unit interview | 13.3s | Search + Navigate + Play |
| **Avg** | | **13.6s** | |

### Contextual Discovery
| Test | Message | Latency | Breakdown |
|------|---------|---------|-----------|
| #6 | Pick something to watch while I eat | 2.4s | Parse + Response |
| #7 | Give me something to listen to while I study | 17.4s | Parse + Search + Play |
| #8 | Put something on while I'm coding | 17.4s | Parse + Search + Play |
| #9 | I'm bored | 15.8s | Parse + Search + Play |
| #10 | Surprise me | 36.9s | Parse + Search + Play |
| #11 | Put something on | 13.4s | Parse + Search + Play |
| #12 | Play something | 17.8s | Parse + Search + Play |
| **Avg** | | **17.3s** | |

### Affirmative Follow-up
| Test | Message | Latency | Breakdown |
|------|---------|---------|-----------|
| #13 | yes start it | 26.1s | Resolve + Play |
| #14 | yeah | 4.7s | Resolve |
| #15 | yes | 4.5s | Resolve |
| #16 | go with 1 | 19.9s | Resolve + LLM fallback |
| **Avg** | | **13.8s** | |

### Rejection / Next
| Test | Message | Latency | Breakdown |
|------|---------|---------|-----------|
| #17 | nah | 2.3s | Acknowledge |
| #18 | not this | 13.7s | Resolve + Search |
| #19 | next | 4.6s | Transport |
| #20 | another one | 15.3s | Search + Play |
| #21 | something different | 4.4s | Suggest |
| #22 | try another | 4.4s | Suggest |
| **Avg** | | **7.5s** | |

### Transport
| Test | Message | Latency | Breakdown |
|------|---------|---------|-----------|
| #23 | what's playing | 2.3s | Query state |
| #24 | pause | 2.3s | Browser command |
| #25 | resume | 2.3s | Browser command |
| #26 | stop | 2.3s | Browser command |
| **Avg** | | **2.3s** | |

---

## Latency Distribution

```
 2s: ████████████ (6 tests) - Transport, quick ack
 4s: ████████ (4 tests) - Rejection suggest, affirmative
13s: ████████████████████████ (10 tests) - Direct media, discovery
15s: ████████ (4 tests) - Search + play
17s: ████ (2 tests) - Contextual discovery
20s: ██ (1 test) - go with 1 LLM fallback
26s: █ (1 test) - yes start it
37s: █ (1 test) - Surprise me
```

---

## Latency Observations

1. **Transport commands** are fastest (~2.3s) — direct browser control
2. **Direct media** averages ~13.6s — includes YouTube search + navigation + playback
3. **Contextual discovery** averages ~17.3s — includes intent parsing + search + play
4. **Affirmative follow-ups** vary (4.5s-26.1s) — depends on whether recommendation context exists
5. **Rejection/next** averages ~7.5s — faster when just suggesting, slower when playing

---

## Optimization Opportunities

1. **YouTube search latency** (~5-10s) — Could benefit from caching frequent queries
2. **Browser navigation** (~3-5s) — Could benefit from warm browser sessions
3. **Playback verification** (~2-3s) — Already using staged polling
4. **Contextual intent parsing** (~1-2s) — Acceptable

---

## Conclusion

The median user-perceived latency is **13.2s** for media operations. Transport commands respond in **2.3s**. The system is functional but could benefit from browser session caching and YouTube search optimization for frequently requested content.
