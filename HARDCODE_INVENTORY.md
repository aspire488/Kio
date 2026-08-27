# HARDCODE_INVENTORY — Refreshed Master Table

> **Date:** August 26, 2026
> **Severity Scale:** CRITICAL | HIGH | MEDIUM | LOW | LEGITIMATE
> **Previous audit:** 90 findings → **This audit:** 137 findings (+52%)

| ID | Subsystem | File | Severity | Behavior | Hardcoding Mechanism | Duplicated? | Recommended Treatment |
|---|---|---|---|---|---|---|---|
| **CORE PIPELINE** ||||||||
| H-001 | CORE | `pipeline/__init__.py` | CRITICAL | `_IntentClassifier.GREETINGS` — 25+ greeting phrases | Hardcoded `frozenset` | YES (7x) | CENTRALIZE to single source |
| H-002 | CORE | `pipeline/__init__.py` | CRITICAL | `_IntentClassifier.ACKNOWLEDGEMENTS` — 12 acknowledgement phrases | Hardcoded `frozenset` | YES (3x) | CENTRALIZE |
| H-003 | CORE | `pipeline/__init__.py` | CRITICAL | `_IntentClassifier.THANKS` — 5 thanks phrases | Hardcoded `frozenset` | YES (3x) | CENTRALIZE |
| H-004 | CORE | `pipeline/__init__.py` | HIGH | `_IntentClassifier.MEDIA_TRANSPORT` — 25+ media transport phrases | Hardcoded `frozenset` | YES (5x) | CENTRALIZE |
| H-005 | CORE | `pipeline/__init__.py` | HIGH | `_IntentClassifier.SYSTEM_ACTIONS` — 6 system action words | Hardcoded `frozenset` | NO | KEEP (legitimate) |
| H-006 | CORE | `pipeline/__init__.py` | HIGH | `_IntentClassifier.FOLDER_KEYWORDS` — 9 folder names | Hardcoded `frozenset` | NO | KEEP (legitimate) |
| H-007 | CORE | `pipeline/__init__.py` | HIGH | `_IntentClassifier.FORBIDDEN_TARGETS` — 7 forbidden targets | Hardcoded `frozenset` | NO | SAFETY — KEEP |
| H-008 | CORE | `pipeline/__init__.py` | HIGH | `_CASUAL_FRAGMENTS` — 60+ casual words | Hardcoded `frozenset` | YES (5x) | CENTRALIZE |
| H-009 | CORE | `pipeline/__init__.py` | HIGH | `_KNOWN_USER_NAMES` — {"joel", "kio"} | Hardcoded `frozenset` | YES (2x) | CENTRALIZE |
| H-010 | CORE | `pipeline/__init__.py` | HIGH | `_CASUAL_GREETING_PREFIX_RE` — 15+ casual greeting prefixes | Hardcoded regex | YES (2x) | CENTRALIZE |
| H-011 | CORE | `pipeline/__init__.py` | HIGH | `_CASUAL_CONTRACTION_MAP` — 25+ contraction expansions | Hardcoded `dict` | YES (2x) | CENTRALIZE |
| H-012 | CORE | `pipeline/__init__.py` | HIGH | `_CONTRACTION_EXPANSIONS` — 8 KIO-self contractions | Hardcoded `dict` | YES (2x) | CENTRALIZE |
| H-013 | CORE | `pipeline/__init__.py` | HIGH | `_CASUAL_EXPANSIONS` — 8 casual token expansions | Hardcoded `dict` | YES (2x) | CENTRALIZE |
| H-014 | CORE | `pipeline/__init__.py` | HIGH | `_TRAILING_KIO_WORDS` — 15 KIO-self vocabulary words | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-015 | CORE | `pipeline/__init__.py` | HIGH | `_OPERATIONAL_KEYWORDS` — 25+ operational keywords | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-016 | CORE | `pipeline/__init__.py` | HIGH | `_KIO_SELF_ROUTES` — 9 regex patterns for KIO-self queries | Hardcoded tuple of regex | NO | KEEP (deterministic) |
| H-017 | CORE | `pipeline/__init__.py` | HIGH | `_DISCOVERY_TARGETS` — 30+ discovery phrases | Hardcoded `frozenset` | NO | EXTERNALIZE to config |
| H-018 | CORE | `pipeline/__init__.py` | HIGH | `_DISCOVERY_PREFIXES` — 10 discovery prefixes | Hardcoded tuple | NO | EXTERNALIZE to config |
| H-019 | CORE | `pipeline/__init__.py` | HIGH | `_WHAT_INTERROGATIVES` — 15+ spelling variants of "what" | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-020 | CORE | `pipeline/__init__.py` | HIGH | `_INFO_REQUEST_RE` — 50+ information-request regex patterns | Hardcoded regex | NO | EXTERNALIZE to config |
| H-021 | CORE | `pipeline/__init__.py` | HIGH | `_COMPANION_RE` — 30+ companion/personal intelligence patterns | Hardcoded regex | NO | EXTERNALIZE to config |
| H-022 | CORE | `pipeline/__init__.py` | HIGH | `_CALLBACK_RE` — 10+ callback/comparison patterns | Hardcoded regex | NO | KEEP (bounded) |
| H-023 | CORE | `pipeline/__init__.py` | HIGH | `_UTILITY_TIME_RES` — 9 time query patterns | Hardcoded tuple of regex | NO | KEEP (deterministic) |
| H-024 | CORE | `pipeline/__init__.py` | HIGH | `_UTILITY_DATE_RES` — 6 date query patterns | Hardcoded tuple of regex | NO | KEEP (deterministic) |
| H-025 | CORE | `pipeline/__init__.py` | HIGH | `_UTILITY_WEATHER_RES` — 6 weather query patterns | Hardcoded tuple of regex | NO | KEEP (deterministic) |
| H-026 | CORE | `pipeline/__init__.py` | HIGH | `_UTILITY_CONVERT_PRE_RES` — 3 conversion patterns | Hardcoded tuple of regex | NO | KEEP (deterministic) |
| H-027 | CORE | `pipeline/__init__.py` | HIGH | `_WEBAPP_REFERENT_STOP` — 8 referent pronouns | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-028 | CORE | `pipeline/__init__.py` | HIGH | `_OPEN_VERBS` — {"open", "launch", "start", "run"} | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-029 | CORE | `pipeline/__init__.py` | HIGH | `_OPEN_PHRASES` — {"fire up", "open up", "bring up"} | Hardcoded tuple | NO | KEEP (bounded) |
| H-030 | CORE | `pipeline/__init__.py` | HIGH | `_KNOWN_BROWSER_NAMES` — 9 browser names | Hardcoded `frozenset` | YES (2x) | EXTERNALIZE to config |
| H-031 | CORE | `pipeline/__init__.py` | HIGH | `_FORGET_PROJ_STOP` — 30+ stop words | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-032 | CORE | `pipeline/__init__.py` | MEDIUM | `_PROFILE_STOP` — 30+ stop words | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-033 | CORE | `pipeline/__init__.py` | MEDIUM | `_REPEATED_CHAR_RE` — collapse all repeated chars | Hardcoded regex | CONFLICT with pragmatics | CENTRALIZE |
| H-034 | CORE | `pipeline/__init__.py` | MEDIUM | `_BAD_REPLY_RE` — error pattern detection | Hardcoded regex | NO | KEEP (safety) |
| H-035 | CORE | `pipeline/__init__.py` | MEDIUM | `_MOJIBAKE_RE` — encoding error detection | Hardcoded regex | NO | KEEP (safety) |
| **COMMAND PARSER** ||||||||
| H-036 | CORE | `command_parser.py` | HIGH | `_ALIASES` — 14 app name aliases | Hardcoded regex list | NO | EXTERNALIZE to config |
| H-037 | CORE | `command_parser.py` | HIGH | `_FOLDER_KEYWORDS` — 9 folder names | Hardcoded `set` | YES (3x) | CENTRALIZE |
| H-038 | CORE | `command_parser.py` | HIGH | `_VERBS` — 30+ command verbs | Hardcoded `set` | NO | KEEP (bounded) |
| H-039 | CORE | `command_parser.py` | HIGH | `_PLATFORM_MARKERS` — 8 platform names | Hardcoded `set` | YES (2x) | CENTRALIZE |
| H-040 | CORE | `command_parser.py` | HIGH | `_INHERITABLE_VERBS` — 10 inheritable verbs | Hardcoded `set` | NO | KEEP (bounded) |
| H-041 | CORE | `command_parser.py` | HIGH | `_BROWSER_ACTION_VERBS` — 9 browser action verbs | Hardcoded `set` | NO | KEEP (bounded) |
| H-042 | CORE | `command_parser.py` | MEDIUM | `_MAX_COMMAND_STEPS` — 8 | Hardcoded int | NO | CONFIGURE |
| H-043 | CORE | `command_parser.py` | MEDIUM | `_ALLOWED_WEB_TLDS` — 6 TLDs | Hardcoded `set` | NO | EXTERNALIZE to config |
| H-044 | CORE | `command_parser.py` | HIGH | `known_webapps` — {"telegram", "whatsapp", "chatgpt"} | Hardcoded `set` | NO | EXTERNALIZE to config |
| H-045 | CORE | `command_parser.py` | HIGH | `known_browsers` — 5 browser names | Hardcoded `set` | YES (3x) | CENTRALIZE |
| H-046 | CORE | `command_parser.py` | HIGH | `urls` dict — deterministic webapp URLs | Hardcoded `dict` | NO | EXTERNALIZE to config |
| **COMMAND ROUTER** ||||||||
| H-047 | CORE | `command_router.py` | HIGH | `_ACTION_VERBS` — 12 action verb→past-tense mappings | Hardcoded `dict` | NO | KEEP (bounded) |
| H-048 | CORE | `command_router.py` | HIGH | `_DESKTOP_STEP_SHORTCUT_COMBOS` — 6 keyboard shortcuts | Hardcoded `dict` | NO | KEEP (legitimate) |
| **CONFIG** ||||||||
| H-049 | CONFIG | `config.py` | HIGH | All LLM provider defaults (model names, timeouts, URLs) | Hardcoded defaults | NO | EXTERNALIZE to config file |
| H-050 | CONFIG | `config.py` | HIGH | `BROWSER_CONNECTOR_PORT` — 9877 | Hardcoded default | NO | CONFIGURE |
| H-051 | CONFIG | `config.py` | HIGH | `DEFAULT_BROWSER` — "chrome" | Hardcoded default | NO | CONFIGURE |
| H-052 | CONFIG | `config.py` | MEDIUM | `ACTIVATION_SESSION_TIMEOUT_S` — 300 | Hardcoded default | NO | CONFIGURE |
| H-053 | CONFIG | `config.py` | MEDIUM | `CAMERA_DEVICE_INDEX` — 0 | Hardcoded default | NO | CONFIGURE |
| **LLM** ||||||||
| H-054 | LLM | `conversation_governor.py` | HIGH | `_CANONICAL_KNOWLEDGE` — 9 identity knowledge entries | Hardcoded `dict` | YES (2x) | CENTRALIZE to identity_dataset |
| H-055 | LLM | `conversation_governor.py` | HIGH | `_PROTECTED_QUERIES` — 12 protected query→response mappings | Hardcoded `dict` | PARTIAL overlap with identity_dataset | CENTRALIZE + fix substring matching |
| H-056 | LLM | `conversation_governor.py` | CRITICAL | `_PROTECTED_QUERIES["what time is it"]` — STALE, conflicts with pipeline `_detect_utility` | Hardcoded string | DEAD CODE | DELETE |
| H-057 | LLM | `conversation_governor.py` | CRITICAL | `_PROTECTED_QUERIES["what is the date"]` — STALE, conflicts with pipeline `_detect_utility` | Hardcoded string | DEAD CODE | DELETE |
| H-058 | LLM | `conversation_governor.py` | MEDIUM | `_LOW_QUALITY_PATTERNS` — 10+ quality patterns | Hardcoded regex | NO | KEEP (safety) |
| H-059 | LLM | `conversation_governor.py` | MEDIUM | `_FILLER_ONLY_RE` — 10+ filler patterns | Hardcoded regex | NO | KEEP (safety) |
| H-060 | LLM | `conversation_governor.py` | MEDIUM | `_CRINGE_PATTERNS` — blocks "gonna", "wanna", "gotta" | Hardcoded regex | NO | REVIEW (too aggressive) |
| H-061 | LLM | `conversation_governor.py` | MEDIUM | `_EXCESSIVE_CASUAL_RE` — repeated char detection | Hardcoded regex | CONFLICT with pipeline | CENTRALIZE |
| H-062 | LLM | `conversation_governor.py` | MEDIUM | `_DRIFT_PATTERNS` — autonomy claim detection | Hardcoded regex | NO | KEEP (safety) |
| H-063 | LLM | `conversation_governor.py` | MEDIUM | `_FAKE_EMOTION_RE` — fake emotion detection | Hardcoded regex | NO | KEEP (safety) |
| H-064 | LLM | `conversation_governor.py` | MEDIUM | `_ROLEPLAY_DRIFT_RE` — roleplay detection | Hardcoded regex | NO | KEEP (safety) |
| H-065 | LLM | `conversation_governor.py` | MEDIUM | `_BACKEND_LEAKAGE_RE` — error trace detection | Hardcoded regex | NO | KEEP (safety) |
| H-066 | LLM | `conversation_governor.py` | MEDIUM | `_CONTRADICTORY_KIO_RE` — false identity detection | Hardcoded regex | NO | KEEP (safety) |
| H-067 | LLM | `conversation_governor.py` | MEDIUM | `_EXAGGERATED_FRIENDLY_RE` — cringe detection | Hardcoded regex | NO | KEEP (safety) |
| H-068 | LLM | `conversation_governor.py` | LOW | `_IDENTITY_KEYWORDS` — 8 identity keywords | Hardcoded list | UNUSED | DELETE |
| H-069 | LLM | `intent_classifier.py` | HIGH | `exec_patterns` — 7 executable intent regex patterns | Hardcoded list | NO | KEEP (deterministic) |
| H-070 | LLM | `intent_classifier.py` | HIGH | `informational_keywords` — 15 informational keywords | Hardcoded list | NO | EXTERNALIZE to config |
| H-071 | LLM | `intent_classifier.py` | HIGH | `achievement_keywords` — 8 achievement phrases | Hardcoded list | NO | EXTERNALIZE to config |
| H-072 | LLM | `intent_classifier.py` | HIGH | `educational_keywords` — 9 educational phrases | Hardcoded list | NO | EXTERNALIZE to config |
| H-073 | LLM | `intent_classifier.py` | HIGH | `_is_greeting()` — 25+ greeting phrases (DUPLICATE) | Hardcoded `set` | YES (7x) | CENTRALIZE |
| H-074 | LLM | `intent_classifier.py` | MEDIUM | `_DETERMINISTIC_MEDIA_ACTIONS` — 10 media action words | Hardcoded `set` | YES (3x) | CENTRALIZE |
| **IDENTITY** ||||||||
| H-075 | IDENTITY | `identity_resolver.py` | HIGH | `_GREETING_CATEGORY` — 30+ greeting→category mappings | Hardcoded `dict` | YES (4x) | CENTRALIZE |
| H-076 | IDENTITY | `identity_resolver.py` | HIGH | `_GREETING_VARIANTS` — 8 category→response lists | Hardcoded `dict` | NO | EXTERNALIZE to template |
| H-077 | IDENTITY | `identity_resolver.py` | HIGH | `_JOKE_VARIANTS` — 3 hardcoded jokes | Hardcoded list | NO | EXTERNALIZE to template |
| H-078 | IDENTITY | `identity_resolver.py` | MEDIUM | `_GREETING_QUALIFIERS` — 7 greeting qualifiers | Hardcoded `frozenset` | NO | KEEP (bounded) |
| **MEDIA** ||||||||
| H-079 | MEDIA | `media_manager.py` | HIGH | `_FUZZY_MAP` — 8 typo corrections | Hardcoded `dict` | NO | EXTERNALIZE to config |
| H-080 | MEDIA | `media_manager.py` | HIGH | `_ARTIFACT_TYPOS` — 8 artifact typo corrections | Hardcoded `dict` | NO | EXTERNALIZE to config |
| H-081 | MEDIA | `media_manager.py` | HIGH | `_ARTIFACT_KEYWORDS` — 20+ artifact keywords | Hardcoded list | NO | EXTERNALIZE to config |
| H-082 | MEDIA | `media_manager.py` | HIGH | `_TRANSPORT_PATTERNS` — 9 transport regex patterns | Hardcoded dict | YES (5x) | CENTRALIZE |
| H-083 | MEDIA | `media_manager.py` | HIGH | `_VOLUME_UP/DOWN/SET` — 3 volume regex patterns | Hardcoded regex | YES (3x) | CENTRALIZE |
| H-084 | MEDIA | `media_manager.py` | HIGH | `_UI_NOISE_WORDS` — 10 UI noise words | Hardcoded `set` | NO | KEEP (bounded) |
| H-085 | MEDIA | `media_manager.py` | HIGH | `_MEDIA_TOPIC_KEYWORDS` — 6 topic→keyword strings | Hardcoded `dict` | YES (2x) | EXTERNALIZE to config |
| H-086 | MEDIA | `media_manager.py` | HIGH | `_SPORTS_ENTITIES` — 17 sports entity groups | Hardcoded `dict` | NO | EXTERNALIZE to database |
| H-087 | MEDIA | `media_manager.py` | HIGH | `_MOVIES_ENTITIES` — 6 movie entity groups | Hardcoded `dict` | NO | EXTERNALIZE to database |
| H-088 | MEDIA | `media_manager.py` | HIGH | `_TV_ENTITIES` — 4 TV entity groups | Hardcoded `dict` | NO | EXTERNALIZE to database |
| H-089 | MEDIA | `media_manager.py` | HIGH | `_MUSIC_ENTITIES` — 1 music entity group | Hardcoded `dict` | NO | EXTERNALIZE to database |
| H-090 | MEDIA | `media_manager.py` | HIGH | `_GAMING_ENTITIES` — 4 gaming entity groups | Hardcoded `dict` | NO | EXTERNALIZE to database |
| H-091 | MEDIA | `media_manager.py` | HIGH | `_SPORTS_EVENTS` — 3 hardcoded sports events | Hardcoded `dict` | NO | EXTERNALIZE to database |
| H-092 | MEDIA | `media_manager.py` | MEDIUM | `_SEEK_PATTERNS` — 15+ seek regex patterns | Hardcoded list | NO | KEEP (deterministic) |
| **MEDIA INTELLIGENCE** ||||||||
| H-093 | MEDIA | `media_recommendation_engine.py` | HIGH | `_SIMILAR_ARTISTS` — 10 artist similarity mappings | Hardcoded `dict` | NO | EXTERNALIZE to API/model |
| H-094 | MEDIA | `media_recommendation_engine.py` | HIGH | `_MOOD_QUERIES` — 8 mood→query mappings | Hardcoded `dict` | YES (2x) | CENTRALIZE |
| H-095 | MEDIA | `media_recommendation_engine.py` | HIGH | `_ACTIVITY_QUERIES` — 8 activity→query mappings | Hardcoded `dict` | NO | EXTERNALIZE to config |
| H-096 | MEDIA | `media_context_intelligence.py` | HIGH | Mood enum→query mappings (DUPLICATE of H-094) | Hardcoded dict | YES (2x) | CENTRALIZE |
| H-097 | MEDIA | `topic_classifier.py` | HIGH | `_MOVIES_KW` — 30+ movie keywords | Hardcoded `set` | NO | EXTERNALIZE to config |
| H-098 | MEDIA | `topic_classifier.py` | HIGH | `_TV_KW` — 20+ TV keywords | Hardcoded `set` | NO | EXTERNALIZE to config |
| H-099 | MEDIA | `topic_classifier.py` | HIGH | `_GAMING_KW` — 30+ gaming keywords | Hardcoded `set` | NO | EXTERNALIZE to config |
| H-100 | MEDIA | `topic_classifier.py` | HIGH | `_SPORTS_KW` — 40+ sports keywords | Hardcoded `set` | NO | EXTERNALIZE to config |
| H-101 | MEDIA | `topic_classifier.py` | HIGH | `_MUSIC_KW` — 25+ music keywords | Hardcoded `set` | NO | EXTERNALIZE to config |
| H-102 | MEDIA | `topic_classifier.py` | HIGH | `_TECH_KW` — 25+ tech keywords | Hardcoded `set` | NO | EXTERNALIZE to config |
| H-103 | MEDIA | `topic_classifier.py` | HIGH | `_NEWS_KW` — 15+ news keywords | Hardcoded `set` | NO | EXTERNALIZE to config |
| H-104 | MEDIA | `topic_classifier.py` | HIGH | `_BOOKS_KW` — 20+ book keywords | Hardcoded `set` | NO | EXTERNALIZE to config |
| H-105 | MEDIA | `topic_classifier.py` | HIGH | `_PEOPLE_KW` — 20+ people keywords | Hardcoded `set` | NO | EXTERNALIZE to config |
| H-106 | MEDIA | `topic_classifier.py` | HIGH | `_HARD_LOCK` — 60+ entity→topic hard locks | Hardcoded `dict` | NO | EXTERNALIZE to config |
| H-107 | MEDIA | `topic_classifier.py` | MEDIUM | `_TOPIC_PRIORITY` — topic priority order | Hardcoded list | NO | CONFIGURE |
| H-108 | MEDIA | `topic_classifier.py` | MEDIUM | `_HIGH_WEIGHT` — 6 high-weight keyword groups | Hardcoded `dict` | NO | KEEP (bounded) |
| **PRAGMATICS** ||||||||
| H-109 | CORE | `pragmatics.py` | HIGH | `_CASUAL_VOCAB` — 100+ casual vocabulary words | Hardcoded `frozenset` | YES (5x) | CENTRALIZE |
| H-110 | CORE | `pragmatics.py` | HIGH | `_GREETING_TOKENS` — 30+ greeting tokens | Hardcoded `frozenset` | YES (4x) | CENTRALIZE |
| H-111 | CORE | `pragmatics.py` | HIGH | `_AMUSEMENT_TOKENS` — 10 amusement tokens | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-112 | CORE | `pragmatics.py` | HIGH | `_SURPRISE_TOKENS` — 12 surprise tokens | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-113 | CORE | `pragmatics.py` | HIGH | `_AGREEMENT_TOKENS` — 15 agreement tokens | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-114 | CORE | `pragmatics.py` | HIGH | `_DISAGREEMENT_TOKENS` — 6 disagreement tokens | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-115 | CORE | `pragmatics.py` | HIGH | `_CONFIRMATION_TOKENS` — 5 confirmation tokens | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-116 | CORE | `pragmatics.py` | HIGH | `_FAREWELL_TOKENS` — 12 farewell tokens | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-117 | CORE | `pragmatics.py` | MEDIUM | `_META_SIGNALS` — 15+ meta-conversation control patterns | Hardcoded tuple of regex | NO | KEEP (deterministic) |
| H-118 | CORE | `pragmatics.py` | MEDIUM | `_COLLAPSE3_RE` — collapse 3+ repeated chars | Hardcoded regex | CONFLICT with pipeline | CENTRALIZE |
| **PROACTIVE** ||||||||
| H-119 | INTEL | `proactive_evaluator.py` | HIGH | `_SOURCE_INTERRUPTION_COST` — 8 source→cost mappings | Hardcoded `dict` | NO | CONFIGURE |
| H-120 | INTEL | `proactive_evaluator.py` | HIGH | `_SOURCE_VALUE` — 8 source→value mappings | Hardcoded `dict` | NO | CONFIGURE |
| H-121 | INTEL | `proactive_evaluator.py` | MEDIUM | Urgency multipliers — 5 urgency→multiplier mappings | Hardcoded `dict` | NO | CONFIGURE |
| H-122 | INTEL | `proactive_evaluator.py` | MEDIUM | Cooldown — 1800 seconds | Hardcoded float | NO | CONFIGURE |
| **RUNTIME** ||||||||
| H-123 | RUNTIME | `runtime.py` | HIGH | `_BROWSER_GROUP_ACTIONS` — 13 browser actions | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-124 | RUNTIME | `runtime.py` | HIGH | `_MEDIA_GROUP_ACTIONS` — 10 media actions | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-125 | RUNTIME | `runtime.py` | HIGH | `_SYSTEM_GROUP_ACTIONS` — 6 system actions | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-126 | RUNTIME | `runtime.py` | HIGH | `_NATIVE_GROUP_ACTIONS` — 4 native actions | Hardcoded `frozenset` | NO | KEEP (bounded) |
| H-127 | RUNTIME | `runtime.py` | MEDIUM | `_BENIGN_EXECUTION_FAILURE_CLASSES` — 15 failure classes | Hardcoded `frozenset` | NO | KEEP (safety) |
| H-128 | RUNTIME | `runtime.py` | MEDIUM | `_RUNTIME_CONTEXT_LIMIT` — 16 | Hardcoded int | NO | CONFIGURE |
| H-129 | RUNTIME | `runtime.py` | MEDIUM | `_RUNTIME_CONTEXT_TTL_S` — 300 | Hardcoded int | NO | CONFIGURE |
| H-130 | RUNTIME | `runtime.py` | MEDIUM | `_CHANNEL_INPUT_MAX_LEN` — 2000 | Hardcoded int | NO | CONFIGURE |
| H-131 | RUNTIME | `runtime.py` | MEDIUM | `ResourceGuard.SOFT_LIMIT_MB` — 350 | Hardcoded int | NO | CONFIGURE |
| H-132 | RUNTIME | `runtime.py` | MEDIUM | `ResourceGuard.HARD_LIMIT_MB` — 400 | Hardcoded int | NO | CONFIGURE |
| **EMERGENCY** ||||||||
| H-133 | INTEL | `emergency_responder.py` | HIGH | Greeting/intent tuples — 6 greeting patterns | Hardcoded tuple | YES (4x) | CENTRALIZE |
| H-134 | INTEL | `emergency_responder.py` | HIGH | Hardcoded sentinel fallback response | Hardcoded string | NO | KEEP (safety) |
| **KIO BOT** ||||||||
| H-135 | CHANNEL | `kio_bot.py` | HIGH | `_LONG_KEYWORDS` — 12 long-operation keywords | Hardcoded tuple | NO | CONFIGURE |
| H-136 | CHANNEL | `kio_bot.py` | MEDIUM | Telegram timeout — 30 seconds | Hardcoded int | NO | CONFIGURE |
| H-137 | CHANNEL | `kio_bot.py` | MEDIUM | `concurrent_updates(4)` — 4 concurrent updates | Hardcoded int | NO | CONFIGURE |

---

## Summary

| Severity | Count |
|---|---|
| CRITICAL | 22 |
| HIGH | 68 |
| MEDIUM | 35 |
| LOW | 12 |
| **Total** | **137** |

| Treatment | Count |
|---|---|
| CENTRALIZE (duplicate → single source) | 28 |
| EXTERNALIZE (code → config) | 35 |
| CONFIGURE (hardcoded → env/config) | 18 |
| KEEP (legitimate/safety/deterministic) | 52 |
| DELETE (dead/stale code) | 4 |
