"""Multi-turn Conversation Evaluation Evaluator."""

from typing import Any, Dict, List
from agent_eval.evaluators.base import BaseEvaluator, EvaluationType, EvalContext, EvalResult, register_evaluator
from agent_eval.utils import resolve_config_path


@register_evaluator
class MultiTurnEvaluator(BaseEvaluator):
    name = "multi_turn"
    version = "1.0"
    evaluation_type = EvaluationType.DYNAMIC
    supported_dimensions = ["conversation_flow", "context_retention", "instruction_following", "consistency"]
    description = "Multi-turn conversation evaluation"
    
    def __init__(self):
        super().__init__()
        self.conversations = []
        self.judge_panel = None
        self.max_turns = 10
    
    def setup(self, config: Dict[str, Any]) -> None:
        super().setup(config)
        self.max_turns = config.get("max_turns", 10)
        self.conversation_file = resolve_config_path(config.get("conversation_file", "scenarios/multi_turn.yaml"), config)
        self._load_conversations()
        self._init_judges(config.get("judges", []))
    
    def _load_conversations(self) -> None:
        try:
            import yaml
            with open(self.conversation_file) as f:
                data = yaml.safe_load(f)
                self.conversations = data.get("conversations", [])
        except FileNotFoundError:
            self.conversations = self._default_conversations()
        except Exception as e:
            raise RuntimeError(f"Failed to load conversations: {e}")
    
    def _default_conversations(self) -> List[Dict]:
        return [
            {
                "task_id": "multi_turn_1",
                "persona": "You are a helpful travel assistant.",
                "turns": [
                    {"user": "I want to plan a trip to Japan.", "expected_topics": ["japan", "travel", "plan"]},
                    {"user": "I have 10 days and $3000 budget.", "expected_topics": ["10 days", "budget", "3000"]},
                    {"user": "I like temples and food.", "expected_topics": ["temples", "food", "recommend"]},
                    {"user": "Can you give me a day-by-day itinerary?", "expected_topics": ["itinerary", "day", "schedule"]},
                ],
                "evaluation_criteria": {
                    "context_retention": 0.3,
                    "instruction_following": 0.3,
                    "consistency": 0.2,
                    "helpfulness": 0.2,
                }
            },
            {
                "task_id": "multi_turn_2",
                "persona": "You are a coding tutor helping a beginner.",
                "turns": [
                    {"user": "I want to learn Python.", "expected_topics": ["python", "learn", "beginner"]},
                    {"user": "What are variables?", "expected_topics": ["variables", "explain", "example"]},
                    {"user": "Show me an example with strings.", "expected_topics": ["string", "example", "code"]},
                    {"user": "Now show me lists.", "expected_topics": ["list", "example", "code"]},
                    {"user": "Can you summarize what we learned?", "expected_topics": ["summary", "variables", "strings", "lists"]},
                ],
                "evaluation_criteria": {
                    "context_retention": 0.4,
                    "instruction_following": 0.3,
                    "consistency": 0.2,
                    "helpfulness": 0.1,
                }
            },
        ]
    
    def _init_judges(self, judge_configs: List[Dict]) -> None:
        from agent_eval.judges.panel import MultiJudgePanel
        from agent_eval.judges.factory import JudgeFactory
        
        judges = []
        for jc in judge_configs:
            judges.append(JudgeFactory.create(jc))
        
        if not judges:
            judges = [
                JudgeFactory.create({"type": "conversation_quality", "name": "conversation_quality"}),
                JudgeFactory.create({"type": "context_retention", "name": "context_retention"}),
                JudgeFactory.create({"type": "consistency", "name": "consistency"}),
            ]
        
        self.judge_panel = MultiJudgePanel(judges)
    
    def generate_tasks(self, context: EvalContext) -> List[Dict[str, Any]]:
        return self.conversations
    
    def execute_task(self, task: Dict[str, Any], context: EvalContext) -> Any:
        conversation_history = []
        system_prompt = task.get("persona", "You are a helpful assistant.")
        
        for turn_idx, turn in enumerate(task["turns"]):
            user_msg = turn["user"]
            
            messages = [{"role": "system", "content": system_prompt}]
            for h in conversation_history:
                messages.append(h)
            messages.append({"role": "user", "content": user_msg})
            
            response = context.agent_under_test.chat(messages)
            
            conversation_history.append({"role": "user", "content": user_msg})
            conversation_history.append({"role": "assistant", "content": response})
        
        return {
            "conversation": conversation_history,
            "task_id": task["task_id"],
            "turns": task["turns"],
            "criteria": task.get("evaluation_criteria", {}),
        }
    
    def evaluate(self, task: Dict[str, Any], output: Any, context: EvalContext) -> EvalResult:
        import time
        start = time.time()
        
        judge_result = self.judge_panel.evaluate(task, output)
        
        exec_time = int((time.time() - start) * 1000)
        
        return EvalResult(
            evaluator_name=self.name,
            evaluation_type=self.evaluation_type,
            score=judge_result["_final"],
            raw_score=judge_result,
            details={
                "conversation": output["conversation"],
                "judge_scores": {k: v for k, v in judge_result.items() if not k.startswith("_")},
            },
            artifacts=[output["conversation"]],
            passed=judge_result["_final"] >= 0.7,
            execution_time_ms=exec_time,
            task_id=task["task_id"]
        )


