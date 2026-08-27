"""Companion Intelligence Layer — persistent cognitive model for KIO.

Provides the bridge between raw evidence (SemanticGraph) and LLM reasoning.
This is a TEMPORARY implementation that works through the existing KIO runtime.
Future AURA can take ownership without rewrite.

Architecture:
    OBSERVATION → EVIDENCE → CONSOLIDATION → BELIEF → MODEL → PROJECTION → LLM
    + Relationship Intelligence
    + Consequence Reasoning
    + Initiative Tracking
    + Situation Modeling
    + Semantic Matching (sentence-transformers)

Freedom of Mind. Governance of Action.
"""
