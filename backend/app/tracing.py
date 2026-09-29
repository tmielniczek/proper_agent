from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Tracer

SERVICE_NAME = "agent-chat"


def build_tracer(span_exporter: SpanExporter | None = None) -> Tracer:
    exporter = ConsoleSpanExporter() if span_exporter is None else span_exporter
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(SERVICE_NAME)
