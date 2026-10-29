import json
import os


def test_nonblocking_human_feedback_round_trip():
    os.environ["CREWAI_TRACING_ENABLED"] = "false"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    from crewai.flow.flow import Flow, start, listen
    from crewai.flow.human_feedback import human_feedback
    from crewai.flow.async_feedback import HumanFeedbackPending
    from pydantic import BaseModel

    class State(BaseModel):
        approved: bool = False
        steps: int = 0

    class PendingProvider:
        def request_feedback(self, context, flow):
            raise HumanFeedbackPending(context=context)

    class ReviewFlow(Flow[State]):
        @start()
        @human_feedback(message="Review fictional draft", provider=PendingProvider())
        def review(self):
            self.state.steps += 1
            return "Fictional draft"

        @listen(review)
        def finish(self, result):
            self.state.approved = json.loads(result.feedback)["approved"]
            self.state.steps += 1
            return self.state.approved

    flow = ReviewFlow(tracing=False)
    pending = flow.kickoff()
    assert isinstance(pending, HumanFeedbackPending)
    assert json.loads(flow.state.model_dump_json())["steps"] == 1
    assert flow.resume('{"approved": true}') is True
    assert flow.state.steps == 2
