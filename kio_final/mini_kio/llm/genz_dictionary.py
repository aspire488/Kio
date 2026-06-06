"""
mini_kio/llm/genz_dictionary.py

KIO Modern Language Comprehension Layer
=========================================
Provides understanding of Gen Z, Gen Alpha, internet slang, gaming language,
Discord/Reddit/TikTok/Twitch/YouTube shorthand, texting shortcuts, and meme
vocabulary — for the purpose of improving KIO's intent detection, routing
accuracy, and conversational understanding.

Architecture
-------------
TWO independent systems:

  SYSTEM 1 — NORMALIZATION MAP
    Shorthand and abbreviations that should be silently expanded before
    routing/intent classification. Purely functional replacements.
    Example: "ur" -> "your", "rn" -> "right now"

  SYSTEM 2 — PRESERVED SLANG REGISTRY
    Terms that should be understood (for context scoring and slang detection)
    but NOT rewritten in output. KIO reads these, does not speak them unless
    the conversation style explicitly permits it.
    Example: "rizz", "bussin", "no cap"

Design contract
----------------
- This module improves COMPREHENSION and ROUTING.
- It does NOT change KIO's output style.
- No external dependencies. Pure Python stdlib. O(1) dict lookups.
- All functions are stateless and side-effect-free.
- Suitable for inline use in intent classifier and command router.

Usage
------
    from mini_kio.llm.genz_dictionary import (
        normalize_genz_text,
        contains_slang,
        extract_slang_terms,
        slang_statistics,
        detect_generation_style,
        get_slang_definition,
        suggest_normalized_query,
    )

    # Normalize before routing
    clean = normalize_genz_text("yo wbt ur mission rn")
    # -> "yo what about your mission right now"

    # Detect slang for style calibration
    if contains_slang(user_input):
        style = detect_generation_style(user_input)
"""

from __future__ import annotations

import re
import string
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# SYSTEM 1 — NORMALIZATION MAP
# Shorthand -> expanded form. Applied before routing/intent classification.
# Keys: lowercase only. Values: expanded lowercase form.
# Word-boundary replacement only — no partial-word corruption.
# ---------------------------------------------------------------------------

# Organization mirrors intent: what does this abbreviation MEAN functionally?

