# ADR 0001: Screen sits on the prompt and the lead's final text

## Status

Accepted

## Context

The screen masks secrets in user text, refuses some prompts, and caps model spend. Those checks could wrap every model call, or they could sit only where the product actually changes stored or shown text.

## Decision

The mask and the phrase list sit on the user's prompt and on the lead's final text. The cost check sits before every model call, from the lead or a worker. Memory, worker tasks, and assistant text saved with a tool call stay as written.

## Consequences

Prompt and closing-answer masking share one path. Tool-call narration streams without waiting on the screen. Caps still cover workers because the cost check runs before each call. Wrapping every model call would have rewritten tasks and memory the product means to leave alone.
