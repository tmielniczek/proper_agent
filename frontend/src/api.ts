export type Conversation = {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export type ChatMessage = {
  id: string
  role: string
  content: string | null
  created_at: string
}

type ConversationDetail = Conversation & {
  messages: ChatMessage[]
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

type StreamEvent = {
  event: string
  data: { text?: string; error?: string }
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

export async function sendPrompt(
  conversationId: string,
  prompt: string,
  onDelta: (text: string) => void,
): Promise<void> {
  const response = await fetch(`/api/conversations/${conversationId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
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
    if (parsed.event === "delta" && parsed.data.text) {
      onDelta(parsed.data.text)
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
  if (!sawDone) {
    throw new Error("Could not get a reply")
  }
}
