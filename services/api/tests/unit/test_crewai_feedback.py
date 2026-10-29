import json
import os


def test_nonblocking_human_feedback_round_trip(tmp_path):
    os.environ["CREWAI_TRACING_ENABLED"] = "false"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    from crewai.flow.flow import Flow, start, listen
    from crewai.flow.human_feedback import human_feedback
    from crewai.flow.async_feedback import HumanFeedbackPending
    from crewai.flow.persistence.sqlite import SQLiteFlowPersistence
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

    persistence = SQLiteFlowPersistence(db_path=str(tmp_path / "feedback.db"))
    flow = ReviewFlow(tracing=False, persistence=persistence)
    pending = flow.kickoff()
    assert isinstance(pending, HumanFeedbackPending)
    assert json.loads(flow.state.model_dump_json())["steps"] == 1
    restored = ReviewFlow.from_pending(pending.context.flow_id, persistence=persistence)
    assert restored.resume('{"approved": true}') is True
    assert restored.state.steps == 2
