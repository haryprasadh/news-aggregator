import { useEffect, useMemo, useRef, useState } from "react";
import {
  ChatMessage,
  Digest,
  HealthInfo,
  getDigest,
  getHealth,
  refreshDigest,
  streamChat,
} from "./api";

const MODES = [
  { id: "default", label: "Default" },
  { id: "tech", label: "Tech lens" },
  { id: "upsc", label: "UPSC CA" },
  { id: "ssc", label: "SSC CGL" },
  { id: "civic", label: "Civic" },
];

const QUICK_PROMPTS = [
  "Summarise today's top India news in 8 bullets.",
  "What's happening in Hyderabad / Telangana today? Include Mahabubabad if anything.",
  "Tech & AI news from the last 24 hours that an Indian software engineer should know.",
  "Current affairs for UPSC for this week, point-wise with sources.",
  "Music / comedy / tech events in Hyderabad in the next 7 days.",
  "Latest remote-friendly software engineering job openings (India).",
];

export function App() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [digest, setDigest] = useState<Digest | null>(null);
  const [digestLoading, setDigestLoading] = useState(false);
  const [digestErr, setDigestErr] = useState<string | null>(null);

  const [mode, setMode] = useState<string>("default");
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamErr, setStreamErr] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messagesEnd = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch((e) => setDigestErr(String(e)));
    loadDigest(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, streaming]);

  async function loadDigest(force: boolean) {
    setDigestLoading(true);
    setDigestErr(null);
    try {
      const d = force ? await refreshDigest() : await getDigest();
      setDigest(d);
    } catch (e) {
      setDigestErr(String(e));
    } finally {
      setDigestLoading(false);
    }
  }

  async function send(prompt?: string) {
    const text = (prompt ?? input).trim();
    if (!text || streaming) return;
    const next: ChatMessage[] = [...history, { role: "user", content: text }];
    setHistory(next);
    setInput("");
    setStreamErr(null);
    setStreaming(true);

    const placeholder: ChatMessage = { role: "assistant", content: "" };
    setHistory([...next, placeholder]);

    const ac = new AbortController();
    abortRef.current = ac;
    try {
      await streamChat(
        next,
        mode,
        (tok) => {
          setHistory((cur) => {
            const copy = cur.slice();
            const last = copy[copy.length - 1];
            if (last && last.role === "assistant") {
              copy[copy.length - 1] = { ...last, content: last.content + tok };
            }
            return copy;
          });
        },
        ac.signal
      );
    } catch (e: any) {
      if (e?.name !== "AbortError") setStreamErr(String(e?.message || e));
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  function clearChat() {
    setHistory([]);
    setStreamErr(null);
  }

  const generated = useMemo(() => {
    if (!digest) return "";
    try {
      return new Date(digest.generated_at).toLocaleString();
    } catch {
      return digest.generated_at;
    }
  }, [digest]);

  return (
    <div className="app">
      {/* LEFT: digest */}
      <div className="panel">
        <div className="panel-header">
          <div className="brand">
            <h1>News Desk</h1>
            <div className="muted">
              {health
                ? `model: ${health.model}${health.search_configured ? " · search on" : " · search off"} · ${health.sources_count} sources`
                : "loading..."}
            </div>
          </div>
          <div className="row">
            <button onClick={() => loadDigest(true)} disabled={digestLoading}>
              {digestLoading ? "refreshing..." : "refresh digest"}
            </button>
          </div>
        </div>
        <div className="panel-body">
          {digestErr ? <div className="warn">error: {digestErr}</div> : null}
          {digestLoading && !digest ? (
            <div className="muted"><span className="spinner" /> building today's digest...</div>
          ) : null}
          {digest && digest.warnings.length ? (
            <div className="warn" style={{ marginBottom: 10 }}>
              {digest.warnings.map((w, i) => (
                <div key={i}>• {w}</div>
              ))}
            </div>
          ) : null}
          {digest && generated ? (
            <div className="muted" style={{ marginBottom: 12 }}>generated {generated}</div>
          ) : null}
          {digest?.sections.map((sec) => (
            <div className="section" key={sec.id || sec.title}>
              <h2>{sec.title}</h2>
              {sec.bullets.length === 0 ? (
                <div className="muted">{sec.note || "no fresh items"}</div>
              ) : null}
              {sec.bullets.map((b, i) => (
                <div className="bullet" key={i}>
                  <div className="what">{b.what}</div>
                  {b.why ? <div className="why">{b.why}</div> : null}
                  {b.link ? (
                    <div className="link">
                      <a href={b.link} target="_blank" rel="noreferrer noopener">
                        {b.link}
                      </a>
                    </div>
                  ) : null}
                </div>
              ))}
              {sec.bullets.length > 0 && sec.note ? (
                <div className="muted">note: {sec.note}</div>
              ) : null}
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT: chat */}
      <div className="panel chat">
        <div className="panel-header">
          <div className="panel-title">Chat</div>
          <div className="row">
            <label className="muted" htmlFor="mode">mode</label>
            <select
              id="mode"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              disabled={streaming}
            >
              {MODES.map((m) => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>
            <button onClick={clearChat} disabled={streaming || history.length === 0}>
              clear
            </button>
          </div>
        </div>

        <div className="messages">
          {history.length === 0 ? (
            <>
              <div className="muted" style={{ marginBottom: 8 }}>
                Ask anything. The model can call your RSS packs and web search.
              </div>
              <div className="quick">
                {QUICK_PROMPTS.map((p) => (
                  <button key={p} onClick={() => send(p)} disabled={streaming}>
                    {p}
                  </button>
                ))}
              </div>
            </>
          ) : null}
          {history.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <div className="role">{m.role}</div>
              <pre>{m.content || (m.role === "assistant" && streaming && i === history.length - 1 ? "…" : "")}</pre>
            </div>
          ))}
          {streamErr ? <div className="warn">stream error: {streamErr}</div> : null}
          <div ref={messagesEnd} />
        </div>

        <div className="composer">
          <textarea
            placeholder="e.g. 'tech jobs in Hyderabad this week' or 'UPSC current affairs of last 3 days'"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                void send();
              }
            }}
            disabled={streaming}
          />
          <div className="col">
            <button onClick={() => send()} disabled={streaming || !input.trim()}>
              send
            </button>
            <button onClick={stop} disabled={!streaming}>
              stop
            </button>
            <span className="muted" style={{ fontSize: 11 }}>cmd/ctrl + ⏎</span>
          </div>
        </div>
      </div>
    </div>
  );
}
