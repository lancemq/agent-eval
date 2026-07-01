import json

from fastapi.testclient import TestClient

from agent_eval.trace.schema import TraceRecord
from agent_eval.trace.store import TraceStore
from agent_eval.web.app import create_app


def test_health_endpoint(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_plugins_endpoint(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))

    response = client.get("/api/evaluators")

    assert response.status_code == 200
    assert "evaluators" in response.json()


def test_validate_config_rejects_bad_storage(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))

    response = client.post("/api/config/validate", json={"config": {"orchestrator": {"storage": {"type": "bad"}}}})

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["errors"][0]["field"] == "orchestrator.storage.type"


def test_reports_endpoint(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))

    response = client.get("/api/reports")

    assert response.status_code == 200
    assert response.json() == {"reports": []}


def test_scorers_endpoint(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))

    response = client.get("/api/scorers")

    assert response.status_code == 200
    assert any(scorer["type"] == "exact_match" for scorer in response.json()["scorers"])


def test_plugins_include_custom_eval(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))

    response = client.get("/api/evaluators")

    assert any(evaluator["name"] == "custom_eval" for evaluator in response.json()["evaluators"])


def test_validate_config_accepts_custom_eval(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))
    config = {
        "evaluators": {
            "custom_eval": {
                "enabled": True,
                "evaluations": [
                    {
                        "id": "qa",
                        "task_source": {"type": "inline", "items": [{"input": "A", "expected": "A"}]},
                        "prompt": {"mode": "generate", "template": "{input}"},
                        "scoring": {"scorers": [{"type": "exact_match"}]},
                    }
                ],
            }
        }
    }

    response = client.post("/api/config/validate", json={"config": config})

    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_validate_config_rejects_custom_eval_bad_scorer(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))
    config = {
        "evaluators": {
            "custom_eval": {
                "enabled": True,
                "evaluations": [
                    {
                        "id": "qa",
                        "task_source": {"type": "inline", "items": [{"input": "A", "expected": "A"}]},
                        "prompt": {"mode": "generate", "template": "{input}"},
                        "scoring": {"scorers": [{"type": "missing_scorer"}]},
                    }
                ],
            }
        }
    }

    response = client.post("/api/config/validate", json={"config": config})

    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_traces_endpoint_lists_trace_summaries(tmp_path):
    traces_dir = tmp_path / "traces"
    store = TraceStore(path=str(traces_dir))
    store.save(TraceRecord(
        trace_id="trace-1",
        timestamp="2026-01-01T00:00:00Z",
        agent_name="agent-a",
        trace_type="tool_use",
        input="Find the answer",
        output="Done",
        success=True,
        duration_ms=42,
        tags=["prod"],
        quality_score=0.9,
    ))
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path), trace_dir=str(traces_dir)))

    response = client.get("/api/traces")

    assert response.status_code == 200
    assert response.json()["traces"] == [
        {
            "trace_id": "trace-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "agent_name": "agent-a",
            "trace_type": "tool_use",
            "success": True,
            "quality_score": 0.9,
            "duration_ms": 42,
            "tags": ["prod"],
            "num_tool_calls": 0,
            "num_turns": 1,
        }
    ]


def test_trace_detail_endpoint_returns_full_trace(tmp_path):
    traces_dir = tmp_path / "traces"
    store = TraceStore(path=str(traces_dir))
    store.save(TraceRecord(trace_id="trace-2", agent_name="agent-b", input="Question", output="Answer"))
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path), trace_dir=str(traces_dir)))

    response = client.get("/api/traces/trace-2")

    assert response.status_code == 200
    assert response.json()["trace_id"] == "trace-2"
    assert response.json()["input"] == "Question"


