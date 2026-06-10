# AgentEval Technical Development Design Document

## 1. Overview

AgentEval is a pluggable, extensible evaluation framework for AI agents. It supports four evaluation types (Benchmark, Dynamic, Adversarial, Custom) and provides a unified pipeline for task generation, execution, judging, and reporting.

**Design Goals:**
- **Modularity**: Every evaluation domain is a plugin; core framework is domain-agnostic.
- **Extensibility**: New plugins, judges, and scorers can be added without modifying core code.
- **Reliability**: Retry logic, timeout handling, error isolation, and teardown guarantees.
- **Observability**: Structured reports with dimension-level scoring, micro/macro aggregation, and multi-format output.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI / API                             │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              EvaluationOrchestrator                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ TaskQueue   │  │ HookManager │  │ ResultStore         │  │
│  │ (priority)  │  │ (lifecycle) │  │ (JSON/SQLite/Mem)   │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
┌────────▼──┐  ┌──────▼────┐  ┌─────▼──────┐
│ Benchmark │  │ Dynamic   │  │ Adversarial│
│ Plugins   │  │ Plugins   │  │ Plugins    │
│ (MMLU,    │  │ (Coding,  │  │ (Jailbreak,│
│ GSM8K,    │  │ ToolUse,  │  │ Injection, │
│ HumanEval)│  │ MultiTurn)│  │ Bias)      │
└─────┬─────┘  └─────┬─────┘  └─────┬──────┘
      │              │              │
      └──────────────┼──────────────┘
                     │
         ┌───────────▼────────────┐
         │    AgentUnderTest      │
         │  (OpenAIAgent /        │
         │   CallableAgent)       │
         └───────────┬────────────┘
                     │
         ┌───────────▼────────────┐
         │      LLMClient         │
         │  (retry + timeout)     │
         └────────────────────────┘
