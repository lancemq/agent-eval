"""Tests for new scorers: similarity, code_quality, text_analysis, format_validation, metrics."""

import pytest
from agent_eval.scorers.similarity import (
    BLEUScorer, ROUGEScorer, F1TokenScorer, EditDistanceScorer,
    JaccardScorer, CosineSimilarityScorer,
)
from agent_eval.scorers.code_quality import (
    CodeQualityScorer, SQLValidationScorer, CyclomaticComplexityScorer, CodeSecurityScorer,
)
from agent_eval.scorers.text_analysis import (
    ReadabilityScorer, LexicalDiversityScorer, SentimentScorer,
    GrammarCheckScorer, CoherenceScorer, FluencyScorer,
)
from agent_eval.scorers.format_validation import (
    DateTimeFormatScorer, URLFormatScorer, EmailFormatScorer,
    MarkdownStructureScorer, CitationCheckScorer, InstructionFollowingScorer,
)
from agent_eval.scorers.metrics import (
    ClassificationMetricsScorer, RegressionMetricsScorer, RankingMetricsScorer,
)
from agent_eval.scorers.factory import ScorerFactory


# =========================== Similarity Tests ===========================

class TestBLEUScorer:
    def test_identical(self):
        s = BLEUScorer()
        r = s.score("the cat sat on the mat", expected="the cat sat on the mat")
        assert r.score == pytest.approx(1.0, abs=0.01)

    def test_completely_different(self):
        s = BLEUScorer()
        r = s.score("zzzzz zzzzz zzzzz zzzzz zzzzz", expected="the cat sat on the mat")
        assert r.score < 0.3

    def test_no_reference(self):
        s = BLEUScorer()
        r = s.score("hello")
        assert r.score == 0.0


class TestROUGEScorer:
    def test_identical(self):
        s = ROUGEScorer()
        r = s.score("the cat sat on the mat", expected="the cat sat on the mat")
        assert r.score > 0.9

    def test_no_overlap(self):
        s = ROUGEScorer()
        r = s.score("zzz zzz zzz", expected="aaa aaa aaa")
        assert r.score == 0.0


class TestF1TokenScorer:
    def test_identical(self):
        s = F1TokenScorer()
        r = s.score("hello world", expected="hello world")
        assert r.score == pytest.approx(1.0)

    def test_partial(self):
        s = F1TokenScorer()
        r = s.score("hello world foo", expected="hello world bar")
        assert 0.3 < r.score < 0.7


class TestEditDistanceScorer:
    def test_identical(self):
        s = EditDistanceScorer()
        r = s.score("hello", expected="hello")
        assert r.score == 1.0

    def test_one_char_off(self):
        s = EditDistanceScorer()
        r = s.score("hallo", expected="hello")
        assert r.score == pytest.approx(0.8, abs=0.01)


class TestJaccardScorer:
    def test_identical(self):
        s = JaccardScorer()
        r = s.score("hello world", expected="hello world")
        assert r.score == pytest.approx(1.0)

    def test_disjoint(self):
        s = JaccardScorer()
        r = s.score("aaa", expected="bbb")
        assert r.score == 0.0


class TestCosineSimilarityScorer:
    def test_identical(self):
        s = CosineSimilarityScorer()
        r = s.score("hello world", expected="hello world")
        assert r.score > 0.99

    def test_different(self):
        s = CosineSimilarityScorer()
        r = s.score("apple banana", expected="car truck")
        assert r.score == 0.0


# =========================== Code Quality Tests ===========================

class TestCodeQualityScorer:
    def test_valid_code(self):
        code = '''def hello(name):\n    """Say hello."""\n    return f"Hello, {name}"\n'''
        s = CodeQualityScorer()
        r = s.score(code)
        assert r.score > 0.5

    def test_syntax_error(self):
        s = CodeQualityScorer()
        r = s.score("def broken(:\n    pass")
        assert "syntax_error" in r.reason.lower()

    def test_with_issues(self):
        code = "x = 1  # TODO: fix this\n"
        s = CodeQualityScorer()
        r = s.score(code)
        assert "todo" in r.reason.lower()


