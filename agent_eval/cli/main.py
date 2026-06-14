"""CLI entry point for AgentEval."""

import argparse
import json
import sys
import os
from typing import Any, Dict

from agent_eval.config import load_config
from agent_eval.orchestrator import EvaluationOrchestrator, OpenAIAgent, CallableAgent, AgentUnderTest
from agent_eval.plugins.base import PluginRegistry
from agent_eval.reporting import ReportGenerator, compare_reports


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
    run_parser.add_argument("--plugins", "-p", nargs="+", default=[], help="Plugins to run")
    run_parser.add_argument("--output", "-o", default="./eval_results", help="Output directory")
    run_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # list plugins
    list_parser = subparsers.add_parser("list", help="List available plugins")
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

    return parser


def cmd_run(args: argparse.Namespace) -> None:
    config = load_config(args.config)

    if args.plugins:
        plugin_names = args.plugins
    else:
        plugin_names = [name for name, pc in config.plugins.items() if pc.enabled]

    agent = create_agent(args.agent, config.agent.config)
    orch_config = config.orchestrator
    orch_config.storage["output_dir"] = args.output

    orchestrator = EvaluationOrchestrator(orch_config)
    plugin_configs = {
        name: {**pc.config, "_config_dir": config.config_dir}
        for name, pc in config.plugins.items()
    }
    report = orchestrator.run_evaluation(agent, plugin_names, config.eval_config, plugin_configs)

    generator = ReportGenerator(args.output)
    generated = generator.generate(report, config.report.get("formats", ["json", "html", "markdown"]))

    print("\nEvaluation complete!")
    print(f"  Overall Score: {report.summary.get('overall_score', 0):.3f}")
    print(f"  Pass Rate: {report.summary.get('pass_rate', 0):.1%}")
    print("  Reports generated:")
    for fmt, path in generated.items():
        print(f"    {fmt}: {path}")


def cmd_list(args: argparse.Namespace) -> None:

    plugins = PluginRegistry.list_plugins()

    if args.json:
        print(json.dumps(plugins, indent=2))
    else:
        print(f"{'Plugin Name':<20} {'Version':<8} {'Type':<15} {'Dimensions':<40}")
        print("-" * 83)
        for name, info in plugins.items():
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


def create_agent(agent_str: str, config: Dict[str, Any]) -> AgentUnderTest:
    if agent_str.startswith("openai:"):
        model = agent_str.split(":", 1)[1]
        cfg = {k: v for k, v in config.items() if k != "model"}
        return OpenAIAgent(model=model, **cfg)
    elif ":" in agent_str:
        return CallableAgent.from_module(agent_str, config)
    else:
        raise ValueError(f"Invalid agent spec: '{agent_str}'. Use 'module:Class' or 'openai:model_name'")


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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
