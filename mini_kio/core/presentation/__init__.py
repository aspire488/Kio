"""
mini_kio.core.presentation — the presentation design engine
============================================================

Plan → design → build → validate → repair → verify → open.

Public entry point: create_presentation().
"""

from mini_kio.core.presentation.design import Deck, PALETTES, TypeScale, detect_palette
from mini_kio.core.presentation.planner import DeckPlan, SlideSpec

__all__ = ["Deck", "PALETTES", "TypeScale", "detect_palette", "DeckPlan", "SlideSpec"]
