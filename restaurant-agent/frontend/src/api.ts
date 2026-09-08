import type { Session, StreamEvent } from "./types";

export async function createSession(customer: { name?: string; phone?: string; email?: string }): Promise<Session> {
  const response = await fetch("/v1/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ customer }) });
  const data = await response.json();
  if (!response.ok) throw new Error(data?.error?.message ?? "Unable to start your session.");
  return data as Session;
}

export async function* streamTurn(sessionId: string, message: string, messageId: string): AsyncGenerator<StreamEvent> {
  const response = await fetch(`/v1/sessions/${sessionId}/messages/stream`, { method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" }, body: JSON.stringify({ client_message_id: messageId, message }) });
  if (!response.ok || !response.body) throw new Error("The reception service is unavailable.");
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read(); buffer += value ?? "";
      const frames = buffer.split("\n\n"); buffer = frames.pop() ?? "";
      for (const frame of frames) {
        if (!frame || frame.startsWith(":")) continue;
        const event = frame.match(/^event: (.+)$/m)?.[1]; const raw = frame.match(/^data: (.+)$/m)?.[1];
        if (event && raw) yield { event, data: JSON.parse(raw) } as StreamEvent;
      }
      if (done) break;
    }
  } finally { reader.releaseLock(); }
}