class TestSQLValidationScorer:
    def test_valid_select(self):
        s = SQLValidationScorer()
        r = s.score("SELECT name FROM users WHERE id = 1")
        assert r.score > 0.7

    def test_select_star(self):
        s = SQLValidationScorer()
        r = s.score("SELECT * FROM users")
        assert "SELECT *" in r.reason

    def test_not_sql(self):
        s = SQLValidationScorer()
        r = s.score("hello world")
        assert r.score < 0.8


class TestCodeSecurityScorer:
    def test_safe_code(self):
        s = CodeSecurityScorer()
        r = s.score("x = 1 + 2\nprint(x)")
        assert r.passed is True

    def test_eval(self):
        s = CodeSecurityScorer()
        r = s.score("eval('1+1')")
        assert "eval" in r.reason.lower()

    def test_hardcoded_password(self):
        s = CodeSecurityScorer()
        r = s.score('password = "secret123"')
        assert r.passed is False


class TestCyclomaticComplexityScorer:
    def test_simple_code(self):
        s = CyclomaticComplexityScorer()
        r = s.score("x = 1\nprint(x)")
        assert r.score == 1.0
        assert r.metadata["complexity"] == 1

    def test_complex_code(self):
        code = "def f(x):\n    if x:\n        for i in range(10):\n            if i:\n                pass\n    while x:\n        pass\n"
        s = CyclomaticComplexityScorer()
        r = s.score(code)
        assert r.metadata["complexity"] > 3

    def test_syntax_error(self):
        s = CyclomaticComplexityScorer()
        r = s.score("def (:")
        assert r.score == 0.0


# =========================== Text Analysis Tests ===========================

class TestReadabilityScorer:
    def test_simple_text(self):
        s = ReadabilityScorer(target_grade=5)
        r = s.score("This is a simple text. It has short sentences. Easy to read.")
        assert "Grade Level" in r.reason

    def test_empty(self):
        s = ReadabilityScorer()
        r = s.score("")
        assert r.score == 0.0


class TestLexicalDiversityScorer:
    def test_diverse_text(self):
        s = LexicalDiversityScorer(min_ttr=0.3, max_ttr=1.0)
        r = s.score("apple banana cherry dog elephant fox grape")
        assert r.score > 0.7

    def test_repetitive(self):
        s = LexicalDiversityScorer(min_ttr=0.3, max_ttr=0.8)
        r = s.score("the the the the the the")
        assert r.score < 0.6


class TestSentimentScorer:
    def test_positive(self):
        s = SentimentScorer()
        r = s.score("This is great and wonderful! I love it!")
        assert r.metadata["polarity"] == "positive"

    def test_negative(self):
        s = SentimentScorer()
        r = s.score("This is terrible and awful. I hate it.")
        assert r.metadata["polarity"] == "negative"

    def test_neutral(self):
        s = SentimentScorer()
        r = s.score("The sky is blue. The grass is green.")
        assert r.metadata["polarity"] == "neutral"

    def test_expected_polarity(self):
        s = SentimentScorer(expected_polarity="positive")
        r = s.score("This is great!")
        assert r.score == 1.0


class TestGrammarCheckScorer:
    def test_clean_text(self):
        s = GrammarCheckScorer()
        r = s.score("This is a well-written sentence with proper grammar.")
        assert r.score > 0.7

    def test_double_word(self):
        s = GrammarCheckScorer()
        r = s.score("I went to the the store.")
        assert "double" in r.reason.lower()

    def test_repeated_punctuation(self):
        s = GrammarCheckScorer()
        r = s.score("Hello!!! How are you??")
        assert "punctuation" in r.reason.lower()


