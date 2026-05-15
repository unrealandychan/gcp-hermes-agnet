'use client'

import { signOut, useSession } from 'next-auth/react'
import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { clearMemories, fetchSessions, streamChat } from '@/lib/api'
import { MessageBubble } from '@/components/MessageBubble'
import type { ChatSession, Message } from '@/types/chat'

export default function ChatPage() {
  const { data: session, status } = useSession()
  const router = useRouter()

  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [sessionId, setSessionId] = useState<string | undefined>()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (status === 'unauthenticated') router.push('/')
  }, [status, router])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (session) loadSessions()
  }, [session]) // eslint-disable-line react-hooks/exhaustive-deps

  const idToken = (session as any)?.idToken as string | undefined
  const userId = session?.user?.email ?? ''

  async function loadSessions() {
    if (!idToken || !userId) return
    const list = await fetchSessions(userId, idToken)
    setSessions(list.map((s) => ({ id: s.id, createTime: s.create_time })))
  }

  async function handleSend() {
    if (!input.trim() || isStreaming || !idToken) return

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsStreaming(true)

    // Placeholder for the streaming assistant message
    const assistantId = crypto.randomUUID()
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: 'assistant', content: '', timestamp: new Date() },
    ])

    await streamChat({
      message: userMsg.content,
      idToken,
      sessionId,
      onChunk: (text, sid) => {
        setSessionId(sid)
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + text } : m)),
        )
      },
      onDone: (sid) => {
        setSessionId(sid)
        setIsStreaming(false)
        loadSessions()
      },
      onError: (err) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: `Error: ${err}` } : m,
          ),
        )
        setIsStreaming(false)
      },
    })
  }

  async function handleClearMemory() {
    if (!idToken || !userId) return
    await clearMemories(userId, idToken)
    alert('Long-term memory cleared.')
  }

  if (status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center text-gray-400">
        Loading…
      </div>
    )
  }

  return (
    <div className="flex h-screen">
      {/* ── Sidebar ── */}
      <aside className="w-60 bg-gray-900 border-r border-gray-800 flex flex-col p-4 space-y-4">
        <div>
          <h2 className="text-xs font-semibold uppercase text-gray-500 tracking-widest mb-2">
            Sessions
          </h2>
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {sessions.length === 0 && (
              <p className="text-xs text-gray-600">No sessions yet.</p>
            )}
            {sessions.map((s) => (
              <button
                key={s.id}
                onClick={() => {
                  setSessionId(s.id)
                  setMessages([])
                }}
                className="w-full text-left text-xs px-2 py-1.5 rounded hover:bg-gray-800 text-gray-300 truncate"
              >
                {s.id.slice(-8)}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={() => {
            setSessionId(undefined)
            setMessages([])
          }}
          className="text-xs text-blue-400 hover:text-blue-300 text-left"
        >
          + New Chat
        </button>

        <div className="mt-auto space-y-2">
          <button
            onClick={handleClearMemory}
            className="w-full text-xs px-2 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-400"
          >
            Clear Memory
          </button>
          <button
            onClick={() => signOut({ callbackUrl: '/' })}
            className="w-full text-xs px-2 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-400"
          >
            Sign Out
          </button>
          <p className="text-xs text-gray-600 truncate">{session?.user?.email}</p>
        </div>
      </aside>

      {/* ── Chat area ── */}
      <div className="flex flex-col flex-1 overflow-hidden">
        {/* Header */}
        <header className="border-b border-gray-800 px-6 py-4 flex items-center">
          <h1 className="font-semibold text-lg">Hermes</h1>
          <span className="ml-2 text-xs text-gray-500">Enterprise AI Assistant</span>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex items-center justify-center h-full text-gray-600 text-sm">
              Start a conversation — ask about data, IT, HR, or code.
            </div>
          )}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          {isStreaming && (
            <div className="text-xs text-gray-500 animate-pulse">Hermes is thinking…</div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-gray-800 px-6 py-4">
          <div className="flex gap-3">
            <textarea
              className="flex-1 bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
              rows={2}
              placeholder="Message Hermes…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
            />
            <button
              onClick={handleSend}
              disabled={isStreaming || !input.trim()}
              className="px-5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium transition-colors"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