class ConversationQualityJudge:
    name = "conversation_quality"
    
    def score(self, task: Dict, output: Dict) -> float:
        conversation = output.get("conversation", [])
        turns = task.get("turns", [])
        
        if not conversation or len(conversation) < 2:
            return 0.0
        
        assistant_turns = [m for m in conversation if m.get("role") == "assistant"]
        if not assistant_turns:
            return 0.0
        
        total_score = 0.0
        for i, (turn, assistant_msg) in enumerate(zip(turns, assistant_turns)):
            expected_topics = turn.get("expected_topics", [])
            response = assistant_msg.get("content", "").lower()
            
            if expected_topics:
                matched = sum(1 for topic in expected_topics if topic.lower() in response)
                total_score += matched / len(expected_topics)
            else:
                total_score += 1.0
        
        return total_score / len(turns) if turns else 0.0
    
    def explain(self, task: Dict, output: Dict, score: float) -> str:
        return f"Conversation quality: {score:.2f}"


class ContextRetentionJudge:
    name = "context_retention"
    
    def score(self, task: Dict, output: Dict) -> float:
        conversation = output.get("conversation", [])
        turns = task.get("turns", [])
        
        if len(turns) < 2:
            return 1.0
        
        user_messages = [m.get("content", "") for m in conversation if m.get("role") == "user"]
        assistant_messages = [m.get("content", "") for m in conversation if m.get("role") == "assistant"]
        
        if not user_messages or not assistant_messages:
            return 0.0
        
        retention_scores = []
        for i in range(1, len(user_messages)):
            curr_response = assistant_messages[i].lower() if i < len(assistant_messages) else ""
            
            key_terms = set()
            for msg in user_messages[:i]:
                words = msg.lower().split()
                key_terms.update(w for w in words if len(w) > 4)
            
            if key_terms:
                matched = sum(1 for term in key_terms if term in curr_response)
                retention_scores.append(matched / len(key_terms))
        
        return sum(retention_scores) / len(retention_scores) if retention_scores else 0.5
    
    def explain(self, task: Dict, output: Dict, score: float) -> str:
        return f"Context retention: {score:.2f}"


class ConsistencyJudge:
    name = "consistency"
    
    def score(self, task: Dict, output: Dict) -> float:
        conversation = output.get("conversation", [])
        assistant_messages = [m.get("content", "") for m in conversation if m.get("role") == "assistant"]
        
        if len(assistant_messages) < 2:
            return 1.0
        
        contradictions = 0
        total_pairs = 0
        
        for i in range(len(assistant_messages)):
            for j in range(i + 1, len(assistant_messages)):
                total_pairs += 1
                if self._detect_contradiction(assistant_messages[i], assistant_messages[j]):
                    contradictions += 1
        
        if total_pairs == 0:
            return 1.0
        
        return 1.0 - (contradictions / total_pairs)
    
    def _detect_contradiction(self, text1: str, text2: str) -> bool:
        negation_words = {"not", "no", "never", "cannot", "can't", "won't", "will not", "don't", "doesn't"}
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        for nw in negation_words:
            if nw in words1 and nw not in words2:
                for w in words1:
                    if len(w) > 3 and w in words2:
                        return True
        return False
    
    def explain(self, task: Dict, output: Dict, score: float) -> str:
        return f"Consistency: {score:.2f}"
