"""Two-task A1 prototype crew using a local model fixture, with no provider calls.

The provider gateway remains opt-in and region-gated. Medical wording and identity
never enter this crew; the authoritative, verbatim source stays in the encrypted DNR.
"""

import json
from app.agents.intake import research_request
from app.compliance.medical_ambiguity import check_medical_ambiguity
from app.compliance.medical_firewall import llm_profile
from app.schemas import DNRRecord, DomainError, Needs


def research_with_crew(request, model=None):
    if check_medical_ambiguity(request.model_dump()):
        raise DomainError("H5: medical wording requires a human review", 409)
    from crewai import Agent, BaseLLM, Crew, Process, Task

    draft = research_request(request)
    fixture = {**llm_profile(request), "record": draft.record.model_dump(mode="json")}

    class LocalFixture(BaseLLM):
        def call(self, messages, **kwargs):
            return "Final Answer: " + json.dumps(fixture)

        def supports_function_calling(self):
            return False

    model = model or LocalFixture(model="local-a1-fixture", provider="local")
    common = {"llm": model, "allow_delegation": False, "max_iter": 2, "verbose": False}
    analyst = Agent(
        role="PMI needs analyst",
        goal="Extract only the supplied stated requirements.",
        backstory="Use source facts; never infer clinical information or approve advice.",
        **common,
    )
    drafter = Agent(
        role="Demands and needs drafter",
        goal="Draft a structured record for broker review.",
        backstory="All drafts require a human G0 decision before RFQs can be released.",
        **common,
    )
    extract = Task(
        description="Extract the stated needs from this minimised fixture: "
        + json.dumps(llm_profile(request)),
        expected_output="JSON containing needs and the clinical-underwriting flag only.",
        agent=analyst,
    )
    write = Task(
        description="Draft the structured needs record from the analyst output and this record template: "
        + json.dumps(fixture["record"]),
        expected_output="JSON with needs and record. Preserve supplied values and references.",
        agent=drafter,
        context=[extract],
    )
    result = Crew(
        agents=[analyst, drafter],
        tasks=[extract, write],
        process=Process.sequential,
        tracing=False,
        verbose=False,
    ).kickoff()
    parsed = json.loads(result.raw)
    needs = Needs.model_validate(parsed["needs"])
    if needs != request.needs:
        raise DomainError("H2: extracted requirements need human verification", 422)
    draft.record = DNRRecord.model_validate(parsed["record"])
    return draft.model_dump(mode="json")