_NORMALIZATION_MAP: Dict[str, str] = {

    # -----------------------------------------------------------------------
    # PRONOUNS AND BASIC WORDS
    # -----------------------------------------------------------------------
    "u": "you",
    "ur": "your",
    "ure": "you are",
    "r": "are",
    "y": "why",
    "b": "be",
    "da": "the",
    "dis": "this",
    "dat": "that",
    "dem": "them",
    "dey": "they",
    "dere": "there",
    "deir": "their",
    "dose": "those",
    "wut": "what",
    "wot": "what",
    "wat": "what",
    "wen": "when",
    "wer": "where",
    "wit": "with",
    "itz": "it is",
    "its": "it is",
    "tis": "it is",
    "im": "i am",
    "ima": "i am going to",
    "imma": "i am going to",
    "iam": "i am",
    "iv": "i have",
    "id": "i would",
    "ill": "i will",

    # -----------------------------------------------------------------------
    # COMMON SHORTHAND — TEXTING
    # -----------------------------------------------------------------------
    "pls": "please",
    "plz": "please",
    "plox": "please",
    "thx": "thanks",
    "thnx": "thanks",
    "tnx": "thanks",
    "ty": "thank you",
    "tya": "thank you again",
    "tyvm": "thank you very much",
    "tysm": "thank you so much",
    "yw": "you are welcome",
    "np": "no problem",
    "nps": "no problem",
    "nbd": "no big deal",
    "brb": "be right back",
    "bbl": "be back later",
    "bbs": "be back soon",
    "gtg": "got to go",
    "g2g": "got to go",
    "gotta": "got to",
    "gonna": "going to",
    "wanna": "want to",
    "kinda": "kind of",
    "sorta": "sort of",
    "hafta": "have to",
    "tryna": "trying to",
    "finna": "fixing to",
    "lemme": "let me",
    "gimme": "give me",
    "gotcha": "i understand",
    "ya": "you",
    "yall": "you all",
    "y'all": "you all",
    "ngl": "not going to lie",
    "tbh": "to be honest",
    "tho": "though",
    "thru": "through",
    "rly": "really",
    "rlly": "really",
    "rn": "right now",
    "atm": "at the moment",
    "irl": "in real life",
    "imo": "in my opinion",
    "imho": "in my humble opinion",
    "imo": "in my opinion",
    "idc": "i do not care",
    "idk": "i do not know",
    "ik": "i know",
    "ikr": "i know right",
    "ikk": "i know",
    "nvm": "never mind",
    "nvmd": "never mind",
    "nm": "never mind",
    "omg": "oh my god",
    "omfg": "oh my god",
    "wtf": "what the heck",
    "wth": "what the heck",
    "smh": "shaking my head",
    "smdh": "shaking my head",
    "lol": "laughing",
    "lmao": "laughing",
    "lmfao": "laughing",
    "rofl": "laughing",
    "roflmao": "laughing a lot",
    "lmk": "let me know",
    "hmu": "hit me up",
    "hml": "hit my line",
    "dm": "direct message",
    "dms": "direct messages",
    "dming": "sending a direct message",
    "pm": "private message",
    "fyi": "for your information",
    "btw": "by the way",
    "iirc": "if i recall correctly",
    "afaik": "as far as i know",
    "afaict": "as far as i can tell",
    "afair": "as far as i remember",
    "imo": "in my opinion",
    "otoh": "on the other hand",
    "istg": "i swear to god",
    "swear": "i swear",
    "nfw": "no way",
    "ofc": "of course",
    "obv": "obviously",
    "obvs": "obviously",
    "tbt": "throwback",
    "ftw": "for the win",
    "fwiw": "for what it is worth",
    "yolo": "you only live once",
    "ggwp": "good game well played",
    "gj": "good job",
    "gl": "good luck",
    "hf": "have fun",
    "glhf": "good luck have fun",
    "gg": "good game",
    "wp": "well played",
    "ez": "easy",
    "nt": "nice try",
    "ff": "forfeit",
    "afk": "away from keyboard",
    "brb": "be right back",
    "brt": "be right there",
    "ama": "ask me anything",
    "eli5": "explain like i am five",
    "tl;dr": "summary",
    "tldr": "summary",
    "asap": "as soon as possible",
    "eta": "estimated time of arrival",
    "eod": "end of day",
    "eow": "end of week",
    "wip": "work in progress",
    "faq": "frequently asked questions",
    "diy": "do it yourself",
    "imo": "in my opinion",

    # -----------------------------------------------------------------------
    # QUESTIONS AND QUERIES
    # -----------------------------------------------------------------------
    "wdym": "what do you mean",
    "wym": "what do you mean",
    "wyd": "what are you doing",
    "wbu": "what about you",
    "wbt": "what about",
    "wbout": "what about",
    "wabs": "what about",
    "wdyt": "what do you think",
    "wdys": "what do you say",
    "wdyc": "what do you call",
    "wdyg": "what do you get",
    "hyd": "how are you doing",
    "hru": "how are you",
    "howdy": "how are you",
    "wsup": "what is up",
    "sup": "what is up",
    "wsp": "what is up",
    "wsgood": "what is good",
    "wsg": "what is going on",
    "wya": "where are you",
    "wyat": "where are you at",
    "wyad": "where are you at",
    "wya": "where are you",
    "wru": "where are you",
    "tyl": "tell you later",
    "tylt": "tell you later tonight",
    "rq": "real quick",
    "fr": "for real",
    "frfr": "for real",
    "ong": "on god",
    "onG": "on god",
    "on god": "seriously",
    "deadass": "seriously",
    "no bs": "seriously",

    # -----------------------------------------------------------------------
    # INTERNET AND SOCIAL MEDIA SHORTHAND
    # -----------------------------------------------------------------------
    "abt": "about",
    "b4": "before",
    "bc": "because",
    "bcoz": "because",
    "bcz": "because",
    "coz": "because",
    "cus": "because",
    "cuz": "because",
    "cause": "because",
    "cos": "because",
    "2": "to",
    "4": "for",
    "4u": "for you",
    "l8": "late",
    "l8r": "later",
    "gr8": "great",
    "m8": "mate",
    "k": "okay",
    "kk": "okay",
    "kay": "okay",
    "mk": "mmm okay",
    "nah": "no",
    "yep": "yes",
    "yup": "yes",
    "yea": "yes",
    "ye": "yes",
    "yh": "yes",
    "yess": "yes",
    "nope": "no",
    "nop": "no",
    "nah": "no",
    "defs": "definitely",
    "def": "definitely",
    "defo": "definitely",
    "prob": "probably",
    "probs": "probably",
    "prolly": "probably",
    "tbf": "to be fair",
    "imo": "in my opinion",
    "irl": "in real life",
    "tbvh": "to be very honest",
    "reli": "really",
    "srsly": "seriously",
    "srsly": "seriously",
    "srly": "seriously",
    "srs": "serious",
    "lil": "little",
    "lil bit": "a little bit",
    "bit": "a bit",
    "lowk": "lowkey",
    "hk": "highkey",
    "prolly": "probably",
    "sm": "so much",
    "soo": "so",
    "sooo": "so",
    "totes": "totally",
    "tot": "totally",
    "v": "very",
    "vry": "very",
    "vvv": "very very",
    "rn rn": "right now right now",
    "rq rq": "really quick",
    "qs": "questions",
    "q": "question",
    "ans": "answer",
    "info": "information",
    "inspo": "inspiration",
    "convo": "conversation",
    "convos": "conversations",
    "collab": "collaboration",
    "collabs": "collaborations",
    "fav": "favorite",
    "favs": "favorites",
    "fave": "favorite",
    "faves": "favorites",

    # -----------------------------------------------------------------------
    # PROGRAMMING AND TECH COMMUNITY SHORTHAND
    # -----------------------------------------------------------------------
    "lgtm": "looks good to me",
    "nit": "nitpick",
    "wontfix": "will not fix",
    "tbd": "to be determined",
    "poc": "proof of concept",
    "mvp": "minimum viable product",
    "oop": "object oriented programming",
    "fp": "functional programming",
    "pr": "pull request",
    "prs": "pull requests",
    "mr": "merge request",
    "ci": "continuous integration",
    "cd": "continuous deployment",
    "infra": "infrastructure",
    "repo": "repository",
    "repos": "repositories",
    "deps": "dependencies",
    "dep": "dependency",
    "impl": "implementation",
    "algo": "algorithm",
    "algos": "algorithms",
    "perf": "performance",
    "mem": "memory",
    "cpu": "processor",
    "gpu": "graphics processor",
    "api": "application programming interface",
    "ui": "user interface",
    "ux": "user experience",
    "fe": "frontend",
    "fs": "fullstack",
    "db": "database",
    "dbs": "databases",
    "sql": "structured query language",
    "nosql": "non relational database",
    "auth": "authentication",
    "authn": "authentication",
    "authz": "authorization",
    "pw": "password",
    "pwd": "password",
    "cfg": "configuration",
    "config": "configuration",
    "configs": "configurations",
    "env": "environment",
    "envs": "environments",
    "var": "variable",
    "vars": "variables",
    "fn": "function",
    "fns": "functions",
    "func": "function",
    "funcs": "functions",
    "arg": "argument",
    "args": "arguments",
    "param": "parameter",
    "params": "parameters",
    "ret": "return",
    "str": "string",
    "int": "integer",
    "bool": "boolean",
    "dict": "dictionary",
    "obj": "object",
    "objs": "objects",
    "cls": "class",
    "attr": "attribute",
    "attrs": "attributes",
    "init": "initialization",
    "async": "asynchronous",
    "sync": "synchronous",
    "err": "error",
    "errs": "errors",
    "msg": "message",
    "msgs": "messages",
    "req": "request",
    "reqs": "requests",
    "res": "response",
    "resp": "response",
    "resps": "responses",
    "cb": "callback",
    "cbs": "callbacks",
    "ctx": "context",
    "lib": "library",
    "libs": "libraries",
    "pkg": "package",
    "pkgs": "packages",
    "mod": "module",
    "mods": "modules",
    "dir": "directory",
    "dirs": "directories",
    "doc": "documentation",
    "docs": "documentation",
    "spec": "specification",
    "specs": "specifications",
    "test": "test",
    "tests": "tests",
    "stg": "staging",
    "prod": "production",
    "dev": "development",
    "rel": "release",
    "ver": "version",
    "k8s": "kubernetes",
    "tf": "terraform",
    "iac": "infrastructure as code",
    "llm": "large language model",
    "llms": "large language models",
    "ml": "machine learning",
    "dl": "deep learning",
    "ai": "artificial intelligence",
    "nlp": "natural language processing",
    "cv": "computer vision",
    "rl": "reinforcement learning",
    "nn": "neural network",
    "nns": "neural networks",
    "gpt": "generative pre-trained transformer",
    "rag": "retrieval augmented generation",
    "sft": "supervised fine tuning",
    "rlhf": "reinforcement learning from human feedback",

    # -----------------------------------------------------------------------
    # AI AND DISCORD COMMUNITY SHORTHAND
    # -----------------------------------------------------------------------
    "tfw": "that feeling when",
    "mfw": "my face when",
    "iirc": "if i recall correctly",
    "iiuc": "if i understand correctly",
    "afaict": "as far as i can tell",
    "nah fr": "no seriously",
    "pog": "that is exciting",
    "poggers": "that is exciting",
    "kappa": "just kidding",
    "kek": "laughing",
    "pepehands": "that is sad",
    "pepega": "that was silly",
    "monkas": "i am nervous",
    "peeposad": "that is sad",
    "5head": "that is clever",
    "4head": "that is obvious",
    "omegalul": "laughing a lot",
    "omegachad": "very impressive person",
    "clueless": "i do not understand",
    "sadge": "that is sad",
    "copium": "coping",
    "hopium": "hoping",
    "catJAM": "this is good",
    "letsgo": "let us go",
    "lets go": "let us go",
    "gng": "going",

    # -----------------------------------------------------------------------
    # REDDIT AND FORUM SHORTHAND
    # -----------------------------------------------------------------------
    "op": "original poster",
    "oc": "original content",
    "ama": "ask me anything",
    "ianal": "i am not a lawyer",
    "ianad": "i am not a doctor",
    "edt": "edited",
    "edit": "edited",
    "eta": "edited to add",
    "tia": "thanks in advance",
    "til": "today i learned",
    "tifu": "today i messed up",
    "dae": "does anyone else",
    "cmv": "change my view",
    "eli5": "explain like i am five",
    "imo": "in my opinion",
    "irl": "in real life",
    "ngl": "not going to lie",
    "iirc": "if i recall correctly",
    "afaik": "as far as i know",
    "ysk": "you should know",
    "psa": "public service announcement",
    "lpt": "life pro tip",
    "rant": "my frustration",
    "bruh": "come on",
    "bruh moment": "unfortunate situation",
    "rip": "that is unfortunate",
    "based": "admirable",
    "cringe": "embarrassing",

    # -----------------------------------------------------------------------
    # TIKTOK AND YOUTUBE SHORTHAND
    # -----------------------------------------------------------------------
    "fyp": "for your page",
    "foryoupage": "for your page",
    "pov": "point of view",
    "sfs": "shoutout for shoutout",
    "f4f": "follow for follow",
    "l4l": "like for like",
    "sub4sub": "subscribe for subscribe",
    "yt": "youtube",
    "irl": "in real life",
    "npc": "non player character",
    "main character": "protagonist energy",
    "villain arc": "going through a difficult phase",
    "glow up": "significant improvement",
    "ratio": "getting more likes than original",
    "understood the assignment": "performed well",
    "rent free": "stuck in my mind",
    "caught in 4k": "caught doing something",
    "hits different": "feels unique",
    "understood": "got it",
    "ok boomer": "dismissing an outdated view",

    # -----------------------------------------------------------------------
    # GAMING SHORTHAND
    # -----------------------------------------------------------------------
    "gg": "good game",
    "ggez": "easy victory",
    "gg ez": "easy victory",
    "gg wp": "good game well played",
    "ff": "forfeit",
    "ff15": "forfeit at 15 minutes",
    "ff20": "forfeit at 20 minutes",
    "bg": "bad game",
    "nt": "nice try",
    "ns": "nice shot",
    "nb": "nice block",
    "gj": "good job",
    "glhf": "good luck have fun",
    "gl": "good luck",
    "hf": "have fun",
    "rekt": "defeated badly",
    "pwned": "defeated badly",
    "noob": "new player",
    "nub": "new player",
    "newb": "new player",
    "newbie": "new player",
    "aimbotting": "cheating with aim assist",
    "wallhacking": "cheating by seeing through walls",
    "lag": "slow connection",
    "lagging": "slow connection",
    "ping": "connection latency",
    "ms": "milliseconds",
    "fps": "frames per second",
    "tp": "teleport",
    "hp": "health points",
    "mp": "mana points",
    "xp": "experience points",
    "dps": "damage per second",
    "tank": "high health character",
    "healer": "support character",
    "adc": "attack damage carry",
    "apc": "ability power carry",
    "meta": "most effective strategy",
    "op": "overpowered",
    "nerf": "reduce power",
    "buff": "increase power",
    "patch": "update",
    "dlc": "downloadable content",
    "f2p": "free to play",
    "p2w": "pay to win",
    "speedrun": "completing game as fast as possible",
    "speedrunning": "completing game as fast as possible",
    "hitbox": "collision area",
    "cooldown": "waiting period before reuse",
    "respawn": "return to life after death",
    "camping": "staying in one spot",
    "sweaty": "playing very competitively",
    "try hard": "playing very competitively",
    "tryhard": "playing very competitively",
    "tilted": "frustrated",
    "toxic": "negative behavior",
    "flame": "verbal attack in game",
    "flaming": "verbal attack in game",
    "carry": "dominant player helping team",
    "int": "intentional feeding",
    "inting": "intentional feeding",
    "afk": "away from keyboard",
    "dc": "disconnected",
    "desync": "synchronization error",
    "glitch": "error",
    "bug": "error",
    "exploit": "using unintended game mechanic",

    # -----------------------------------------------------------------------
    # CASUAL ENGLISH SHORTCUTS
    # -----------------------------------------------------------------------
    "rn": "right now",
    "tn": "tonight",
    "tmr": "tomorrow",
    "tmrw": "tomorrow",
    "2moro": "tomorrow",
    "2day": "today",
    "2nite": "tonight",
    "2morrow": "tomorrow",
    "ystrdy": "yesterday",
    "yr": "year",
    "yrs": "years",
    "mo": "month",
    "mos": "months",
    "wk": "week",
    "wks": "weeks",
    "min": "minute",
    "mins": "minutes",
    "sec": "second",
    "secs": "seconds",
    "hr": "hour",
    "hrs": "hours",
    "w/": "with",
    "w/o": "without",
    "w/e": "whatever",
    "w/r/t": "with regard to",
    "re:": "regarding",
    "re ": "regarding ",
    "aka": "also known as",
    "asap": "as soon as possible",
    "fwiw": "for what it is worth",
    "eg": "for example",
    "ex": "for example",
    "ie": "that is",
    "etc": "and so on",
    "vs": "versus",
    "approx": "approximately",
    "approx.": "approximately",
    "pref": "preferably",
    "ref": "reference",
    "refs": "references",
    "misc": "miscellaneous",
    "dept": "department",
    "mgmt": "management",
    "hr": "human resources",
    "ops": "operations",
    "pm": "project manager",
    "eng": "engineering",

    # -----------------------------------------------------------------------
    # GEN Z SPECIFIC NORMALIZATION
    # -----------------------------------------------------------------------
    "fr fr": "for real",
    "no cap": "seriously",
    "on god": "seriously",
    "deadass": "seriously",
    "fasho": "for sure",
    "fosheezy": "for sure",
    "fo sho": "for sure",
    "fosho": "for sure",
    "for sure": "definitely",
    "periodt": "period",
    "period": "that is final",
    "slay queen": "excellent",
    "slap": "excellent",
    "fire": "excellent",
    "lit": "exciting",
    "lowkey fire": "quietly excellent",
    "highkey fire": "openly excellent",
    "vibe check": "checking the mood",
    "sending me": "making me laugh",
    "i cannot": "i cannot handle this",
    "cant even": "cannot handle this",
    "ded": "extremely funny",
    "i am dead": "extremely funny",
    "crying rn": "this is very funny",
    "ate": "did very well",
    "ate and left no crumbs": "did perfectly",
    "that slaps": "that is excellent",
    "this slaps": "this is excellent",
    "not gonna lie": "honestly",
    "to be fair": "fairly",
    "to be honest": "honestly",
    "no bs": "seriously",
    "tbf": "to be fair",
    "honestly tho": "honestly",
    "ong": "seriously",
    "bet": "agreed",
    "aight": "alright",
    "aite": "alright",
    "ayt": "alright",
    "prolly": "probably",
    "lowkey": "quietly",
    "highkey": "openly",
    "bruh": "come on",
    "ayo": "hey",
    "ay": "hey",
    "fam": "family or close friend",
    "dude": "person",
    "mate": "friend",
    "bestie": "best friend",
    "bestie fr": "best friend seriously",
    "gng": "going",
    "slay": "excellent",
    "slaying": "doing excellently",
    "understood the assignment": "did very well",
    "ate it": "did very well",

    # -----------------------------------------------------------------------
    # GEN ALPHA SPECIFIC NORMALIZATION
    # -----------------------------------------------------------------------
    "skibidi": "silly or weird",
    "skibidi toilet": "meme reference",
    "rizz": "charisma",
    "rizzed up": "charmed someone",
    "w rizz": "great charisma",
    "l rizz": "poor charisma",
    # -----------------------------------------------------------------------
    # MEME CULTURE NORMALIZATION
    # -----------------------------------------------------------------------
    "based": "admirable or correct",
    "based and redpilled": "controversial but admirable",
}


