"""Tests for sandbox tool isolation."""

import os

from agent_eval.sandbox import LocalSandbox


def test_local_sandbox_file_tools_are_confined_to_work_dir(tmp_path):
    sandbox = LocalSandbox(work_dir=str(tmp_path))
    sandbox.setup()

    result = sandbox.execute({
        "tool": "file_write",
        "params": {"path": "nested/test.txt", "content": "hello"},
    })
    assert result["error"] is None
    assert (tmp_path / "nested" / "test.txt").read_text() == "hello"

    read = sandbox.execute({"tool": "file_read", "params": {"path": "nested/test.txt"}})
    assert read["output"] == "hello"


def test_local_sandbox_file_tools_reject_path_escape(tmp_path):
    sandbox = LocalSandbox(work_dir=str(tmp_path))
    sandbox.setup()

    result = sandbox.execute({
        "tool": "file_write",
        "params": {"path": "../escape.txt", "content": "nope"},
    })

    assert result["output"] is None
    assert "escapes sandbox" in result["error"]
    assert not os.path.exists(tmp_path.parent / "escape.txt")


def test_calculator_rejects_non_arithmetic_code(tmp_path):
    sandbox = LocalSandbox(work_dir=str(tmp_path))
    sandbox.setup()

    result = sandbox.execute({
        "tool": "calculator",
        "params": {"expression": "__import__('os').system('echo nope')"},
    })

    assert result["error"] is None
    assert result["output"].startswith("Error:")


def test_python_repl_uses_restricted_builtins(tmp_path):
    sandbox = LocalSandbox(work_dir=str(tmp_path))
    sandbox.setup()

    result = sandbox.execute({
        "tool": "python_repl",
        "params": {"code": "result = __import__('os').getcwd()"},
    })

    assert result["error"] is None
    assert "__import__" in result["output"]
