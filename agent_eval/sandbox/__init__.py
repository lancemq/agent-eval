"""Sandbox factory and base classes for isolated execution environments."""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseSandbox(ABC):
    """Base class for execution sandboxes."""

    @abstractmethod
    def execute(self, action: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass


class LocalSandbox(BaseSandbox):
    """Local execution sandbox (no isolation, for development)."""

    def execute(self, action: Dict[str, Any]) -> Dict[str, Any]:
        tool = action.get("tool", "")
        params = action.get("params", {})
        try:
            result = self._call_tool(tool, params)
            return {"output": result, "error": None, "new_state": {tool: result}}
        except Exception as e:
            return {"output": None, "error": str(e), "new_state": {}}

    def setup(self) -> None:
        pass

    def teardown(self) -> None:
        pass

    def _call_tool(self, tool: str, params: Dict) -> Any:
        from agent_eval.sandbox.tools import ToolRegistry
        return ToolRegistry.call(tool, **params)


class DockerSandbox(BaseSandbox):
    """Docker-based sandbox for isolated execution."""

    def __init__(self, image: str = "python:3.11-slim", timeout: int = 30):
        self.image = image
        self.timeout = timeout
        self.container_id = None

    def execute(self, action: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import docker
            client = docker.from_env()
            container = client.containers.get(self.container_id)
            code = action.get("params", {}).get("code", "")
            result = container.exec_run(
                ["python", "-c", code],
                timeout=self.timeout,
            )
            return {
                "output": result.output.decode() if result.output else "",
                "error": None if result.exit_code == 0 else result.output.decode(),
                "new_state": {},
            }
        except Exception as e:
            return {"output": None, "error": str(e), "new_state": {}}

    def setup(self) -> None:
        try:
            import docker
            client = docker.from_env()
            self.container_id = client.containers.run(
                self.image, "sleep infinity", detach=True, remove=True
            ).id
        except ImportError:
            raise RuntimeError("docker library required: pip install docker")

    def teardown(self) -> None:
        if self.container_id:
            try:
                import docker
                client = docker.from_env()
                container = client.containers.get(self.container_id)
                container.stop(timeout=5)
            except Exception:
                pass


class SandboxFactory:
    """Creates sandbox instances from config."""

    @classmethod
    def create(cls, sandbox_type: str = "local", config: Dict[str, Any] = None) -> BaseSandbox:
        config = config or {}
        if sandbox_type == "local":
            return LocalSandbox()
        elif sandbox_type == "docker":
            return DockerSandbox(
                image=config.get("image", "python:3.11-slim"),
                timeout=config.get("timeout", 30),
            )
        else:
            raise ValueError(f"Unknown sandbox type: {sandbox_type}")