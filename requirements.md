Agentic AI Coding Round Problem
Statement
Overview
Design and implement an AI-powered Restaurant Reception Agent that converses with
customers in natural language and acts on their behalf handling reservations, orders, and menu
enquiries against the restaurant's data. The agent must autonomously decide what to do next
based on conversational context, take action against the underlying system, and remember
relevant facts about returning customers.
You will receive a working Restaurant Reservation API (FastAPI + Postgres, Dockerised) the
data layer is already built and seeded. You need to build the agent on top of it as a separate
application. You have 90 minutes for the round.
Setup
You will receive a zip file restaurant-api.zip. Extract it and run the application using the
following commands:
cd restaurant-api
docker compose up -d --build
This starts Postgres, builds the FastAPI service, and seeds sample data automatically. Verify:
curl http://localhost:8000/health # {"status":"ok"}
Visit http://localhost:8000/docs in your browser for application docs. Read
restaurant-api/README.md for the full API surface, conventions, and reseed commands.
Do not modify this codebase. Build your agent in a separate project.
What's in the seeded data
● 8 tables (mix of indoor and outdoor; capacities 2 / 4 / 6 / 8)
● 12 menu items with tags (vegetarian, vegan, contains-nuts, contains-dairy) ●
3 customers, including one (Priya Sharma) with stored preferences and order history, useful

for demoing memory recall
API surface (summary)
● GET /tables, GET /menu, GET /availability
● POST /customers, GET /customers/lookup, GET /customers/{id} ● PATCH
/customers/{id}/preferences shallow-merges into a free-form JSON blob, schema
is yours to design
● GET /customers/{id}/reservations, GET /customers/{id}/orders ●
POST/GET/DELETE /reservations, POST/GET/DELETE
/reservations/{id}/orders
Full docs at /docs after starting the stack
Core Requirements for the Agent
Conversational agent
Accepts free-form natural-language input from a customer and responds appropriately. Real
examples it must handle:
● "Book me a table for 4 tomorrow at 7:30 PM, preferably outside."
● "What vegetarian starters do you have under 400?"
● "Add two pasta and one tiramisu to my booking, and skip anything with nuts."
● "Actually cancel that reservation."
● "What did I order last time?"
The agent figures out what the customer wants, asks for any missing information, performs the
right actions against the backend, and replies naturally. A single user message may require
several actions in sequence (e.g. check availability → book table → place order against it).
Tool layer
The agent operates the restaurant by calling tools which are typed, well-described functions
that wrap HTTP calls to the backend. You decide the tool surface. Things to think about:
● How are tools described to the LLM?
● How is a tool invocation parsed out of the LLM's response and dispatched safely? ● How
is the result of a tool surfaced back so the LLM can decide what to do next? ● What happens
when the LLM hallucinates a tool that doesn't exist, or passes malformed arguments?
● How easy is it to add a new tool?

