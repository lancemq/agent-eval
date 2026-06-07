"""Agent and conversation-specific scorers."""

from agent_eval.scorers.base import BaseScorer, ScorerResult


class TaskCompletionScorer(BaseScorer):
    """Evaluates if an agent successfully completed a multi-step task.

    Checks the trajectory of actions against the task goal and success criteria.
    """

    name = "task_completion"
    description = "Evaluates if an agent completed a multi-step task successfully"

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        trajectory = kwargs.get("trajectory", kwargs.get("output", {}).get("trajectory", []))
        goal = kwargs.get("goal", kwargs.get("output", {}).get("goal", ""))
        success_criteria = kwargs.get("success_criteria", kwargs.get("output", {}).get("success_criteria", {}))

        if not trajectory and not output:
            return ScorerResult(name=self.name, score=0.0, reason="No trajectory data", passed=False, execution_time_ms=0)

        prompt = f"""You are evaluating whether an AI agent successfully completed a task.

TASK GOAL:
{goal or "Complete the assigned task"}

SUCCESS CRITERIA:
{success_criteria}

AGENT'S ACTION TRAJECTORY:
{str(trajectory)[:6000] if trajectory else str(output)[:6000]}

Evaluate:
1. **Goal Achievement**: Did the agent achieve the stated goal? (0.0-1.0)
2. **Efficiency**: Did the agent use a reasonable number of steps? (0.0-1.0)
3. **Correctness**: Were the agent's actions logically correct? (0.0-1.0)

Overall Score: <0.0-1.0>
Reason: <explanation>"""

        response = self._call_llm(prompt)
        score = self._parse_score(response)
        reason = self._parse_reason(response)
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason=reason,
            passed=score >= 0.5,
            execution_time_ms=elapsed,
        )


class ToolCallCorrectnessScorer(BaseScorer):
    """Evaluates whether the agent selected and called tools correctly.

    Checks if the right tools were used with the correct parameters.
    """

    name = "tool_call_correctness"
    description = "Evaluates tool selection and parameter accuracy"

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        trajectory = kwargs.get("trajectory", kwargs.get("output", {}).get("trajectory", []))
        available_tools = kwargs.get("available_tools", kwargs.get("output", {}).get("available_tools", []))
        must_call = kwargs.get("must_call", kwargs.get("output", {}).get("success_criteria", {}).get("must_call", []))

        if not trajectory:
            return ScorerResult(name=self.name, score=0.0, reason="No trajectory data", passed=False, execution_time_ms=0)

        # Extract tool calls from trajectory
        tool_calls = []
        for step in trajectory:
            action = step.get("action", {})
            if action.get("type") == "tool_call":
                tool_calls.append(action)

        if not tool_calls:
            return ScorerResult(name=self.name, score=0.0, reason="No tool calls made", passed=False, execution_time_ms=0)

        called_tools = {tc.get("tool", "") for tc in tool_calls}
        missing_required = set(must_call) - called_tools if must_call else set()

        # Check for invalid tool calls
        invalid_calls = [tc for tc in tool_calls if tc.get("tool", "") not in available_tools]

        base_score = 1.0
        if missing_required:
            base_score -= 0.3 * len(missing_required)
        if invalid_calls:
            base_score -= 0.2 * len(invalid_calls)

        score = max(0.0, base_score)
        reasons = []
        if missing_required:
            reasons.append(f"Missing required tools: {missing_required}")
        if invalid_calls:
            reasons.append(f"Invalid tool calls: {[tc.get('tool') for tc in invalid_calls]}")
        if not reasons:
            reasons.append(f"All {len(tool_calls)} tool calls correct")

        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name,
            score=score,
            reason="; ".join(reasons),
            passed=score >= 0.5,
            metadata={
                "tool_calls": len(tool_calls),
                "called_tools": list(called_tools),
                "missing_required": list(missing_required),
                "invalid_calls": [tc.get("tool") for tc in invalid_calls],
                "available_tools": available_tools,
            },
            execution_time_ms=elapsed,
        )


