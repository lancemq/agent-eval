"""Plugins package - auto-discovers and registers built-in plugins."""

from agent_eval.plugins.base import (
    BasePlugin, EvaluationType, EvalContext, EvalResult,
    register_plugin, PluginRegistry, discover_entry_point_plugins,
)

# Import built-in plugins to trigger registration
from agent_eval.plugins.benchmark import mmlu_plugin, humaneval_plugin, gsm8k_plugin
from agent_eval.plugins.dynamic import tool_use_plugin, multi_turn_plugin, coding_plugin
from agent_eval.plugins.adversarial import jailbreak_plugin, injection_plugin, bias_plugin

# Discover third-party plugins via setuptools entry points
discover_entry_point_plugins()

__all__ = [
    "BasePlugin",
    "EvaluationType",
    "EvalContext",
    "EvalResult",
    "register_plugin",
    "PluginRegistry",
    "discover_entry_point_plugins",
    "mmlu_plugin",
    "humaneval_plugin",
    "gsm8k_plugin",
    "tool_use_plugin",
    "multi_turn_plugin",
    "coding_plugin",
    "jailbreak_plugin",
    "injection_plugin",
    "bias_plugin",
]