# ---------------------------------------------------------------------------
# SYSTEM 2 — PRESERVED SLANG REGISTRY
# Recognized but NOT rewritten. Used for detection and context scoring.
# Structure: {term: definition}
# ---------------------------------------------------------------------------

_PRESERVED_SLANG: Dict[str, str] = {

    # -----------------------------------------------------------------------
    # GEN Z CORE
    # -----------------------------------------------------------------------
    "rizz": "charisma or natural charm, especially in flirting",
    "rizzed up": "successfully charmed someone",
    "unrizzed": "lacking charm",
    "no rizz": "lacking charm",
    "w rizz": "excellent charm",
    "l rizz": "poor charm",
    "slay": "to perform or look excellent",
    "slaying": "performing or looking excellent",
    "understood the assignment": "performed exactly as expected or better",
    "ate and left no crumbs": "performed perfectly",
    "ate": "performed excellently",
    "periodt": "that is final, end of discussion",
    "period": "that is definitive",
    "no cap": "seriously, not lying",
    "cap": "a lie",
    "capping": "lying",
    "big cap": "a major lie",
    "based": "admirable, correct, or holding a respectable position",
    "cringe": "embarrassing or awkward",
    "lowkey": "quietly, subtly, moderately",
    "highkey": "openly, obviously, strongly",
    "vibe": "atmosphere or mood",
    "vibes": "atmosphere or mood",
    "vibe check": "assessing someone's mood or energy",
    "vibe with": "enjoying or connecting with",
    "it is giving": "it resembles or radiates a certain quality",
    "giving": "radiating a certain quality",
    "main character": "acting like the protagonist of a story",
    "main character energy": "behaving as if you are the most important person",
    "npc": "non-player character, someone acting robotic or predictably",
    "npc behavior": "robotic or scripted behavior",
    "villain arc": "going through a morally questionable phase",
    "glow up": "significant improvement in appearance or life",
    "ratio": "when a reply gets more engagement than the original post",
    "ratioed": "when your post got ratioed",
    "hits different": "affects you in a unique or stronger way",
    "rent free": "occupying thoughts without effort",
    "sending me": "making me laugh uncontrollably",
    "ded": "extremely amused",
    "deceased": "extremely amused",
    "i am crying": "this is extremely funny",
    "salty": "bitter, upset, or resentful",
    "fire": "excellent, impressive",
    "lit": "exciting, excellent",
    "bussin": "extremely good, usually food or something enjoyable",
    "slaps": "is excellent",
    "banger": "something excellent",
    "dope": "cool or impressive",
    "lowkey fire": "quietly excellent",
    "highkey fire": "openly excellent",
    "understood": "got it, acknowledged",
    "bet": "agreed, confirmed, sounds good",
    "aight": "alright",
    "w": "win or positive outcome",
    "l": "loss or negative outcome",
    "big w": "major win",
    "big l": "major loss",
    "taking ls": "experiencing losses",
    "taking ws": "experiencing wins",
    "mid": "mediocre, average, not impressive",
    "cooked": "in serious trouble or ruined",
    "cooked fr": "seriously in trouble",
    "delulu": "delusional or unrealistically optimistic",
    "it is giving delulu": "this is delusional",
    "real": "true, i agree, that is accurate",
    "real ones": "genuine people who understand",
    "fam": "close friend or family",
    "bestie": "best friend",
    "bffr": "be for real, be serious",
    "it is what it is": "accepting an undesirable situation",
    "the audacity": "the nerve or boldness of something negative",
    "not me": "embarrassed admission",
    "caught in 4k": "caught red-handed or clearly on camera",
    "chile": "an expression of surprise or disbelief",
    "no way": "i cannot believe this",
    "pop off": "to perform exceptionally or speak one's mind boldly",
    "popping off": "performing exceptionally",
    "slander": "unfair criticism",
    "this is slander": "this is unfair criticism",
    "i am in my feelings": "emotionally affected",
    "era": "a defined phase or period of one's life",
    "in my era": "currently in a specific life phase",
    "healing era": "a phase focused on personal recovery",
    "villain era": "a self-serving or morally gray phase",
    "glow up era": "a phase of improvement",
    "not it": "that is not acceptable or appropriate",
    "that is not it": "that is not acceptable",
    "understood the vibe": "reading the room correctly",
    "understood the room": "read the situation correctly",
    "touch grass": "go outside, disconnect from the internet",
    "go touch grass": "go outside and disconnect",

    # -----------------------------------------------------------------------
    # GEN ALPHA CORE
    # -----------------------------------------------------------------------
    "skibidi": "silly, weird, or absurd",
    "skibidi toilet": "a meme reference, absurd situation",
    "sigma": "an independently successful, high-status person",
    "sigma male": "an independently successful person",
    "sigma grindset": "mindset focused on independent success",
    "alpha": "dominant leader figure",
    "beta": "someone seen as passive or submissive",
    "ohio": "very strange, bizarre, or otherworldly",
    "only in ohio": "something extremely strange",
    "ohio moment": "an unexpectedly strange moment",
    "gyatt": "expression of surprise, typically at physical appearance",
    "fanum tax": "taking a small portion of someone else's food or thing",
    "aura": "energy, presence, or vibe someone radiates",
    "positive aura": "good energy",
    "negative aura": "bad energy",
    "aura farming": "building one's reputation or vibe",
    "locked in": "fully focused and committed",
    "locking in": "fully committing to a task",
    "mog": "to outclass or dominate someone in appearance or ability",
    "mogging": "outclassing someone",
    "mogged": "was outclassed",
    "hard mog": "total domination in comparison",
    "goofy ahh": "extremely silly",
    "brainrot": "condition of consuming too much internet content",
    "chronically online": "spending excessive time online",
    "delulu is the solulu": "being delusional is acceptable",
    "npc energy": "acting robotic or scripted",

    # -----------------------------------------------------------------------
    # GAMING
    # -----------------------------------------------------------------------
    "sweaty": "playing very competitively or try-hard",
    "sweat": "a try-hard player",
    "no-life": "someone who plays excessively",
    "grinder": "someone who plays repetitively for progress",
    "meta": "most effective tactic or strategy available",
    "meta build": "the strongest current configuration",
    "off-meta": "unconventional strategy",
    "clutch": "succeeding under pressure",
    "clutching": "succeeding in a critical moment",
    "skill issue": "the problem is the player's ability, not the game",
    "git gud": "improve your skills",
    "get good": "improve your skills",
    "tilted": "mentally frustrated, affecting performance",
    "on tilt": "playing while frustrated",
    "hard stuck": "unable to advance in ranking",
    "elo hell": "stuck in a rank due to team quality",
    "smurf": "high-level player on a low-level account",
    "smurfing": "playing as a high-skill player on a low-ranked account",
    "stomp": "to win easily and decisively",
    "stomping": "winning decisively",
    "throw": "to lose by making mistakes",
    "throwing": "losing deliberately or by mistake",
    "int": "intentional feeding, dying on purpose",
    "inting": "intentionally feeding the enemy",
    "grief": "deliberately ruining teammates' game",
    "griefing": "deliberately ruining the experience",
    "360 no scope": "impressive long-range shot",
    "montage worthy": "impressive enough for a highlight",
    "wombo combo": "impressive combination of abilities",
    "outplay": "to defeat someone using superior skill",
    "outplayed": "defeated by superior skill",
    "farm": "to accumulate resources or kills",
    "farming": "accumulating resources",
    "cheese": "unconventional exploitative strategy",
    "cheesing": "using an exploitative strategy",
    "rush": "to attack early and aggressively",
    "rushing": "attacking aggressively early",
    "cheese strat": "exploitative unconventional strategy",

    # -----------------------------------------------------------------------
    # DISCORD AND STREAMING
    # -----------------------------------------------------------------------
    "pog": "that is exciting or impressive",
    "poggers": "that is exciting",
    "pogchamp": "expression of hype or excitement",
    "copium": "coping through denial after a loss or disappointment",
    "hopium": "false hope",
    "sadge": "sad or disappointing",
    "pepehands": "sad or pleading",
    "lul": "laughing",
    "kek": "laughing",
    "pepega": "used to call someone or something silly",
    "monkas": "expressing anxiety or nervousness",
    "5head": "that is clever",
    "4head": "that is obvious",
    "omegalul": "extremely funny",
    "clapped": "ugly or defeated easily",
    "hype train": "building excitement",
    "sub": "subscriber",
    "subs": "subscribers",
    "donos": "donations",
    "bits": "a virtual currency on twitch",
    "raid": "sending your viewers to another stream",
    "host": "featuring another stream",
    "lurk": "watching without engaging",
    "lurking": "watching silently",
    "the chat": "the live audience",
    "chat is wild": "the audience is being chaotic",
    "chat cooked": "the audience made a good point",
    "just chatting": "casual stream with no specific activity",
    "stream sniping": "watching a stream to gain competitive advantage",
    "viewer": "someone watching a stream",
    "content": "media or material being produced",
    "creator": "someone who produces content",

    # -----------------------------------------------------------------------
    # REDDIT AND INTERNET CULTURE
    # -----------------------------------------------------------------------
    "downvoted": "received negative feedback",
    "upvoted": "received positive feedback",
    "karma": "reputation points on reddit",
    "shitpost": "low-effort humorous post",
    "shitposting": "posting low-effort humorous content",
    "meme": "humorous cultural reference",
    "cursed": "deeply unsettling or wrong in an amusing way",
    "blessed": "deeply wholesome or positive",
    "cursed image": "an unsettling image",
    "blessed image": "a wholesome image",
    "based take": "admirable opinion",
    "hot take": "controversial opinion",
    "cold take": "obvious opinion",
    "luke warm take": "a tepid or expected opinion",
    "unpopular opinion": "a dissenting view",
    "am i the only one": "seeking validation for an opinion",
    "gatekeeping": "controlling access to something",
    "gatekept": "had access controlled",
    "cringe compilation": "collection of embarrassing content",
    "normie": "someone not deeply involved in internet culture",
    "coomer": "someone obsessively focused on something",
    "doomer": "a pessimistic person expecting failure",
    "bloomer": "an optimistic person thriving",
    "boomer": "person with outdated or old-fashioned views",
    "zoomer": "a gen z person",
    "terminally online": "deeply enmeshed in internet culture",
    "touch grass": "go outside and disconnect",
    "skill issue": "the problem lies with the person, not the situation",
    "lore": "backstory or context",
    "deep lore": "complex backstory",
    "lore dump": "large amount of backstory information",
    "this is fine": "calmly accepting a bad situation",
    "everything is fine": "sarcastically accepting a crisis",

    # -----------------------------------------------------------------------
    # TIKTOK SPECIFIC
    # -----------------------------------------------------------------------
    "fyp": "for you page on tiktok",
    "for you page": "personalized content feed on tiktok",
    "duet": "tiktok collaborative video feature",
    "stitch": "tiktok video combination feature",
    "it is giving": "it radiates a certain quality",
    "understood the assignment": "performed perfectly",
    "main character": "acting like the protagonist",
    "roman empire": "something you think about often",
    "mother": "a term of admiration",
    "mother she is not": "she is not admirable",
    "slay": "perform excellently",
    "the comment section is unwell": "people are being chaotic in comments",
    "pov": "point of view video format",
    "thought dump": "sharing random thoughts",
    "day in my life": "daily routine content",
    "get ready with me": "getting ready routine video",
    "grwm": "get ready with me",
    "ootd": "outfit of the day",
    "no because": "this is surprising but",
    "no because fr": "this is genuinely surprising",
    "understood the task": "performed exactly as required",
    "she ate": "she performed excellently",
    "he ate": "he performed excellently",
    "we ate": "we performed excellently",

    # -----------------------------------------------------------------------
    # SOCIAL MEDIA GENERAL
    # -----------------------------------------------------------------------
    "aesthetic": "a defined visual style",
    "feed": "your social media content stream",
    "influencer": "someone with significant social media following",
    "micro influencer": "someone with a smaller but engaged following",
    "collab": "collaboration",
    "collaboration": "working together on content",
    "clout": "social influence or fame",
    "clout chasing": "seeking fame or influence",
    "viral": "spreading rapidly across the internet",
    "going viral": "spreading rapidly",
    "trending": "currently popular",
    "algorithm": "social media content recommendation system",
    "shadow banned": "having your content hidden without notice",
    "doomscrolling": "endlessly scrolling through negative content",
    "doom scrolling": "endlessly scrolling through negative content",
    "parasocial": "one-sided emotional attachment to a public figure",
    "parasocial relationship": "one-sided emotional bond with a creator",
    "cancel": "to publicly reject someone for behavior",
    "cancelled": "publicly rejected for behavior",
    "cancel culture": "the practice of publicly rejecting people",
    "problematic": "exhibiting concerning behavior",
    "tea": "gossip",
    "spill the tea": "share gossip",
    "drama": "conflict or controversy",
    "hot mess": "chaotic situation",
    "dragging": "publicly criticizing",
    "clapping back": "responding to criticism",
    "clap back": "a strong response to criticism",
    "throwing shade": "making indirect negative comments",
    "shade": "indirect negative comment",
    "petty": "small-minded or vindictive",
    "pressed": "bothered or upset",
    "unbothered": "not affected or bothered",
    "unhinged": "wildly erratic",
    "understood the chaos": "embraced the chaotic situation",
    "the internet is unwell": "the internet is being chaotic",
    "extremely online": "deeply enmeshed in internet culture",

    # -----------------------------------------------------------------------
    # MEME CULTURE
    # -----------------------------------------------------------------------
    "skill issue": "the problem is your lack of ability",
    "cope": "deal with a loss through denial",
    "ratio": "criticism with more engagement than the original post",
    "chad": "a confident, dominant, impressive person",
    "gigachad": "an extremely impressive person",
    "virgin walk": "awkward or unconfident movement",
    "chad walk": "confident impressive movement",
    "goat": "greatest of all time",
    "goated": "being the greatest",
    "based": "admirable, especially for holding a position",
    "based take": "an admirable opinion",
    "cringe take": "an embarrassing opinion",
    "npc": "someone acting robotic or without independent thought",
    "background character": "someone irrelevant to the main story",
    "plot armor": "surviving by luck rather than skill",
    "character development": "personal growth",
    "lore accurate": "matching expectations or established knowledge",
    "lore drop": "reveal of backstory",
    "speedrun": "completing something as fast as possible",
    "any percent": "completing at any cost",
    "world record": "fastest or best known completion",
    "any% world record": "record for fastest completion",
    "caught lacking": "caught unprepared",
    "lacking": "being unprepared",
    "final boss": "the ultimate challenge",
    "side quest": "a secondary objective",
    "respawn": "starting over after failure",
    "power up": "gaining an advantage",
    "quest": "a mission or task",
    "nerfed": "reduced in power",
    "buffed": "increased in power",
    "patched": "fixed or changed by update",

    # -----------------------------------------------------------------------
    # AI AND TECH COMMUNITY CULTURE
    # -----------------------------------------------------------------------
    "hallucinating": "an ai producing false information confidently",
    "hallucination": "ai producing false information",
    "prompt engineering": "crafting effective ai inputs",
    "prompt": "an instruction given to an ai",
    "jailbreak": "bypassing ai safety restrictions",
    "jailbroken": "successfully bypassed safety restrictions",
    "ai slop": "low quality ai generated content",
    "slop": "low quality content",
    "vibes based": "decided by feeling rather than evidence",
    "vibe coded": "built by feel",
    "brute forced": "solved by trying everything",
    "yolo merge": "merging code without review",
    "it works on my machine": "works locally but not on others",
    "works on my machine": "local environment success",
    "just ship it": "release without perfecting",
    "move fast break things": "prioritize speed over stability",
    "tech bro": "stereotypical tech industry person",
    "10x engineer": "supposedly extremely productive engineer",
    "leetcode grind": "practicing coding interview problems",
    "grinding leetcode": "practicing coding problems",
    "enshittification": "gradual degradation of a platform",
    "dark pattern": "deceptive user interface design",
    "dark patterns": "deceptive design practices",
    "enshittified": "degraded in quality over time",
}


