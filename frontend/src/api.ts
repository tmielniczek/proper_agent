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

export async function sendPrompt(conversationId: string, prompt: string): Promise<void> {
  const response = await fetch(`/api/conversations/${conversationId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  })
  if (!response.ok || !response.body) {
    throw new Error("Could not save the prompt")
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let body = ""
  for (;;) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    body += decoder.decode(value, { stream: true })
  }
  if (!body.includes("event: done")) {
    throw new Error("Could not save the prompt")
  }
}
