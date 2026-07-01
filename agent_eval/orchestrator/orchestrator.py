"""Core evaluation orchestrator."""

import logging
import os
import time
import uuid
import threading
from datetime import datetime, timezone
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Any, Dict, List, Tuple

from agent_eval.evaluators.base import BaseEvaluator, EvalContext, EvalResult, EvaluatorRegistry
from agent_eval.orchestrator.agent import AgentUnderTest
from agent_eval.orchestrator.task_queue import TaskQueue
from agent_eval.orchestrator.result_store import ResultStore, EvaluationReport
from agent_eval.orchestrator.hooks import HookManager


class EvaluationOrchestrator:
    """Core orchestrator for running evaluations."""

    def __init__(self, config: Any = None, workspace: str = None):
        from agent_eval.config import OrchestratorConfig
        self.config = config or OrchestratorConfig()
        self.logger = logging.getLogger("agent_eval")
        self.workspace = workspace or os.getcwd()
        self.task_queue = TaskQueue({"backend": self.config.queue_backend})
        self.result_store = ResultStore(self.config.storage)
        self.hooks = HookManager()
        self._agent_semaphore = (
            threading.Semaphore(self.config.agent_concurrency)
            if getattr(self.config, "agent_concurrency", 0)
            else None
        )
        self._cancelled = False
        self._progress_callbacks: List = []
        self._setup_logging()

    @property
    def is_cancelled(self) -> bool:
        """Check if evaluation has been cancelled."""
        return self._cancelled

    def cancel(self) -> None:
        """Request cancellation of the running evaluation."""
        self._cancelled = True
        self.logger.info("Evaluation cancellation requested")

    def on_progress(self, callback) -> None:
        """Register a progress callback.

        Callback signature: callback(completed: int, total: int, current_result: Optional[EvalResult])
        """
        self._progress_callbacks.append(callback)

    def _notify_progress(self, completed: int, total: int, result=None) -> None:
        """Notify all registered progress callbacks."""
        for cb in self._progress_callbacks:
            try:
                cb(completed, total, result)
            except Exception as e:
                self.logger.warning(f"Progress callback error: {e}")

    def _setup_logging(self) -> None:
        level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    def run_evaluation(
        self,
        agent: AgentUnderTest,
        evaluator_names: List[str],
        eval_config: Dict[str, Any] = None,
        evaluator_configs: Dict[str, Dict[str, Any]] = None,
    ) -> EvaluationReport:
        """Run a complete evaluation pipeline."""
        eval_config = eval_config or {}
        evaluator_configs = evaluator_configs or {}
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
            workspace=self.workspace,
        )

        self.hooks.trigger("evaluation_start", context)
        self.logger.info(f"Starting evaluation run {run_id} with evaluators: {evaluator_names}")

        start_time = time.time()

        evaluators = []
        try:
            evaluators = self._init_evaluators(evaluator_names, evaluator_configs)
            all_results = self._execute_evaluators(evaluators, context)
            report = self._generate_report(run_id, timestamp, agent, context, all_results, evaluators)

            elapsed = time.time() - start_time
            self.logger.info(f"Evaluation completed in {elapsed:.2f}s. Score: {report.summary.get('overall_score', 0):.3f}")

            saved_path = self.result_store.save(report)
            self.logger.info(f"Report saved: {saved_path}")

            self.hooks.trigger("evaluation_complete", report)
            return report
        finally:
            self._teardown_evaluators(evaluators)

    def _init_evaluators(self, evaluator_names: List[str], eval_config: Dict) -> List[BaseEvaluator]:
        evaluators = []
        for name in evaluator_names:
            try:
                evaluator = EvaluatorRegistry.get(name)
                evaluator_config = eval_config.get(name, {})
                evaluator.setup(evaluator_config)
                evaluators.append(evaluator)
                self.logger.info(f"Evaluator '{name}' initialized")
                self.hooks.trigger("evaluator_setup", evaluator)
            except Exception as e:
                self.logger.error(f"Failed to initialize evaluator '{name}': {e}")
                raise
        return evaluators

    def _execute_evaluators(
        self, evaluators: List[BaseEvaluator], context: EvalContext
    ) -> Dict[str, List[EvalResult]]:
        all_results: Dict[str, List[EvalResult]] = {}

        for evaluator in evaluators:
            if self._cancelled:
                self.logger.warning("Evaluation cancelled, skipping evaluator '%s'", evaluator.name)
                break

            self.logger.info(f"Generating tasks for evaluator '{evaluator.name}'...")
            tasks = evaluator.generate_tasks(context)
            self.hooks.trigger("task_generated", evaluator, tasks)
            self.logger.info(f"Generated {len(tasks)} tasks for '{evaluator.name}'")

            task_ids = self.task_queue.enqueue_batch(
                tasks, priority=context.task_config.get("priority", "normal")
            )
            for task_id in task_ids:
                task = self.task_queue.get(task_id)
                if task:
                    task.max_retries = getattr(self.config, "max_task_retries", 3)

            # Sort task IDs by priority for execution ordering
            sorted_task_ids = sorted(
                task_ids,
                key=lambda tid: self.task_queue.get(tid) or type("T", (), {"priority": type("P", (), {"value": 0})()})(),
                reverse=True,  # Higher priority first
            )

            evaluator_results = []
            max_workers = self.config.max_workers
            total_tasks = len(sorted_task_ids)
            completed_count = 0

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                # Submit in priority order
                for task_id in sorted_task_ids:
                    if self._cancelled:
                        break
                    task = self.task_queue.get(task_id)
                    if not task:
                        raise ValueError(f"Task {task_id} not found")
                    future = executor.submit(
                        self._execute_single_task,
                        evaluator,
                        task.data,
                        context,
                        task.retries + 1,
                    )
                    futures[future] = task_id

                while futures:
                    if self._cancelled:
                        # Cancel pending futures
                        for f in futures:
                            f.cancel()
                        self.logger.warning("Evaluation cancelled mid-run, %d tasks incomplete", len(futures))
                        break

                    done, _ = wait(futures, return_when=FIRST_COMPLETED)
                    for future in done:
                        task_id = futures.pop(future)
                        try:
                            result, attempt = future.result()
                            evaluator_results.append(result)
                            self.task_queue.complete(task_id, result)
                            self.hooks.trigger("task_complete", task_id, result)
                            completed_count += 1
                            self._notify_progress(completed_count, total_tasks, result)
                            self.logger.debug(f"Task {task_id} completed on attempt {attempt}: {result.score:.3f}")
                        except Exception as e:
                            self.task_queue.fail(task_id, str(e))
                            task = self.task_queue.get(task_id)
                            if task and task.status.value == "pending":
                                self.logger.warning(
                                    f"Task {task_id} failed on attempt {task.retries}: {e}; retrying"
                                )
                                retry_future = executor.submit(
                                    self._execute_single_task,
                                    evaluator,
                                    task.data,
                                    context,
                                    task.retries + 1,
                                )
                                futures[retry_future] = task_id
                            else:
                                attempts = (task.retries + 1) if task else 1
                                evaluator_results.append(self._failure_result(evaluator, task_id, str(e), attempts))
                                self.hooks.trigger("task_failed", task_id, e)
                                self.logger.error(f"Task {task_id} failed after {attempts} attempts: {e}")

            all_results[evaluator.name] = evaluator_results
            self.logger.info(f"Evaluator '{evaluator.name}': {len(evaluator_results)} tasks evaluated")

        return all_results

    def _execute_single_task(
        self, evaluator: BaseEvaluator, task: Dict[str, Any], context: EvalContext, attempt: int = 1
    ) -> Tuple[EvalResult, int]:
        self.hooks.trigger("task_execute", evaluator, task)
        if self._agent_semaphore:
            with self._agent_semaphore:
                output = evaluator.execute_task(task, context)
        else:
            output = evaluator.execute_task(task, context)
        self.hooks.trigger("task_evaluate", evaluator, task, output)
        result = evaluator.evaluate(task, output, context)
        result.details.setdefault("attempt", attempt)
        return result, attempt

    def _failure_result(self, evaluator: BaseEvaluator, task_id: str, error: str, attempts: int) -> EvalResult:
        return EvalResult(
            evaluator_name=evaluator.name,
            evaluation_type=evaluator.evaluation_type,
            score=0.0,
            raw_score={"error": error, "attempts": attempts},
            details={"attempts": attempts},
            artifacts=[],
            passed=False,
            execution_time_ms=0,
            task_id=task_id,
            error=error,
        )

    def _generate_report(
        self,
        run_id: str,
        timestamp: str,
        agent: AgentUnderTest,
        context: EvalContext,
        all_results: Dict[str, List[EvalResult]],
        evaluators: List[BaseEvaluator],
    ) -> EvaluationReport:
        evaluator_results_summary = {}
        dimension_scores: Dict[str, List[float]] = {}
        total_tasks = 0
        total_passed = 0
        total_score = 0.0
        all_task_scores: List[float] = []

        for evaluator in evaluators:
            results = all_results.get(evaluator.name, [])
            if not results:
                continue

            passed = sum(1 for r in results if r.passed)
            scores = [r.score for r in results]
            avg_score = sum(scores) / len(scores) if scores else 0.0

            evaluator_results_summary[evaluator.name] = {
                "score": avg_score,
                "passed": passed,
                "failed": len(results) - passed,
                "total": len(results),
                "pass_rate": passed / len(results) if results else 0.0,
                "type": evaluator.evaluation_type.value,
            }

            total_tasks += len(results)
            total_passed += passed
            total_score += avg_score
            all_task_scores.extend(scores)

            # Per-task dimension scores, with fallback to evaluator-level dims
            for result in results:
                if result.dimension_scores:
                    for dim, score in result.dimension_scores.items():
                        dimension_scores.setdefault(dim, []).append(score)
                else:
                    for dim in evaluator.supported_dimensions:
                        dimension_scores.setdefault(dim, []).append(result.score)

        macro_score = total_score / len(evaluators) if evaluators else 0.0
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
            "num_evaluators": len(evaluators),
        }

        task_results = {
            evaluator_name: [self._serialize_eval_result(result) for result in results]
            for evaluator_name, results in all_results.items()
        }

        return EvaluationReport(
            run_id=run_id,
            timestamp=timestamp,
            agent_name=agent.name,
            agent_version=agent.version,
            summary=summary,
            evaluator_results=evaluator_results_summary,
            metadata=context.metadata,
            task_results=task_results,
        )

    def _serialize_eval_result(self, result: EvalResult) -> Dict[str, Any]:
        return {
            "evaluator_name": result.evaluator_name,
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

    def _teardown_evaluators(self, evaluators: List[BaseEvaluator]) -> None:
        for evaluator in evaluators:
            try:
                evaluator.teardown()
                self.hooks.trigger("evaluator_teardown", evaluator)
            except Exception as e:
                self.logger.warning(f"Evaluator '{evaluator.name}' teardown failed: {e}")