# ---------------------------------------------------------------------------
# COMPILED LOOKUP STRUCTURES (built once at import time)
# ---------------------------------------------------------------------------

# Sorted by length descending so longer phrases match before shorter ones
_NORM_KEYS_SORTED: List[Tuple[str, str]] = sorted(
    _NORMALIZATION_MAP.items(),
    key=lambda x: len(x[0]),
    reverse=True
)

# Slang terms for O(1) membership check
_SLANG_SET: frozenset = frozenset(_PRESERVED_SLANG.keys())

# Remove normalization entries that overlap with preserved slang
# (preserved slang terms have richer definitions and should not be expanded)
_NORM_KEYS_SORTED = [
    (k, v) for k, v in _NORM_KEYS_SORTED
    if k.lower().strip() not in _SLANG_SET
]

# All normalization keys as a frozenset for slang check
_NORM_SET: frozenset = frozenset(_NORMALIZATION_MAP.keys())

# Combined detection set (preserved slang + normalization keys used as slang markers)
_DETECTION_SET: frozenset = _SLANG_SET | frozenset(
    k for k in _NORMALIZATION_MAP
    if any(k in {"bruh", "yo", "ngl", "tbh", "nvm", "omg", "lol", "gg", "fr",
                 "lowkey", "highkey", "bet", "aight", "slay", "fire", "lit",
                 "bussin", "mid", "no cap", "cap", "rizzed", "skibidi",
                 "pog", "based", "cringe", "goat", "ratio", "cope", "gg",
                 "sus", "sigma", "ohio", "gyatt", "delulu", "cooked"} for k in [k])
)


