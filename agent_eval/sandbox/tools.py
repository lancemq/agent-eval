"""Tool registry for sandbox execution."""

import ast
import os
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
        func = cls._tools[name]
        try:
            return func(**kwargs)
        except TypeError as e:
            if "work_dir" not in kwargs:
                raise
            kwargs.pop("work_dir")
            try:
                return func(**kwargs)
            except TypeError:
                raise e

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
        return str(_eval_arithmetic(expression))
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
def file_write(path: str, content: str, work_dir: str = None) -> str:
    """Write content to a file."""
    safe_path = _resolve_sandbox_path(path, work_dir)
    os.makedirs(os.path.dirname(safe_path), exist_ok=True)
    with open(safe_path, "w") as f:
        f.write(content)
    return f"Written to {path}"


@tool("file_read")
def file_read(path: str, work_dir: str = None) -> str:
    """Read content from a file."""
    safe_path = _resolve_sandbox_path(path, work_dir)
    with open(safe_path) as f:
        return f.read()


@tool("python_repl")
def python_repl(code: str) -> str:
    """Execute Python code and return result."""
    try:
        local_vars = {}
        safe_builtins = {
            "abs": abs,
            "all": all,
            "any": any,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "float": float,
            "int": int,
            "len": len,
            "list": list,
            "max": max,
            "min": min,
            "range": range,
            "round": round,
            "set": set,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip,
        }
        exec(code, {"__builtins__": safe_builtins}, local_vars)
        result = local_vars.get("result", local_vars.get("output", None))
        return str(result) if result is not None else "Executed successfully"
    except Exception as e:
        return f"Error: {e}"


def _resolve_sandbox_path(path: str, work_dir: str = None) -> str:
    if not work_dir:
        raise ValueError("file tools require a sandbox work_dir")
    base = os.path.abspath(work_dir)
    resolved = os.path.abspath(os.path.join(base, path))
    if os.path.commonpath([base, resolved]) != base:
        raise ValueError(f"path escapes sandbox work_dir: {path}")
    return resolved


def _eval_arithmetic(expression: str) -> Any:
    operators = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a ** b,
    }
    unary = {
        ast.UAdd: lambda a: +a,
        ast.USub: lambda a: -a,
    }

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in unary:
            return unary[type(node.op)](visit(node.operand))
        raise ValueError("Only arithmetic expressions are allowed")

    return visit(ast.parse(expression, mode="eval"))
