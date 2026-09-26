import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react"
import {
  createConversation,
  getConversation,
  listConversations,
  sendPrompt,
  type ChatMessage,
  type Conversation,
} from "./api.ts"

function displayTitle(title: string): string {
  return title.trim() === "" ? "New chat" : title
}

function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof Error ? cause.message : fallback
}

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listConversations()
      .then(setConversations)
      .catch((cause: unknown) => {
        setError(errorMessage(cause, "Could not load conversations"))
      })
  }, [])

  async function openConversation(conversationId: string) {
    setSelectedId(conversationId)
    setError(null)
    try {
      const detail = await getConversation(conversationId)
      setMessages(detail.messages)
    } catch (cause: unknown) {
      setError(errorMessage(cause, "Could not open that conversation"))
    }
  }

  function startNewChat() {
    setSelectedId(null)
    setMessages([])
    setError(null)
    setDraft("")
  }

  async function submitPrompt() {
    const prompt = draft.trim()
    if (prompt === "" || sending) {
      return
    }
    setSending(true)
    setError(null)
    try {
      const conversationId = selectedId ?? (await createConversation()).id
      setSelectedId(conversationId)
      await sendPrompt(conversationId, prompt)
      const [nextConversations, detail] = await Promise.all([
        listConversations(),
        getConversation(conversationId),
      ])
      setConversations(nextConversations)
      setMessages(detail.messages)
      setDraft("")
    } catch (cause: unknown) {
      setError(errorMessage(cause, "Could not save the prompt"))
    } finally {
      setSending(false)
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    void submitPrompt()
  }

  function onComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      void submitPrompt()
    }
  }

  const selected = conversations.find((conversation) => conversation.id === selectedId)

  return (
    <div className="flex h-full flex-col bg-stone-950 text-stone-100 md:flex-row">
      <aside className="flex max-h-56 shrink-0 flex-col border-b border-stone-800 md:max-h-none md:w-72 md:border-r md:border-b-0">
        <div className="flex items-center justify-between px-4 py-4">
          <p className="text-sm font-medium tracking-wide text-stone-400">Conversations</p>
          <button
            type="button"
            onClick={startNewChat}
            className="rounded-md px-2 py-1 text-sm text-stone-200 hover:bg-stone-800"
          >
            New chat
          </button>
        </div>
        <ul className="flex-1 overflow-y-auto px-2 pb-3">
          {conversations.length === 0 ? (
            <li className="px-2 py-3 text-sm text-stone-500">No conversations yet</li>
          ) : (
            conversations.map((conversation) => (
              <li key={conversation.id}>
                <button
                  type="button"
                  onClick={() => void openConversation(conversation.id)}
                  className={`w-full truncate rounded-md px-3 py-2 text-left text-sm ${
                    conversation.id === selectedId
                      ? "bg-stone-800 text-stone-50"
                      : "text-stone-300 hover:bg-stone-900"
                  }`}
                >
                  {displayTitle(conversation.title)}
                </button>
              </li>
            ))
          )}
        </ul>
      </aside>

      <main className="flex min-h-0 flex-1 flex-col">
        <header className="border-b border-stone-800 px-6 py-4">
          <h1 className="truncate text-base font-medium">
            {selected ? displayTitle(selected.title) : "New chat"}
          </h1>
        </header>

        <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-6 py-6">
          {messages.length === 0 ? (
            <p className="m-auto max-w-sm text-center text-sm text-stone-500">
              Send a message to start a conversation. It will be named from your first prompt.
            </p>
          ) : (
            messages.map((message) => (
              <div
                key={message.id}
                className="ml-auto max-w-[40rem] rounded-2xl bg-stone-800 px-4 py-3 text-sm leading-6"
              >
                <p className="whitespace-pre-wrap">{message.content}</p>
              </div>
            ))
          )}
        </div>

        <form onSubmit={onSubmit} className="border-t border-stone-800 px-6 py-4">
          {error ? <p className="mb-2 text-sm text-red-300">{error}</p> : null}
          <div className="flex items-end gap-3">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={onComposerKeyDown}
              rows={2}
              placeholder="Write a message"
              aria-label="Message"
              className="min-h-16 flex-1 resize-none rounded-xl border border-stone-700 bg-stone-900 px-4 py-3 text-sm outline-none placeholder:text-stone-500 focus:border-stone-500"
            />
            <button
              type="submit"
              disabled={sending || draft.trim() === ""}
              className="rounded-xl bg-stone-100 px-4 py-3 text-sm font-medium text-stone-950 disabled:opacity-40"
            >
              {sending ? "Sending" : "Send"}
            </button>
          </div>
        </form>
      </main>
    </div>
  )
}