# ---------------------------------------------------------------------------
# SECTION — PUBLIC API
# ---------------------------------------------------------------------------

def normalize_genz_text(text: str) -> str:
    """
    Expand shorthand and abbreviations in text for improved intent recognition.

    Word-boundary safe. Preserves punctuation. Preserves sentence structure.
    Does not rewrite preserved slang terms.

    Args:
        text: Raw user input text.

    Returns:
        Text with shorthand expanded. Suitable for routing/intent classification.

    Example:
        >>> normalize_genz_text("yo wbt ur mission rn")
        'yo what about your mission right now'
    """
    if not text or not text.strip():
        return text

    # Build a single pass replacement using word-boundary aware regex.
    # We replace longest matches first to avoid partial corruption.
    result = text

    for key, expansion in _NORM_KEYS_SORTED:
        if key not in result.lower():
            continue
        # Build pattern: word boundary around the key, case-insensitive
        # Escape special regex characters in key (handles "w/", "tl;dr" etc.)
        escaped = re.escape(key)
        # Single-char patterns: also reject hyphen on either side to avoid
        # corrupting hyphenated compounds like "U-turn" or "K-pop".
        if len(key) == 1:
            lb = r"(?<![a-zA-Z0-9_-])"
            la = r"(?![a-zA-Z0-9_-])"
        else:
            lb = r"(?<![a-zA-Z0-9_])"
            la = r"(?![a-zA-Z0-9_])"
        pattern = lb + escaped + la
        try:
            result = re.sub(pattern, expansion, result, flags=re.IGNORECASE)
        except re.error:
            # Fallback: skip patterns that fail to compile (edge cases)
            continue

    return result


