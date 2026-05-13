import { useEffect, useRef, useState } from 'react'
import { db } from './firebase'
import { ref, onValue, query, orderByKey, limitToLast } from 'firebase/database'
import SkyBackground from './SkyBackground'

const STUDY_ID = 'v2'
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const hour = new Date().getHours()
let isDay = hour >= 6 && hour < 21
if (new URLSearchParams(window.location.search).get('theme') === 'day') isDay = true
if (new URLSearchParams(window.location.search).get('theme') === 'night') isDay = false

const theme = isDay ? {
  page:          'bg-[#f7f7f4] text-[#1a1a18]',
  headerBorder:  'border-[#e0e0dc]',
  subtext:       'text-[#dbeeff]',
  headerName:    'text-[#eeeeee]',
  avatar:        'bg-[#5a6e5e]',
  charlieName:   'text-[#f0f0ee]',
  mention:       '#c07828',
  charlieBubble: 'bg-white border border-[#e0e0dc] text-[#1a1a18]',
  myBubble:      'bg-[#dbeeff] border border-[#a8d4f5] text-[#1a3050]',
  otherBubble:   'bg-white border border-[#e0e0dc] text-[#1a1a18]',
  otherName:     'text-[#f0f0ee]',
  timestamp:     'text-[#b8b8b0]',
  inputBorder:   'border-[#ffffff24]',
  input:         'bg-white/30 text-[#1a1a18] placeholder-[#dbeeff] focus:ring-[#5a6e5e]/30',
  sendBtn:       'bg-[#d08a2e] hover:bg-[#bc7a22] disabled:bg-[#e8c88a] disabled:text-white/60 disabled:cursor-not-allowed text-white cursor-pointer',
} : {
  page:          'bg-[#1a1a1a] text-[#d4d4d0]',
  headerBorder:  'border-white/10',
  subtext:       'text-[#6e6e6a]',
  headerName:    'text-[#d4d4d0]',
  avatar:        'bg-[#6e8878]',
  charlieName:   'text-[#d4d4d0]',
  mention:       '#9abfd4',
  charlieBubble: 'bg-[#212121] border border-[#6e8878]/30 text-[#c4d4c8]',
  myBubble:      'bg-[#2e2e2e] text-[#e8e8e6]',
  otherBubble:   'bg-[#242424] text-[#c4c4c0]',
  otherName:     'text-[#d4d4d0]',
  timestamp:     'text-[#404040]',
  inputBorder:   'border-white/10',
  input:         'bg-[#242424] text-[#d4d4d0] placeholder-[#4e4e4a] focus:ring-[#6e8878]/40',
  sendBtn:       'bg-[#4a5a90] hover:bg-[#3a4a80] disabled:bg-[#6878a8] disabled:text-white/50 disabled:cursor-not-allowed text-white cursor-pointer',
}

