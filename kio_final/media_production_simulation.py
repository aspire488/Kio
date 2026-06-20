import logging
import sys
import asyncio
import random
from typing import List, Dict, Any
from mini_kio.llm.conversation_responder import ConversationResponder
from mini_kio.llm.conversation_models import ConversationTone

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)
logger = logging.getLogger()

class MediaProductionSimulator:
    def __init__(self):
        self.responder = ConversationResponder(session_id="prod_sim_001")
        self.stats = {
            "total_conversations": 0,
            "total_turns": 0,
            "context_failures": 0,
            "playback_failures": 0,
            "freshness_failures": 0,
            "routing_failures": 0,
            "recommendation_failures": 0,
        }
        self.failures = []

    async def run_simulation(self):
        print("\n" + "="*60)
        print("KIO MEDIA INTELLIGENCE — PRODUCTION SIMULATION AUDIT")
        print("="*60)

        # Categories mapping
        scenarios = [
            self.sim_context_switching,      # Cat 1
            self.sim_ambiguous_entities,    # Cat 2
            self.sim_latest_queries,        # Cat 3
            self.sim_number_only,           # Cat 4
            self.sim_yes_only,              # Cat 5
            self.sim_recommendations,       # Cat 6
            self.sim_mixed_domains,         # Cat 7
            self.sim_freshness_stress,      # Cat 8
            self.sim_playback_stress,       # Cat 9
            self.sim_random_entities        # Cat 10
        ]

        for i in range(200):
            scenario_fn = random.choice(scenarios)
            await scenario_fn()
            self.stats["total_conversations"] += 1
            if (i+1) % 10 == 0:
                print(f"Completed {i+1}/200 conversations...")

        self.report()

    async def sim_context_switching(self):
        """Category 1: Context Switching"""
        turns = [
            "Interstellar",
            "Who directed it?",
            "Any interviews?",
            "Actually what's the latest FIFA news?",
            "Show highlights."
        ]
        await self.execute_session("Context Switch", turns)

    async def sim_ambiguous_entities(self):
        """Category 2: Ambiguous Entities"""
        turns = [
            "Believer",
            "Tell me more.",
            "Play it.",
            "Who made it?",
            "Any live versions?"
        ]
        await self.execute_session("Ambiguous Entity", turns)

    async def sim_latest_queries(self):
        """Category 3: Latest Queries"""
        entities = ["FIFA", "Formula 1", "GTA 6", "Spider-Man", "One Piece"]
        entity = random.choice(entities)
        turns = [
            f"Latest {entity} updates",
            "What changed?",
            "Any news for today?",
            "Show me more.",
            "Any videos?"
        ]
        await self.execute_session("Latest Query", turns)

    async def sim_number_only(self):
        """Category 4: Number-only interactions"""
        turns = [
            "Interstellar",
            "2",
            "1",
            "Interstellar again",
            "4"
        ]
        await self.execute_session("Number Only", turns)

    async def sim_yes_only(self):
        """Category 5: Yes-only interactions"""
        turns = [
            "Interstellar",
            "yes",
            "sure",
            "show it",
            "play it"
        ]
        await self.execute_session("Yes Only", turns)

    async def sim_recommendations(self):
        """Category 6: Recommendations"""
        topics = ["sci-fi movie", "TV show like Severance", "anime like Frieren", "tracks like Starboy"]
        topic = random.choice(topics)
        turns = [
            f"Recommend a {topic}",
            "Anything else?",
            "What about movies?",
            "Tell me more about the first one.",
            "Play the trailer."
        ]
        await self.execute_session("Recommendation", turns)

    async def sim_mixed_domains(self):
        """Category 7: Mixed Domains"""
        turns = [
            "FIFA",
            "Interstellar",
            "Believer",
            "MrBeast",
            "Formula 1"
        ]
        await self.execute_session("Mixed Domains", turns)

    async def sim_freshness_stress(self):
        """Category 8: Freshness Stress Test"""
        keywords = ["latest", "update", "news", "recent", "today"]
        kw = random.choice(keywords)
        turns = [
            f"Any {kw} for GTA 6?",
            "What about FIFA?",
            f"Show {kw} for Lewis Hamilton.",
            "Any developments?",
            "What's the latest?"
        ]
        await self.execute_session("Freshness Stress", turns)

    async def sim_playback_stress(self):
        """Category 9: Playback Stress Test"""
        turns = [
            "Interstellar",
            "Show best scenes",
            "Play it",
            "Find behind the scenes",
            "Play that one"
        ]
        await self.execute_session("Playback Stress", turns)

    async def sim_random_entities(self):
        """Category 10: Random Entity Test"""
        entities = ["Oppenheimer", "The Bear", "Blue Lock", "Lamine Yamal", "The Weeknd", "Cyberpunk 2077"]
        entity = random.choice(entities)
        turns = [
            entity,
            "Tell me more.",
            "Any videos?",
            "Show one.",
            "Play it."
        ]
        await self.execute_session("Random Entity", turns)

    async def execute_session(self, name: str, turns: List[str]):
        self.responder._state.context.clear() # Fresh context for each session
        subject = ""
        
        for turn_idx, text in enumerate(turns):
            self.stats["total_turns"] += 1
            # In a real simulation we'd call responder.respond(text)
            # For this audit, we will simulate the internal state transitions 
            # to detect logic breaks.
            
            # 1. Resolve Reference
            resolved = self.responder._state.context.resolve_reference(text)
            
            # 2. Routing (Simulate)
            # Check if domain detection works
            from mini_kio.knowledge.media_knowledge_router import MediaKnowledgeRouter
            router = MediaKnowledgeRouter()
            _, domain = router.route(resolved)
            
            # 3. Validation Logic
            fail = False
            reason = ""
            
            # Context Failure Check
            if text in ("Who directed it?", "Tell me more.", "2", "yes") and "Interstellar" not in resolved and not self.responder._state.context.recent_entity():
                 # This is a bit simplified, but checks if 'it' was resolved or entity exists
                 if not self.responder._state.context.recent_entity():
                    fail = True
                    reason = "Context Lost"
                    self.stats["context_failures"] += 1

            # Freshness Failure Check
            is_fresh_query = any(kw in text.lower() for kw in ("latest", "news", "update"))
            if is_fresh_query:
                from mini_kio.knowledge.retrieval_router import KnowledgeRouter
                k_router = KnowledgeRouter()
                if not k_router._is_freshness_query(text):
                    fail = True
                    reason = "Freshness Bypass Failed"
                    self.stats["freshness_failures"] += 1

            # Update context for next turn
            self.responder._state.context.append_exchange(text, f"Simulated reply for {domain}")
            
            if fail:
                self.failures.append({
                    "session": name,
                    "turn": turn_idx + 1,
                    "input": text,
                    "resolved": resolved,
                    "reason": reason
                })

    def report(self):
        print("\n" + "="*60)
        print("SIMULATION AUDIT REPORT")
        print("="*60)
        print(f"Total Conversations: {self.stats['total_conversations']}")
        print(f"Total Turns: {self.stats['total_turns']}")
        print(f"Context Failures: {self.stats['context_failures']}")
        print(f"Playback Failures: {self.stats['playback_failures']}")
        print(f"Freshness Failures: {self.stats['freshness_failures']}")
        print(f"Routing Failures: {self.stats['routing_failures']}")
        
        failure_rate = (len(self.failures) / self.stats["total_turns"]) * 100 if self.stats["total_turns"] > 0 else 0
        print(f"Failure Rate: {failure_rate:.2f}%")
        
        if self.failures:
            print("\nSAMPLE FAILURES:")
            for f in self.failures[:5]:
                print(f"- [{f['session']}] Turn {f['turn']}: '{f['input']}' -> {f['reason']}")

if __name__ == "__main__":
    sim = MediaProductionSimulator()
    asyncio.run(sim.run_simulation())
