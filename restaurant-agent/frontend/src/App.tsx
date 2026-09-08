import { Component, ErrorInfo, FormEvent, KeyboardEvent, ReactNode, useEffect, useRef, useState } from "react";
import { createSession, streamTurn } from "./api";
import type { Message, Session } from "./types";

const prompts = ["Reserve a table for two", "Show vegetarian starters", "What did I order last time?"];
const uid = (): string => globalThis.crypto?.randomUUID?.() ?? `message-${Date.now()}-${Math.random().toString(36).slice(2)}`;

class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error("Restaurant UI render failure", error, info.componentStack); }
  render() {
    if (this.state.failed) return <main className="recovery" role="alert"><div className="recovery-card"><span className="brand-mark">J</span><p className="eyebrow">LET’S TRY THAT AGAIN</p><h1>The conversation hit a small snag.</h1><p>Your restaurant data is safe. Refresh this page to reconnect with reception.</p><button onClick={() => globalThis.location.reload()}>Refresh conversation</button></div></main>;
    return this.props.children;
  }
}

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [phase, setPhase] = useState("Ready");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState<{ text: string; id: string } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => bottomRef.current?.scrollIntoView?.({ behavior: "smooth" }), [messages]);

  async function onboard(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setBusy(true);
    const form = new FormData(event.currentTarget);
    const customer = Object.fromEntries([...form.entries()].map(([k, v]) => [k, String(v).trim()]).filter(([, v]) => v));
    if (!customer.phone && !customer.email) { setError("Enter a phone number or email to continue."); setBusy(false); return; }
    try {
      const next = await createSession(customer); setSession(next);
      setMessages([{ id: uid(), role: "assistant", text: `Welcome, ${next.customer.name}. I can arrange tables, explore the menu, manage pre-orders, and remember your preferences. What shall we plan?` }]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to start a session."); }
    finally { setBusy(false); }
  }

  async function send(text: string, messageId: string = uid()) {
    const clean = text.trim(); if (!clean || !session || busy) return;
    setBusy(true); setError(""); setRetry({ text: clean, id: messageId }); setDraft("");
    const assistantId = uid();
    setMessages(current => [...current, { id: messageId, role: "user", text: clean }, { id: assistantId, role: "assistant", text: "", state: "streaming" }]);
    try {
      for await (const event of streamTurn(session.session_id, clean, messageId)) {
        if (event.event === "status") setPhase(String(event.data.message ?? "Working…"));
        if (event.event === "delta") setMessages(current => current.map(item => item.id === assistantId ? { ...item, text: item.text + String(event.data.text ?? "") } : item));
        if (event.event === "error") throw new Error(String((event.data.error as { message?: string })?.message ?? "The turn failed."));
        if (event.event === "complete") { setRetry(null); setPhase("Ready"); }
      }
      setMessages(current => current.map(item => item.id === assistantId ? { ...item, state: undefined } : item));
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : "Connection interrupted."; setPhase("Needs attention");
      setMessages(current => current.map(item => item.id === assistantId ? { ...item, text: item.text || detail, state: "failed" } : item));
    } finally { setBusy(false); }
  }

  function reset() { setSession(null); setMessages([]); setRetry(null); setDraft(""); setPhase("Ready"); setError(""); }
  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(draft); } }

  return <main className="shell">
    <aside className="story-panel">
      <a className="brand" href="/" aria-label="Juniper home"><span>J</span><div><strong>Juniper</strong><small>AI reception</small></div></a>
      <div className="story"><p className="eyebrow">THOUGHTFUL HOSPITALITY</p><h1>Good evenings begin with a conversation.</h1><p>From the first table to the final course, your personal reception assistant keeps every detail in mind.</p><div className="service-list"><span><b>01</b> Find the right table</span><span><b>02</b> Explore today’s menu</span><span><b>03</b> Remember your favourites</span></div></div>
      <div className="availability"><i /><div><strong>Reception online</strong><small>Serving daily · 12:00–22:30</small></div></div>
    </aside>
    <section className="stage">
      {!session ? <section className="onboarding" aria-labelledby="welcome-title">
        <div className="welcome-badge"><span className="mini-avatar">J</span><div><strong>Your digital maître d’</strong><small><i /> Available now</small></div></div>
        <p className="eyebrow">WELCOME TO JUNIPER</p><h2 id="welcome-title">Let’s start with you.</h2><p className="lede">We use your details to find reservations and remember what you enjoy.</p>
        <form onSubmit={onboard} noValidate><div className="fields"><label>Name <span>New guests</span><input name="name" autoComplete="name" placeholder="Priya Sharma" /></label><label>Phone<input name="phone" autoComplete="tel" placeholder="+91 98765 43210" /></label></div><label>Email<input name="email" type="email" autoComplete="email" placeholder="priya@example.com" /></label><p className="error" role="alert">{error}</p><button className="start" disabled={busy}>{busy ? "Finding your profile…" : "Begin conversation"}<span>→</span></button></form>
        <p className="privacy">Private by design · Your details stay within this restaurant experience.</p>
      </section> : <section className="chat" aria-label="Restaurant reception conversation">
        <header className="chat-head"><span className="avatar">J</span><div><strong>Reception assistant</strong><small><i /> {phase}</small></div><div className="guest"><strong>{session.customer.name}</strong><small>{session.customer.is_new ? "New guest" : "Welcome back"} · {session.session_id.slice(0, 8)}</small></div><button className="reset" onClick={reset} aria-label="Start new conversation" title="New conversation">↻</button></header>
        <div className="transcript" role="log" aria-live="polite">{messages.map(item => <article key={item.id} className={`row ${item.role}`}><div className={`bubble ${item.state ?? ""}`}>{item.text || <span className="typing"><i /><i /><i /></span>}{item.state === "failed" && retry && <button className="retry" onClick={() => void send(retry.text, retry.id)}>Retry safely</button>}<time>{new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></div></article>)}<div ref={bottomRef} /></div>
        {messages.length < 2 && <div className="prompts" aria-label="Suggested prompts">{prompts.map(prompt => <button key={prompt} onClick={() => void send(prompt)}>{prompt}<span>↗</span></button>)}</div>}
        <div className="compose"><textarea value={draft} onChange={event => setDraft(event.target.value)} onKeyDown={keyDown} placeholder="Ask about a table, menu, or order…" rows={1} maxLength={4000} disabled={busy} aria-label="Message" /><button onClick={() => void send(draft)} disabled={busy || !draft.trim()} aria-label="Send message">↑</button></div>
        <footer><span>{busy ? phase : "Ready when you are"}</span><span>Enter to send · Shift + Enter for a new line</span></footer>
      </section>}
    </section>
  </main>;
}

export default function RootApp() { return <AppErrorBoundary><App /></AppErrorBoundary>; }
