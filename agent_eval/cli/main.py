"""CLI entry point for AgentEval."""

import argparse
import json
import os
import sys

from agent_eval.config import load_config
from agent_eval.evaluators.base import EvaluatorRegistry
from agent_eval.reporting import ReportGenerator, compare_reports
from agent_eval.runner import run_evaluation_from_config


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-eval",
        description="AI Agent Evaluation Framework",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run command
    run_parser = subparsers.add_parser("run", help="Run evaluation")
    run_parser.add_argument("--agent", "-a", required=True, help="Agent module path (e.g. 'my_module:MyAgent') or 'openai:gpt-4o'")
    run_parser.add_argument("--config", "-c", default="eval_config.yaml", help="Config file path")
    run_parser.add_argument("--evaluators", "-e", nargs="+", default=[], help="Evaluators to run")
    run_parser.add_argument("--output", "-o", default="./eval_results", help="Output directory")
    run_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # list evaluators
    list_parser = subparsers.add_parser("list", help="List available evaluators")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # compare command
    compare_parser = subparsers.add_parser("compare", help="Compare evaluation reports")
    compare_parser.add_argument("reports", nargs="+", help="Report file paths")
    compare_parser.add_argument("--output", "-o", default="./eval_results/comparison.md", help="Output path")

    # report command
    report_parser = subparsers.add_parser("report", help="Generate report from results")
    report_parser.add_argument("--run-id", required=True, help="Run ID to generate report for")
    report_parser.add_argument("--output-dir", default="./eval_results", help="Output directory")
    report_parser.add_argument("--formats", nargs="+", default=["json", "html", "markdown"], help="Output formats")

    # ui command
    ui_parser = subparsers.add_parser("ui", help="Start the local Web UI")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    ui_parser.add_argument("--port", type=int, default=8080, help="Port to bind")
    ui_parser.add_argument("--output-dir", default="./eval_results", help="Output directory")
    ui_parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload")

    # dataset command
    dataset_parser = subparsers.add_parser("dataset", help="Manage versioned eval datasets")
    dataset_sub = dataset_parser.add_subparsers(dest="dataset_command")
    dataset_sub.add_parser("list", help="List datasets")
    ds_get = dataset_sub.add_parser("get", help="Show a dataset (optionally a specific version)")
    ds_get.add_argument("name", help="Dataset name")
    ds_get.add_argument("--version", default=None, help="Version (default: latest)")
    ds_get.add_argument("--json", action="store_true", help="Output as JSON")
    ds_from_traces = dataset_sub.add_parser("from-traces", help="Build a dataset from traces")
    ds_from_traces.add_argument("name", help="New dataset name")
    ds_from_traces.add_argument("--trace-dir", default="./traces", help="Trace directory")
    ds_from_traces.add_argument("--description", default="", help="Dataset description")
    ds_from_traces.add_argument("--min-quality", type=float, default=0.0, help="Min trace quality score")
    ds_from_traces.add_argument("--filters", default=None, help="JSON filter dict, e.g. '{\"trace_type\":\"tool_use\"}'")

    return parser


def cmd_run(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    result = run_evaluation_from_config(
        config,
        agent_spec=args.agent,
        evaluator_names=args.evaluators or None,
        output_dir=args.output,
    )

    print("\nEvaluation complete!")
    print(f"  Overall Score: {result.report.summary.get('overall_score', 0):.3f}")
    print(f"  Pass Rate: {result.report.summary.get('pass_rate', 0):.1%}")
    print("  Reports generated:")
    for fmt, path in result.generated_reports.items():
        print(f"    {fmt}: {path}")


def cmd_list(args: argparse.Namespace) -> None:
    evaluators = EvaluatorRegistry.list_evaluators()

    if args.json:
        print(json.dumps(evaluators, indent=2))
    else:
        print(f"{'Evaluator Name':<20} {'Version':<8} {'Type':<15} {'Dimensions':<40}")
        print("-" * 83)
        for name, info in evaluators.items():
            dims = ", ".join(info.get("dimensions", [])[:3])
            print(f"{name:<20} {info.get('version', ''):<8} {info.get('type', ''):<15} {dims:<40}")


def cmd_compare(args: argparse.Namespace) -> None:
    result = compare_reports(args.reports)
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            f.write(result)
        print(f"Comparison saved to {args.output}")
    else:
        print(result)


def cmd_report(args: argparse.Namespace) -> None:
    from agent_eval.orchestrator import ResultStore
    store = ResultStore({"type": "json", "output_dir": args.output_dir})
    report = store.load(args.run_id)
    if not report:
        print(f"Report {args.run_id} not found in {args.output_dir}")
        sys.exit(1)

    generator = ReportGenerator(args.output_dir)
    generated = generator.generate(report, args.formats)
    for fmt, path in generated.items():
        print(f"  {fmt}: {path}")


def cmd_ui(args: argparse.Namespace) -> None:
    try:
        import uvicorn
    except ImportError:
        print("Web UI dependencies are not installed. Install with: pip install -e '.[web]'")
        sys.exit(1)

    print(f"Starting AgentEval Web UI at http://{args.host}:{args.port}")
    if args.host != "127.0.0.1":
        print("Warning: the Web UI can execute local agent modules. Do not expose it to untrusted networks.")

    from agent_eval.web.app import create_app

    uvicorn.run(
        create_app(output_dir=args.output_dir),
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def cmd_dataset(args: argparse.Namespace) -> None:
    from agent_eval.datasets import DatasetStore
    from agent_eval.trace.store import TraceStore
    from agent_eval.trace.task_generator import TaskGenerator
    from agent_eval.datasets import DatasetBuilder

    workspace = os.getcwd()
    store = DatasetStore(workspace)

    if args.dataset_command == "list":
        items = store.list_datasets()
        if not items:
            print("No datasets found.")
            return
        print(f"{'Name':<24} {'Version':<10} {'Rows':<6} {'Versions':<9} {'Updated':<12}")
        print("-" * 65)
        for it in items:
            print(f"{it['name']:<24} v{it['latest_version']:<9} {it['row_count']:<6} {it['version_count']:<9} {it['updated_at'][:10]}")
    elif args.dataset_command == "get":
        record = store.get(args.name, args.version)
        if args.json:
            print(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"Dataset: {record.name}  v{record.version}  ({record.row_count} rows)")
            if record.description:
                print(f"Description: {record.description}")
            print(f"Source traces: {record.source_traces or '(none)'}")
            print("Rows:")
            for row in record.rows:
                print(f"  - {json.dumps(row, ensure_ascii=False)}")
    elif args.dataset_command == "from-traces":
        trace_store = TraceStore(path=args.trace_dir)
        filters = json.loads(args.filters) if args.filters else {}
        traces = trace_store.query(filters)
        if args.min_quality > 0:
            traces = [t for t in traces if t.quality_score >= args.min_quality]
        deduped = DatasetBuilder._deduplicate(traces) if traces else []
        tasks = TaskGenerator().generate_batch(deduped)
        rows = []
        for task in tasks:
            item = task.to_dict()
            item["expected"] = item.pop("expected_output", "")
            rows.append(item)
        record = store.create(
            name=args.name, rows=rows, description=args.description,
            source_traces=[t.trace_id for t in deduped],
        )
        print(f"Created dataset '{record.name}' v{record.version} with {record.row_count} rows from {len(deduped)} traces.")
    else:
        print("Usage: agent-eval dataset {list|get|from-traces}")


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "compare":
        cmd_compare(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "ui":
        cmd_ui(args)
    elif args.command == "dataset":
        cmd_dataset(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
