import pytest
import os
from mini_kio.memory.memory_store import MemoryStore
from mini_kio.llm.conversation_responder import ConversationResponder

@pytest.fixture
def memory():
    # Use a persistent session ID for testing persistence
    m = MemoryStore(session_id="persistence_test")
    m.clear()
    yield m
    m.clear()

def test_continuity_persistence(memory):
    os.environ["KIO_TEST_MODE"] = "1" # Disable real LLM
    
    # 1. Start a session, add history
    resp1 = ConversationResponder()
    resp1._memory = memory
    resp1._context.sync_from_memory(memory)
    
    memory.append("user", "Hello KIO")
    memory.append("assistant", "Hi there!")
    
    # 2. Simulate responder restart
    resp2 = ConversationResponder()
    resp2._memory = memory
    resp2._context.sync_from_memory(memory)
    
    # Check if history survived
    assert len(resp2._context._exchanges) == 1
    assert resp2._context._exchanges[0] == ("Hello KIO", "Hi there!")

def test_fact_persistence(memory):
    # 1. Store fact in session 1
    memory.set_fact("favorite_color", "blue")
    
    # 2. Retrieve fact in session 2
    memory2 = MemoryStore(session_id="persistence_test")
    assert memory2.get_fact("favorite_color") == "blue"
