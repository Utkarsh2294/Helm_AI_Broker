"""Trace only operation metadata; source documents and model prompts are never attributes."""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider


def instrument(app):
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from app.config import settings
    provider = TracerProvider()
    if settings().otlp_endpoint:
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings().otlp_endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
