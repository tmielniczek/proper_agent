# ADR 0002: One console trace per turn

## Status

Accepted

## Context

A turn calls the language model, runs tools, and may start workers, and none of that timing or token use is visible outside the thread. The screen note shows cost after a finished turn, but not the shape of the work. A phrase-list or budget refusal never appears as measured traffic. Spans could wrap only model calls, copy the prompt into attributes, treat a stop as an error, or export over OTLP to a collector.

## Decision

Each handled prompt emits one console trace whose root span is the turn. Model calls and tool runs nest under that turn as child spans. Spans carry operational attributes only: no prompt text, refusal text, tool arguments, tool results, memory, task text, or screen-note text. OpenTelemetry status is ERROR only for `app.status` `error` and `provider_rejection`; `ok`, `stopped`, `cancelled`, and `refused` stay OK with no `error.type`. The screen stays as in ADR 0001.

## Consequences

A gated prompt still shows up as a `refused` turn with no model-call span. A finished reply is an `ok` turn. The running app prints spans on the console with no collector. Rejected alternatives were spans only around model calls, copying the prompt into the span, treating a stop as an error, and exporting OTLP.
