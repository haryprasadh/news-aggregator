export type HealthInfo = {
  ok: boolean;
  llm_configured: boolean;
  search_configured: boolean;
  model: string;
  digest_model: string;
  sources_count: number;
};

export type DigestBullet = { what: string; why: string; link: string };
export type DigestSection = {
  id: string;
  title: string;
  bullets: DigestBullet[];
  note: string;
};
export type Digest = {
  generated_at: string;
  sections: DigestSection[];
  model: string;
  used_search: boolean;
  warnings: string[];
};

export type ChatMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
};

export async function getHealth(): Promise<HealthInfo> {
  const r = await fetch("/api/health");
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

export async function getDigest(): Promise<Digest> {
  const r = await fetch("/api/digest");
  if (!r.ok) throw new Error(`digest ${r.status}`);
  return r.json();
}

export async function refreshDigest(): Promise<Digest> {
  const r = await fetch("/api/digest/refresh", { method: "POST" });
  if (!r.ok) throw new Error(`refresh ${r.status}`);
  return r.json();
}

/** Stream chat tokens. Uses fetch + manual SSE parsing because EventSource
 *  cannot do POST with a JSON body. */
export async function streamChat(
  messages: ChatMessage[],
  mode: string,
  onToken: (s: string) => void,
  signal?: AbortSignal
): Promise<void> {
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ messages, mode }),
    signal,
  });
  if (!r.ok || !r.body) {
    const err = await r.text().catch(() => "");
    throw new Error(`chat ${r.status}: ${err}`);
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const lines = raw.split("\n");
      let event = "message";
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^\s/, ""));
      }
      const data = dataLines.join("\n");
      if (event === "token") onToken(data);
      else if (event === "error") throw new Error(data || "stream error");
      else if (event === "done") return;
    }
  }
}
