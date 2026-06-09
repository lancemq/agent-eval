"""Reporting and visualization module."""

import html
import json
import os
from typing import Dict, List
from agent_eval.orchestrator.result_store import EvaluationReport


class ReportGenerator:
    """Generates evaluation reports in multiple formats."""

    def __init__(self, output_dir: str = "./eval_results"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate(self, report: EvaluationReport, formats: List[str] = None) -> Dict[str, str]:
        """Generate report in specified formats."""
        formats = formats or ["json", "html", "markdown"]
        generated = {}

        for fmt in formats:
            if fmt == "json":
                path = self._generate_json(report)
            elif fmt == "html":
                path = self._generate_html(report)
            elif fmt == "markdown":
                path = self._generate_markdown(report)
            else:
                continue
            generated[fmt] = path

        return generated

    def _generate_json(self, report: EvaluationReport) -> str:
        path = os.path.join(self.output_dir, f"{report.run_id}.json")
        with open(path, "w") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        return path

    def _generate_html(self, report: EvaluationReport) -> str:
        path = os.path.join(self.output_dir, f"{report.run_id}.html")
        html = self._build_html(report)
        with open(path, "w") as f:
            f.write(html)
        return path

    def _generate_markdown(self, report: EvaluationReport) -> str:
        path = os.path.join(self.output_dir, f"{report.run_id}.md")
        md = self._build_markdown(report)
        with open(path, "w") as f:
            f.write(md)
        return path

    def _build_html(self, report: EvaluationReport) -> str:
        dim_rows = ""
        for dim, score in report.summary.get("dimensions", {}).items():
            dim_rows += f"""
            <tr>
                <td>{html.escape(str(dim))}</td>
                <td><div class="bar-container"><div class="bar" style="width:{score*100:.0f}%">{score:.2f}</div></div></td>
            </tr>"""

        plugin_rows = ""
        for name, pr in report.plugin_results.items():
            plugin_rows += f"""
            <tr>
                <td>{html.escape(str(name))}</td>
                <td>{html.escape(str(pr.get('type', '')))}</td>
                <td><div class="bar-container"><div class="bar" style="width:{pr.get('score', 0)*100:.0f}%">{pr.get('score', 0):.2f}</div></div></td>
                <td>{pr.get('passed', 0)}/{pr.get('total', 0)}</td>
            </tr>"""

        run_id = html.escape(str(report.run_id))
        agent_name = html.escape(str(report.agent_name))
        agent_version = html.escape(str(report.agent_version))
        timestamp = html.escape(str(report.timestamp))

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>AgentEval Report - {run_id[:8]}</title>
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
        h1, h2, h3 {{ color: #1a1a1a; }}
        .card {{ background: #fff; border-radius: 8px; padding: 20px; margin: 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.12); }}
        .score {{ font-size: 48px; font-weight: bold; text-align: center; color: #2563eb; }}
        .score-label {{ text-align: center; color: #666; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e5e5e5; }}
        th {{ background: #fafafa; font-weight: 600; }}
        .bar-container {{ background: #e5e5e5; border-radius: 4px; overflow: hidden; }}
        .bar {{ background: linear-gradient(90deg, #2563eb, #3b82f6); color: #fff; padding: 2px 6px; font-size: 12px; border-radius: 4px; white-space: nowrap; }}
        .meta {{ color: #666; font-size: 14px; }}
        .green {{ color: #22c55e; }} .red {{ color: #ef4444; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>AgentEval Report</h1>
        <p class="meta">Run ID: {run_id}</p>
        <p class="meta">Agent: {agent_name} v{agent_version}</p>
        <p class="meta">Time: {timestamp}</p>
    </div>

    <div class="card">
        <div class="score">{report.summary.get('overall_score', 0):.3f}</div>
        <div class="score-label">Overall Score</div>
        <p style="text-align:center;margin-top:8px;">
            Passed: <span class="green">{report.summary.get('total_passed', 0)}</span> /
            Total: {report.summary.get('total_tasks', 0)}
        </p>
    </div>

    <div class="card">
        <h2>Dimensions</h2>
        <table><tr><th>Dimension</th><th>Score</th></tr>{dim_rows}</table>
    </div>

    <div class="card">
        <h2>Plugin Results</h2>
        <table>
            <tr><th>Plugin</th><th>Type</th><th>Score</th><th>Passed</th></tr>
            {plugin_rows}
        </table>
    </div>
</body>
</html>"""

    def _build_markdown(self, report: EvaluationReport) -> str:
        lines = [
            "# AgentEval Report",
            "",
            f"- **Run ID:** {report.run_id}",
            f"- **Agent:** {report.agent_name} v{report.agent_version}",
            f"- **Time:** {report.timestamp}",
            "",
            f"## Overall Score: {report.summary.get('overall_score', 0):.3f}",
            "",
            f"- Total Tasks: {report.summary.get('total_tasks', 0)}",
            f"- Passed: {report.summary.get('total_passed', 0)}",
            f"- Failed: {report.summary.get('total_failed', 0)}",
            f"- Pass Rate: {report.summary.get('pass_rate', 0):.1%}",
            "",
            "## Dimension Scores",
            "| Dimension | Score |",
            "|----------|-------|",
        ]
        for dim, score in report.summary.get("dimensions", {}).items():
            bar = "█" * int(score * 20)
            lines.append(f"| {dim} | {score:.3f} {bar} |")

        lines.extend(["", "## Plugin Results", "| Plugin | Type | Score | Passed |", "|--------|------|-------|--------|"])
        for name, pr in report.plugin_results.items():
            lines.append(f"| {name} | {pr.get('type', '')} | {pr.get('score', 0):.3f} | {pr.get('passed', 0)}/{pr.get('total', 0)} |")

        return "\n".join(lines)


def compare_reports(report_paths: List[str]) -> str:
    """Compare multiple reports and generate comparison markdown."""
    reports = []
    for path in report_paths:
        with open(path) as f:
            data = json.load(f)
            reports.append(data)

    lines = ["# Cross-Report Comparison", ""]
    for i, report in enumerate(reports):
        agent = report.get("agent", {})
        lines.append(f"## {i+1}. {agent.get('name', 'unknown')} v{agent.get('version', '?')}")
        lines.append(f"- Score: {report.get('summary', {}).get('overall_score', 0):.3f}")
        lines.append(f"- Pass Rate: {report.get('summary', {}).get('pass_rate', 0):.1%}")
        lines.append("")

    if len(reports) >= 2:
        lines.extend(["## Dimension Comparison", "| Dimension | " + " | ".join([f"Run {i+1}" for i in range(len(reports))]) + " |", "|" + "|".join(["---" for _ in range(len(reports)+1)]) + "|"])
        all_dims = set()
        for report in reports:
            all_dims.update(report.get("summary", {}).get("dimensions", {}).keys())
        for dim in sorted(all_dims):
            scores = [f"{report.get('summary', {}).get('dimensions', {}).get(dim, 0):.3f}" for report in reports]
            lines.append(f"| {dim} | " + " | ".join(scores) + " |")

    return "\n".join(lines)