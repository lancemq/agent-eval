"""Tool registry for sandbox execution."""

from typing import Any, Callable, Dict


class ToolRegistry:
    """Registry for tools available in sandbox environments."""

    _tools: Dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str, func: Callable) -> None:
        cls._tools[name] = func

    @classmethod
    def call(cls, name: str, **kwargs) -> Any:
        if name not in cls._tools:
            raise ValueError(f"Unknown tool: {name}. Available: {list(cls._tools.keys())}")
        return cls._tools[name](**kwargs)

    @classmethod
    def list_tools(cls) -> Dict[str, str]:
        return {name: getattr(func, "__doc__", "") for name, func in cls._tools.items()}


def tool(name: str):
    """Decorator to register a tool."""
    def decorator(func):
        ToolRegistry.register(name, func)
        return func
    return decorator


@tool("calculator")
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression."""
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"Error: {e}"


@tool("web_search")
def web_search(query: str) -> str:
    """Simulate a web search."""
    return f"Simulated search results for: {query}"


@tool("weather_api")
def weather_api(location: str) -> str:
    """Get weather for a location."""
    return f"Simulated weather for {location}: 72°F, Sunny"


@tool("file_write")
def file_write(path: str, content: str) -> str:
    """Write content to a file."""
    with open(path, "w") as f:
        f.write(content)
    return f"Written to {path}"


@tool("file_read")
def file_read(path: str) -> str:
    """Read content from a file."""
    with open(path) as f:
        return f.read()


@tool("python_repl")
def python_repl(code: str) -> str:
    """Execute Python code and return result."""
    try:
        local_vars = {}
        exec(code, {"__builtins__": __builtins__}, local_vars)
        result = local_vars.get("result", local_vars.get("output", None))
        return str(result) if result is not None else "Executed successfully"
    except Exception as e:
        return f"Error: {e}"