import { useRef, useEffect } from "react";

/* ── SVG Icons ─────────────────────────────────────────────────── */
function IconBack() {
  return (
    <svg viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 18l-6-6 6-6" />
    </svg>
  );
}

function IconInfo() {
  return (
    <svg viewBox="0 0 24 24" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="8.5" />
      <line x1="12" y1="11" x2="12" y2="16" />
    </svg>
  );
}

function IconSend() {
  return (
    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d="M2 21l21-9L2 3v7l15 2-15 2v7z" />
    </svg>
  );
}

/* ── Time display ──────────────────────────────────────────────── */
function nowTime() {
  return new Date().toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

/* ── Component ─────────────────────────────────────────────────── */
export default function ChatIntake({
  title,
  messages,
  chips,
  input,
  setInput,
  onSend,
  busy,
  error,
  onBack,
}) {
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  /* Auto-scroll to bottom on new message */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  /* Auto-resize textarea */
  function handleInput(e) {
    setInput(e.target.value);
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!busy && input.trim()) onSend(e);
    }
  }

  function handleChip(chip) {
    if (!busy) {
      setInput(chip);
      textareaRef.current?.focus();
    }
  }

  return (
    <div className="chat-screen" id="screen-chat">
      {/* Navigation */}
      <nav className="chat-nav">
        <button className="chat-nav-back" onClick={onBack} type="button" aria-label="Go back">
          <IconBack />
        </button>
        <span className="chat-nav-title">{title}</span>
        <div className="chat-nav-info" aria-hidden="true">
          <IconInfo />
        </div>
      </nav>

      {/* Messages */}
      <div className="chat-messages" role="log" aria-live="polite" aria-label="Conversation">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`bubble-group ${msg.role}`}
          >
            <div className={`bubble ${msg.role}`}>{msg.text}</div>
            <span className={`bubble-time ${msg.role}`}>
              {msg.time || nowTime()}
            </span>
          </div>
        ))}

        {/* Thinking indicator */}
        {busy && (
          <div className="bubble-group assistant">
            <div className="thinking-bubble">
              <div className="dot" />
              <div className="dot" />
              <div className="dot" />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Quick chips */}
      {chips && chips.length > 0 && (
        <div className="quick-chips" aria-label="Quick suggestions">
          {chips.map((chip) => (
            <button
              key={chip}
              className="quick-chip"
              type="button"
              onClick={() => handleChip(chip)}
              disabled={busy}
            >
              {chip}
            </button>
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="chat-error" role="alert">{error}</div>
      )}

      {/* Composer */}
      <div className="chat-composer">
        <form className="composer-row" onSubmit={onSend}>
          <textarea
            id="chat-input"
            ref={textareaRef}
            className="composer-textarea"
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Type a message…"
            disabled={busy}
            rows={1}
            aria-label="Message input"
          />
          <button
            id="btn-send-message"
            type="submit"
            className="composer-send"
            disabled={busy || !input.trim()}
            aria-label="Send message"
          >
            <IconSend />
          </button>
        </form>
      </div>
    </div>
  );
}
