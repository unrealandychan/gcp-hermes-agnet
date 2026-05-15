/**
 * streamChat — SSE streaming client for the Hermes gateway.
 *
 * Calls POST /chat with the user message and streams back text chunks.
 * Calls onChunk for each text event, onDone when the stream closes,
 * and onError on error events or network failures.
 */

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL ?? 'http://localhost:8080'

interface StreamChatOptions {
  message: string
  idToken: string
  sessionId?: string
  onChunk: (text: string, sessionId: string) => void
  onDone: (sessionId: string) => void
  onError: (error: string) => void
}

export async function streamChat({
  message,
  idToken,
  sessionId,
  onChunk,
  onDone,
  onError,
}: StreamChatOptions): Promise<void> {
  const resp = await fetch(`${GATEWAY_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${idToken}`,
    },
    body: JSON.stringify({ message, session_id: sessionId ?? null }),
  })

  if (!resp.ok || !resp.body) {
    onError(`Gateway error: ${resp.status} ${resp.statusText}`)
    return
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const raw = line.slice(6).trim()
      if (!raw) continue
      try {
        const event = JSON.parse(raw)
        if (event.type === 'text') {
          onChunk(event.content, event.session_id)
        } else if (event.type === 'done') {
          onDone(event.session_id)
        } else if (event.type === 'error') {
          onError(event.content)
        }
      } catch {
        // ignore parse errors on malformed SSE lines
      }
    }
  }
}

export async function fetchSessions(
  userId: string,
  idToken: string,
): Promise<Array<{ id: string; create_time: string }>> {
  const resp = await fetch(`${GATEWAY_URL}/sessions/${encodeURIComponent(userId)}`, {
    headers: { Authorization: `Bearer ${idToken}` },
  })
  if (!resp.ok) return []
  const data = await resp.json()
  return data.sessions ?? []
}

export async function clearMemories(userId: string, idToken: string): Promise<void> {
  await fetch(`${GATEWAY_URL}/memories/${encodeURIComponent(userId)}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${idToken}` },
  })
}
