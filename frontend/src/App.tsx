import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react"
import {
  createConversation,
  getConversation,
  listConversations,
  sendPrompt,
  type ChatMessage,
  type Conversation,
} from "./api.ts"

const TOOL_LABELS: Record<string, string> = {
  get_weather: "Checking weather...",
  search_database: "Searching database...",
  calculator: "Calculating...",
}

type LiveSegment =
  | { kind: "text"; id: string; text: string }
  | { kind: "pill"; id: string; tool: string; text: string; status: "running" | "complete" }

function ToolPill({ text, status }: { text: string; status: "running" | "complete" }) {
  const running = status === "running"
  return (
    <p
      role="status"
      data-status={status}
      aria-label={running ? text : `${text} complete`}
      className={`mr-auto inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
        running
          ? "animate-pulse border-amber-800 bg-amber-950/50 text-amber-100"
          : "border-stone-700 bg-stone-900 text-stone-300"
      }`}
    >
      <span aria-hidden="true">{running ? "●" : "✓"}</span>
      {text}
    </p>
  )
}

function MessageBubble({ role, content }: { role: string; content: string }) {
  const isUser = role === "user"
  return (
    <div
      className={`max-w-[40rem] rounded-2xl px-4 py-3 text-sm leading-6 ${
        isUser ? "ml-auto bg-stone-800" : "mr-auto border border-stone-800 bg-stone-900"
      }`}
    >
      <p className="whitespace-pre-wrap">{content}</p>
    </div>
  )
}

function PersistedTurn({ message }: { message: ChatMessage }) {
  if (message.role === "tool") {
    return null
  }
  const pills = (message.tool_calls ?? []).map((call) => ({
    id: call.id,
    text: TOOL_LABELS[call.function.name] ?? call.function.name,
  }))
  const text = message.content ?? ""
  if (text === "" && pills.length === 0) {
    return null
  }
  return (
    <div className="flex flex-col gap-2">
      {text !== "" ? <MessageBubble role={message.role} content={text} /> : null}
      {pills.map((pill) => (
        <ToolPill key={pill.id} text={pill.text} status="complete" />
      ))}
    </div>
  )
}

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
  const [liveSegments, setLiveSegments] = useState<LiveSegment[]>([])
  const threadRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listConversations()
      .then(setConversations)
      .catch((cause: unknown) => {
        setError(errorMessage(cause, "Could not load conversations"))
      })
  }, [])

  useEffect(() => {
    const thread = threadRef.current
    if (thread) {
      thread.scrollTop = thread.scrollHeight
    }
  }, [messages, liveSegments])

  async function openConversation(conversationId: string) {
    setSelectedId(conversationId)
    setError(null)
    try {
      const detail = await getConversation(conversationId)
      setLiveSegments([])
      setMessages(detail.messages)
    } catch (cause: unknown) {
      setError(errorMessage(cause, "Could not open that conversation"))
    }
  }

  function startNewChat() {
    setSelectedId(null)
    setMessages([])
    setLiveSegments([])
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
    setDraft("")
    setLiveSegments([])
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", content: prompt, created_at: "" },
    ])
    try {
      const conversationId = selectedId ?? (await createConversation()).id
      setSelectedId(conversationId)
      await sendPrompt(conversationId, prompt, {
        onDelta: (text) => {
          setLiveSegments((current) => {
            const last = current[current.length - 1]
            if (last?.kind === "text") {
              return [...current.slice(0, -1), { ...last, text: `${last.text}${text}` }]
            }
            return [...current, { kind: "text", id: crypto.randomUUID(), text }]
          })
        },
        onToolStart: (tool, displayText) => {
          setLiveSegments((current) => [
            ...current,
            { kind: "pill", id: crypto.randomUUID(), tool, text: displayText, status: "running" },
          ])
        },
        onToolEnd: (tool) => {
          setLiveSegments((current) => {
            const index = current.findIndex(
              (segment) =>
                segment.kind === "pill" && segment.tool === tool && segment.status === "running",
            )
            if (index === -1) {
              return current
            }
            const next = current.slice()
            const pill = next[index]
            if (pill?.kind === "pill") {
              next[index] = { ...pill, status: "complete" }
            }
            return next
          })
        },
      })
      const [nextConversations, detail] = await Promise.all([
        listConversations(),
        getConversation(conversationId),
      ])
      setConversations(nextConversations)
      setLiveSegments([])
      setMessages(detail.messages)
    } catch (cause: unknown) {
      setError(errorMessage(cause, "Could not get a reply"))
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

        <div ref={threadRef} className="flex flex-1 flex-col gap-3 overflow-y-auto px-6 py-6">
          {messages.length === 0 && liveSegments.length === 0 ? (
            <p className="m-auto max-w-sm text-center text-sm text-stone-500">
              Send a message to start a conversation. It will be named from your first prompt.
            </p>
          ) : (
            <>
              {messages.map((message) => (
                <PersistedTurn key={message.id} message={message} />
              ))}
              {liveSegments.map((segment) =>
                segment.kind === "text" ? (
                  <MessageBubble key={segment.id} role="assistant" content={segment.text} />
                ) : (
                  <ToolPill key={segment.id} text={segment.text} status={segment.status} />
                ),
              )}
            </>
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
