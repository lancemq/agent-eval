"""Hook system for evaluation lifecycle events."""

from typing import Any, Callable, Dict, List


class HookManager:
    """Manages lifecycle hooks for the evaluation pipeline."""

    def __init__(self):
        self._hooks: Dict[str, List[Callable]] = {
            "evaluation_start": [],
            "evaluation_complete": [],
            "plugin_setup": [],
            "plugin_teardown": [],
            "task_generated": [],
            "task_execute": [],
            "task_complete": [],
            "task_failed": [],
            "task_evaluate": [],
        }

    def register(self, event: str, callback: Callable) -> None:
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(callback)

    def unregister(self, event: str, callback: Callable) -> None:
        if event in self._hooks:
            self._hooks[event] = [h for h in self._hooks[event] if h is not callback]

    def trigger(self, event: str, *args, **kwargs) -> List[Any]:
        results = []
        for hook in self._hooks.get(event, []):
            try:
                result = hook(*args, **kwargs)
                results.append(result)
            except Exception as e:
                results.append(e)
        return results

    def clear(self) -> None:
        for hooks in self._hooks.values():
            hooks.clear()

    def list_events(self) -> List[str]:
        return list(self._hooks.keys())