class TestCoherenceScorer:
    def test_coherent_text(self):
        text = "The cat sat on the mat. The cat was happy. The cat purred loudly."
        s = CoherenceScorer()
        r = s.score(text)
        assert r.score > 0.0
        assert "overlap" in r.reason.lower()

    def test_short_text(self):
        s = CoherenceScorer()
        r = s.score("Only one sentence.")
        assert r.score == 0.5


class TestFluencyScorer:
    def test_good_fluency(self):
        text = "The system uses a modular architecture. Components communicate through well-defined interfaces. Testing ensures reliability across modules."
        s = FluencyScorer()
        r = s.score(text)
        assert r.score > 0.0

    def test_too_short(self):
        s = FluencyScorer()
        r = s.score("Short.")
        assert r.score == 0.5


# =========================== Format Validation Tests ===========================

class TestDateTimeFormatScorer:
    def test_iso_date(self):
        s = DateTimeFormatScorer()
        r = s.score("2024-01-15")
        assert r.score == 1.0

    def test_iso_datetime(self):
        s = DateTimeFormatScorer()
        r = s.score("2024-01-15T10:30:00")
        assert r.score == 1.0

    def test_invalid(self):
        s = DateTimeFormatScorer()
        r = s.score("hello world")
        assert r.score == 0.0


class TestURLFormatScorer:
    def test_valid_https(self):
        s = URLFormatScorer()
        r = s.score("https://example.com/path")
        assert r.score == 1.0

    def test_valid_http(self):
        s = URLFormatScorer()
        r = s.score("http://localhost:8080")
        assert r.score == 1.0

    def test_invalid(self):
        s = URLFormatScorer()
        r = s.score("not a url")
        assert r.score == 0.0

    def test_require_https(self):
        s = URLFormatScorer(require_https=True)
        r = s.score("http://example.com")
        assert r.score == 0.0


class TestEmailFormatScorer:
    def test_valid(self):
        s = EmailFormatScorer()
        r = s.score("user@example.com")
        assert r.score == 1.0

    def test_invalid(self):
        s = EmailFormatScorer()
        r = s.score("not-an-email")
        assert r.score == 0.0


class TestMarkdownStructureScorer:
    def test_valid_markdown(self):
        md = "# Title\n\nSome text here.\n\n- item 1\n- item 2\n"
        s = MarkdownStructureScorer()
        r = s.score(md)
        assert r.score > 0.5

    def test_require_headings(self):
        s = MarkdownStructureScorer(require_headings=True)
        r = s.score("Just plain text without headings")
        assert "headings" in r.reason.lower()

    def test_unclosed_code_block(self):
        md = "```python\nprint('hello')\n"
        s = MarkdownStructureScorer()
        r = s.score(md)
        assert "unclosed" in r.reason.lower()


class TestCitationCheckScorer:
    def test_with_citations(self):
        text = "According to Smith (2024), the results are significant [1]."
        s = CitationCheckScorer()
        r = s.score(text)
        assert r.metadata["total_citations"] >= 2

    def test_no_citations(self):
        s = CitationCheckScorer()
        r = s.score("This is just a plain text without any references.")
        assert r.metadata["total_citations"] == 0


class TestInstructionFollowingScorer:
    def test_json_instruction(self):
        s = InstructionFollowingScorer()
        r = s.score('{"key": "value"}', instruction="Answer in JSON format")
        assert any("JSON" in c for c in r.metadata["checks_passed"])

    def test_bullet_instruction(self):
        s = InstructionFollowingScorer()
        r = s.score("- item 1\n- item 2", instruction="Use bullet points")
        assert any("bullet" in c for c in r.metadata["checks_passed"])

    def test_word_count(self):
        s = InstructionFollowingScorer()
        r = s.score("one two three", instruction="Respond in less than 10 words")
        assert len(r.metadata["checks_passed"]) > 0

    def test_word_count_exceeded(self):
        s = InstructionFollowingScorer()
        r = s.score("a " * 20, instruction="Respond in less than 5 words")
        assert len(r.metadata["checks_failed"]) > 0


