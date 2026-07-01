"""Build versioned datasets from trace records.

A thin importer that converts :class:`TraceRecord` objects into dataset rows
via :class:`TaskGenerator`, then persists them through :class:`DatasetStore`.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from agent_eval.trace.schema import TraceRecord
from agent_eval.trace.task_generator import EvalTask, TaskGenerator


class DatasetBuilder:
    """Builds versioned evaluation datasets from traces.

    Usage:
        builder = DatasetBuilder(name="prod_eval_v1")
        builder.from_traces(traces, min_quality=0.5)
        builder.save("./datasets/prod_v1.json")
    """

    def __init__(self, name: str = "unnamed", version: str = "1.0"):
        self.name = name
        self.version = version
        self.tasks: List[EvalTask] = []
        self.metadata: Dict[str, Any] = {
            "name": name,
            "version": version,
            "source_traces": [],
            "stats": {},
        }

    def from_traces(
        self,
        traces: List[TraceRecord],
        min_quality: float = 0.0,
        deduplicate: bool = True,
        filters: Optional[Dict[str, Any]] = None,
        max_tasks: int = 0,
    ) -> "DatasetBuilder":
        """Build dataset from a list of traces."""
        filtered = traces

        if filters:
            filtered = [
                t for t in filtered
                if all(getattr(t, k, None) == v for k, v in filters.items())
            ]

        if min_quality > 0:
            filtered = [t for t in filtered if t.quality_score >= min_quality]

        if deduplicate:
            filtered = self._deduplicate(filtered)

        if max_tasks > 0:
            filtered = filtered[:max_tasks]

        generator = TaskGenerator()
        self.tasks = generator.generate_batch(filtered)
        self.metadata["source_traces"] = [t.trace_id for t in filtered]
        self.metadata["stats"] = self._compute_stats()
        return self

    def from_trace_store(
        self,
        store: Any,
        min_quality: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> "DatasetBuilder":
        """Build from a TraceStore."""
        traces = store.query(filters or {})
        return self.from_traces(traces, min_quality=min_quality, **kwargs)

    @staticmethod
    def _deduplicate(traces: List[TraceRecord]) -> List[TraceRecord]:
        """Remove near-duplicate traces based on input hashing."""
        seen: Dict[str, TraceRecord] = {}
        for t in traces:
            key = hashlib.sha256(t.input.encode()).hexdigest()[:16]
            if key not in seen:
                seen[key] = t
            elif t.quality_score > seen[key].quality_score:
                seen[key] = t
        return list(seen.values())

    def _compute_stats(self) -> Dict[str, Any]:
        if not self.tasks:
            return {}
        type_counts: Dict[str, int] = {}
        all_scorers: List[str] = []
        for task in self.tasks:
            type_counts[task.task_type] = type_counts.get(task.task_type, 0) + 1
            all_scorers.extend(task.scorers)
        return {
            "total_tasks": len(self.tasks),
            "by_type": type_counts,
            "unique_scorers": sorted(set(all_scorers)),
        }

    def save(self, path: str) -> str:
        """Save dataset to JSON file."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        data = {
            "name": self.name,
            "version": self.version,
            "metadata": self.metadata,
            "tasks": [t.to_dict() for t in self.tasks],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    def to_store(self, store: Any) -> Any:
        """Persist this dataset into a :class:`DatasetStore` as a new dataset.

        Returns the created :class:`DatasetRecord`.
        """
        rows = []
        for task in self.tasks:
            item = task.to_dict()
            item["expected"] = item.pop("expected_output", "")
            rows.append(item)
        return store.create(
            name=self.name,
            rows=rows,
            description=self.metadata.get("description", ""),
            source_traces=self.metadata.get("source_traces", []),
        )

    @classmethod
    def load(cls, path: str) -> "DatasetBuilder":
        """Load a saved dataset."""
        with open(path) as f:
            data = json.load(f)
        builder = cls(name=data["name"], version=data.get("version", "1.0"))
        builder.tasks = [EvalTask.from_dict(t) for t in data.get("tasks", [])]
        builder.metadata = data.get("metadata", {})
        return builder

    def export_yaml(self, path: str) -> str:
        """Export as YAML config compatible with agent-eval CLI."""
        lines = [
            f"# Auto-generated dataset: {self.name} v{self.version}",
            f"# Total tasks: {len(self.tasks)}",
            "",
            "evaluators:",
            "  trace_eval:",
            "    enabled: true",
            "    type: custom",
            "    test_cases:",
        ]
        for task in self.tasks:
            lines.append(f"      - id: \"{task.task_id}\"")
            lines.append(f"        type: \"{task.task_type}\"")
            lines.append(f"        input: {task.input!r}")
            if task.expected_output:
                lines.append(f"        expected: {task.expected_output!r}")
            if task.scorers:
                lines.append(f"        scorers: {task.scorers}")
        lines.append("")

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write("\n".join(lines))
        return path
