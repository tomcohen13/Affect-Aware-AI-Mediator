# CHARLIE v2 — Build Summary

## What is this?

CHARLIE (v2) is a public-facing group chat with an AI mediator. Anyone who visits [talktocharlie.io](https://talktocharlie.io) joins a single global chat room and talks to the same agent. It is intentionally not scalable — it's an MVP for iterating on CHARLIE's personality and making the agent accessible to external users for feedback and research.

## Architecture

### Backend (FastAPI)
- **`app.py`** — FastAPI server with a lifespan that initializes Redis, the LangGraph checkpointer, the AffectiveMediator, and the EventManager.
- **`/chat/message`** — Accepts a user message, writes it to Firebase RTDB, and asynchronously calls the mediator. If CHARLIE decides to intervene, her response is written to Firebase via `EventManager.post_message_to_session`.
- **`/chat/join`** — Fires when a user enters the chat. Writes a `type: "join"` event to Firebase for display in the UI.
- The mediator uses a single fixed `discussion_id = "global"` so all users share one LangGraph conversation thread and checkpointed memory.
- Firebase Admin SDK handles all writes (bypasses security rules). The browser never writes directly to Firebase.

### Frontend (React + Vite + Tailwind)
- **`src/App.jsx`** — Single-file React app. Subscribes to Firebase RTDB at `v2/states/global/chat/messages` for real-time message delivery. POSTs to the FastAPI backend to send messages and join events.
- **`src/firebase.js`** — Firebase web client initialization from `VITE_*` env vars.
- Participant identity is a name entered on first visit, stored in `localStorage`.

### Real-time flow
```
User types message
  → POST /chat/message (FastAPI)
    → Firebase RTDB write (Admin SDK)
    → asyncio.create_task → mediator.process_new_message()
      → if should_intervene → Firebase RTDB write (CHARLIE's response)
  ← Firebase RTDB onValue subscription → UI updates for all connected clients
```

## Design

- **Two automatic themes** based on time of day: day (6am–8pm) and night (8pm–6am). No manual toggle.
  - Day: warm off-white (`#f7f7f4`), muted sage green accents
  - Night: dark charcoal (`#1a1a1a`, Cursor Dark-inspired), desaturated sage accents
- **Font**: Fraunces (serif) — chosen for its warmth and human quality, deliberately departing from the sans-serif AI product aesthetic.
- **Message types**:
  - `user` — standard chat bubble, right-aligned for self
  - `mediator` — distinct sage-tinted bubble, left-aligned with CHARLIE label
  - `join` — quiet centered divider line: `——— name joined ———`
- Scrollbar hidden, custom ease-out-quart scroll animation on new messages.

## Infrastructure

- **Backend**: Render Web Service (Python 3.11), `uvicorn app:app --host 0.0.0.0 --port $PORT`
- **Frontend**: Render Static Site, root `frontend/`, build `npm install && npm run build`, publish `dist/`
- **Domain**: talktocharlie.io (Namecheap) → Render via ALIAS + CNAME records. SSL via Let's Encrypt (auto-provisioned by Render).
- **Firebase RTDB rules**: public read on `v2/states/global/chat/messages`, no public writes.

## Key environment variables

| Variable | Used by |
|---|---|
| `REDIS_HOST/PORT/USERNAME/PASSWORD` | LangGraph checkpointer, pub-sub |
| `FIREBASE_URL` | Firebase Admin SDK |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Firebase Admin SDK |
| `STUDY_ID` | Firebase path prefix (`v2`) |
| `OPENROUTER_API_KEY` | LLM calls via OpenRouter |
| `DEFAULT_LLM` | Primary and summarization LLM model name |
| `VITE_FIREBASE_*` | Frontend Firebase client |
| `VITE_API_URL` | Frontend → backend URL |

## What's next

- Agent personality tuning (possible GPT-4o-mini fine-tune)
- Richer landing page / onboarding that sets tone for CHARLIE's purpose
- UI polish: header identity, CHARLIE avatar, landing page copy