# =========================== ML Metrics Tests ===========================

class TestClassificationMetricsScorer:
    def test_perfect(self):
        s = ClassificationMetricsScorer()
        r = s.score("A,B,A", expected="A,B,A")
        assert r.score == 1.0
        assert r.metadata["accuracy"] == 1.0

    def test_partial(self):
        s = ClassificationMetricsScorer()
        r = s.score("A,B,A", expected="A,A,A")
        assert r.score < 1.0
        assert r.metadata["accuracy"] == pytest.approx(2/3, abs=0.01)

    def test_multiclass(self):
        s = ClassificationMetricsScorer()
        r = s.score(["cat", "dog", "cat", "bird"], expected=["cat", "dog", "dog", "bird"])
        assert r.metadata["accuracy"] == pytest.approx(0.75)


class TestRegressionMetricsScorer:
    def test_perfect(self):
        s = RegressionMetricsScorer()
        r = s.score("3.0, 4.0, 5.0", expected="3.0, 4.0, 5.0")
        assert r.score == 1.0
        assert r.metadata["r2"] == 1.0

    def test_with_error(self):
        s = RegressionMetricsScorer()
        r = s.score("2.0, 4.0, 6.0", expected="3.0, 5.0, 7.0")
        assert r.score < 1.0
        assert r.metadata["mae"] == 1.0


class TestRankingMetricsScorer:
    def test_perfect_ranking(self):
        s = RankingMetricsScorer()
        r = s.score(["doc1", "doc2", "doc3"], expected={"doc1": 3, "doc2": 2, "doc3": 1})
        assert r.score == pytest.approx(1.0, abs=0.01)

    def test_bad_ranking(self):
        s = RankingMetricsScorer()
        r = s.score(["doc3", "doc2", "doc1"], expected={"doc1": 3, "doc2": 2, "doc3": 1})
        assert r.score < 1.0

    def test_with_list_relevance(self):
        s = RankingMetricsScorer()
        r = s.score(["relevant", "irrelevant", "relevant2"], expected=["relevant", "relevant2"])
        assert r.metadata["mrr"] == pytest.approx(1.0)


# =========================== Factory Integration Tests ===========================

class TestNewScorersInFactory:
    def test_all_56_scorers_registered(self):
        scorers = ScorerFactory.list_scorers()
        assert len(scorers) == 56

    def test_factory_creates_bleu(self):
        s = ScorerFactory.create("bleu")
        assert isinstance(s, BLEUScorer)

    def test_factory_creates_code_quality(self):
        s = ScorerFactory.create("code_quality")
        assert isinstance(s, CodeQualityScorer)

    def test_factory_creates_sentiment(self):
        s = ScorerFactory.create("sentiment")
        assert isinstance(s, SentimentScorer)

    def test_factory_creates_url_format(self):
        s = ScorerFactory.create("url_format")
        assert isinstance(s, URLFormatScorer)

    def test_factory_creates_classification_metrics(self):
        s = ScorerFactory.create("classification_metrics")
        assert isinstance(s, ClassificationMetricsScorer)

    def test_new_scorers_in_list(self):
        scorers = ScorerFactory.list_scorers()
        for name in [
            "bleu", "rouge", "f1_token", "edit_distance", "jaccard",
            "cosine_similarity", "semantic_similarity",
            "code_quality", "sql_validation", "code_format", "complexity", "code_security",
            "readability", "lexical_diversity", "sentiment", "grammar_check",
            "tone_analysis", "coherence", "fluency",
            "datetime_format", "url_format", "email_format",
            "markdown_structure", "citation_check", "instruction_following",
            "classification_metrics", "regression_metrics", "ranking_metrics",
        ]:
            assert name in scorers, f"Missing scorer: {name}"
