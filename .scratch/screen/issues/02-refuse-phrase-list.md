# 02: Refuse a prompt on the phrase list

**What to build:** A prompt that contains any phrase on the fixed list is refused before any model call. The masked prompt is stored, the mask note is skipped, and the only reply is one Stopped sentence delivered as a single piece of assistant text. A paraphrase that is not on the list goes through.

**Blocked by:** 01 Mask the prompt and show the screen note

**Status:** ready-for-agent

- [x] The turn is refused when the original prompt contains any of these phrases, in any case: "ignore previous instructions", "ignore all previous instructions", "ignore your instructions", "ignore the instructions", "disregard your instructions", "disregard the instructions", "reveal your system prompt", "show your system prompt", "print your system prompt", "what is your system prompt"
- [x] A phrase inside a longer sentence refuses the turn
- [x] A paraphrase that is not on that list goes through
- [x] A phrase that sits only after `password:` or `api_key:` still refuses the turn
- [x] The refusal stores the masked prompt, writes no screen note, and emits no `screen` event
- [x] The only reply is `Stopped: that request asks to ignore instructions or reveal the system prompt.`
- [x] That reply is one `delta` of the Stopped sentence, then `done`, and the turn is marked done. The stream still emits `prompt` with the stored prompt before that reply
- [x] The refusal makes no model call
