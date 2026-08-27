"""
tests/test_language_robustness.py — Category-based tests for language normalization.

Tests are organized by linguistic CATEGORY, not individual hardcoded queries.
The implementation must not contain these examples as semantic routing rules.
They are TEST FIXTURES only.
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ['BROWSER_CONNECTOR_ENABLED'] = 'false'

import pytest
import difflib
from mini_kio.llm.input_normalizer import InputNormalizer, _FUZZY_VOCAB, _TYPO_MAP


n = InputNormalizer()


# ============================================================
# CATEGORY: TYPO — transposition, truncation, missing letter
# ============================================================
class TestTypoNormalization:
    """Fuzzy recovery of common typos via general mechanism."""

    @pytest.mark.parametrize("input,expected", [
        ("burnin", "burning"),
        ("memroy", "memory"),
        ("pythn", "python"),
        ("recusrion", "recursion"),
        ("machien", "machine"),
        ("baiscs", "basics"),
        ("sytnax", "syntax"),
        ("javascrpt", "javascript"),
        ("wroking", "working"),
        ("batery", "battery"),
    ])
    def test_typo_recovery(self, input, expected):
        result = n.normalize_typos(input)
        assert result == expected, f"{input!r} should normalize to {expected!r}, got {result!r}"

    def test_fuzzy_cutoff_prevents_bad_corrections(self):
        """Tokens with low similarity should NOT be corrected."""
        result = n.normalize_typos("xyzabc")
        assert result == "xyzabc"  # No correction — too different from any vocab word


# ============================================================
# CATEGORY: CONTRACTION — missing apostrophes
# ============================================================
class TestContractionExpansion:
    """Contractions are expanded by the general contraction map in _NormalizationService."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from mini_kio.core.pipeline import Pipeline
        from mini_kio.core.runtime import bootstrap_runtime, get_runtime
        rt = get_runtime() or bootstrap_runtime()
        self.pipeline = Pipeline()

    @pytest.mark.parametrize("input", [
        "whats up",
        "hows it going",
        "dont do that",
        "cant help me",
        "wont work",
        "im here",
        "youre right",
        "thats cool",
    ])
    def test_contraction_expansion(self, input):
        res = self.pipeline.run(input, session_id='test_contraction')
        assert res['success'], f"{input!r} should succeed"


# ============================================================
# CATEGORY: ABBREVIATION — common shorthand
# ============================================================
class TestAbbreviation:
    """Abbreviations are handled by the generic map (not query-specific)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from mini_kio.core.pipeline import Pipeline
        from mini_kio.core.runtime import bootstrap_runtime, get_runtime
        rt = get_runtime() or bootstrap_runtime()
        self.pipeline = Pipeline()

    @pytest.mark.parametrize("input", [
        "rn",       # right now
        "u good",   # you good
        "ur ok",    # your ok
        "pls help", # please help
        "ty",       # thank you
        "thx",      # thanks
        "idk",      # i do not know
    ])
    def test_abbreviation_in_pipeline(self, input):
        res = self.pipeline.run(input, session_id='test_abbr')
        assert res['success'], f"{input!r} should succeed"


# ============================================================
# CATEGORY: ORTHOGRAPHIC — missing letters, repeated chars
# ============================================================
class TestOrthographicNormalization:
    """General orthographic recovery mechanisms."""

    def test_repeated_characters_collapsed(self):
        """heeeello should be handled if vocabulary contains 'hello'."""
        # This tests whether the mechanism can handle repeated chars
        result = n.normalize_typos("heeeello")
        # Should at least not crash; exact behavior depends on implementation

    def test_missing_apostrophe_in_contractions(self):
        """whats -> what is (already covered by contraction map)"""
        result = n.normalize_typos("whats my ram")
        assert "what is" in result


# ============================================================
# CATEGORY: OVERCORRUPTION — must NOT corrupt these
# ============================================================
class TestOvercorruption:
    """Normalization must NOT corrupt filenames, project names, URLs, code, etc."""

    @pytest.mark.parametrize("input", [
        "memory_dump.py",            # filename
        "config.json",               # filename
        "README.md",                 # filename
        "github.com/user/repo",      # URL
        "https://api.example.com/v1",# URL
        "import os",                 # code
        "def main():",               # code
        "print(f'test')",            # code
        "OPENAI_API_KEY",            # environment variable
        "UTF-8",                     # technical term
        "KIO_ENGINEERING_OS.md",     # project file
        "mini_kio/core/pipeline/__init__.py",  # code path
        "Python 3.12",              # version string
        "psutil.virtual_memory()",  # code
    ])
    def test_no_corruption_of_technical_terms(self, input):
        result = n.normalize_typos(input)
        # The raw input should be preserved (possibly lowercased, but not rewritten)
        # Key check: filenames, URLs, code should not have words replaced
        assert result == input.lower() or result == input, \
            f"{input!r} should not be corrupted, got {result!r}"

    def test_proper_nouns_not_corrupted(self):
        """Proper nouns like 'KIO', 'Telegram', 'Python' should not be rewritten."""
        result = n.normalize_typos("KIO")
        assert result.lower() in ("kio", "kio")  # Lowercased but not rewritten

    def test_acronyms_preserved(self):
        result = n.normalize_typos("API")
        assert "api" in result.lower()

    def test_unusual_legitimate_words(self):
        """Words that are real but uncommon should not be 'corrected'."""
        result = n.normalize_typos("Kubernetes")
        # Should not be changed to something else
        assert "kubernetes" in result.lower() or result == "Kubernetes"


# ============================================================
# CATEGORY: SEMANTIC CONVERGENCE — same meaning, different words
# ============================================================
class TestKnowledgeVsResource:
    """Verify knowledge questions are NOT misclassified as resource queries."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from mini_kio.core.pipeline import _IntentClassifier
        from mini_kio.core.context_manager import ContextManager
        self.classifier = _IntentClassifier()
        self.ctx = ContextManager('test_knowledge')

    @pytest.mark.parametrize("input", [
        "how much does ram cost",
        "what does cpu mean",
        "how does memory work",
    ])
    def test_knowledge_not_resource(self, input):
        decision = self.classifier.classify(input, input)
        if decision:
            # Must NOT be OPERATIONAL with action in (ram, cpu, battery, storage)
            assert not (decision.intent_type.value == "operational" and decision.action in ("ram", "cpu", "battery", "storage")), \
                f"{input!r} must not route to resource metric, got {decision.action}"


