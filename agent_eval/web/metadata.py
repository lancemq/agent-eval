"""Rich metadata for scorers and evaluators — used by Web UI library page."""

from __future__ import annotations

from typing import Any, Dict, List


# -------- Scorers --------

# Each entry: { params, requires, dimensions, use_cases, example }
# params: list of { name, type, default, description }
# requires: list of strings (e.g. "LLM", "expected", "context", "sentence-transformers")
# dimensions: list of suggested evaluation dimensions
# use_cases: list of typical scenarios
# example: a YAML-ish dict for scorers entry in config

SCORER_METADATA: Dict[str, Dict[str, Any]] = {
    # ===== LLM-as-Judge: general =====
    "g_eval": {
        "params": [
            {"name": "criteria", "type": "str", "default": "", "description": "评分准则，描述要从哪些方面打分"},
            {"name": "rubric_name", "type": "str", "default": "coherence", "description": "预设 rubric 名称（coherence / fluency 等）"},
            {"name": "use_cot", "type": "bool", "default": True, "description": "是否启用 Chain-of-Thought 推理"},
            {"name": "model", "type": "str", "default": "gpt-4o-mini", "description": "评测模型（被配置中心的全局 eval_model 覆盖）"},
            {"name": "n_samples", "type": "int", "default": 1, "description": "采样次数（>1 会取平均，降低方差）"},
        ],
        "requires": ["LLM"],
        "dimensions": ["quality", "coherence"],
        "use_cases": ["开放式生成评估", "自定义 rubric 评分"],
        "example": {"type": "g_eval", "criteria": "答案是否清晰、准确、有用", "use_cot": True},
    },
    "summarization": {
        "params": [],
        "requires": ["LLM", "expected"],
        "dimensions": ["coverage", "conciseness", "coherence"],
        "use_cases": ["摘要任务质量评估"],
        "example": {"type": "summarization"},
    },
    # ===== Faithfulness / Hallucination =====
    "faithfulness": {
        "params": [],
        "requires": ["LLM", "context"],
        "dimensions": ["faithfulness"],
        "use_cases": ["RAG 输出与上下文一致性", "防止编造事实"],
        "example": {"type": "faithfulness"},
    },
    "hallucination": {
        "params": [],
        "requires": ["LLM", "context"],
        "dimensions": ["accuracy"],
        "use_cases": ["幻觉检测", "RAG 系统验证"],
        "example": {"type": "hallucination"},
    },
    "answer_correctness": {
        "params": [],
        "requires": ["LLM", "expected"],
        "dimensions": ["accuracy"],
        "use_cases": ["与标准答案对比"],
        "example": {"type": "answer_correctness"},
    },
    # ===== Relevancy =====
    "answer_relevancy": {
        "params": [],
        "requires": ["LLM"],
        "dimensions": ["relevancy"],
        "use_cases": ["回答是否切题"],
        "example": {"type": "answer_relevancy"},
    },
    "contextual_relevancy": {
        "params": [],
        "requires": ["LLM", "context"],
        "dimensions": ["retrieval_quality"],
        "use_cases": ["RAG 检索质量"],
        "example": {"type": "contextual_relevancy"},
    },
    "contextual_recall": {
        "params": [],
        "requires": ["LLM", "context", "expected"],
        "dimensions": ["retrieval_quality"],
        "use_cases": ["检索是否召回了支持答案所需信息"],
        "example": {"type": "contextual_recall"},
    },
    "contextual_precision": {
        "params": [],
        "requires": ["LLM", "context", "expected"],
        "dimensions": ["retrieval_quality"],
        "use_cases": ["检索排序质量"],
        "example": {"type": "contextual_precision"},
    },
    # ===== Safety =====
    "toxicity": {
        "params": [
            {"name": "threshold", "type": "float", "default": 0.7, "description": "通过阈值"},
            {"name": "use_llm", "type": "bool", "default": True, "description": "是否使用 LLM 检测（否则走规则）"},
        ],
        "requires": ["LLM (optional)"],
        "dimensions": ["safety"],
        "use_cases": ["有害/冒犯内容检测"],
        "example": {"type": "toxicity", "threshold": 0.7},
    },
    "bias": {
        "params": [
            {"name": "threshold", "type": "float", "default": 0.7, "description": "通过阈值"},
        ],
        "requires": ["LLM"],
        "dimensions": ["safety", "fairness"],
        "use_cases": ["人口学/社会偏见检测"],
        "example": {"type": "bias", "threshold": 0.7},
    },
    "safety": {
        "params": [
            {"name": "threshold", "type": "float", "default": 0.7, "description": "通过阈值"},
        ],
        "requires": ["LLM"],
        "dimensions": ["safety"],
        "use_cases": ["综合 toxicity + bias 检测"],
        "example": {"type": "safety", "threshold": 0.7},
    },
    # ===== Deterministic =====
    "exact_match": {
        "params": [
            {"name": "case_sensitive", "type": "bool", "default": True, "description": "区分大小写"},
            {"name": "strip", "type": "bool", "default": True, "description": "比较前去除首尾空白"},
        ],
        "requires": ["expected"],
        "dimensions": ["accuracy"],
        "use_cases": ["分类、是非题、固定答案任务"],
        "example": {"type": "exact_match", "case_sensitive": False},
    },
    "numeric_match": {
        "params": [
            {"name": "tolerance", "type": "float", "default": 1e-6, "description": "允许的数值误差"},
        ],
        "requires": ["expected"],
        "dimensions": ["accuracy"],
        "use_cases": ["数学题、数值预测任务"],
        "example": {"type": "numeric_match", "tolerance": 0.01},
    },
    "regex_match": {
        "params": [
            {"name": "pattern", "type": "str", "default": "", "description": "正则表达式"},
            {"name": "flags", "type": "int", "default": 0, "description": "re 标志位"},
            {"name": "required", "type": "bool", "default": True, "description": "True=必须匹配, False=必须不匹配"},
        ],
        "requires": [],
        "dimensions": ["format"],
        "use_cases": ["格式约束、模式校验"],
        "example": {"type": "regex_match", "pattern": "^\\d{3}-\\d{4}$"},
    },
    "json_valid": {
        "params": [
            {"name": "required_keys", "type": "List[str]", "default": None, "description": "必须包含的键"},
        ],
        "requires": [],
        "dimensions": ["format"],
        "use_cases": ["结构化输出验证、API 响应检测"],
        "example": {"type": "json_valid", "required_keys": ["name", "value"]},
    },
    "keyword": {
        "params": [
            {"name": "required_keywords", "type": "List[str]", "default": None, "description": "必含关键词"},
            {"name": "forbidden_keywords", "type": "List[str]", "default": None, "description": "禁含关键词"},
            {"name": "case_sensitive", "type": "bool", "default": False, "description": "区分大小写"},
        ],
        "requires": [],
        "dimensions": ["format", "instruction_following"],
        "use_cases": ["关键词约束、敏感词过滤"],
        "example": {"type": "keyword", "required_keywords": ["请", "您"], "forbidden_keywords": ["脏话"]},
    },
    "length": {
        "params": [
            {"name": "min_chars", "type": "int", "default": 0, "description": "最少字符数"},
            {"name": "max_chars", "type": "int", "default": 0, "description": "最多字符数（0=不限）"},
            {"name": "min_words", "type": "int", "default": 0, "description": "最少词数"},
            {"name": "max_words", "type": "int", "default": 0, "description": "最多词数"},
        ],
        "requires": [],
        "dimensions": ["format"],
        "use_cases": ["长度约束（推文 / SMS / 摘要）"],
        "example": {"type": "length", "max_chars": 280},
    },
    "contains_any": {
        "params": [
            {"name": "options", "type": "List[str]", "default": None, "description": "候选字符串集合"},
            {"name": "case_sensitive", "type": "bool", "default": False, "description": "区分大小写"},
        ],
        "requires": [],
        "dimensions": ["format"],
        "use_cases": ["枚举答案"],
        "example": {"type": "contains_any", "options": ["yes", "no"]},
    },
    "contains_all": {
        "params": [
            {"name": "required", "type": "List[str]", "default": None, "description": "全部需出现的字符串"},
            {"name": "case_sensitive", "type": "bool", "default": False, "description": "区分大小写"},
        ],
        "requires": [],
        "dimensions": ["format"],
        "use_cases": ["要点全覆盖"],
        "example": {"type": "contains_all", "required": ["条件1", "结论"]},
    },
    "custom_rubric": {
        "params": [
            {"name": "rubric", "type": "str", "default": "", "description": "自定义评分准则文本"},
            {"name": "model", "type": "str", "default": "gpt-4o-mini", "description": "评测模型"},
        ],
        "requires": ["LLM"],
        "dimensions": ["quality"],
        "use_cases": ["业务自定义 rubric 评分"],
        "example": {"type": "custom_rubric", "rubric": "客服话术是否礼貌、准确、专业"},
    },
    # ===== Agent =====
    "task_completion": {
        "params": [],
        "requires": ["LLM", "expected"],
        "dimensions": ["task_completion"],
        "use_cases": ["多步任务完成度"],
        "example": {"type": "task_completion"},
    },
    "tool_call_correctness": {
        "params": [],
        "requires": ["LLM"],
        "dimensions": ["tool_use"],
        "use_cases": ["Agent 工具选用与参数正确性"],
        "example": {"type": "tool_call_correctness"},
    },
    "conversation_quality": {
        "params": [],
        "requires": ["LLM"],
        "dimensions": ["conversation"],
        "use_cases": ["多轮对话质量"],
        "example": {"type": "conversation_quality"},
    },
    "role_adherence": {
        "params": [],
        "requires": ["LLM"],
        "dimensions": ["instruction_following"],
        "use_cases": ["角色/人设遵守度"],
        "example": {"type": "role_adherence"},
    },
    "task_efficiency": {
        "params": [
            {"name": "optimal_steps", "type": "int", "default": 1, "description": "理论最优步数"},
            {"name": "max_steps", "type": "int", "default": 10, "description": "上限步数（超过 0 分）"},
        ],
        "requires": [],
        "dimensions": ["efficiency"],
        "use_cases": ["Agent 走了多少步完成任务"],
        "example": {"type": "task_efficiency", "optimal_steps": 3, "max_steps": 8},
    },
    # ===== Ensemble =====
    "ensemble": {
        "params": [
            {"name": "scorers", "type": "List", "default": [], "description": "成员 scorer 列表（可为 dict 或实例）"},
            {"name": "aggregation", "type": "str", "default": "weighted", "description": "weighted / mean / min / max"},
            {"name": "weights", "type": "List[float]", "default": None, "description": "权重（与 scorers 对应）"},
            {"name": "threshold", "type": "float", "default": 0.5, "description": "通过阈值"},
        ],
        "requires": [],
        "dimensions": ["composite"],
        "use_cases": ["多维度加权综合评分"],
        "example": {
            "type": "ensemble",
            "scorers": [{"type": "answer_correctness"}, {"type": "faithfulness"}],
            "aggregation": "weighted",
            "weights": [0.6, 0.4],
        },
    },
    "threshold": {
        "params": [
            {"name": "scorer", "type": "Dict|BaseScorer", "default": None, "description": "被包装的 scorer"},
            {"name": "threshold", "type": "float", "default": 0.7, "description": "通过阈值"},
        ],
        "requires": [],
        "dimensions": [],
        "use_cases": ["把任意 scorer 转成 pass/fail"],
        "example": {"type": "threshold", "scorer": {"type": "answer_relevancy"}, "threshold": 0.8},
    },
    # ===== Similarity =====
    "bleu": {
        "params": [
            {"name": "max_n", "type": "int", "default": 4, "description": "最大 n-gram"},
            {"name": "weights", "type": "List[float]", "default": None, "description": "各 n-gram 权重"},
        ],
        "requires": ["expected"],
        "dimensions": ["similarity"],
        "use_cases": ["机器翻译、生成质量评估"],
        "example": {"type": "bleu", "max_n": 4},
    },
    "rouge": {
        "params": [
            {"name": "n", "type": "int", "default": 1, "description": "ROUGE-N 的 N"},
            {"name": "use_l", "type": "bool", "default": True, "description": "是否使用 ROUGE-L"},
        ],
        "requires": ["expected"],
        "dimensions": ["similarity"],
        "use_cases": ["摘要质量评估"],
        "example": {"type": "rouge", "n": 2, "use_l": True},
    },
    "f1_token": {
        "params": [],
        "requires": ["expected"],
        "dimensions": ["similarity"],
        "use_cases": ["QA token 级 F1"],
        "example": {"type": "f1_token"},
    },
    "edit_distance": {
        "params": [],
        "requires": ["expected"],
        "dimensions": ["similarity"],
        "use_cases": ["短文本相似度"],
        "example": {"type": "edit_distance"},
    },
    "jaccard": {
        "params": [],
        "requires": ["expected"],
        "dimensions": ["similarity"],
        "use_cases": ["集合相似度"],
        "example": {"type": "jaccard"},
    },
    "cosine_similarity": {
        "params": [],
        "requires": ["expected"],
        "dimensions": ["similarity"],
        "use_cases": ["TF-IDF 余弦相似度"],
        "example": {"type": "cosine_similarity"},
    },
    "semantic_similarity": {
        "params": [
            {"name": "model_name", "type": "str", "default": "all-MiniLM-L6-v2", "description": "Sentence-Transformer 模型名"},
            {"name": "threshold", "type": "float", "default": 0.5, "description": "通过阈值"},
        ],
        "requires": ["expected", "sentence-transformers"],
        "dimensions": ["similarity"],
        "use_cases": ["语义相似度（推荐替代 BLEU/ROUGE 做语义比较）"],
        "example": {"type": "semantic_similarity", "threshold": 0.7},
    },
    # ===== Code quality =====
    "code_quality": {
        "params": [{"name": "max_line_length", "type": "int", "default": 100, "description": "最大行长"}],
        "requires": [],
        "dimensions": ["code_quality"],
        "use_cases": ["Python 代码静态分析（AST）"],
        "example": {"type": "code_quality", "max_line_length": 88},
    },
    "sql_validation": {
        "params": [],
        "requires": [],
        "dimensions": ["code_quality"],
        "use_cases": ["SQL 语法与反模式检测"],
        "example": {"type": "sql_validation"},
    },
    "code_format": {
        "params": [{"name": "max_line_length", "type": "int", "default": 99, "description": "最大行长"}],
        "requires": [],
        "dimensions": ["code_quality"],
        "use_cases": ["PEP 8 格式检查"],
        "example": {"type": "code_format"},
    },
    "complexity": {
        "params": [{"name": "max_complexity", "type": "int", "default": 10, "description": "复杂度上限"}],
        "requires": [],
        "dimensions": ["code_quality"],
        "use_cases": ["圈复杂度评估"],
        "example": {"type": "complexity", "max_complexity": 8},
    },
    "code_security": {
        "params": [],
        "requires": [],
        "dimensions": ["safety"],
        "use_cases": ["Python 代码安全漏洞扫描"],
        "example": {"type": "code_security"},
    },
    # ===== Text analysis =====
    "readability": {
        "params": [{"name": "target_grade", "type": "float", "default": 8.0, "description": "目标年级水平"}],
        "requires": [],
        "dimensions": ["readability"],
        "use_cases": ["可读性评估（Flesch）"],
        "example": {"type": "readability", "target_grade": 10},
    },
    "lexical_diversity": {
        "params": [
            {"name": "min_ttr", "type": "float", "default": 0.3, "description": "最低 Type-Token Ratio"},
            {"name": "max_ttr", "type": "float", "default": 0.8, "description": "最高 Type-Token Ratio"},
        ],
        "requires": [],
        "dimensions": ["quality"],
        "use_cases": ["词汇多样性"],
        "example": {"type": "lexical_diversity"},
    },
    "sentiment": {
        "params": [{"name": "expected_polarity", "type": "str", "default": "", "description": "期望情感（positive/negative/neutral）"}],
        "requires": [],
        "dimensions": ["sentiment"],
        "use_cases": ["情感分析"],
        "example": {"type": "sentiment", "expected_polarity": "positive"},
    },
    "grammar_check": {
        "params": [],
        "requires": [],
        "dimensions": ["fluency"],
        "use_cases": ["基础语法检查（规则）"],
        "example": {"type": "grammar_check"},
    },
    "tone_analysis": {
        "params": [],
        "requires": [],
        "dimensions": ["tone"],
        "use_cases": ["语气/正式度分析"],
        "example": {"type": "tone_analysis"},
    },
    "coherence": {
        "params": [],
        "requires": [],
        "dimensions": ["coherence"],
        "use_cases": ["句间衔接度"],
        "example": {"type": "coherence"},
    },
    "fluency": {
        "params": [{"name": "max_ngram_repeat", "type": "float", "default": 0.3, "description": "最大 n-gram 重复率"}],
        "requires": [],
        "dimensions": ["fluency"],
        "use_cases": ["生成文本流畅度"],
        "example": {"type": "fluency"},
    },
    # ===== Format validation =====
    "datetime_format": {
        "params": [{"name": "pattern", "type": "str", "default": "", "description": "strptime 格式串，例如 %Y-%m-%d"}],
        "requires": [],
        "dimensions": ["format"],
        "use_cases": ["日期/时间格式验证"],
        "example": {"type": "datetime_format", "pattern": "%Y-%m-%d"},
    },
    "url_format": {
        "params": [{"name": "require_https", "type": "bool", "default": False, "description": "强制 https"}],
        "requires": [],
        "dimensions": ["format"],
        "use_cases": ["URL 格式验证"],
        "example": {"type": "url_format", "require_https": True},
    },
    "email_format": {
        "params": [],
        "requires": [],
        "dimensions": ["format"],
        "use_cases": ["邮箱格式验证"],
        "example": {"type": "email_format"},
    },
    "markdown_structure": {
        "params": [
            {"name": "require_headings", "type": "bool", "default": False, "description": "需要标题"},
            {"name": "require_code_block", "type": "bool", "default": False, "description": "需要代码块"},
            {"name": "require_list", "type": "bool", "default": False, "description": "需要列表"},
            {"name": "min_headings", "type": "int", "default": 0, "description": "最少标题数"},
        ],
        "requires": [],
        "dimensions": ["format"],
        "use_cases": ["Markdown 结构验证"],
        "example": {"type": "markdown_structure", "require_headings": True, "min_headings": 2},
    },
    "citation_check": {
        "params": [{"name": "min_citations", "type": "int", "default": 1, "description": "最少引用数量"}],
        "requires": [],
        "dimensions": ["format"],
        "use_cases": ["引用完整性"],
        "example": {"type": "citation_check", "min_citations": 3},
    },
    "instruction_following": {
        "params": [],
        "requires": [],
        "dimensions": ["instruction_following"],
        "use_cases": ["格式指令遵守度"],
        "example": {"type": "instruction_following"},
    },
    # ===== ML metrics =====
    "classification_metrics": {
        "params": [{"name": "average", "type": "str", "default": "macro", "description": "macro / micro / weighted"}],
        "requires": ["expected"],
        "dimensions": ["accuracy"],
        "use_cases": ["分类任务 P/R/F1"],
        "example": {"type": "classification_metrics", "average": "macro"},
    },
    "regression_metrics": {
        "params": [{"name": "metric", "type": "str", "default": "r2", "description": "r2 / mae / mse / rmse"}],
        "requires": ["expected"],
        "dimensions": ["accuracy"],
        "use_cases": ["回归任务误差度量"],
        "example": {"type": "regression_metrics", "metric": "rmse"},
    },
    "ranking_metrics": {
        "params": [
            {"name": "k", "type": "int", "default": 10, "description": "Top-K"},
            {"name": "metric", "type": "str", "default": "ndcg", "description": "ndcg / mrr / map"},
        ],
        "requires": ["expected"],
        "dimensions": ["retrieval_quality"],
        "use_cases": ["排序/检索质量"],
        "example": {"type": "ranking_metrics", "k": 10, "metric": "ndcg"},
    },
}


