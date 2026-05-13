import { useEffect, useRef, useState } from 'react'
import { db } from './firebase'
import { ref, onValue, query, orderByKey, limitToLast } from 'firebase/database'

const STUDY_ID = 'v2'
const SESSION_ID = 'global'
const MESSAGES_PATH = `${STUDY_ID}/states/${SESSION_ID}/chat/messages`
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const hour = new Date().getHours()
let isDay = hour >= 6 && hour < 20
if (new URLSearchParams(window.location.search).get('theme') === 'day') isDay = true
if (new URLSearchParams(window.location.search).get('theme') === 'night') isDay = false

const theme = isDay ? {
  page:          'bg-[#f7f7f4] text-[#1a1a18]',
  headerBorder:  'border-[#e0e0dc]',
  subtext:       'text-[#909088]',
  avatar:        'bg-[#5a6e5e]',
  charlieName:   'text-[#5a6e5e]',
  charlieBubble: 'bg-[#eceee9] border border-[#cdd4c8] text-[#1a1a18]',
  myBubble:      'bg-[#282828] text-white',
  otherBubble:   'bg-white border border-[#e0e0dc] text-[#1a1a18]',
  otherName:     'text-[#909088]',
  timestamp:     'text-[#b8b8b0]',
  inputBorder:   'border-[#e0e0dc]',
  input:         'bg-white text-[#1a1a18] placeholder-[#b8b8b0] focus:ring-[#5a6e5e]/30',
  sendBtn:       'bg-[#5a6e5e] hover:bg-[#4a5e4e] disabled:opacity-40 text-white',
} : {
  page:          'bg-[#1a1a1a] text-[#d4d4d0]',
  headerBorder:  'border-white/10',
  subtext:       'text-[#6e6e6a]',
  avatar:        'bg-[#6e8878]',
  charlieName:   'text-[#7a9882]',
  charlieBubble: 'bg-[#212121] border border-[#6e8878]/30 text-[#c4d4c8]',
  myBubble:      'bg-[#2e2e2e] text-[#e8e8e6]',
  otherBubble:   'bg-[#242424] text-[#c4c4c0]',
  otherName:     'text-[#6e6e6a]',
  timestamp:     'text-[#404040]',
  inputBorder:   'border-white/10',
  input:         'bg-[#242424] text-[#d4d4d0] placeholder-[#4e4e4a] focus:ring-[#6e8878]/40',
  sendBtn:       'bg-[#4a5e4e] hover:bg-[#3a4e3e] disabled:opacity-40 text-white',
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(typeof ts === 'number' ? ts * 1000 : ts)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [participantId, setParticipantId] = useState(() => {
    return localStorage.getItem('charlie_participant_id') || ''
  })
  const [nameSet, setNameSet] = useState(!!localStorage.getItem('charlie_participant_id'))
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
    const messagesRef = query(ref(db, MESSAGES_PATH), orderByKey(), limitToLast(30))
    const unsub = onValue(messagesRef, (snapshot) => {
      const data = snapshot.val()
      if (!data) return
      const sorted = Object.values(data).sort((a, b) => a.ts - b.ts)
      setMessages(sorted)
    })
    return unsub
  }, [])

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
        body: JSON.stringify({ participant_id: name }),
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
        body: JSON.stringify({ participant_id: participantId, content }),
      })
    } catch (err) {
      console.error('Failed to send message', err)
    } finally {
      setSending(false)
    }
  }

  if (!nameSet) {
    return (
      <div className={`flex items-center justify-center min-h-screen ${theme.page}`}>
        <form onSubmit={saveName} className="flex flex-col gap-4 w-80">
          <h1 className="text-2xl font-semibold text-center">Talk to CHARLIE</h1>
          <p className={`text-sm text-center ${theme.subtext}`}>Enter a name to join the conversation</p>
          <input
            autoFocus
            className={`rounded-xl px-4 py-3 outline-none focus:ring-2 border ${theme.input} ${theme.inputBorder}`}
            placeholder="Your name"
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
    <div className={`min-h-screen ${theme.page}`}>
    <div className={`flex flex-col h-screen max-w-2xl mx-auto border-x ${theme.headerBorder}`}>
      <div className={`flex items-center gap-3 px-6 py-4 border-b ${theme.headerBorder}`}>
        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold text-white ${theme.avatar}`}>C</div>
        <div>
          <p className="font-semibold leading-none">charlie</p>
          <p className={`text-xs ${theme.subtext}`}>#global</p>
        </div>
      </div>

      <div ref={scrollRef} className="hide-scrollbar flex-1 overflow-y-auto overscroll-contain px-4 py-4 flex flex-col gap-3" style={{ WebkitOverflowScrolling: 'touch' }}>
        {messages.map((msg) => {
          if (msg.type === 'join') {
            return (
              <div key={msg.id} className="flex items-center gap-3 py-1">
                <div className={`flex-1 h-px ${theme.headerBorder}`} />
                <span className={`text-xs ${theme.subtext}`}>{msg.content} joined</span>
                <div className={`flex-1 h-px ${theme.headerBorder}`} />
              </div>
            )
          }
          const isCharlie = msg.type === 'mediator' || msg.senderId === '__mediator__'
          const isMe = msg.senderId === participantId
          return (
            <div key={msg.id} className={`flex flex-col gap-1 ${isMe ? 'items-end' : 'items-start'}`}>
              {!isMe && (
                <span className={`text-xs font-medium ${isCharlie ? theme.charlieName : theme.otherName}`}>
                  {isCharlie ? 'CHARLIE' : msg.senderId}
                </span>
              )}
              <div className={`px-4 py-2.5 rounded-2xl max-w-sm text-sm leading-relaxed ${
                isCharlie ? theme.charlieBubble : isMe ? theme.myBubble : theme.otherBubble
              }`}>
                {msg.content}
              </div>
              <span className={`text-xs ${theme.timestamp}`}>{formatTime(msg.ts)}</span>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>

<form onSubmit={sendMessage} className={`flex gap-2 px-4 py-4 border-t ${theme.inputBorder}`}>
        <input
          className={`flex-1 rounded-xl px-4 py-3 text-sm outline-none focus:ring-2 border ${theme.input} ${theme.inputBorder}`}
          placeholder="Say something..."
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={sending}
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className={`rounded-xl px-5 py-3 text-sm font-medium transition-colors ${theme.sendBtn}`}
        >
          Send
        </button>
      </form>
    </div>
    </div>
  )
}