function renderContent(text, mentionColor) {
  const parts = text.split(/(@charlie)/gi)
  return parts.map((part, i) =>
    /^@charlie$/i.test(part)
      ? <strong key={i} style={{ color: mentionColor }}>charlie</strong>
      : part
  )
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(typeof ts === 'number' ? ts * 1000 : ts)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function App() {
  const [sessionId, setSessionId] = useState(null)
  const [sessionCode, setSessionCode] = useState('')
  const [sessionError, setSessionError] = useState(false)
  const [validating, setValidating] = useState(false)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [participantId, setParticipantId] = useState('')
  const [nameSet, setNameSet] = useState(false)
  const [sending, setSending] = useState(false)
  const bottomRef = useRef(null)
  const scrollRef = useRef(null)

  function smoothScroll(el) {
    const start = el.scrollTop
    const end = el.scrollHeight - el.clientHeight
    const distance = end - start
    if (distance <= 0) return
    const duration = 420
    let startTime = null
    const easeOutQuart = t => 1 - Math.pow(1 - t, 4)
    function step(now) {
      if (!startTime) startTime = now
      const progress = Math.min((now - startTime) / duration, 1)
      el.scrollTop = start + distance * easeOutQuart(progress)
      if (progress < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }

  useEffect(() => {
    if (!sessionId) return
    const path = `${STUDY_ID}/states/${sessionId}/chat/messages`
    const messagesRef = query(ref(db, path), orderByKey(), limitToLast(30))
    const unsub = onValue(messagesRef, (snapshot) => {
      const data = snapshot.val()
      if (!data) { setMessages([]); return }
      const sorted = Object.values(data).sort((a, b) => a.ts - b.ts)
      setMessages(sorted)
    })
    return unsub
  }, [sessionId])

  useEffect(() => {
    if (!nameSet || !sessionId) return
    const handleLeave = () => {
      const blob = new Blob(
        [JSON.stringify({ participant_id: participantId, session_id: sessionId })],
        { type: 'text/plain' }
      )
      navigator.sendBeacon(`${API_URL}/chat/leave`, blob)
    }
    window.addEventListener('beforeunload', handleLeave)
    return () => window.removeEventListener('beforeunload', handleLeave)
  }, [nameSet, sessionId, participantId])

  useEffect(() => {
    if (scrollRef.current) smoothScroll(scrollRef.current)
  }, [messages])

  async function saveName(e) {
    e.preventDefault()
    const name = participantId.trim()
    if (!name) return
    localStorage.setItem('charlie_participant_id', name)
    setParticipantId(name)
    setNameSet(true)
    try {
      await fetch(`${API_URL}/chat/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ participant_id: name, session_id: sessionId }),
      })
    } catch (err) {
      console.error('Failed to send join event', err)
    }
  }

  async function sendMessage(e) {
    e.preventDefault()
    const content = input.trim()
    if (!content || sending) return
    setSending(true)
    setInput('')
    try {
      await fetch(`${API_URL}/chat/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ participant_id: participantId, content, session_id: sessionId }),
      })
    } catch (err) {
      console.error('Failed to send message', err)
    } finally {
      setSending(false)
    }
  }

  if (!sessionId) {
    return (
      <div className={`flex items-center justify-center min-h-screen relative ${theme.page}`}>
        <SkyBackground isDay={isDay} />
        <div className={`relative z-10 flex flex-col gap-5 w-80 p-8 rounded-2xl`}>
          <h1 className={`text-3xl font-semibold text-center ${theme.headerName}`}>talk to charlie</h1>
          <form onSubmit={async e => {
            e.preventDefault()
            const code = sessionCode.trim()
            if (!code) return
            setValidating(true)
            setSessionError(false)
            try {
              const res = await fetch(`${API_URL}/session/${encodeURIComponent(code)}`)
              if (res.ok) { setSessionId(code) }
              else { setSessionError(true) }
            } catch { setSessionError(true) }
            finally { setValidating(false) }
          }} className="flex flex-col gap-3">
            <input
              autoFocus
              className={`rounded-xl px-4 py-3 outline-none  border ${theme.input} ${theme.inputBorder}`}
              placeholder="Invite code"
              value={sessionCode}
              onChange={e => setSessionCode(e.target.value)}
            />
            {sessionError && <p className="text-sm text-center text-red-400">Invalid invite code</p>}
            <button type="submit" disabled={!sessionCode.trim() || validating} className={`rounded-xl px-4 py-3 font-medium transition-colors ${theme.sendBtn}`}>
              {validating ? 'Checking…' : 'Join session'}
            </button>
          </form>
          <div className="flex items-center gap-3">
            <div className={`flex-1 h-px ${theme.headerBorder}`} />
            <span className={`text-sm ${theme.subtext}`}>or</span>
            <div className={`flex-1 h-px ${theme.headerBorder}`} />
          </div>
          <button onClick={() => setSessionId('global')} className={`rounded-xl px-4 py-3 font-medium transition-colors cursor-pointer ${isDay ? 'bg-white/40 hover:bg-white/60 text-[#1a1a18]' : 'bg-white/10 hover:bg-white/15 text-[#d4d4d0]'}`}>
            Join global session
          </button>
        </div>
      </div>
    )
  }

  if (!nameSet) {
    return (
      <div className={`flex items-center justify-center min-h-screen relative ${theme.page}`}>
        <SkyBackground isDay={isDay} />
        <form onSubmit={saveName} className={`relative z-10 flex flex-col gap-4 w-80 p-8 rounded-2xl`}>
          <h1 className={`text-3xl font-semibold text-center ${theme.headerName}`}>talk to charlie</h1>
          <p className={`text-base text-center ${theme.subtext}`}>Joining <strong>#{sessionId}</strong></p>
          <input
            autoFocus
            className={`rounded-xl px-4 py-3 outline-none border ${theme.input} ${theme.inputBorder}`}
            placeholder="Pick a nickname"
            value={participantId}
            onChange={e => setParticipantId(e.target.value)}
          />
          <button type="submit" className={`rounded-xl px-4 py-3 font-medium transition-colors ${theme.sendBtn}`}>
            Join
          </button>
        </form>
      </div>
    )
  }

  return (
    <div className={`h-screen overflow-hidden relative flex flex-col ${theme.page}`}>
    <SkyBackground isDay={isDay} />
    <nav className="relative z-10 px-6 py-4 flex-shrink-0">
      <span className="text-white font-semibold text-lg tracking-tight">talktocharlie</span>
    </nav>
    <div className="relative z-10 flex-1 min-h-0 grid" style={{ gridTemplateColumns: '1fr min(672px, 100%) 1fr' }}>

    {/* Left gutter — members list */}
    <div className="hidden lg:flex flex-col items-end pt-8 pr-6 gap-0.5">
      <p className="text-xs font-semibold uppercase tracking-widest mb-3 text-white/80" style={{ fontFamily: "'DM Sans', sans-serif" }}>Members</p>
      {(() => {
        const joined = new Set(messages.filter(m => m.type === 'join').map(m => m.senderId))
        const left   = new Set(messages.filter(m => m.type === 'leave').map(m => m.senderId))
        const active = [...joined].filter(id => !left.has(id))
        const hasCharlie = messages.some(m => m.senderId === '__mediator__')
        return hasCharlie ? ['__mediator__', ...active] : active
      })().map(id => (
        <div key={id} className="px-3 py-1.5 text-base font-medium text-white/80">
          {id === '__mediator__' ? 'charlie 🤠' : id}
          {id === participantId && <span className="text-white/40 text-sm ml-1">(you)</span>}
        </div>
      ))}
    </div>

    {/* Chat panel — middle column of grid, always centered */}
    <div className="flex flex-col min-h-0 w-full">
      <div className={`flex items-center gap-3 px-6 py-4  ${theme.headerBorder}`}>
        <div className="w-8 h-8 flex items-center justify-center text-2xl">🤠</div>
        <div>
          <p className={`font-semibold leading-none ${theme.headerName}`}>#{sessionId}</p>
        </div>
      </div>

      <div ref={scrollRef} className="hide-scrollbar flex-1 overflow-y-auto overscroll-contain px-4 py-4 flex flex-col gap-3" style={{ WebkitOverflowScrolling: 'touch' }}>
        {messages.map((msg) => {
          if (msg.type === 'join' || msg.type === 'leave') {
            return (
              <div key={msg.id} className="flex items-center gap-3 py-1">
                <div className={`flex-1 h-px ${theme.headerBorder}`} />
                <span className={`text-sm ${theme.subtext}`}>{msg.content} {msg.type === 'join' ? 'joined' : 'left'}</span>
                <div className={`flex-1 h-px ${theme.headerBorder}`} />
              </div>
            )
          }
          const isCharlie = msg.type === 'mediator' || msg.senderId === '__mediator__'
          const isMe = msg.senderId === participantId
          return (
            <div key={msg.id} className={`flex flex-col gap-1 ${isMe ? 'items-end' : 'items-start'}`}>
              {!isMe && (
                <span className={`text-sm font-medium ${isCharlie ? theme.charlieName : theme.otherName}`}>
                  {isCharlie ? 'charlie' : msg.senderId}
                </span>
              )}
              <div className={`px-4 py-2.5 rounded-2xl max-w-sm text-base leading-relaxed ${
                isCharlie ? theme.charlieBubble : isMe ? theme.myBubble : theme.otherBubble
              }`}>
                {renderContent(msg.content, theme.mention)}
              </div>
              <span className={`text-sm ${theme.timestamp}`}>{formatTime(msg.ts)}</span>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>

<form onSubmit={sendMessage} className={`flex gap-2 px-4 py-4 border-t ${theme.inputBorder}`}>
        <input
          className={`flex-1 rounded-xl px-4 py-3 text-base outline-none focus:ring-2 border ${theme.input} ${theme.inputBorder}`}
          placeholder="Say something..."
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={sending}
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className={`rounded-xl px-5 py-3 text-base font-medium transition-colors ${theme.sendBtn}`}
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5 -rotate-90">
            <path d="M3.478 2.405a.75.75 0 0 0-.926.94l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.405Z" />
          </svg>
        </button>
      </form>
    </div>
    </div>
    </div>
  )
}
