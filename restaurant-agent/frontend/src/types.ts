export type Customer = { id: number; name: string; is_new: boolean };
export type Session = { session_id: string; customer: Customer; created_at: string };
export type Message = { id: string; role: "user" | "assistant"; text: string; state?: "streaming" | "failed" };
export type StreamEvent = { event: "status" | "delta" | "complete" | "error"; data: Record<string, unknown> };