class ConversationQualityScorer(BaseScorer):
    """Evaluates multi-turn conversation quality.

    Covers coherence, context retention, and helpfulness across turns.
    """

    name = "conversation_quality"
    description = "Multi-turn conversation quality evaluation"

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        conversation = kwargs.get("conversation", kwargs.get("output", {}).get("conversation", []))
        if not conversation:
            return ScorerResult(name=self.name, score=0.5, reason="No conversation data", passed=True, execution_time_ms=0)

        conv_str = str(conversation)[:6000]

        prompt = f"""You are evaluating a multi-turn conversation between a user and an AI assistant.

CONVERSATION:
{conv_str}

Evaluate the assistant's performance on:
1. **Context Retention**: Does the assistant remember and reference earlier parts of the conversation? (0.0-1.0)
2. **Coherence**: Are the assistant's responses logically connected and coherent? (0.0-1.0)
3. **Helpfulness**: Are the responses helpful and addressing user needs? (0.0-1.0)
4. **Consistency**: Does the assistant maintain a consistent persona and avoid contradictions? (0.0-1.0)

Overall Score: <weighted average, 0.0-1.0>
Reason: <explanation>"""

        response = self._call_llm(prompt)
        score = self._parse_score(response)
        reason = self._parse_reason(response)
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason=reason,
            passed=score >= 0.5,
            metadata={"turns": len(conversation) // 2 if isinstance(conversation, list) else 0},
            execution_time_ms=elapsed,
        )


class RoleAdherenceScorer(BaseScorer):
    """Evaluates whether the agent stays in character / adheres to its assigned role."""

    name = "role_adherence"
    description = "Evaluates if agent maintains its assigned persona/role"

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        persona = kwargs.get("persona", kwargs.get("system_prompt", kwargs.get("role", "")))
        conversation = kwargs.get("conversation", kwargs.get("output", {}).get("conversation", []))
        text = str(conversation)[:6000] if conversation else output

        if not persona:
            return ScorerResult(name=self.name, score=0.5, reason="No persona defined", passed=True, execution_time_ms=0)

        prompt = f"""You are evaluating whether an AI assistant adheres to its assigned role.

ASSIGNED ROLE / PERSONA:
{persona}

CONVERSATION / OUTPUT:
{text[:6000]}

Evaluate:
1. **Role Consistency**: Does the assistant consistently act within its assigned role? (0.0-1.0)
2. **Scope**: Does the assistant stay within the boundaries of its role? (0.0-1.0)

Overall Score: <0.0-1.0>
Reason: <explanation>"""

        response = self._call_llm(prompt)
        score = self._parse_score(response)
        reason = self._parse_reason(response)
        elapsed = int((time.time() - start) * 1000)

        return ScorerResult(
            name=self.name,
            score=score,
            reason=reason or "Role adherence evaluation",
            passed=score >= 0.5,
            execution_time_ms=elapsed,
        )


class TaskEfficiencyScorer(BaseScorer):
    """Measures how efficiently the agent completed a task (fewer steps = better)."""

    name = "task_efficiency"
    description = "Measures efficiency of task completion (fewer steps/tokens = better)"

    def __init__(self, optimal_steps: int = 1, max_steps: int = 10):
        self.optimal_steps = optimal_steps
        self.max_steps = max_steps

    def score(self, output: str, **kwargs) -> ScorerResult:
        import time
        start = time.time()
        trajectory = kwargs.get("trajectory", kwargs.get("output", {}).get("trajectory", []))
        n_steps = len(trajectory) if trajectory else 1

        if n_steps <= self.optimal_steps:
            score = 1.0
        elif n_steps >= self.max_steps:
            score = 0.0
        else:
            ratio = (n_steps - self.optimal_steps) / (self.max_steps - self.optimal_steps)
            score = 1.0 - ratio

        elapsed = int((time.time() - start) * 1000)
        return ScorerResult(
            name=self.name,
            score=score,
            reason=f"{n_steps} steps used (optimal={self.optimal_steps}, max={self.max_steps})",
            passed=score >= 0.3,
            metadata={"steps": n_steps, "optimal": self.optimal_steps, "max": self.max_steps},
            execution_time_ms=elapsed,
        )