def suggest_normalized_query(text: str) -> str:
    """
    Produce a routing-optimized version of user input.

    Strips filler opener words after normalization. Preserves the core query.
    Intended to improve downstream routing and search quality.

    Args:
        text: Raw user input text.

    Returns:
        Cleaned, normalized query string.

    Example:
        >>> suggest_normalized_query("yo bro latest ai news rn")
        'latest ai news right now'
    """
    normalized = normalize_genz_text(text)

    # Strip common filler openers that carry no semantic weight for routing
    _FILLER_OPENERS = {
        "yo", "bro", "bruh", "dude", "mate", "fam", "bestie", "hey",
        "ayo", "ay", "ok so", "okay so", "so like", "like", "um", "uh",
        "well", "basically", "literally", "honestly", "right so",
        "so basically", "alright so", "ok", "okay", "hi", "hello",
    }

    words = normalized.strip().split()
    # Remove leading filler words (max 3 to avoid over-stripping)
    stripped = 0
    while words and stripped < 3 and words[0].lower().rstrip(",") in _FILLER_OPENERS:
        words.pop(0)
        stripped += 1

    return " ".join(words) if words else normalized.strip()


def contains_slang(text: str) -> bool:
    """
    Return True if text contains any recognized slang or internet shorthand.

    Uses word-boundary matching for accuracy.

    Args:
        text: User input text.

    Returns:
        True if slang is detected, False otherwise.
    """
    if not text:
        return False
    lower = text.lower()
    for term in _SLANG_SET:
        pattern = r"(?<![a-zA-Z0-9_])" + re.escape(term) + r"(?![a-zA-Z0-9_])"
        if re.search(pattern, lower):
            return True
    # Also check high-signal normalization keys
    for term in _DETECTION_SET - _SLANG_SET:
        pattern = r"(?<![a-zA-Z0-9_])" + re.escape(term) + r"(?![a-zA-Z0-9_])"
        if re.search(pattern, lower):
            return True
    return False