def test_trace_eval_config_endpoint_builds_custom_eval(tmp_path):
    traces_dir = tmp_path / "traces"
    store = TraceStore(path=str(traces_dir))
    store.save(TraceRecord(trace_id="trace-3", trace_type="single_turn", input="2+2?", output="4"))
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path), trace_dir=str(traces_dir)))

    response = client.post("/api/traces/eval-config", json={
        "trace_ids": ["trace-3"],
        "scorers": ["exact_match"],
        "eval_id": "trace_eval_math",
        "name": "Trace Math Eval",
        "dimensions": ["correctness"],
    })

    assert response.status_code == 200
    custom_eval = response.json()["custom_eval"]
    evaluation = custom_eval["evaluations"][0]
    assert custom_eval["enabled"] is True
    assert evaluation["id"] == "trace_eval_math"
    assert evaluation["task_source"]["items"][0]["task_id"] == "trace-3"
    assert evaluation["task_source"]["items"][0]["expected"] == "4"
    assert evaluation["scoring"]["scorers"][0]["type"] == "exact_match"


def test_unknown_api_endpoint_returns_json_404(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))

    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == "API endpoint not found"


def test_settings_endpoint_returns_defaults_and_masked_langfuse(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path), trace_dir=str(tmp_path / "traces")))

    response = client.get("/api/settings")

    assert response.status_code == 200
    data = response.json()
    assert data["run_defaults"]["agent"] == "openai:gpt-4o-mini"
    assert data["run_defaults"]["output_dir"] == "./eval_results"
    assert data["run_defaults"]["orchestrator"]["max_workers"] == 2
    assert data["trace"]["trace_dir"] == str(tmp_path / "traces")
    assert data["langfuse"]["secret_configured"] is False
    assert "secret_key" not in data["langfuse"]


def test_settings_endpoint_saves_run_defaults_and_langfuse(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))

    response = client.post("/api/settings", json={
        "run_defaults": {
            "agent": "openai:gpt-4o",
            "output_dir": "./custom_results",
            "report_formats": ["json"],
            "orchestrator": {
                "max_workers": 4,
                "queue_backend": "memory",
                "storage": {"type": "json", "output_dir": "./custom_results"},
                "log_level": "DEBUG",
            },
        },
        "langfuse": {
            "host": "https://langfuse.example.com",
            "public_key": "pk-settings",
            "secret_key": "sk-settings",
            "project": "settings-project",
            "enabled": True,
        },
    })

    assert response.status_code == 200
    data = response.json()
    assert data["run_defaults"]["agent"] == "openai:gpt-4o"
    assert data["langfuse"]["secret_configured"] is True
    saved_settings = json.loads((tmp_path / ".agent-eval" / "web-settings.json").read_text())
    assert saved_settings["run_defaults"]["output_dir"] == "./custom_results"
    saved_langfuse = json.loads((tmp_path / ".agent-eval" / "langfuse.json").read_text())
    assert saved_langfuse["secret_key"] == "sk-settings"


def test_langfuse_config_defaults_are_masked(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))

    response = client.get("/api/langfuse/config")

    assert response.status_code == 200
    assert response.json() == {
        "host": "https://cloud.langfuse.com",
        "public_key": "",
        "project": "",
        "enabled": False,
        "secret_configured": False,
    }


def test_langfuse_config_save_masks_secret_and_persists_file(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))

    response = client.post("/api/langfuse/config", json={
        "host": "https://langfuse.example.com",
        "public_key": "pk-test",
        "secret_key": "sk-test",
        "project": "demo",
        "enabled": True,
    })

    assert response.status_code == 200
    assert response.json()["secret_configured"] is True
    assert "secret_key" not in response.json()
    saved = json.loads((tmp_path / ".agent-eval" / "langfuse.json").read_text())
    assert saved["secret_key"] == "sk-test"


def test_langfuse_config_save_preserves_existing_secret(tmp_path):
    config_dir = tmp_path / ".agent-eval"
    config_dir.mkdir()
    (config_dir / "langfuse.json").write_text(json.dumps({
        "host": "https://old.example.com",
        "public_key": "pk-old",
        "secret_key": "sk-keep",
        "project": "old",
        "enabled": True,
    }))
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))

    response = client.post("/api/langfuse/config", json={
        "host": "https://new.example.com",
        "public_key": "pk-new",
        "secret_key": "",
        "project": "new",
        "enabled": False,
    })

    assert response.status_code == 200
    saved = json.loads((config_dir / "langfuse.json").read_text())
    assert saved["secret_key"] == "sk-keep"
    assert saved["host"] == "https://new.example.com"