```

---

## 3. Core Components

### 3.1 EvaluationOrchestrator

**File:** `agent_eval/orchestrator/orchestrator.py`

The orchestrator is the central controller. It manages the full evaluation lifecycle:

1. **Initialize plugins** (`_init_plugins`): Creates fresh plugin instances per run, passes plugin-specific config, calls `setup()`.
2. **Generate & enqueue tasks** (`_execute_plugins`): Each plugin generates its task list; tasks are enqueued into `TaskQueue` with priority.
3. **Parallel execution** (`ThreadPoolExecutor`): Workers dequeue tasks, call `plugin.execute_task()` and `plugin.evaluate()`.
4. **Report generation** (`_generate_report`): Aggregates results, computes micro/macro scores and dimension breakdowns.
5. **Teardown** (`finally` block): Guarantees `plugin.teardown()` is called even if evaluation fails.

**Key Design Decisions:**
- **Instance isolation**: `PluginRegistry.get()` creates a new instance every time. This prevents state leakage between runs.
- **Config per plugin**: `plugin_configs` dict maps plugin name to its config, allowing heterogeneous plugin configurations in a single run.
- **Micro vs Macro scoring**:
  - `micro_score`: Task-weighted average (each task contributes equally to the total).
  - `macro_score`: Plugin-weighted average (each plugin contributes equally, regardless of task count).
  - `overall_score` defaults to `micro_score` for benchmark fairness.

### 3.2 Plugin System

**File:** `agent_eval/plugins/base.py`

**BasePlugin** defines the contract:
- `setup(config)`: Load datasets, initialize judges, configure environments.
- `generate_tasks(context)`: Return list of task dicts.
- `execute_task(task, context)`: Interact with `AgentUnderTest`, return raw output.
- `evaluate(task, output, context)`: Judge output, return `EvalResult`.
- `teardown()`: Cleanup resources.

**PluginRegistry** uses a class-level dict with thread-safe locking (`threading.Lock`). Registration is via `@register_plugin` decorator.

**Evaluation Types:**
| Type | Purpose | Example |
|------|---------|---------|
| BENCHMARK | Fixed dataset, deterministic scoring | MMLU, GSM8K, HumanEval |
| DYNAMIC | Interactive, multi-turn, sandboxed | Coding, ToolUse, MultiTurn |
| ADVERSARIAL | Safety/red-teaming | Jailbreak, Injection, Bias |
| CUSTOM | User-defined | Any bespoke evaluation |

### 3.3 Agent Under Test

**File:** `agent_eval/orchestrator/agent.py`

**AgentUnderTest** is an abstract interface with three modes:
- `generate(prompt) -> str`: Single-turn text generation.
- `chat(messages) -> str`: Multi-turn conversation.
- `act(state, tools, goal) -> dict`: Tool-use / agentic action (returns JSON dict).

**Implementations:**
- **OpenAIAgent**: Wraps any OpenAI-compatible model via `LLMClient`.
- **CallableAgent**: Wraps arbitrary Python callables or module classes via `from_module()`.

**JSON Extraction** (`_extract_json`):
Tries fenced code blocks first (` ```json ... ``` `), then scans outermost `{...}` pairs. Returns `{"type": "error", ...}` on failure so callers can distinguish parse failures from legitimate actions.

### 3.4 Task Queue

**File:** `agent_eval/orchestrator/task_queue.py`

Priority-based queue using Python `heapq`. Supports:
- 4 priority levels: LOW, NORMAL, HIGH, CRITICAL
- Retry with exponential backoff (max 3 retries by default)
- Lifecycle callbacks (enqueue, dequeue, complete, fail, cancel)
- Progress tracking (pending/running/completed/failed counts)

**Thread Safety:** The queue is accessed from `ThreadPoolExecutor` workers; all operations are atomic at the object level (Python GIL protects dict/list ops). The `TaskQueue` itself does not use explicit locks, relying on CPython's GIL for simplicity.

### 3.5 Judge System

**File:** `agent_eval/judges/base.py`, `agent_eval/judges/panel.py`, `agent_eval/judges/llm_judge.py`

**BaseJudge** defines `score(task, output) -> float` and `explain(task, output, score) -> str`.

**MultiJudgePanel** provides cross-validation:
- Runs all judges independently.
- Catches exceptions per-judge (sets `score=None`, continues).
- Computes consistency (`1 - 2 * stdev(scores)`).
- Supports 7 aggregation strategies: `weighted`, `mean`, `median`, `unanimous`, `majority`, `min`, `max`.
- **Weighted aggregation** normalizes weights when some judges error out.

**LLMJudge** uses self-consistency sampling (`n_samples` calls, median score) with chain-of-thought prompting.

**EnsembleJudge** combines multiple judges with weights, skipping judges that throw exceptions.

### 3.6 Scorer System

**File:** `agent_eval/scorers/base.py`, `agent_eval/scorers/factory.py`

28 built-in scorers across 6 categories:
- **Deterministic**: exact_match, numeric_match, regex_match, json_valid, keyword, length, contains_any, contains_all
- **LLM-based**: g_eval, faithfulness, hallucination, answer_correctness, answer_relevancy, contextual_relevancy/recall/precision, summarization
- **Safety**: toxicity, bias, safety
- **Agent-specific**: task_completion, tool_call_correctness, conversation_quality, role_adherence, task_efficiency
- **Ensemble**: ensemble (multi-scorer aggregation), threshold (wrapper)

**BaseScorer** provides:
- `_call_llm(prompt)` via unified `LLMClient` (retry, timeout)
- `_parse_score(text)` robust regex-based extraction
- `_parse_reason(text)` extracts `REASON:` prefix

**ScorerBridge** (`agent_eval/judges/factory.py`) wraps any `BaseScorer` as a `BaseJudge` for backward compatibility.

### 3.7 LLM Client

**File:** `agent_eval/llm_client.py`

Unified wrapper around OpenAI client:
- **Lazy initialization**: `_get_client()` creates the client on first use.
- **Retry logic**: Exponential backoff on `429`, `502`, `503`, `504`.
- **Fail-fast**: No retry on `401`, `403`.
- **Configurable**: model, timeout, max_retries, backoff, api_key, base_url.

### 3.8 Result Store

**File:** `agent_eval/orchestrator/result_store.py`

Pluggable storage backends:
- **JSONBackend**: Filesystem-based, human-readable.
- **SQLiteBackend**: Structured query support.
- **MemoryBackend**: Ephemeral, for testing.

**EvaluationReport** is the canonical report structure:
- `run_id`, `timestamp`, `agent_name`, `agent_version`
- `summary`: overall_score, macro_score, micro_score, total_tasks, pass_rate, dimensions
- `plugin_results`: per-plugin score, passed, failed, total, pass_rate
- `task_results`: per-task serialized `EvalResult` (including `dimension_scores`)
- `metadata`: run context

### 3.9 Hook System

**File:** `agent_eval/orchestrator/hooks.py`

Lifecycle events:
- `evaluation_start / evaluation_complete`
- `plugin_setup / plugin_teardown`
- `task_generated / task_execute / task_evaluate / task_complete / task_failed`

Hooks are fire-and-forget (exceptions are caught and returned in a list, not propagated).

### 3.10 Reporting

**File:** `agent_eval/reporting.py`

Generates reports in 3 formats:
- **JSON**: Raw structured data.
- **HTML**: Styled dashboard with score bars, dimension tables, plugin breakdowns. All dynamic content is HTML-escaped for XSS safety.
- **Markdown**: Human-readable with ASCII bar charts.

---

## 4. Data Flow

```
1. CLI parses args + config
   └── agent, plugin_names, plugin_configs, eval_config

