"""Evaluators package - auto-discovers and registers built-in evaluators."""

from agent_eval.evaluators.base import (
    BaseEvaluator, EvaluationType, EvalContext, EvalResult,
    register_evaluator, EvaluatorRegistry, discover_entry_point_evaluators,
)

# Import built-in evaluators to trigger registration
from agent_eval.evaluators.benchmark import mmlu_plugin, humaneval_plugin, gsm8k_plugin
from agent_eval.evaluators.dynamic import tool_use_plugin, multi_turn_plugin, coding_plugin
from agent_eval.evaluators.adversarial import jailbreak_plugin, injection_plugin, bias_plugin
from agent_eval.evaluators import custom_eval_plugin

# Discover third-party evaluators via setuptools entry points
discover_entry_point_evaluators()

__all__ = [
    "BaseEvaluator",
    "EvaluationType",
    "EvalContext",
    "EvalResult",
    "register_evaluator",
    "EvaluatorRegistry",
    "discover_entry_point_evaluators",
    "mmlu_plugin",
    "humaneval_plugin",
    "gsm8k_plugin",
    "tool_use_plugin",
    "multi_turn_plugin",
    "coding_plugin",
    "jailbreak_plugin",
    "injection_plugin",
    "bias_plugin",
    "custom_eval_plugin",
]