def test_langfuse_trace_eval_config_endpoint_builds_custom_eval(tmp_path):
    config_dir = tmp_path / ".agent-eval"
    config_dir.mkdir()
    (config_dir / "langfuse.json").write_text(json.dumps({
        "host": "https://langfuse.example.com",
        "public_key": "pk-test",
        "secret_key": "sk-test",
        "project": "demo",
        "enabled": True,
    }))
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))
    app = client.app
    app.state.service.langfuse_client.fetch_trace = lambda trace_id: {
        "id": trace_id,
        "name": "math trace",
        "sessionId": "session-1",
        "input": "2+2?",
        "output": "4",
        "timestamp": "2026-01-01T00:00:00Z",
    }

    response = client.post("/api/langfuse/traces/eval-config", json={
        "trace_ids": ["lf-trace-1"],
        "scorers": ["exact_match"],
        "eval_id": "lf_eval",
        "name": "Langfuse Eval",
        "dimensions": ["correctness"],
    })

    assert response.status_code == 200
    evaluation = response.json()["custom_eval"]["evaluations"][0]
    item = evaluation["task_source"]["items"][0]
    assert item["task_id"] == "lf-trace-1"
    assert item["input"] == "2+2?"
    assert item["expected"] == "4"
    assert item["metadata"]["langfuse_session_id"] == "session-1"


def test_dataset_crud_endpoints(tmp_path):
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))

    # create
    resp = client.post("/api/datasets", json={
        "name": "ds1",
        "rows": [{"task_id": "t1", "input": "hi", "expected": "hello"}],
        "description": "first",
    })
    assert resp.status_code == 200
    assert resp.json()["version"] == "1.0.0"

    # list
    resp = client.get("/api/datasets")
    assert resp.status_code == 200
    assert resp.json()["datasets"][0]["name"] == "ds1"

    # get
    resp = client.get("/api/datasets/ds1")
    assert resp.status_code == 200
    assert resp.json()["rows"][0]["task_id"] == "t1"

    # update rows
    resp = client.put("/api/datasets/ds1/rows", json={
        "rows": [{"task_id": "t1", "input": "hi", "expected": "changed"}],
    })
    assert resp.status_code == 200
    assert resp.json()["version"] == "1.0.1"

    # add version
    resp = client.post("/api/datasets/ds1/versions", json={
        "rows": [{"task_id": "t1"}, {"task_id": "t2"}],
    })
    assert resp.status_code == 200
    assert resp.json()["version"] == "1.1.0"

    # diff
    resp = client.get("/api/datasets/ds1/diff", params={"v1": "1.0.0", "v2": "1.1.0"})
    assert resp.status_code == 200
    assert resp.json()["summary"]["added"] == 1

    # delete
    resp = client.delete("/api/datasets/ds1")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_trend_endpoint(tmp_path):
    from agent_eval.orchestrator import EvaluationReport
    from agent_eval.orchestrator.result_store import ResultStore

    store = ResultStore({"type": "json", "output_dir": str(tmp_path)})
    store.save(EvaluationReport(
        run_id="r1", timestamp="2026-01-01T00:00:00Z",
        agent_name="agent_a", agent_version="1.0",
        summary={"overall_score": 0.8, "pass_rate": 0.8, "dimensions": {"acc": 0.8}},
        evaluator_results={}, metadata={"agent_name": "agent_a"},
    ))
    client = TestClient(create_app(output_dir=str(tmp_path), workspace=str(tmp_path)))
    resp = client.get("/api/trend", params={"agent_name": "agent_a"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["points"]) == 1
    assert data["points"][0]["overall_score"] == 0.8