2. Orchestrator.run_evaluation()
   a. Create EvalContext (agent, metadata, run_id)
   b. Init plugins (setup + config)
   c. For each plugin:
      i.   generate_tasks() → task dicts
      ii.  enqueue_batch() → TaskQueue
      iii. ThreadPoolExecutor:
           - dequeue task
           - execute_task(task) → raw output
           - evaluate(task, output) → EvalResult
           - complete/fail task
   d. Generate report:
      - Aggregate scores (micro/macro)
      - Compute dimension averages
      - Serialize task results
   e. Save report → ResultStore
   f. teardown plugins (finally)

3. ReportGenerator.generate()
   └── JSON / HTML / Markdown files
```

---

## 5. Extension Points

### 5.1 Adding a Plugin

```python
from agent_eval.plugins.base import BasePlugin, EvaluationType, EvalContext, EvalResult, register_plugin

@register_plugin
class MyPlugin(BasePlugin):
    name = "my_plugin"
    evaluation_type = EvaluationType.CUSTOM
    supported_dimensions = ["accuracy", "speed"]

    def setup(self, config):
        pass

    def generate_tasks(self, context):
        return [{"task_id": "t1", "prompt": "..."}]

    def execute_task(self, task, context):
        return context.agent_under_test.generate(task["prompt"])

    def evaluate(self, task, output, context):
        return EvalResult(
            plugin_name=self.name,
            evaluation_type=self.evaluation_type,
            score=1.0,
            raw_score={},
            details={},
            artifacts=[output],
            passed=True,
            execution_time_ms=0,
            task_id=task["task_id"],
            dimension_scores={"accuracy": 1.0},
        )
```

### 5.2 Adding a Scorer

```python
from agent_eval.scorers.base import BaseScorer, ScorerResult
from agent_eval.scorers.factory import scorer

@scorer("my_scorer")
class MyScorer(BaseScorer):
    name = "my_scorer"

    def score(self, output: str, **kwargs) -> ScorerResult:
        score = 1.0 if "correct" in output else 0.0
        return ScorerResult(name=self.name, score=score, reason="...", passed=score >= 0.5)
```

### 5.3 Adding a Judge

```python
from agent_eval.judges.base import BaseJudge

class MyJudge(BaseJudge):
    name = "my_judge"

    def score(self, task, output) -> float:
        return 1.0

    def explain(self, task, output, score) -> str:
        return f"Score: {score}"
```

Register via `JudgeFactory.register("my_judge", MyJudge)`.

---

## 6. Configuration System

**File:** `agent_eval/config.py`

Hierarchical config:
```yaml
orchestrator:
  max_workers: 4
  queue_backend: memory
  storage:
    type: json
    output_dir: ./eval_results
  log_level: INFO

agent:
  type: callable
  module: my_module:MyAgent
  config: {}

plugins:
  coding:
    enabled: true
    timeout: 30
    task_file: scenarios/coding.yaml
  jailbreak:
    enabled: true
    attack_config: attacks/comprehensive.yaml

eval_config: {}

report:
  formats: [json, html, markdown]
  output_dir: ./eval_results
```

---

## 7. Error Handling Strategy

| Layer | Strategy |
|-------|----------|
| Plugin setup | Fatal (raise) |
| Task generate | Fatal (raise), teardown via `finally` |
| Task execute | Catch all, return failed `EvalResult`, retry up to 3x |
| Judge score | Catch per-judge, set `score=None`, continue |
| Plugin teardown | Catch and log warning, never fatal |
| LLM call | Retry on transient, fail-fast on auth |

---

## 8. Security Considerations

1. **Code Execution**: `CodingPlugin` and `HumanEvalPlugin` run arbitrary Python via `subprocess`. Production use should use sandboxed containers (Docker, gVisor).
2. **HTML Reports**: All dynamic content is escaped via `html.escape()` before injection.
3. **API Keys**: `LLMClient` supports `api_key` and `base_url` parameters. Keys should be passed via env vars, not config files.
4. **Adversarial Tests**: Jailbreak/Injection plugins contain harmful prompt templates for red-teaming. These are safety evaluation tools, not attack payloads.

---

## 9. Testing Strategy

- **Unit tests**: `tests/unit/` covers orchestrator, task queue, agent JSON extraction, LLM client retry logic, judge panel aggregation.
- **Mock-based**: All LLM calls and plugin executions are mocked.
- **Key test scenarios**:
  - Plugin config propagation
  - Instance isolation across runs
  - Teardown on failure
  - Task result serialization/deserialization
  - Micro/macro score calculation
  - Dimension score override
  - Judge error handling

---

## 10. Future Enhancements

1. **Distributed Execution**: Replace `ThreadPoolExecutor` with Celery / Ray for horizontal scaling.
2. **Sandbox Integration**: Docker-based sandbox for code execution plugins.
3. **Live Dashboard**: Real-time WebSocket updates during evaluation runs.
4. **Regression Detection**: Automatic comparison against baseline reports with statistical significance testing.
5. **Custom Scorer DSL**: YAML-based scorer configuration without writing Python.