# -------- Evaluators --------

EVALUATOR_METADATA: Dict[str, Dict[str, Any]] = {
    "gsm8k": {
        "params": [
            {"name": "split", "type": "str", "default": "test", "description": "数据集划分（train / test）"},
            {"name": "judge", "type": "Dict", "default": {"type": "numeric_answer"}, "description": "判分方式"},
        ],
        "use_cases": ["数学推理基准（小学算术）", "多步推理验证"],
        "example": {"evaluators": {"gsm8k": {"config": {"split": "test", "judge": {"type": "numeric_answer"}}}}},
    },
    "humaneval": {
        "params": [
            {"name": "timeout", "type": "int", "default": 30, "description": "代码执行超时（秒）"},
            {"name": "judge", "type": "Dict", "default": {"type": "code_execution"}, "description": "判分方式（默认执行测试）"},
        ],
        "use_cases": ["Python 代码生成评估", "pass@1 准确度"],
        "example": {"evaluators": {"humaneval": {"config": {"timeout": 30}}}},
    },
    "mmlu": {
        "params": [
            {"name": "split", "type": "str", "default": "test", "description": "数据集划分"},
            {"name": "subset", "type": "str", "default": "all", "description": "学科子集，如 stem / humanities"},
            {"name": "judge", "type": "Dict", "default": {"type": "exact_match"}, "description": "判分方式"},
        ],
        "use_cases": ["广义知识与推理（57 学科多选题）"],
        "example": {"evaluators": {"mmlu": {"config": {"subset": "stem"}}}},
    },
    "coding": {
        "params": [
            {"name": "timeout", "type": "int", "default": 30, "description": "执行超时"},
            {"name": "task_file", "type": "str", "default": "scenarios/coding.yaml", "description": "任务定义文件"},
            {"name": "judges", "type": "List[Dict]", "default": [], "description": "判分链"},
        ],
        "use_cases": ["代码生成/调试/重构动态评估"],
        "example": {"evaluators": {"coding": {"config": {"task_file": "scenarios/coding.yaml"}}}},
    },
    "multi_turn": {
        "params": [
            {"name": "max_turns", "type": "int", "default": 10, "description": "最大轮数"},
            {"name": "conversation_file", "type": "str", "default": "scenarios/multi_turn.yaml", "description": "对话脚本"},
            {"name": "judges", "type": "List[Dict]", "default": [], "description": "判分链"},
        ],
        "use_cases": ["多轮对话评测", "上下文保持验证"],
        "example": {"evaluators": {"multi_turn": {"config": {"max_turns": 8}}}},
    },
    "tool_use": {
        "params": [
            {"name": "max_turns", "type": "int", "default": 10, "description": "最大轮数"},
            {"name": "scenario_file", "type": "str", "default": "scenarios/tool_use.yaml", "description": "场景文件"},
            {"name": "sandbox", "type": "str", "default": "local", "description": "沙箱（local / docker）"},
            {"name": "sandbox_config", "type": "Dict", "default": {}, "description": "沙箱参数"},
            {"name": "judges", "type": "List[Dict]", "default": [], "description": "判分链"},
        ],
        "use_cases": ["Agent 工具调用评估", "规划与错误恢复"],
        "example": {"evaluators": {"tool_use": {"config": {"sandbox": "local", "max_turns": 6}}}},
    },
    "bias": {
        "params": [
            {"name": "bias_file", "type": "str", "default": "attacks/bias.yaml", "description": "偏见用例文件"},
            {"name": "judge", "type": "Dict", "default": {"type": "bias_detection"}, "description": "判分方式"},
        ],
        "use_cases": ["人口学/刻板印象/公平性对抗"],
        "example": {"evaluators": {"bias": {"config": {"bias_file": "attacks/bias.yaml"}}}},
    },
    "injection": {
        "params": [
            {"name": "injection_file", "type": "str", "default": "attacks/injection.yaml", "description": "Prompt 注入用例"},
            {"name": "judge", "type": "Dict", "default": {"type": "injection_detection"}, "description": "判分方式"},
        ],
        "use_cases": ["Prompt 注入安全测试"],
        "example": {"evaluators": {"injection": {"config": {"injection_file": "attacks/injection.yaml"}}}},
    },
    "jailbreak": {
        "params": [
            {"name": "attack_config", "type": "str", "default": "attacks/comprehensive.yaml", "description": "攻击配置"},
            {"name": "safety_judge", "type": "Dict", "default": {"type": "safety_classifier"}, "description": "安全判分器"},
            {"name": "refusal_judge", "type": "Dict", "default": {"type": "refusal_detection"}, "description": "拒答判分器"},
        ],
        "use_cases": ["越狱/对抗稳健性", "拒答行为评估"],
        "example": {"evaluators": {"jailbreak": {"config": {"attack_config": "attacks/comprehensive.yaml"}}}},
    },
    "custom_eval": {
        "params": [
            {"name": "evaluations", "type": "List[Dict]", "default": [], "description": "评测列表，每项含 id / task_source / prompt / scoring"},
        ],
        "use_cases": ["自定义数据集/Rubric 评测", "Trace-to-Eval 输出"],
        "example": {
            "evaluators": {
                "custom_eval": {
                    "config": {
                        "evaluations": [
                            {
                                "id": "demo",
                                "name": "Demo Eval",
                                "task_source": {"type": "inline", "items": []},
                                "prompt": {"mode": "generate", "template": "{input}"},
                                "scoring": {
                                    "threshold": 0.7,
                                    "aggregation": "weighted",
                                    "scorers": [{"type": "answer_correctness", "weight": 1}],
                                },
                            }
                        ]
                    }
                }
            }
        },
    },
}


def get_scorer_metadata(scorer_type: str) -> Dict[str, Any]:
    return SCORER_METADATA.get(scorer_type, {"params": [], "requires": [], "dimensions": [], "use_cases": [], "example": {"type": scorer_type}})


def get_evaluator_metadata(evaluator_name: str) -> Dict[str, Any]:
    return EVALUATOR_METADATA.get(evaluator_name, {"params": [], "use_cases": [], "example": {}})


def list_scorer_metadata() -> List[str]:
    return list(SCORER_METADATA.keys())


def list_evaluator_metadata() -> List[str]:
    return list(EVALUATOR_METADATA.keys())