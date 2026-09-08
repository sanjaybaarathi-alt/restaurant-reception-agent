import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const streamTurn = vi.fn();
vi.mock("./api", () => ({
  createSession: vi.fn().mockResolvedValue({ session_id: "session-123", customer: { name: "New guest", is_new: true } }),
  streamTurn: (...args: unknown[]) => streamTurn(...args),
}));

beforeEach(() => {
  streamTurn.mockReset();
  streamTurn.mockImplementation(async function* () {
    yield { event: "status", data: { message: "Looking up your order" } };
    yield { event: "delta", data: { text: "You ordered the truffle pasta." } };
    yield { event: "complete", data: {} };
  });
});

afterEach(cleanup);

describe("App", () => {
  it("renders accessible customer onboarding", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /let’s start with you/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /begin conversation/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/phone/i)).toBeInTheDocument();
  });

  it("keeps the chatbot visible after selecting the previous-order prompt", async () => {
    render(<App />);
    fireEvent.change(screen.getByLabelText(/phone/i), { target: { value: "+91 98765 43210" } });
    fireEvent.click(screen.getByRole("button", { name: /begin conversation/i }));
    const suggestion = await screen.findByRole("button", { name: /what did i order last time/i });
    fireEvent.click(suggestion);
    expect(await screen.findByText("You ordered the truffle pasta.")).toBeInTheDocument();
    await waitFor(() => expect(streamTurn).toHaveBeenCalledWith("session-123", "What did I order last time?", expect.any(String)));
    expect(screen.getByRole("log")).toBeInTheDocument();
  });
});
