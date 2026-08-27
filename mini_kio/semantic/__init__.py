"""KIO FINAL semantic substrate.

ONE graph (Node + Link + universal metadata + computed Activation + Planner).
User state, KIO state, third-party state, world state, goals, evidence,
memory, temporal state and execution state are QUERIES over this graph —
never independent storage systems.

The public entry point for the runtime is `mini_kio.semantic.intelligence`
(ingest_turn / semantic_state_block / resolve_references / planner_decision /
record_kio_reply); everything else is internal machinery.
"""
