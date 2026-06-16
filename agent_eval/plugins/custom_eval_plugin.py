"""Configuration-driven custom evaluation plugin."""

import csv
import json
import os
import statistics
import time
from string import Formatter
from typing import Any, Dict, List

from agent_eval.plugins.base import BasePlugin, EvalContext, EvalResult, EvaluationType, register_plugin
from agent_eval.scorers.factory import ScorerFactory


ALLOWED_TASK_SOURCE_TYPES = {"inline", "file"}
ALLOWED_FILE_FORMATS = {"json", "yaml", "yml", "csv"}
ALLOWED_PROMPT_MODES = {"generate", "chat"}
ALLOWED_AGGREGATIONS = {"weighted", "mean", "median", "min", "max"}


@register_plugin
class CustomEvalPlugin(BasePlugin):
    name = "custom_eval"
    version = "1.0"
    evaluation_type = EvaluationType.CUSTOM
    supported_dimensions = ["custom"]
    description = "Configuration-driven custom evaluation with task data, prompt templates, and scorers"

    def __init__(self):
        super().__init__()
        self.evaluations: List[Dict[str, Any]] = []

    def setup(self, config: Dict[str, Any]) -> None:
        super().setup(config)
        errors = validate_custom_eval_config(config)
        if errors:
            messages = "; ".join(error["message"] for error in errors)
            raise ValueError(f"Invalid custom_eval config: {messages}")
        self.evaluations = config.get("evaluations", [])

    def generate_tasks(self, context: EvalContext) -> List[Dict[str, Any]]:
        tasks = []
        for evaluation in self.evaluations:
            eval_id = evaluation["id"]
            task_items = _load_task_items(evaluation["task_source"])
            for index, item in enumerate(task_items):
                task_id = item.get("task_id", f"task_{index}")
                tasks.append({
                    **item,
                    "task_id": f"{eval_id}:{task_id}",
                    "custom_eval_id": eval_id,
                    "custom_eval_name": evaluation.get("name", eval_id),
                    "custom_eval_description": evaluation.get("description", ""),
                    "prompt": evaluation["prompt"],
                    "scoring": evaluation["scoring"],
                    "dimensions": evaluation.get("dimensions", ["custom"]),
                    "metadata": evaluation.get("metadata", {}),
                })
        return tasks

    def execute_task(self, task: Dict[str, Any], context: EvalContext) -> Dict[str, Any]:
        start = time.time()
        prompt_config = task["prompt"]
        mode = prompt_config.get("mode", "generate")
        if mode == "chat":
            messages = [
                {"role": message["role"], "content": _render_template(message["content"], task)}
                for message in prompt_config.get("messages", [])
            ]
            response = context.agent_under_test.chat(messages)
            rendered_prompt = messages
        else:
            rendered_prompt = _render_template(prompt_config["template"], task)
            response = context.agent_under_test.generate(rendered_prompt)

        return {
            "response": response,
            "rendered_prompt": rendered_prompt,
            "mode": mode,
            "execution_time_ms": int((time.time() - start) * 1000),
        }

    def evaluate(self, task: Dict[str, Any], output: Dict[str, Any], context: EvalContext) -> EvalResult:
        start = time.time()
        scoring = task["scoring"]
        scorer_results = []
        dimension_scores: Dict[str, float] = {}

        for scorer_config in scoring.get("scorers", []):
            scorer = ScorerFactory.create({
                "type": scorer_config["type"],
                **scorer_config.get("params", {}),
            })
            result = scorer.score(
                output["response"],
                expected=task.get("expected"),
                expected_output=task.get("expected"),
                input=task.get("input"),
                task=task,
                context=context,
                rendered_prompt=output["rendered_prompt"],
            )
            weight = float(scorer_config.get("weight", 1.0))
            dimension = scorer_config.get("dimension")
            result_dict = result.to_dict()
            result_dict.update({
                "id": scorer_config.get("id", scorer_config["type"]),
                "type": scorer_config["type"],
                "weight": weight,
                "dimension": dimension,
            })
            scorer_results.append(result_dict)
            if dimension:
                dimension_scores[dimension] = result.score

        score = _aggregate_scores(scorer_results, scoring.get("aggregation", "weighted"))
        threshold = float(scoring.get("threshold", 0.7))
        passed = score >= threshold
        exec_time = output.get("execution_time_ms", 0) + int((time.time() - start) * 1000)

        return EvalResult(
            plugin_name=self.name,
            evaluation_type=self.evaluation_type,
            score=score,
            raw_score={"scorers": scorer_results, "aggregation": scoring.get("aggregation", "weighted")},
            details={
                "custom_eval_id": task["custom_eval_id"],
                "custom_eval_name": task["custom_eval_name"],
                "input": task.get("input"),
                "expected": task.get("expected"),
                "response": output["response"],
                "rendered_prompt": output["rendered_prompt"],
                "threshold": threshold,
            },
            artifacts=[output["response"]],
            passed=passed,
            execution_time_ms=exec_time,
            task_id=task["task_id"],
            dimension_scores=dimension_scores or {dimension: score for dimension in task.get("dimensions", ["custom"])},
        )


