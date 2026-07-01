"""Base classes for evaluation evaluators."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type
from enum import Enum
import threading


class EvaluationType(Enum):
    """Types of evaluation supported."""
    BENCHMARK = "benchmark"
    DYNAMIC = "dynamic"
    ADVERSARIAL = "adversarial"
    CUSTOM = "custom"


@dataclass
class Score:
    """A single scoring result (Braintrust-aligned).

    Each scorer applied to a task produces one ``Score``. An ``EvalResult``
    aggregates one or more ``Score`` objects alongside execution metadata.
    """
    name: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    dimension: Optional[str] = None


@dataclass
class EvalContext:
    """Evaluation context passed through the entire pipeline."""
    agent_under_test: Any
    task_config: Dict[str, Any]
    environment: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    run_id: str = ""
    timestamp: str = ""
    workspace: str = ""


@dataclass
class EvalResult:
    """Unified evaluation result format.

    Carries the aggregated ``score`` plus per-scorer ``scores`` for
    fine-grained analysis. ``evaluator_name`` identifies which evaluator
    produced this result.
    """
    evaluator_name: str
    evaluation_type: EvaluationType
    score: float
    raw_score: Any
    details: Dict[str, Any]
    artifacts: List[Any]
    passed: bool
    execution_time_ms: int
    task_id: str = ""
    error: Optional[str] = None
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    scores: List[Score] = field(default_factory=list)


class BaseEvaluator(ABC):
    """Base class for all evaluation evaluators."""

    name: str = ""
    version: str = "1.0"
    evaluation_type: EvaluationType = EvaluationType.CUSTOM
    supported_dimensions: List[str] = []
    description: str = ""

    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._initialized = False

    @abstractmethod
    def setup(self, config: Dict[str, Any]) -> None:
        """Initialize evaluator: load datasets, connect environments, configure judges."""
        self._config = config
        self._initialized = True

    @abstractmethod
    def generate_tasks(self, context: EvalContext) -> List[Dict[str, Any]]:
        """Generate evaluation tasks. Returns list of task dictionaries."""
        pass

    @abstractmethod
    def execute_task(self, task: Dict[str, Any], context: EvalContext) -> Any:
        """Execute a single task. Returns agent output."""
        pass

    @abstractmethod
    def evaluate(self, task: Dict[str, Any], output: Any, context: EvalContext) -> EvalResult:
        """Evaluate task output. Returns EvalResult."""
        pass

    def teardown(self) -> None:
        """Cleanup resources."""
        pass

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self._config.get(key, default)

    @property
    def is_initialized(self) -> bool:
        return self._initialized


class EvaluatorRegistry:
    """Registry for evaluator discovery and management."""

    _evaluators: Dict[str, Type[BaseEvaluator]] = {}
    _instances: Dict[str, BaseEvaluator] = {}
    _lock = threading.Lock()

    @classmethod
    def register(cls, evaluator_class: Type[BaseEvaluator]) -> Type[BaseEvaluator]:
        """Register an evaluator class."""
        if not evaluator_class.name:
            raise ValueError(f"Evaluator {evaluator_class.__name__} must have a name")
        with cls._lock:
            if evaluator_class.name in cls._evaluators:
                raise ValueError(f"Evaluator '{evaluator_class.name}' already registered")
            cls._evaluators[evaluator_class.name] = evaluator_class
        return evaluator_class

    @classmethod
    def get(cls, name: str) -> BaseEvaluator:
        """Create an evaluator instance."""
        with cls._lock:
            if name not in cls._evaluators:
                raise ValueError(f"Evaluator '{name}' not found. Available: {list(cls._evaluators.keys())}")
            return cls._evaluators[name]()

    @classmethod
    def get_class(cls, name: str) -> Type[BaseEvaluator]:
        """Get evaluator class without instantiating."""
        if name not in cls._evaluators:
            raise ValueError(f"Evaluator '{name}' not found")
        return cls._evaluators[name]

    @classmethod
    def list_evaluators(cls) -> Dict[str, Dict[str, Any]]:
        """List all registered evaluators with metadata."""
        return {
            name: {
                "version": evaluator.version,
                "type": evaluator.evaluation_type.value,
                "dimensions": evaluator.supported_dimensions,
                "description": evaluator.description,
            }
            for name, evaluator in cls._evaluators.items()
        }

    @classmethod
    def clear(cls) -> None:
        """Clear registry (mainly for testing)."""
        with cls._lock:
            cls._evaluators.clear()


def register_evaluator(evaluator_class: Type[BaseEvaluator]) -> Type[BaseEvaluator]:
    """Decorator to register an evaluator."""
    return EvaluatorRegistry.register(evaluator_class)


def discover_entry_point_evaluators() -> Dict[str, str]:
    """Discover third-party evaluators registered via setuptools entry points.

    Evaluators can register themselves in pyproject.toml:

        [project.entry-points."agent_eval.evaluators"]
        my_evaluator = "my_package:MyEvaluator"

    Returns:
        Dict mapping evaluator name to discovered module:class string.
    """
    discovered: Dict[str, str] = {}
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return discovered

    try:
        eps = entry_points()
        # Python 3.12+ returns Selectable
        if hasattr(eps, "select"):
            evaluator_eps = eps.select(group="agent_eval.evaluators")
        else:
            evaluator_eps = eps.get("agent_eval.evaluators", [])
    except Exception:
        return discovered

    for ep in evaluator_eps:
        try:
            evaluator_cls = ep.load()
            if issubclass(evaluator_cls, BaseEvaluator) and evaluator_cls.name:
                EvaluatorRegistry.register(evaluator_cls)
                discovered[evaluator_cls.name] = f"{ep.value}"
            else:
                import logging
                logging.getLogger("agent_eval.evaluators").warning(
                    f"Entry point '{ep.name}' -> {ep.value} is not a valid BaseEvaluator"
                )
        except Exception as e:
            import logging
            logging.getLogger("agent_eval.evaluators").warning(
                f"Failed to load entry point '{ep.name}': {e}"
            )

    return discovered