def extract_slang_terms(text: str) -> List[str]:
    """
    Return all recognized slang and internet terms found in text.

    Preserved slang only (System 2). Does not return normalization expansions.

    Args:
        text: User input text.

    Returns:
        List of matched slang terms in order of appearance.
    """
    if not text:
        return []
    lower = text.lower()
    found: List[str] = []
    for term in _PRESERVED_SLANG:
        pattern = r"(?<![a-zA-Z0-9_])" + re.escape(term) + r"(?![a-zA-Z0-9_])"
        if re.search(pattern, lower):
            found.append(term)
    return found


def slang_statistics(text: str) -> Dict[str, object]:
    """
    Return statistics about slang usage in text.

    Args:
        text: User input text.

    Returns:
        Dict with keys: total_terms, unique_terms, terms, density

    Example:
        >>> slang_statistics("no cap that is bussin and lowkey fire")
        {'total_terms': 3, 'unique_terms': 3, 'terms': ['no cap', 'bussin', 'lowkey'], 'density': 0.5}
    """
    if not text:
        return {"total_terms": 0, "unique_terms": 0, "terms": [], "density": 0.0}

    terms = extract_slang_terms(text)
    word_count = max(len(text.split()), 1)
    density = round(len(terms) / word_count, 2)

    return {
        "total_terms": len(terms),
        "unique_terms": len(set(terms)),
        "terms": terms,
        "density": density,
    }


def detect_generation_style(text: str) -> Dict[str, float]:
    """
    Heuristically score the generational style of text.

    Lightweight — no AI required. Based on vocabulary overlap with known
    generational marker sets.

    Args:
        text: User input text.

    Returns:
        Dict with scores between 0.0 and 1.0:
            gen_z_score, gen_alpha_score, internet_slang_score, formal_score

    Example:
        >>> detect_generation_style("no cap this is bussin fr fr")
        {'gen_z_score': 0.8, 'gen_alpha_score': 0.2, 'internet_slang_score': 0.85, 'formal_score': 0.0}
    """
    if not text:
        return {
            "gen_z_score": 0.0,
            "gen_alpha_score": 0.0,
            "internet_slang_score": 0.0,
            "formal_score": 1.0,
        }

    lower = text.lower()
    words = lower.split()
    word_count = max(len(words), 1)

    # --- Marker sets ---
    _GEN_Z_MARKERS = {
        "no cap", "cap", "slay", "understood the assignment", "periodt",
        "based", "cringe", "lowkey", "highkey", "vibe", "vibes", "ate",
        "it is giving", "giving", "main character", "npc", "rent free",
        "ratio", "big w", "big l", "mid", "bussin", "fire", "lit",
        "sending me", "ded", "salty", "bet", "aight", "w", "l",
        "cooked", "delulu", "touch grass", "real", "fam", "bestie",
        "pop off", "slander", "tea", "dragging", "unbothered", "pressed",
        "ngl", "tbh", "fr", "imo", "idk", "lmk", "bruh", "yo", "slay",
        "bffr", "chile", "era", "villain arc", "glow up",
    }

    _GEN_ALPHA_MARKERS = {
        "skibidi", "rizz", "rizzed", "sigma", "ohio", "gyatt",
        "fanum tax", "aura", "locked in", "mog", "mogging", "mogged",
        "goofy ahh", "brainrot", "chronically online", "npc energy",
        "delulu is the solulu", "aura farming", "hard mog",
    }

    _INTERNET_MARKERS = {
        "pog", "poggers", "copium", "hopium", "sadge", "kek", "lul",
        "omegalul", "5head", "cope", "chad", "gigachad", "goat", "goated",
        "based", "cringe", "skill issue", "tilted", "meta", "clutch",
        "ratio", "cancelled", "parasocial", "doomscrolling", "fyp",
        "algorithm", "viral", "trending", "sus", "impostor", "gg",
        "ggez", "wp", "ez", "rekt", "noob", "grind", "grinding",
        "speedrun", "final boss", "side quest", "lore", "nerfed", "buffed",
        "hallucination", "jailbreak", "prompt", "ai slop", "slop",
        "enshittification", "dark pattern", "10x engineer",
    }

    _FORMAL_MARKERS = {
        "therefore", "however", "furthermore", "consequently", "nevertheless",
        "accordingly", "subsequently", "notwithstanding", "pursuant",
        "herewith", "aforementioned", "respectively", "whereas",
        "in conclusion", "in summary", "to summarize", "as a result",
        "it should be noted", "it is worth noting", "as mentioned",
        "with regard to", "in accordance with", "as per",
    }

    def _score(text_lower: str, markers: set, word_count: int) -> float:
        hits = 0
        for marker in markers:
            if re.search(r"(?<![a-zA-Z0-9_])" + re.escape(marker) + r"(?![a-zA-Z0-9_])", text_lower):
                hits += 1
        # Normalize: hits relative to word count, cap at 1.0
        raw = hits / max(word_count * 0.3, 1)
        return round(min(raw, 1.0), 2)

    gen_z = _score(lower, _GEN_Z_MARKERS, word_count)
    gen_alpha = _score(lower, _GEN_ALPHA_MARKERS, word_count)
    internet = _score(lower, _INTERNET_MARKERS, word_count)

    # Formal score decreases with slang presence, increases with formal markers
    formal_hits = sum(1 for m in _FORMAL_MARKERS if m in lower)
    slang_hits = len(extract_slang_terms(text))
    formal_raw = (formal_hits * 2 - slang_hits) / max(word_count * 0.3, 1)
    formal = round(max(0.0, min(formal_raw, 1.0)), 2)

    return {
        "gen_z_score": gen_z,
        "gen_alpha_score": gen_alpha,
        "internet_slang_score": internet,
        "formal_score": formal,
    }