def validate_custom_eval_config(config: Dict[str, Any], workspace: str = None) -> List[Dict[str, str]]:
    errors = []
    evaluations = config.get("evaluations", [])
    if not isinstance(evaluations, list) or not evaluations:
        return [{"field": "plugins.custom_eval.evaluations", "message": "evaluations must be a non-empty list"}]

    for eval_index, evaluation in enumerate(evaluations):
        prefix = f"plugins.custom_eval.evaluations[{eval_index}]"
        if not evaluation.get("id"):
            errors.append({"field": f"{prefix}.id", "message": "id is required"})

        task_source = evaluation.get("task_source")
        if not isinstance(task_source, dict):
            errors.append({"field": f"{prefix}.task_source", "message": "task_source is required"})
        else:
            source_type = task_source.get("type", "inline")
            if source_type not in ALLOWED_TASK_SOURCE_TYPES:
                errors.append({"field": f"{prefix}.task_source.type", "message": f"unsupported task source type: {source_type}"})
            if source_type == "inline" and not isinstance(task_source.get("items"), list):
                errors.append({"field": f"{prefix}.task_source.items", "message": "inline task_source requires items list"})
            if source_type == "file":
                path = task_source.get("path")
                fmt = task_source.get("format", _infer_format(path or ""))
                if not path:
                    errors.append({"field": f"{prefix}.task_source.path", "message": "file task_source requires path"})
                elif workspace:
                    abs_path = os.path.abspath(path)
                    if os.path.commonpath([os.path.abspath(workspace), abs_path]) != os.path.abspath(workspace):
                        errors.append({"field": f"{prefix}.task_source.path", "message": "path is outside the configured workspace"})
                if fmt not in ALLOWED_FILE_FORMATS:
                    errors.append({"field": f"{prefix}.task_source.format", "message": f"unsupported file format: {fmt}"})

        prompt = evaluation.get("prompt")
        if not isinstance(prompt, dict):
            errors.append({"field": f"{prefix}.prompt", "message": "prompt is required"})
        else:
            mode = prompt.get("mode", "generate")
            if mode not in ALLOWED_PROMPT_MODES:
                errors.append({"field": f"{prefix}.prompt.mode", "message": f"unsupported prompt mode: {mode}"})
            if mode == "generate" and not prompt.get("template"):
                errors.append({"field": f"{prefix}.prompt.template", "message": "generate mode requires template"})
            if mode == "chat" and not isinstance(prompt.get("messages"), list):
                errors.append({"field": f"{prefix}.prompt.messages", "message": "chat mode requires messages list"})

        scoring = evaluation.get("scoring")
        if not isinstance(scoring, dict):
            errors.append({"field": f"{prefix}.scoring", "message": "scoring is required"})
        else:
            aggregation = scoring.get("aggregation", "weighted")
            if aggregation not in ALLOWED_AGGREGATIONS:
                errors.append({"field": f"{prefix}.scoring.aggregation", "message": f"unsupported aggregation: {aggregation}"})
            threshold = scoring.get("threshold", 0.7)
            if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
                errors.append({"field": f"{prefix}.scoring.threshold", "message": "threshold must be between 0 and 1"})
            scorers = scoring.get("scorers", [])
            if not isinstance(scorers, list) or not scorers:
                errors.append({"field": f"{prefix}.scoring.scorers", "message": "scoring requires non-empty scorers list"})
            else:
                for scorer_index, scorer_config in enumerate(scorers):
                    scorer_prefix = f"{prefix}.scoring.scorers[{scorer_index}]"
                    scorer_type = scorer_config.get("type")
                    if not scorer_type:
                        errors.append({"field": f"{scorer_prefix}.type", "message": "scorer type is required"})
                    else:
                        try:
                            ScorerFactory.create({"type": scorer_type, **scorer_config.get("params", {})})
                        except Exception as exc:
                            errors.append({"field": f"{scorer_prefix}.type", "message": str(exc)})
                    weight = scorer_config.get("weight", 1.0)
                    if not isinstance(weight, (int, float)) or weight < 0:
                        errors.append({"field": f"{scorer_prefix}.weight", "message": "weight must be non-negative"})
    return errors


def _load_task_items(task_source: Dict[str, Any]) -> List[Dict[str, Any]]:
    source_type = task_source.get("type", "inline")
    if source_type == "inline":
        return task_source.get("items", [])

    path = task_source["path"]
    fmt = task_source.get("format", _infer_format(path))
    if fmt == "json":
        with open(path) as file:
            data = json.load(file)
    elif fmt in {"yaml", "yml"}:
        import yaml
        with open(path) as file:
            data = yaml.safe_load(file) or []
    elif fmt == "csv":
        with open(path, newline="") as file:
            data = list(csv.DictReader(file))
    else:
        raise ValueError(f"Unsupported task file format: {fmt}")

    if isinstance(data, dict):
        return data.get("tasks", data.get("items", []))
    return data


def _render_template(template: str, values: Dict[str, Any]) -> str:
    fields = {field for _, field, _, _ in Formatter().parse(template) if field}
    missing = [field for field in fields if field not in values]
    if missing:
        raise KeyError(f"Missing template fields: {missing}")
    return template.format(**values)


def _aggregate_scores(results: List[Dict[str, Any]], aggregation: str) -> float:
    scores = [float(result["score"]) for result in results]
    if not scores:
        return 0.0
    if aggregation == "mean":
        return sum(scores) / len(scores)
    if aggregation == "median":
        return statistics.median(scores)
    if aggregation == "min":
        return min(scores)
    if aggregation == "max":
        return max(scores)

    total_weight = sum(float(result.get("weight", 1.0)) for result in results)
    if total_weight <= 0:
        return sum(scores) / len(scores)
    return sum(float(result["score"]) * float(result.get("weight", 1.0)) for result in results) / total_weight


def _infer_format(path: str) -> str:
    return path.rsplit(".", 1)[-1].lower() if "." in path else "json"
