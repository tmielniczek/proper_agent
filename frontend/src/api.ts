export type Conversation = {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export type ToolCallRecord = {
  id: string
  type: string
  function: {
    name: string
    arguments: string
  }
}

export type ChatMessage = {
  id: string
  role: string
  content: string | null
  created_at: string
  tool_calls?: ToolCallRecord[] | null
  tool_call_id?: string | null
  screen_notes?: string[] | null
}

export type Compaction = {
  brief: string
  after_message_id: string | null
}

export type TokenStats = {
  tokens: number
  context_window: number
  compaction_line: number
}

type ConversationDetail = Conversation & {
  messages: ChatMessage[]
  compaction: Compaction | null
}

async function readJson<T>(response: Response, message: string): Promise<T> {
  if (!response.ok) {
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export function listConversations(): Promise<Conversation[]> {
  return fetch("/api/conversations").then((response) =>
    readJson<Conversation[]>(response, "Could not load conversations"),
  )
}

export function createConversation(): Promise<Conversation> {
  return fetch("/api/conversations", { method: "POST" }).then((response) =>
    readJson<Conversation>(response, "Could not start a conversation"),
  )
}

export function getConversation(conversationId: string): Promise<ConversationDetail> {
  return fetch(`/api/conversations/${conversationId}`).then((response) =>
    readJson<ConversationDetail>(response, "Could not open that conversation"),
  )
}

export function getTokenStats(conversationId: string): Promise<TokenStats> {
  return fetch(`/api/conversations/${conversationId}/tokens`).then((response) =>
    readJson<TokenStats>(response, "Could not load token use"),
  )
}

type StreamEvent = {
  event: string
  data: {
    text?: string
    error?: string
    tool?: string
    display_text?: string
    call_id?: string
    after_message_id?: string
  }
}

export type ChatHandlers = {
  onPrompt?: (text: string) => void
  onScreen?: (text: string) => void
  onDelta: (text: string) => void
  onToolStart: (tool: string, displayText: string, callId?: string) => void
  onToolEnd: (tool: string, callId?: string) => void
  onRefused: (displayText: string) => void
  onCompaction?: (brief: string, afterMessageId: string | null) => void
}

function parseSseBlock(block: string): StreamEvent | null {
  if (block.trim() === "" || block.trimStart().startsWith(":")) {
    return null
  }
  let event = "message"
  let data: StreamEvent["data"] | null = null
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim()
    } else if (line.startsWith("data:")) {
      data = JSON.parse(line.slice("data:".length).trim()) as StreamEvent["data"]
    }
  }
  if (data === null) {
    return null
  }
  return { event, data }
}

export function cancelConversation(conversationId: string): Promise<void> {
  return fetch(`/api/conversations/${conversationId}/cancel`, { method: "POST" }).then(
    (response) => {
      if (!response.ok) {
        throw new Error("Could not cancel the reply")
      }
    },
  )
}

export async function sendPrompt(
  conversationId: string,
  prompt: string,
  handlers: ChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/conversations/${conversationId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
    signal,
  })
  if (!response.ok || !response.body) {
    throw new Error("Could not get a reply")
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let sawDone = false

  const handleBlock = (block: string) => {
    const parsed = parseSseBlock(block)
    if (parsed === null) {
      return
    }
    if (parsed.event === "prompt" && parsed.data.text) {
      handlers.onPrompt?.(parsed.data.text)
    }
    if (parsed.event === "screen" && parsed.data.text) {
      handlers.onScreen?.(parsed.data.text)
    }
    if (parsed.event === "delta" && parsed.data.text) {
      handlers.onDelta(parsed.data.text)
    }
    if (parsed.event === "tool_start" && parsed.data.tool) {
      handlers.onToolStart(
        parsed.data.tool,
        parsed.data.display_text ?? parsed.data.tool,
        parsed.data.call_id,
      )
    }
    if (parsed.event === "tool_end" && parsed.data.tool) {
      handlers.onToolEnd(parsed.data.tool, parsed.data.call_id)
    }
    if (parsed.event === "refused_task" && parsed.data.display_text) {
      handlers.onRefused(parsed.data.display_text)
    }
    if (parsed.event === "compaction" && parsed.data.text) {
      handlers.onCompaction?.(parsed.data.text, parsed.data.after_message_id ?? null)
    }
    if (parsed.event === "error") {
      throw new Error(parsed.data.error ?? "Could not get a reply")
    }
    if (parsed.event === "done") {
      sawDone = true
    }
  }

  for (;;) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split("\n\n")
    buffer = blocks.pop() ?? ""
    for (const block of blocks) {
      handleBlock(block)
    }
  }
  buffer += decoder.decode()
  if (buffer.trim() !== "") {
    handleBlock(buffer)
  }
  if (signal?.aborted) {
    throw new DOMException("The operation was aborted.", "AbortError")
  }
  if (!sawDone) {
    throw new Error("Could not get a reply")
  }
}