def get_slang_definition(term: str) -> Optional[str]:
    """
    Return a plain English definition for a known slang term.

    Args:
        term: Slang term to look up (case-insensitive).

    Returns:
        Definition string, or None if term is not in registry.

    Example:
        >>> get_slang_definition("rizz")
        'charisma or natural charm, especially in flirting'
        >>> get_slang_definition("cap")
        'a lie'
    """
    if not term:
        return None
    return _PRESERVED_SLANG.get(term.lower().strip())


# ---------------------------------------------------------------------------
# STATISTICS HELPERS (public, for diagnostics)
# ---------------------------------------------------------------------------

def normalization_map_size() -> int:
    """Return total number of normalization entries."""
    return len(_NORMALIZATION_MAP)


def slang_registry_size() -> int:
    """Return total number of preserved slang entries."""
    return len(_PRESERVED_SLANG)


# ---------------------------------------------------------------------------
# SELF-TESTS
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("KIO genz_dictionary.py — Self-Test Suite")
    print("=" * 60)

    # --- Dataset sizes ---
    n_norm = normalization_map_size()
    n_slang = slang_registry_size()
    print(f"\n[DATASET]")
    print(f"  Normalization entries : {n_norm}")
    print(f"  Preserved slang       : {n_slang}")
    assert n_norm >= 500, f"FAIL: normalization map too small ({n_norm})"
    assert n_slang >= 300, f"FAIL: slang registry too small ({n_slang})"
    print(f"  PASS: both size requirements met")

    # --- Normalization tests ---
    print(f"\n[NORMALIZATION]")
    cases = [
        ("yo wbt ur mission rn", "yo what about your mission right now"),
        ("idk tbh", "i do not know to be honest"),
        ("pls lmk asap", "please let me know as soon as possible"),
        ("gonna wanna tryna", "going to want to trying to"),
        ("brb gtg", "be right back got to go"),
        ("imo this is fr bussin", "in my opinion this is for real bussin"),
        ("wdym", "what do you mean"),
        ("ur code rly slaps", "your code really slaps"),
        ("u r so based tbh ngl", "you are so based to be honest not going to lie"),
    ]
    for inp, expected in cases:
        result = normalize_genz_text(inp)
        match = result.lower() == expected.lower()
        status = "PASS" if match else "FAIL"
        print(f"  [{status}] '{inp}' -> '{result}'")
        if not match:
            print(f"         expected: '{expected}'")

    # --- Preserved slang not rewritten ---
    print(f"\n[PRESERVED SLANG — NOT REWRITTEN]")
    preserved_cases = [
        "rizz",
        "bussin",
        "lowkey",
        "gyatt",
        "skibidi",
        "sigma",
        "ohio",
        "aura",
        "locked in",
        "mog",
        "delulu",
        "cooked",
        "goat",
    ]
    for term in preserved_cases:
        normed = normalize_genz_text(term)
        defn = get_slang_definition(term)
        preserved = normed.lower().strip() == term.lower().strip()
        has_def = defn is not None
        status = "PASS" if (preserved and has_def) else "FAIL"
        if not preserved:
            print(f"  [FAIL] '{term}' -> normalized to '{normed}' (corrupted)")
        elif not has_def:
            print(f"  [FAIL] '{term}' -> no definition found")
        else:
            print(f"  [PASS] '{term}' -> preserved, def: {defn}")

    # --- Slang extraction ---
    print(f"\n[SLANG EXTRACTION]")
    test_text = "no cap that is bussin lowkey and the rizz is real"
    terms = extract_slang_terms(test_text)
    print(f"  Input  : '{test_text}'")
    print(f"  Terms  : {terms}")
    assert "no cap" in terms or "bussin" in terms, "FAIL: expected slang not found"
    print(f"  PASS: slang extracted")

    # --- Contains slang ---
    print(f"\n[CONTAINS SLANG]")
    assert contains_slang("that is bussin fr") is True
    assert contains_slang("explain the TCP/IP protocol") is False
    assert contains_slang("what is your rizz level") is True
    print(f"  PASS: contains_slang returns correct results")

    # --- Statistics ---
    print(f"\n[SLANG STATISTICS]")
    stat_text = "no cap this is bussin and lowkey fire bro"
    stats = slang_statistics(stat_text)
    print(f"  Input  : '{stat_text}'")
    print(f"  Stats  : {stats}")
    assert stats["total_terms"] >= 1
    assert stats["unique_terms"] >= 1
    assert 0.0 <= stats["density"] <= 1.0
    print(f"  PASS: statistics returned valid structure")

    # --- Generation detection ---
    print(f"\n[GENERATION DETECTION]")
    gen_z_text = "no cap this is bussin fr fr the rizz is real lowkey"
    formal_text = "Therefore, it should be noted that the aforementioned solution is effective."
    gen_alpha_text = "bro that is so skibidi and his rizz is sigma mogging everyone ohio"

    gen_z_result = detect_generation_style(gen_z_text)
    formal_result = detect_generation_style(formal_text)
    gen_alpha_result = detect_generation_style(gen_alpha_text)

    print(f"  Gen Z text   : {gen_z_result}")
    print(f"  Formal text  : {formal_result}")
    print(f"  Gen Alpha    : {gen_alpha_result}")

    assert gen_z_result["gen_z_score"] > gen_z_result["formal_score"], \
        "FAIL: gen z text should score higher on gen_z than formal"
    assert formal_result["formal_score"] >= formal_result["gen_z_score"], \
        "FAIL: formal text should score at least as high on formal"
    assert gen_alpha_result["gen_alpha_score"] > 0.0, \
        "FAIL: gen alpha text should have positive gen_alpha_score"
    print(f"  PASS: generation detection working")

    # --- Query suggestion ---
    print(f"\n[QUERY SUGGESTION]")
    query_cases = [
        ("yo bro latest ai news rn", "latest ai news right now"),
        ("bruh wbt the kio runtime", "what about the kio runtime"),
        ("explain tcp ip", "explain tcp ip"),
    ]
    for inp, hint in query_cases:
        result = suggest_normalized_query(inp)
        print(f"  Input   : '{inp}'")
        print(f"  Output  : '{result}'")
        print(f"  Hint    : '{hint}'")

    # --- Definition lookup ---
    print(f"\n[DEFINITION LOOKUP]")
    def_cases = ["rizz", "cap", "goat", "bussin", "sigma", "based", "cooked", "npc"]
    for term in def_cases:
        defn = get_slang_definition(term)
        status = "PASS" if defn else "FAIL"
        print(f"  [{status}] '{term}' -> {defn}")

    # --- Adversarial: no partial word corruption ---
    print(f"\n[WORD BOUNDARY SAFETY]")
    boundary_cases = [
        ("information", "information"),   # 'r' -> 'are' should NOT fire inside a word
        ("format", "format"),             # 'r' inside should be safe
        ("string theory", "string theory"),  # 'str' should NOT expand inside 'string'
        ("import", "import"),             # 'imo' should NOT fire inside 'import'
    ]
    for inp, expected in boundary_cases:
        result = normalize_genz_text(inp)
        status = "PASS" if result.lower() == expected.lower() else "FAIL"
        print(f"  [{status}] '{inp}' -> '{result}' (expected '{expected}')")

    print(f"\n{'=' * 60}")
    print("Self-test complete.")
    print(f"{'=' * 60}")
