# 01: Mask the prompt and show the screen note

**What to build:** A dashed social security number, a Luhn-valid card number, or the value after `password:` or `api_key:` is replaced before the prompt is stored or sent to the lead. The user's bubble shows that masked prompt before the lead replies, a new conversation's title is the first 30 characters of the masked prompt, and a later turn sends the lead the stored masked prompt. When something was masked, one screen note sits on that message as a status line. An ordinary prompt stays quiet. Record the ADR for this shape: the mask and the phrase list sit on the prompt and the lead's final text, the cost check sits before every model call, and memory, worker tasks, and tool-call narration stay as written.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] A dashed social security number, such as `123-45-6789`, is replaced with `[ssn]` in the stored prompt and in what is sent to the lead
- [ ] Nine digits with no dashes are left as written
- [ ] A card number of 13 to 19 digits, spaces or dashes allowed, is replaced with `[card number]` when it passes the Luhn check
- [ ] The same shape of number is left as written when it fails the Luhn check
- [ ] A run of digits shorter than 13 or longer than 19 is left as written
- [ ] `password:` or `api_key:`, in any case, keeps the label and replaces the rest of that line with `[secret]`
- [ ] Text before the label on that line is still scanned for a social security number or a card number
- [ ] The value after the label is left as one secret, so a card number inside that value is not also rewritten as a card
- [ ] Several masks in one prompt become one screen note, kinds in this order — social security number, card number, secret — with a plural when there is more than one
- [ ] That note reads `Screen: masked 1 social security number, 2 card numbers, 1 secret` for those counts
- [ ] A prompt with nothing to mask shows no "allowed" line and no screen note on the user's message
- [ ] The stream emits `prompt` with the stored prompt text before the lead starts, and the bubble shows the masked prompt before the lead replies
- [ ] A new conversation's title is the first 30 characters of the masked prompt
- [ ] A later turn sends the lead the stored masked prompt
- [ ] The user's message carries that mask note in `screen_notes` when the turn was not refused. The note is not a separate message. After `done`, the thread is the stored messages, so a live note is not shown a second time
- [ ] The client draws each screen note as a status line on that message, in the same family as a tool pill, not as a user or assistant bubble
- [ ] An ADR records that the mask and the phrase list sit on the prompt and the lead's final text, the cost check sits before every model call, and memory, worker tasks, and tool-call narration stay as written