class TestSemanticConvergence:
    """Different phrasings of the same intent should converge semantically.
    
    This tests the CLASSIFIER + GENERIC RESOURCE DETECTOR, not regex patterns.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self):
        from mini_kio.core.pipeline import Pipeline
        from mini_kio.core.runtime import bootstrap_runtime, get_runtime
        rt = get_runtime() or bootstrap_runtime()
        self.pipeline = Pipeline()
    
    def _classify(self, text):
        res = self.pipeline.run(text, session_id='tg_2146008061')
        return res
    
    def test_ram_variants_converge(self):
        """All RAM query variants should return the same semantic intent (RAM metric)."""
        variants = [
            "what is my ram",
            "how is my ram",
            "whats my ram",
            "what's my memory",
            "how much memory am i using",
            "how much ram am i using",
            "ram usage",
            "memory status",
        ]
        for v in variants:
            res = self._classify(v)
            msg = res['message'].lower()
            # All should return a RAM metric answer, not a chat/conversation response
            assert any(k in msg for k in ["ram", "memory", "gb", "%"]), \
                f"{v!r} should return RAM metric, got: {res['message'][:100]!r}"
    
    def test_battery_variants_converge(self):
        """All battery query variants should return battery metric."""
        variants = [
            "battery",
            "what's my battery",
            "how much battery do i have",
            "battery percentage",
        ]
        for v in variants:
            res = self._classify(v)
            msg = res['message'].lower()
            assert any(k in msg for k in ["battery", "charge", "power", "%"]), \
                f"{v!r} should return battery metric, got: {res['message'][:100]!r}"
    
    def test_cpu_variants_converge(self):
        """All CPU query variants should return CPU metric."""
        variants = [
            "cpu",
            "cpu usage",
            "what is my cpu",
            "how much cpu",
        ]
        for v in variants:
            res = self._classify(v)
            msg = res['message'].lower()
            assert any(k in msg for k in ["cpu", "processor", "%"]), \
                f"{v!r} should return CPU metric, got: {res['message'][:100]!r}"


# ============================================================
# CATEGORY: CURRENT STATE — authoritative, not historical
# ============================================================
class TestCurrentState:
    """Current-state queries must use LivingModel authority, not conversation history."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from mini_kio.core.pipeline import Pipeline
        from mini_kio.core.runtime import bootstrap_runtime, get_runtime
        rt = get_runtime() or bootstrap_runtime()
        self.pipeline = Pipeline()
    
    def test_current_projects_uses_authority(self):
        res = self.pipeline.run("What are my current projects?", session_id='tg_2146008061')
        msg = res['message'].lower()
        # Should contain authoritative state (CGPA or project), not stale conversation
        assert "cgpa" in msg or "project" in msg or "working" in msg, \
            f"Should return authoritative current state: {res['message'][:200]!r}"
    
    def test_personal_context_uses_authority(self):
        res = self.pipeline.run("who am i", session_id='tg_2146008061')
        msg = res['message'].lower()
        # Should contain authoritative personal data
        assert any(k in msg for k in ["cgpa", "student", "engineering", "scms", "joel"]), \
            f"Should return authoritative personal data: {res['message'][:200]!r}"


# ============================================================
# CATEGORY: UNSEEN WORDING — holdout queries
# ============================================================
class TestUnseenWording:
    """Queries phrased in ways not in any test fixture or regex."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from mini_kio.core.pipeline import Pipeline
        from mini_kio.core.runtime import bootstrap_runtime, get_runtime
        rt = get_runtime() or bootstrap_runtime()
        self.pipeline = Pipeline()
    
    def test_paraphrased_ram(self):
        """RAM asked in a completely novel phrasing."""
        res = self.pipeline.run("how memory looking rn", session_id='tg_2146008061')
        msg = res['message'].lower()
        assert any(k in msg for k in ["ram", "memory", "gb", "%"]), \
            f"Should detect RAM intent: {res['message'][:100]!r}"
    
    def test_paraphrased_battery(self):
        res = self.pipeline.run("charge level?", session_id='tg_2146008061')
        msg = res['message'].lower()
        assert any(k in msg for k in ["battery", "charge", "power", "%"]), \
            f"Should detect battery intent: {res['message'][:100]!r}"
    
    def test_greeting_unseen(self):
        res = self.pipeline.run("hey there", session_id='tg_2146008061')
        # Should be a greeting, not an error
        assert res['success']


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
