"""Core evaluation orchestrator."""

import logging
import time
import uuid
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from agent_eval.plugins.base import BasePlugin, EvalContext, EvalResult, PluginRegistry
from agent_eval.orchestrator.agent import AgentUnderTest
from agent_eval.orchestrator.task_queue import TaskQueue
from agent_eval.orchestrator.result_store import ResultStore, EvaluationReport
from agent_eval.orchestrator.hooks import HookManager


class EvaluationOrchestrator:
    """Core orchestrator for running evaluations."""

    def __init__(self, config: Any = None):
        from agent_eval.config import OrchestratorConfig
        self.config = config or OrchestratorConfig()
        self.logger = logging.getLogger("agent_eval")
        self.task_queue = TaskQueue({"backend": self.config.queue_backend})
        self.result_store = ResultStore(self.config.storage)
        self.hooks = HookManager()
        self._setup_logging()

    def _setup_logging(self) -> None:
        level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    def run_evaluation(
        self,
        agent: AgentUnderTest,
        plugin_names: List[str],
        eval_config: Dict[str, Any] = None,
        plugin_configs: Dict[str, Dict[str, Any]] = None,
    ) -> EvaluationReport:
        """Run a complete evaluation pipeline."""
        eval_config = eval_config or {}
        plugin_configs = plugin_configs or {}
        run_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        context = EvalContext(
            agent_under_test=agent,
            task_config=eval_config,
            environment=None,
            metadata={
                "run_id": run_id,
                "timestamp": timestamp,
                "agent_name": agent.name,
                "agent_version": agent.version,
            },
            run_id=run_id,
            timestamp=timestamp,
        )

        self.hooks.trigger("evaluation_start", context)
        self.logger.info(f"Starting evaluation run {run_id} with plugins: {plugin_names}")

        start_time = time.time()

        plugins = []
        try:
            plugins = self._init_plugins(plugin_names, plugin_configs)
            all_results = self._execute_plugins(plugins, context)
            report = self._generate_report(run_id, timestamp, agent, context, all_results, plugins)

            elapsed = time.time() - start_time
            self.logger.info(f"Evaluation completed in {elapsed:.2f}s. Score: {report.summary.get('overall_score', 0):.3f}")

            saved_path = self.result_store.save(report)
            self.logger.info(f"Report saved: {saved_path}")

            self.hooks.trigger("evaluation_complete", report)
            return report
        finally:
            self._teardown_plugins(plugins)

    def _init_plugins(self, plugin_names: List[str], eval_config: Dict) -> List[BasePlugin]:
        plugins = []
        for name in plugin_names:
            try:
                plugin = PluginRegistry.get(name)
                plugin_config = eval_config.get(name, {})
                plugin.setup(plugin_config)
                plugins.append(plugin)
                self.logger.info(f"Plugin '{name}' initialized")
                self.hooks.trigger("plugin_setup", plugin)
            except Exception as e:
                self.logger.error(f"Failed to initialize plugin '{name}': {e}")
                raise
        return plugins

    def _execute_plugins(
        self, plugins: List[BasePlugin], context: EvalContext
    ) -> Dict[str, List[EvalResult]]:
        all_results: Dict[str, List[EvalResult]] = {}

        for plugin in plugins:
            self.logger.info(f"Generating tasks for plugin '{plugin.name}'...")
            tasks = plugin.generate_tasks(context)
            self.hooks.trigger("task_generated", plugin, tasks)
            self.logger.info(f"Generated {len(tasks)} tasks for '{plugin.name}'")

            task_ids = self.task_queue.enqueue_batch(
                tasks, priority=context.task_config.get("priority", "normal")
            )

            plugin_results = []
            max_workers = self.config.max_workers

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for task_id in task_ids:
                    task = self.task_queue.get(task_id)
                    future = executor.submit(
                        self._execute_single_task, plugin, task.data, context
                    )
                    futures[future] = task_id

                for future in as_completed(futures):
                    task_id = futures[future]
                    try:
                        result = future.result()
                        plugin_results.append(result)
                        self.task_queue.complete(task_id, result)
                        self.hooks.trigger("task_complete", task_id, result)
                        self.logger.debug(f"Task {task_id} completed: {result.score:.3f}")
                    except Exception as e:
                        plugin_results.append(EvalResult(
                            plugin_name=plugin.name,
                            evaluation_type=plugin.evaluation_type,
                            score=0.0,
                            raw_score={"error": str(e)},
                            details={},
                            artifacts=[],
                            passed=False,
                            execution_time_ms=0,
                            task_id=task_id,
                            error=str(e),
                        ))
                        self.task_queue.fail(task_id, str(e))
                        self.hooks.trigger("task_failed", task_id, e)
                        self.logger.error(f"Task {task_id} failed: {e}")

            all_results[plugin.name] = plugin_results
            self.logger.info(f"Plugin '{plugin.name}': {len(plugin_results)} tasks evaluated")

        return all_results

    def _execute_single_task(
        self, plugin: BasePlugin, task: Dict[str, Any], context: EvalContext
    ) -> EvalResult:
        self.hooks.trigger("task_execute", plugin, task)
        output = plugin.execute_task(task, context)
        self.hooks.trigger("task_evaluate", plugin, task, output)
        return plugin.evaluate(task, output, context)

    def _generate_report(
        self,
        run_id: str,
        timestamp: str,
        agent: AgentUnderTest,
        context: EvalContext,
        all_results: Dict[str, List[EvalResult]],
        plugins: List[BasePlugin],
    ) -> EvaluationReport:
        plugin_results_summary = {}
        dimension_scores: Dict[str, List[float]] = {}
        total_tasks = 0
        total_passed = 0
        total_score = 0.0
        all_task_scores: List[float] = []

        for plugin in plugins:
            results = all_results.get(plugin.name, [])
            if not results:
                continue

            passed = sum(1 for r in results if r.passed)
            scores = [r.score for r in results]
            avg_score = sum(scores) / len(scores) if scores else 0.0

            plugin_results_summary[plugin.name] = {
                "score": avg_score,
                "passed": passed,
                "failed": len(results) - passed,
                "total": len(results),
                "pass_rate": passed / len(results) if results else 0.0,
                "type": plugin.evaluation_type.value,
            }

            total_tasks += len(results)
            total_passed += passed
            total_score += avg_score
            all_task_scores.extend(scores)

            # Per-task dimension scores, with fallback to plugin-level dims
            for result in results:
                if result.dimension_scores:
                    for dim, score in result.dimension_scores.items():
                        dimension_scores.setdefault(dim, []).append(score)
                else:
                    for dim in plugin.supported_dimensions:
                        dimension_scores.setdefault(dim, []).append(result.score)

        macro_score = total_score / len(plugins) if plugins else 0.0
        micro_score = sum(all_task_scores) / len(all_task_scores) if all_task_scores else 0.0

        summary = {
            "overall_score": micro_score,
            "macro_score": macro_score,
            "micro_score": micro_score,
            "total_tasks": total_tasks,
            "total_passed": total_passed,
            "total_failed": total_tasks - total_passed,
            "pass_rate": total_passed / total_tasks if total_tasks else 0.0,
            "dimensions": {
                dim: sum(scores) / len(scores)
                for dim, scores in dimension_scores.items()
            },
            "num_plugins": len(plugins),
        }

        task_results = {
            plugin_name: [self._serialize_eval_result(result) for result in results]
            for plugin_name, results in all_results.items()
        }

        return EvaluationReport(
            run_id=run_id,
            timestamp=timestamp,
            agent_name=agent.name,
            agent_version=agent.version,
            summary=summary,
            plugin_results=plugin_results_summary,
            metadata=context.metadata,
            task_results=task_results,
        )

    def _serialize_eval_result(self, result: EvalResult) -> Dict[str, Any]:
        return {
            "plugin_name": result.plugin_name,
            "evaluation_type": result.evaluation_type.value,
            "score": result.score,
            "raw_score": result.raw_score,
            "details": result.details,
            "artifacts": result.artifacts,
            "passed": result.passed,
            "execution_time_ms": result.execution_time_ms,
            "task_id": result.task_id,
            "error": result.error,
            "dimension_scores": result.dimension_scores,
        }

    def _teardown_plugins(self, plugins: List[BasePlugin]) -> None:
        for plugin in plugins:
            try:
                plugin.teardown()
                self.hooks.trigger("plugin_teardown", plugin)
            except Exception as e:
                self.logger.warning(f"Plugin '{plugin.name}' teardown failed: {e}")