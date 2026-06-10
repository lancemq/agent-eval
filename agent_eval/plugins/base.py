"""Base classes for evaluation plugins."""

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
class EvalContext:
    """Evaluation context passed through the entire pipeline."""
    agent_under_test: Any
    task_config: Dict[str, Any]
    environment: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    run_id: str = ""
    timestamp: str = ""


@dataclass
class EvalResult:
    """Unified evaluation result format."""
    plugin_name: str
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


class BasePlugin(ABC):
    """Base class for all evaluation plugins."""
    
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
        """Initialize plugin: load datasets, connect environments, configure judges."""
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


class PluginRegistry:
    """Registry for plugin discovery and management."""
    
    _plugins: Dict[str, Type[BasePlugin]] = {}
    _instances: Dict[str, BasePlugin] = {}
    _lock = threading.Lock()
    
    @classmethod
    def register(cls, plugin_class: Type[BasePlugin]) -> Type[BasePlugin]:
        """Register a plugin class."""
        if not plugin_class.name:
            raise ValueError(f"Plugin {plugin_class.__name__} must have a name")
        with cls._lock:
            if plugin_class.name in cls._plugins:
                raise ValueError(f"Plugin '{plugin_class.name}' already registered")
            cls._plugins[plugin_class.name] = plugin_class
        return plugin_class
    
    @classmethod
    def get(cls, name: str) -> BasePlugin:
        """Create a plugin instance."""
        with cls._lock:
            if name not in cls._plugins:
                raise ValueError(f"Plugin '{name}' not found. Available: {list(cls._plugins.keys())}")
            return cls._plugins[name]()
    
    @classmethod
    def get_class(cls, name: str) -> Type[BasePlugin]:
        """Get plugin class without instantiating."""
        if name not in cls._plugins:
            raise ValueError(f"Plugin '{name}' not found")
        return cls._plugins[name]
    
    @classmethod
    def list_plugins(cls) -> Dict[str, Dict[str, Any]]:
        """List all registered plugins with metadata."""
        return {
            name: {
                "version": plugin.version,
                "type": plugin.evaluation_type.value,
                "dimensions": plugin.supported_dimensions,
                "description": plugin.description,
            }
            for name, plugin in cls._plugins.items()
        }
    
    @classmethod
    def clear(cls) -> None:
        """Clear registry (mainly for testing)."""
        with cls._lock:
            cls._plugins.clear()


def register_plugin(plugin_class: Type[BasePlugin]) -> Type[BasePlugin]:
    """Decorator to register a plugin."""
    return PluginRegistry.register(plugin_class)