"""Example agent for testing."""


class MyAgent:
    """A simple agent wrapper for evaluation."""

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.0):
        self.model = model
        self.temperature = temperature
        self.name = "my_agent"
        self.version = "1.0"
        self._client = None

    def _get_client(self):
        if self._client is None:
            import openai
            self._client = openai.OpenAI()
        return self._client

    def generate(self, prompt: str) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
        )
        return response.choices[0].message.content.strip()

    def chat(self, messages: list) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        return response.choices[0].message.content.strip()

    def act(self, state: dict, available_tools: list, goal: str) -> dict:
        prompt = f"""Goal: {goal}
Current State: {state}
Available Tools: {available_tools}

Decide on the next action. Return a JSON with keys: type ("tool_call" or "finish"), tool (if type is "tool_call"), params (dict of params)."""
        response = self.generate(prompt)
        import json, re
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {"type": "finish"}