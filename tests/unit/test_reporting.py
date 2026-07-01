"""Tests for HTML report escaping."""

from agent_eval.orchestrator.result_store import EvaluationReport
from agent_eval.reporting import ReportGenerator


def _make_report(agent_name="<script>alert(1)</script>"):
    return EvaluationReport(
        run_id="test-run",
        timestamp="2024-01-01T00:00:00Z",
        agent_name=agent_name,
        agent_version="1.0",
        summary={
            "overall_score": 0.5,
            "total_tasks": 1,
            "total_passed": 1,
            "total_failed": 0,
            "pass_rate": 1.0,
            "dimensions": {"<b>dim</b>": 0.5},
            "num_evaluators": 1,
        },
        evaluator_results={
            "<img onerror=alert(1)>": {
                "score": 0.5,
                "type": "<script>",
                "passed": 1,
                "total": 1,
            },
        },
        metadata={},
    )


def test_html_report_escapes_agent_name():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = ReportGenerator(tmpdir)
        paths = gen.generate(_make_report(), formats=["html"])
        with open(paths["html"]) as f:
            content = f.read()
        assert "<script>alert(1)</script>" not in content
        assert "&lt;script&gt;" in content


def test_html_report_escapes_dimension_names():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = ReportGenerator(tmpdir)
        paths = gen.generate(_make_report(), formats=["html"])
        with open(paths["html"]) as f:
            content = f.read()
        assert "<b>dim</b>" not in content
        assert "&lt;b&gt;dim&lt;/b&gt;" in content


def test_html_report_escapes_plugin_names():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = ReportGenerator(tmpdir)
        paths = gen.generate(_make_report(), formats=["html"])
        with open(paths["html"]) as f:
            content = f.read()
        assert "<img onerror=alert(1)>" not in content
        assert "&lt;img onerror=alert(1)&gt;" in content
