from agent_eval.web.events import EventBus


class DummyHooks:
    def __init__(self):
        self.callbacks = {}

    def register(self, event, callback):
        self.callbacks[event] = callback


class DummyOrchestrator:
    def __init__(self):
        self.hooks = DummyHooks()


def test_event_bus_publish_and_stream():
    bus = EventBus()
    bus.create_run("run-1")
    bus.publish("run-1", "evaluation_complete", {"summary": {"overall_score": 1.0}})

    event = next(bus.stream("run-1"))

    assert event["event"] == "evaluation_complete"
    assert "overall_score" in event["data"]


def test_event_bus_attach_hooks():
    bus = EventBus()
    orch = DummyOrchestrator()

    bus.attach_orchestrator_hooks("run-1", orch)

    assert "task_complete" in orch.hooks.callbacks
    assert "evaluation_complete" in orch.hooks.callbacks
