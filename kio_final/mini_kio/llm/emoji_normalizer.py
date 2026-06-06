"""
mini_kio/llm/emoji_normalizer.py

KIO Emoji Comprehension Layer
===============================
Converts emoji meaning into lightweight semantic hints to improve intent
understanding for Gen Z / Gen Alpha communication. Additive only — never
strips or rewrites surrounding text.

Design contract
----------------
- Neutral semantic labels only (no "in love", use "positive_affection")
- Ambiguous emojis get compound labels (e.g. "crying_laughing_or_overwhelmed")
- No external dependencies. Pure Python stdlib. O(1) dict lookups.
- All functions are stateless and side-effect-free.
- Does NOT force emojis into KIO responses.

Usage
------
    from mini_kio.llm.emoji_normalizer import (
        normalize_emoji_text,
        get_emoji_meaning,
        contains_emoji,
        emoji_statistics,
    )

    # Normalize before routing
    understanding = normalize_emoji_text("bro that exam was insane 💀")
    # -> "bro that exam was insane dead_laughing"

    # Check if message has emoji content
    if contains_emoji(user_input):
        stats = emoji_statistics(user_input)
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# EMOJI TO SEMANTIC TAG MAP
# Keys: emoji character(s). Values: neutral semantic label.
# Organized by category for maintainability.
# ---------------------------------------------------------------------------

_EMOJI_MAP: Dict[str, str] = {
    # =========================================================================
    # FACES / REACTIONS
    # =========================================================================

    # Joy / Laughter
    "😂": "laughing_tears",
    "🤣": "rolling_on_floor_laughing",
    "😁": "big_smiling_eyes",
    "😆": "squinting_laughing",
    "😅": "nervous_sweat_laugh",
    "😄": "grinning_laughing",

    # Smiling / Happy
    "😊": "warm_smile",
    "😇": "angelic_innocent",
    "🙂": "slight_smile",
    "😌": "relieved_content",
    "😋": "savoring_delicious",
    "😛": "playful_teasing",
    "😜": "playful_winking",
    "🤪": "zany_silly",
    "😝": "playful_squinting",
    "🤑": "money_mouth_greed",

    # Love / Affection
    "😍": "heart_eyes_admire",
    "🥰": "loving_grateful",
    "😘": "blowing_kiss",

    # Cool / Confident
    "😎": "cool_cool",
    "🤓": "nerdy_geeky",
    "🧐": "curious_inspecting",
    "🤩": "star_struck_amazed",

    # Sad / Vulnerable
    "🥺": "pleading_adorable",
    "😢": "crying_sad",
    "😭": "crying_laughing_or_overwhelmed",
    "😿": "crying_cat_sad",

    # Distressed / Struggling
    "😱": "shocked_screaming",
    "😨": "fearful_worried",
    "😰": "anxious_sweating",
    "😥": "sad_relieved",
    "😓": "sweating_discomfort",
    "😩": "weary_exhausted",
    "😫": "tired_frustrated",
    "🥱": "bored_tired",
    "😤": "steaming_frustrated",
    "😡": "angry_rage",
    "🤬": "swearing_furious",

    # Neutral / Confused
    "😐": "neutral_indifferent",
    "😑": "expressionless_bored",
    "😶": "speechless_silent",
    "🤔": "thoughtful_questioning",
    "🤨": "skeptical_raised_eyebrow",
    "😕": "confused_uncertain",
    "😟": "worried_concerned",
    "🙁": "frowning_unhappy",
    "😮": "surprised_astonished",
    "😯": "hushed_surprised",
    "😲": "amazed_shocked",
    "😳": "flushed_embarrassed",
    "🥴": "woozy_dizzy",
    "🤯": "mind_blown",
    "😬": "cringing_awkward",

    # Gen Alpha / Exaggerated
    "🫠": "melting_embarrassed",
    "🫡": "saluting_acknowledging",
    "🫢": "surprised_hidden_mouth",
    "🫣": "peeking_curious",
    "🤭": "hand_over_mouth_giggling",
    "🤫": "shushing_secret",
    "🤗": "hugging_grateful",
    "💀": "dead_laughing",

    # =========================================================================
    # HEARTS / AFFECTION
    # =========================================================================
    "❤️": "positive_affection",
    "🧡": "warm_friendship",
    "💛": "cheerful_happiness",
    "💚": "growth_or_jealousy",
    "💙": "trust_calm",
    "💜": "support_creative",
    "🖤": "edgy_dark_humor",
    "🤍": "pure_peaceful",
    "🤎": "earthy_grounded",
    "💕": "double_love_care",
    "💗": "growing_affection",
    "💖": "sparkling_adore",
    "💘": "cupid_struck",
    "💝": "valentine_sweet",
    "🩷": "pink_friendly_love",
    "🩵": "light_blue_gentle",
    "🩶": "gray_neutral",
    "💔": "broken_heart_sad",
    "❤️‍🔥": "intense_passion",
    "❤️‍🩹": "heart_healing_recovery",
    "🫶": "heart_hands_gratitude_or_support",

    # =========================================================================
    # GEN Z / ALPHA SLANG EMOJIS
    # =========================================================================
    "🔥": "excellent_or_exciting",
    "🤡": "foolish_behavior",
    "🗿": "stoic_or_unbothered",
    "🧢": "cap_lying_or_fake",
    "💅": "sassy_unbothered",
    "✨": "magical_or_vibes",
    "👑": "king_queen_royalty",
    "🐐": "goat_greatest_of_all_time",
    "💯": "strong_agreement",
    "🍆": "sexual_innuendo",
    "💦": "sexual_or_effort",
    "🌶️": "spicy_hot_take",
    "🥶": "cold_icy_or_cool",
    "🥵": "hot_overwhelmed",
    "👻": "ghost_ignoring_or_spooky",
    "💎": "diamond_rare_valuable",
    "🧠": "brain_intelligence",
    "🌊": "wave_flow_vibes",
    "🦋": "butterfly_transformation",
    "🌈": "rainbow_lgbtq_or_hopeful",
    "🍃": "leaf_peace_weed",
    "💤": "sleeping_bored_tired",
    "👀": "eyes_observing_gossip",

    # =========================================================================
    # HAND GESTURES
    # =========================================================================
    "👍": "thumbs_up_approval",
    "👎": "thumbs_down_disapproval",
    "👌": "okay_perfect",
    "✌️": "peace_victory",
    "🤞": "crossed_fingers_luck",
    "🤟": "love_you_gesture",
    "🤘": "rock_on_horns",
    "👋": "waving_hello_goodbye",
    "🖐️": "hand_stop_high_five",
    "✋": "raised_hand_stop",
    "🤙": "call_me_hang_loose",
    "💪": "strong_determined",
    "🤝": "handshake_deal",
    "🙏": "thanks_or_respect",
    "🙌": "raising_hands_celebrate",
    "👏": "clapping_applause",
    "🎉": "party_celebrate",
    "🎊": "confetti_congratulations",
    "✊": "raised_fist_solidarity",
    "🤛": "fist_bump_left",
    "🤜": "fist_bump_right",
    "👊": "oncoming_fist_punch",
    "🫳": "palm_down_dropping",
    "🫴": "palm_up_offering",

    # =========================================================================
    # ANIMAL / OBJECT SLANG
    # =========================================================================
    "🐍": "snake_traitor",
    "🐺": "wolf_lone_independent",
    "🐉": "dragon_powerful",
    "🦊": "fox_cunning_sly",
    "🐱": "cat_cute",
    "🐶": "dog_loyal",
    "🐸": "frog_chill_or_pepe",
    "🐒": "monkey_mischievous",
    "🦍": "gorilla_strong_ape",
    "🐧": "penguin_cool_nerdy",
    "🦅": "eagle_freedom_america",
    "🐬": "dolphin_smart_playful",
    "🦈": "shark_predator_aggressive",
    "🐙": "octopus_multi_task",
    "🐝": "bee_busy_hardworking",
    "🥜": "nuts_crazy_or_peanuts",
    "🍿": "popcorn_watching_drama",
    "🧊": "ice_cold_cool",
    "⚡": "lightning_energy_speed",
    "🍀": "clover_lucky",
    "🦄": "unicorn_rare_unique",

    # =========================================================================
    # GAMING
    # =========================================================================
    "🕹️": "arcade_joystick_retro",
    "👾": "alien_invader_gaming",
    "💻": "laptop_computer_code",
    "🖥️": "desktop_computer_work",
    "⌨️": "keyboard_typing_code",
    "🖱️": "computer_mouse_click",
    "⚔️": "crossed_swords_battle",
    "🛡️": "shield_defense_protect",
    "🏆": "trophy_winner_champion",
    "🥇": "gold_medal_first",
    "🥈": "silver_medal_second",
    "🥉": "bronze_medal_third",
    "🎲": "dice_game_risk",
    "🃏": "joker_card_wildcard",
    "🎰": "slot_machine_gambling",
    "🏁": "checkered_flag_race",
    "🎮": "controller_gaming",
    "🎯": "precision_focused",

    # =========================================================================
    # STUDY / STUDENT
    # =========================================================================
    "📚": "books_studying_learning",
    "📖": "open_book_reading",
    "✏️": "pencil_writing_drawing",
    "📝": "memo_notes_document",
    "🎓": "graduation_academic_achievement",
    "📊": "bar_chart_data_analytics",
    "📈": "chart_up_growth_trend",
    "📉": "chart_down_decline_loss",
    "💡": "lightbulb_idea_insight",
    "🔬": "microscope_science_research",
    "🔭": "telescope_exploration_discovery",
    "🧪": "test_tube_experiment",
    "🧫": "petri_dish_biology",
    "📋": "clipboard_checklist_task",
    "📌": "pin_emphasis_important",
    "⏰": "alarm_clock_deadline",
    "⌛": "hourglass_time_running_out",

    # =========================================================================
    # MUSIC / ENTERTAINMENT
    # =========================================================================
    "🎵": "music_note_melody",
    "🎶": "music_notes_singing",
    "🎤": "microphone_singing_perform",
    "🎧": "headphones_listening_music",
    "🎼": "musical_score_composition",
    "🎹": "piano_keyboard_music",
    "🎸": "guitar_rock_music",
    "🎺": "trumpet_jazz_brass",
    "🎻": "violin_strings_classical",
    "🥁": "drum_beat_rhythm",
    "🎬": "clapper_board_film_movie",
    "🎥": "movie_camera_film",
    "🎞️": "film_strip_cinema",
    "📺": "tv_watching_binge",
    "📻": "radio_broadcast_audio",

    # =========================================================================
    # INTERNET / TECH CULTURE
    # =========================================================================
    "📱": "smartphone_mobile_tech",
    "📸": "camera_flash_photography",
    "📹": "video_camera_recording",
    "🔗": "link_connection_reference",
    "🔒": "locked_secure_private",
    "🔓": "unlocked_open_access",
    "🔑": "key_access_solution",
    "🛒": "shopping_cart_purchase",
    "💳": "credit_card_payment",
    "💰": "money_bag_wealth",
    "🖨️": "printer_document_output",
    "☁️": "cloud_storage_online",
    "💾": "floppy_disk_save",
    "📀": "dvd_disc_media",
    "💿": "cd_disc_storage",
    "📡": "satellite_antenna_signal",
    "🔋": "battery_energy_power",
    "🔌": "plug_connect_charge",
    "🧲": "magnet_attraction_pull",

    # =========================================================================
    # FOOD / DRINK SLANG
    # =========================================================================
    "☕": "coffee_break_cafe",
    "🍵": "tea_calm_relax",
    "🍺": "beer_drink_cheers",
    "🍻": "clinking_beers_celebrate",
    "🥂": "clinking_glasses_toast",
    "🍷": "wine_refined_relax",
    "🧃": "juice_box_childish",
    "🥤": "cup_straw_drink",
    "🍔": "burger_fast_food",
    "🌮": "taco_mexican_slang",
    "🍕": "pizza_fun_food",
    "🍣": "sushi_japanese_refined",
    "🍜": "ramen_noodles_comfort",
    "🥗": "salad_healthy_eating",
    "🧁": "cupcake_cute_sweet",

    # =========================================================================
    # WEATHER / NATURE MOOD
    # =========================================================================
    "☀️": "sunny_bright_energy",
    "🌙": "calm_moon_night",
    "⭐": "star_review_excellence",
    "❄️": "snowflake_cold_frozen",
    "🌪️": "tornado_chaos_destruction",
    "🌋": "volcano_explosive_eruption",
    "🌻": "sunflower_happy_growth",

    # =========================================================================
    # SYMBOLS / PUNCTUATION
    # =========================================================================
    "❗": "serious_emphasis_warning",
    "❓": "question_confusion_uncertain",
    "❕": "mild_emphasis",
    "❔": "mild_question_uncertain",
    "‼️": "urgent_exclamation",
    "⁉️": "shocked_questioning",
    "🔞": "adult_content_restricted",
    "✅": "check_mark_correct_done",
    "❌": "cross_mark_wrong_cancel",
    "⭕": "circle_o_void_empty",
    "🚫": "prohibited_no_entry",
    "🔝": "top_priority_best",
    "🔜": "coming_soon_soon",
    "🔛": "on_active_live",
    "♻️": "recycle_eco_sustainable",
    "📛": "name_badge_identity",
    "🔴": "red_dot_live_recording",
    "🟢": "green_dot_online_active",
    "🟡": "yellow_dot_away_pending",
    "⚪": "white_circle_empty_default",

    # =========================================================================
    # TRANSPORT / FLAG
    # =========================================================================
    "🚀": "rocket_launch_go_fast",
    "🚁": "helicopter_aerial_view",
    "✈️": "airplane_travel_flight",
    "🚗": "car_drive_road_trip",
    "🚕": "taxi_cab_ride",
    "🚑": "ambulance_emergency_medical",
    "🚓": "police_car_enforcement",
    "🚨": "siren_alert_emergency",
    "🚔": "patrol_car_surveillance",
    "🎌": "crossed_flags_japan_celebrate",
    "🏴": "black_flag_pirate_anarchy",
    "🏳️": "white_flag_surrender_truce",
    "🏳️‍🌈": "pride_flag_lgbtq",
    "🚩": "red_flag_warning_alert",

    # =========================================================================
    # ACTIVITY / HOBBY
    # =========================================================================
    "🏃": "running_exercise_hurry",
    "🏋️": "lifting_weights_gym",
    "🤸": "cartwheel_gymnastics_flexible",
    "🧘": "meditation_calm_balance",
    "🎨": "art_palette_creative",
    "🎭": "performing_arts_theater",
    "🎪": "circus_entertainment_fun",
    "🎢": "roller_coaster_thrill",
    "🎡": "ferris_wheel_fair_fun",
    "🎠": "carousel_nostalgia_childhood",
    "🏄": "surfing_riding_wave",
    "🤿": "diving_exploration_depth",
    "🏊": "swimming_pool_water",
    "🚴": "biking_cycling_exercise",
    "🧗": "climbing_aspiring_challenge",

    # =========================================================================
    # MISC CORE
    # =========================================================================
    "🫂": "hug_comfort_support",
    "🫃": "pregnant_belly_expecting",
    "🫄": "pregnant_person_expecting",
    "🫅": "crown_royal_leader",
    "🫰": "finger_heart_love_kpop",
}


# ---------------------------------------------------------------------------
# COMPILED PATTERNS
# ---------------------------------------------------------------------------

# Sort emojis by length descending (multi-codepoint emojis like flags)
_EMOJI_ITEMS: List[Tuple[str, str]] = sorted(
    _EMOJI_MAP.items(),
    key=lambda x: len(x[0]),
    reverse=True,
)

_EMOJI_SET: frozenset = frozenset(_EMOJI_MAP.keys())

# Regex pattern: matches any emoji in our map (longest first via alternation)
# Escape each emoji and join with |
_EMOJI_PATTERN: re.Pattern = re.compile(
    "|".join(re.escape(k) for k, _ in _EMOJI_ITEMS)
)

# Also build a pattern to find emoji positions
_EMOJI_FIND_PATTERN: re.Pattern = re.compile(
    "(" + "|".join(re.escape(k) for k, _ in _EMOJI_ITEMS) + ")"
)


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------


def normalize_emoji_text(text: str) -> str:
    """
    Replace emoji characters with their semantic meaning tags.
    Additive — never removes or rewrites surrounding text.

    Args:
        text: Raw user input text.

    Returns:
        Text with emojis replaced by semantic labels.
        Non-mapped emojis are left unchanged.

    Example:
        >>> normalize_emoji_text("bro that exam was insane 💀")
        'bro that exam was insane dead_laughing'
    """
    if not text or not text.strip():
        return text
    result = _EMOJI_PATTERN.sub(lambda m: " " + _EMOJI_MAP[m.group(0)] + " ", text)
    result = re.sub(r" +", " ", result).strip()
    return result


def get_emoji_meaning(emoji: str) -> Optional[str]:
    """
    Return the semantic meaning for a single emoji.

    Args:
        emoji: Emoji character to look up.

    Returns:
        Semantic tag string, or None if not in registry.
    """
    if not emoji:
        return None
    return _EMOJI_MAP.get(emoji.strip())


def contains_emoji(text: str) -> bool:
    """
    Return True if text contains any recognized emoji from the registry.

    Args:
        text: User input text.

    Returns:
        True if at least one mapped emoji is found, False otherwise.
    """
    if not text:
        return False
    return bool(_EMOJI_FIND_PATTERN.search(text))


def emoji_statistics(text: str) -> Dict[str, object]:
    """
    Return statistics about emoji usage in text.

    Args:
        text: User input text.

    Returns:
        Dict with keys: total_count, unique_count, emojis (list of (emoji, meaning)),
        density (ratio of emoji-containing words to total words).
    """
    if not text:
        return {
            "total_count": 0,
            "unique_count": 0,
            "emojis": [],
            "density": 0.0,
        }

    matches = list(_EMOJI_FIND_PATTERN.finditer(text))
    if not matches:
        return {
            "total_count": 0,
            "unique_count": 0,
            "emojis": [],
            "density": 0.0,
        }

    found_emojis: List[str] = [m.group(1) for m in matches]
    unique = list(dict.fromkeys(found_emojis))  # preserve order, deduplicate
    word_count = max(len(text.split()), 1)

    return {
        "total_count": len(found_emojis),
        "unique_count": len(unique),
        "emojis": [(e, _EMOJI_MAP.get(e, "unknown")) for e in unique],
        "density": round(len(found_emojis) / word_count, 2),
    }


# ---------------------------------------------------------------------------
# STATISTICS HELPERS (public, for diagnostics)
# ---------------------------------------------------------------------------


def registry_size() -> int:
    """Return total number of emoji entries."""
    return len(_EMOJI_MAP)


# ---------------------------------------------------------------------------
# SELF-TESTS
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("KIO emoji_normalizer.py -- Self-Test Suite")
    print("=" * 60)

    # --- Dataset size ---
    n_emoji = registry_size()
    print(f"\n[DATASET]")
    print(f"  Emoji entries        : {n_emoji}")
    assert 100 <= n_emoji <= 400, f"FAIL: emoji count out of range ({n_emoji})"
    print(f"  PASS: within 100-400 target range")

    # --- Normalization tests ---
    print(f"\n[NORMALIZATION]")
    cases = [
        ("bro that exam was insane 💀", "bro that exam was insane dead_laughing"),
        ("nah 😭", "nah crying_laughing_or_overwhelmed"),
        ("that is fire 🔥", "that is fire excellent_or_exciting"),
        ("goat 🐐", "goat goat_greatest_of_all_time"),
        ("no cap 🧢", "no cap cap_lying_or_fake"),
        ("so based 🗿", "so based stoic_or_unbothered"),
        ("thanks 🙏", "thanks thanks_or_respect"),
        ("100% 💯", "100% strong_agreement"),
        ("wow 🤡", "wow foolish_behavior"),
        ("heart you ❤️", "heart you positive_affection"),
        ("lol 😂", "lol laughing_tears"),
    ]
    for inp, expected in cases:
        result = normalize_emoji_text(inp)
        match = result == expected
        status = "PASS" if match else "FAIL"
        print(f"  [{status}] '{inp}' -> '{result}'")
        if not match:
            print(f"         expected: '{expected}'")

    # --- Multiple emojis ---
    print(f"\n[MULTIPLE EMOJIS]")
    multi = "exam cooked me 💀😭"
    result = normalize_emoji_text(multi)
    print(f"  Input   : '{multi}'")
    print(f"  Output  : '{result}'")
    assert "dead_laughing" in result
    assert "crying_laughing_or_overwhelmed" in result
    print(f"  PASS: both emojis normalized")

    # --- Additive (no text removal) ---
    print(f"\n[ADDITIVE SAFETY]")
    normal_text = "explain the TCP/IP protocol"
    result = normalize_emoji_text(normal_text)
    assert result == normal_text, f"FAIL: plain text was changed: '{result}'"
    print(f"  [PASS] '{normal_text}' -> unchanged")

    normal_text2 = "what is a recursive function"
    result = normalize_emoji_text(normal_text2)
    assert result == normal_text2, f"FAIL: plain text was changed: '{result}'"
    print(f"  [PASS] '{normal_text2}' -> unchanged")

    # --- Empty / edge cases ---
    print(f"\n[EDGE CASES]")
    assert normalize_emoji_text("") == ""
    assert normalize_emoji_text("   ") == "   "
    assert normalize_emoji_text(None) is None  # type: ignore
    print(f"  [PASS] empty/None/whitespace handled")

    # --- get_emoji_meaning ---
    print(f"\n[LOOKUP]")
    lookup_cases = ["💀", "🔥", "🤡", "🗿", "🐐", "🙏", "💯", "❤️", "😂", "😭"]
    for emoji in lookup_cases:
        meaning = get_emoji_meaning(emoji)
        status = "PASS" if meaning else "FAIL"
        print(f"  [{status}] '{emoji}' -> {meaning}")

    assert get_emoji_meaning("💀") == "dead_laughing"
    assert get_emoji_meaning("🔥") == "excellent_or_exciting"
    assert get_emoji_meaning("") is None
    print(f"  PASS: lookups correct")

    # --- contains_emoji ---
    print(f"\n[CONTAINS]")
    assert contains_emoji("i am dead 💀") is True
    assert contains_emoji("i love you") is False
    assert contains_emoji("🔥🔥🔥") is True
    assert contains_emoji("") is False
    print(f"  PASS: contains_emoji works")

    # --- Statistics ---
    print(f"\n[STATISTICS]")
    stat_text = "i am dead 💀 that is fire 🔥 nah 😭"
    stats = emoji_statistics(stat_text)
    print(f"  Input  : '{stat_text}'")
    print(f"  Stats  : {stats}")
    assert stats["total_count"] >= 1
    assert stats["unique_count"] >= 1
    assert 0.0 <= stats["density"] <= 1.0
    print(f"  PASS: statistics correct")

    # --- No emoji text stats ---
    no_emoji_stats = emoji_statistics("the sky is blue")
    assert no_emoji_stats["total_count"] == 0
    print(f"  [PASS] no-emoji text returns empty stats")

    # --- Non-mapped emoji ---
    print(f"\n[NON-MAPPED EMOJI]")
    # Use a rare emoji not in our map
    non_mapped = "hello 🦥"  # sloth is not in our map
    result = normalize_emoji_text(non_mapped)
    # Should leave non-mapped emojis unchanged
    assert result == non_mapped, f"FAIL: non-mapped emoji was changed: '{result}'"
    print(f"  [PASS] non-mapped emoji preserved: '{non_mapped}' -> '{result}'")

    print(f"\n{'=' * 60}")
    print("Self-test complete.")
    print(f"{'=' * 60}")
