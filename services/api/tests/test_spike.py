"""P0: execute actual CrewAI objects using a local, deterministic model stub."""


def test_crewai_flow_and_two_task_crew_without_provider_credentials(monkeypatch):
    monkeypatch.setenv("CREWAI_TRACING_ENABLED", "false")
    monkeypatch.setenv("CREWAI_DISABLE_TELEMETRY", "true")
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    from crewai import Agent, BaseLLM, Crew, Process, Task
    from crewai.flow.flow import Flow, listen, start

    calls = []

    class LocalModel(BaseLLM):
        def call(self, messages, **kwargs):
            calls.append(True)
            return "Final Answer: ok"

        def supports_function_calling(self):
            return False

    class PlumbingFlow(Flow):
        @start()
        def first(self):
            return "ok"

        @listen(first)
        def second(self, result):
            return result + " complete"

    assert PlumbingFlow(tracing=False).kickoff() == "ok complete"
    agent = Agent(
        role="Fictional plumbing checker",
        goal="Return a fixed local fixture",
        backstory="A deterministic test, with no customer data or external tools.",
        llm=LocalModel(model="local-fixture", provider="local"),
        allow_delegation=False,
        max_iter=1,
    )
    tasks = [Task(description=f"Verify fixture {i}", expected_output="ok", agent=agent) for i in range(2)]
    result = Crew(agents=[agent], tasks=tasks, process=Process.sequential, tracing=False).kickoff()
    assert result.raw == "ok"
    assert len(result.tasks_output) == 2
    assert len(calls) >= 2