Customer memory
Returning customers shouldn't have to restate things they've already told the restaurant.
Examples:
● A customer who always asks for outdoor seating shouldn't need to specify it again.
● Dietary preferences and allergies should be recalled and respected.
● Past orders / favourite dishes may be referenced when relevant.
The backend exposes GET /customers/{id} (which includes a JSON blob holding the
customer's preferences) and PATCH /customers/{id}/preferences. The schema of
preferences is deliberately open which means you decide what to store there, when to read
it, when to update it, and how it enters the agent's reasoning.
Conversation Interface
For interacting with the agent you need to build an interface in your application that lets a
customer have a multi-turn conversation with the agent. The customer should be identifiable
(phone or email) so memory ties to them. Build either:
● REST API: endpoints to start a session for a customer (creating them if new) and to
continue it across turns.
● CLI: interactive prompt where the user identifies themself once at the start, then converses
freely.

Business rules (enforced by the backend)
● Tables cannot be double-booked or booked beyond their capacity.
● Time slots are 30-minute increments from 12:00 to 22:30 inclusive.
● Reservations cannot be cancelled within 2 hours of the slot.
● Customers are identified by phone or email; the agent should ask if neither is provided.
● Menu items marked unavailable cannot be ordered.
● Orders on a reservation can only be added or removed before the reservation's slot time.
Past reservations are read-only.
● Reservation statuses are confirmed, cancelled, and completed (set automatically once the
slot has passed).
These return real HTTP errors from the backend. Your agent must handle them gracefully,
surface the issue to the customer, don't crash, don't lie.
Example Interaction

Customer: Hi, this is Priya. Phone is +91-9876543210. Can I book a table for 3 tonight around
8?
Agent: Welcome back, Priya! I see you usually prefer outdoor seating. Should I look for an
outdoor table for 3 at 8:00 PM tonight?
Customer: Yes please.
Agent: Booked Table 7 (outdoor, seats 4) at 8:00 PM tonight. Reservation ID is 4. Would you
like to pre-order? Last time you had paneer tikka, dal makhani, and roti.
Customer: Add one paneer tikka and two dal makhani. And one gulab jamun.
Agent: Added to reservation 4:
● Paneer Tikka × 1
● Dal Makhani × 2
● Gulab Jamun × 1
See you at 8!
This single exchange involves: customer lookup, preference recall, availability check, table
assignment, reservation creation, order placement, and order history recall across several agent
turns.
Suggested Approach
Build incrementally. Get a minimum end-to-end loop working before adding capabilities. A
reasonable progression:
● Stage 1: Walking skeleton. Conversation interface accepts a message, agent calls one
read-only tool (e.g. list_menu), returns a natural-language response. No memory, no
multi-turn state. Prove the loop works.
● Stage 2: Multi-turn with state. Conversation history flows back to the LLM each turn. Add
the tools needed for the booking flow (check_availability, create_reservation,
add_order_item).
● Stage 3: Customer memory. On session start, load the customer's stored preferences and
recent orders into context. The agent uses them naturally.
● Stage 4: Hardening. Tests on tool dispatch with a stub LLM. Defensive handling of
malformed tool calls. Error surfacing from the backend.
● Stage 5: Advanced. Pick from the advanced section if time remains.
Advanced section
Smart table assignment
When the customer doesn't specify a particular table, automatically assign the smallest table

that fits the party and respect the customer's stored location preference when there is one. This
maximises seating utilisation.
Personalised recommendations
When a customer asks "what should I get?" or "any suggestions?", draw on their order history
and stored dietary preferences to suggest items.
Reasoning trace
Expose a verbose mode that surfaces the agent's intermediate decisions for a turn: what it
considered, what it called, what it observed, what it concluded so the restaurant manager can
audit a conversation after the fact.

Evaluation criteria
Architecture (Harness)
We care about the harness you build around the LLM: the agent loop, tool layer, memory
architecture, and how cleanly you wire it all together. Specifically:
● Is the agent's decision logic structured, inspectable, and testable?
● Are tools defined, registered, and dispatched cleanly? Is adding a new tool a one-file
change?
● Is durable customer memory separated from in-conversation state?
● Defensive handling of LLM misbehaviour: malformed tool calls, unknown tool names,
runaway loops, partial JSON
● Are responsibilities cleanly split LLM client, tool layer, HTTP layer, interface?
Not Considered for Evaluation as part of Harness
● Model choice: pick whatever you can wire up fastest. Hosted (OpenAI, Anthropic, Gemini)
or local (Ollama, llama.cpp) your call.
● Prompt-engineering finesse: you need prompts that work, not prompts that are art. We will
not grade prose.
Code quality
● Naming, file/folder structure, adherence to SOLID
● Type hints, docstrings, sensible exceptions
Tests

● The tool layer is unit-testable without invoking a real LLM.
● The agent loop can be exercised end-to-end with a fake/stub LLM.
● Critical paths covered: booking flow, cancellation, memory recall, error propagation from
the backend.
Decisions & documentation
● Choice of LLM, libraries, storage, and why.
● Assumptions documented in your README.
Source control
● Frequent, focused commits with clear messages, not one giant final push.
Constraints

1. Do not modify the provided backend. Treat it as a black box accessible only over HTTP
at http://localhost:8000.
2. No UI required, a CLI or REST API interface is enough.
Notes
1. There is no single correct solution. Design as you see fit.
2. Some details are intentionally left open, document your assumptions in your README.