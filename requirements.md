# Agentic AI Coding Round Problem

## 1. Problem Statement

### Overview

Design and implement an **AI-powered Restaurant Reception Agent** that converses with customers in natural language and acts on their behalf to handle:

* Reservations
* Orders
* Menu enquiries
* Customer memory and preferences

The agent must autonomously decide what to do next based on conversational context, take actions against the underlying restaurant system, and remember relevant facts about returning customers.

You will receive a working **Restaurant Reservation API** built with:

* FastAPI
* PostgreSQL
* Docker

The data layer is already built and seeded.

You need to build the **agent as a separate application** on top of this API.

> **Time limit:** 90 minutes

---

# 2. Setup

You will receive a ZIP file:

```text
restaurant-api.zip
```

Extract it and run the application:

```bash
cd restaurant-api
docker compose up -d --build
```

This starts:

* PostgreSQL
* FastAPI service
* Sample data seeding

### Verify the API

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok"
}
```

API documentation is available at:

```text
http://localhost:8000/docs
```

Read:

```text
restaurant-api/README.md
```

for the complete API surface, conventions, and reseed commands.

> **Important:** Do not modify the provided `restaurant-api` codebase. Build the agent in a separate project.

---

# 3. Seeded Data

The backend contains the following sample data.

### Tables

* 8 tables
* Indoor and outdoor tables
* Capacities:

  * 2
  * 4
  * 6
  * 8

### Menu

* 12 menu items
* Menu items contain tags such as:

  * `vegetarian`
  * `vegan`
  * `contains-nuts`
  * `contains-dairy`

### Customers

There are 3 seeded customers.

One of them is:

```text
Priya Sharma
```

Priya has:

* Stored preferences
* Previous order history

This data is useful for demonstrating the **customer memory** capability.

---

# 4. Backend API

The backend exposes APIs for:

### Tables and Menu

```http
GET /tables
GET /menu
GET /availability
```

### Customers

```http
POST /customers
GET /customers/lookup
GET /customers/{id}
PATCH /customers/{id}/preferences
```

### Customer History

```http
GET /customers/{id}/reservations
GET /customers/{id}/orders
```

### Reservations

```http
POST /reservations
GET /reservations
DELETE /reservations/{id}
```

### Reservation Orders

```http
POST /reservations/{id}/orders
GET /reservations/{id}/orders
DELETE /reservations/{id}/orders
```

The complete API documentation is available at:

```text
http://localhost:8000/docs
```

---

# 5. Core Requirements

## 5.1 Conversational Agent

The agent must accept **free-form natural-language input** from customers and respond appropriately.

The agent should:

1. Understand the customer's intent.
2. Determine what information is missing.
3. Ask clarification questions when required.
4. Decide which tools need to be called.
5. Execute one or more actions.
6. Use the results of previous tool calls to determine the next action.
7. Respond naturally to the customer.
8. Maintain conversational context across turns.

---

## 5.2 Example Requests

The agent should be able to handle requests such as:

### Reservation

```text
Book me a table for 4 tomorrow at 7:30 PM, preferably outside.
```

The agent should:

```text
Understand request
        ↓
Check availability
        ↓
Select suitable table
        ↓
Create reservation
        ↓
Confirm booking
```

---

### Menu Search

```text
What vegetarian starters do you have under 400?
```

The agent should:

```text
Understand filters
        ↓
Query menu
        ↓
Filter vegetarian items
        ↓
Filter price <= 400
        ↓
Return matching items
```

---

### Add Orders

```text
Add two pasta and one tiramisu to my booking, and skip anything with nuts.
```

The agent should:

```text
Understand order
        ↓
Identify reservation
        ↓
Find requested menu items
        ↓
Respect dietary restrictions
        ↓
Add items to reservation
        ↓
Confirm order
```

---

### Cancellation

```text
Actually cancel that reservation.
```

The agent should use conversational context to determine which reservation the customer is referring to.

---

### Order History

```text
What did I order last time?
```

The agent should retrieve the customer's previous orders and respond using their stored history.

---

# 6. Multi-Step Agent Actions

A single user message may require multiple actions.

For example:

```text
Book me a table for 3 tomorrow at 8 PM and add two paneer tikka.
```

The agent may need to execute:

```text
check_availability
        ↓
create_reservation
        ↓
find_menu_item
        ↓
add_order_item
```

The important requirement is that the **LLM decides the next action based on the result of the previous action**.

---

# 7. Tool Layer

The agent must operate the restaurant through a set of **typed and well-described tools**.

You decide the exact tool surface.

Possible tools include:

```text
list_menu
check_availability
lookup_customer
create_customer
get_customer
update_customer_preferences
create_reservation
cancel_reservation
get_customer_reservations
get_customer_orders
add_order_item
remove_order_item
```

---

## 7.1 Tool Design

Consider the following questions:

### How are tools described to the LLM?

Each tool should have:

* Name
* Description
* Input schema
* Output schema

For example:

```python
class CheckAvailabilityInput(BaseModel):
    date: str
    time: str
    party_size: int
    seating_preference: str | None = None
```

---

### How are tool calls parsed?

The agent should safely parse tool invocations generated by the LLM.

Example:

```json
{
  "tool": "check_availability",
  "arguments": {
    "date": "2026-09-10",
    "time": "19:30",
    "party_size": 4,
    "seating_preference": "outdoor"
  }
}
```

---

### How are tools dispatched?

A central dispatcher should:

1. Validate the tool name.
2. Validate arguments.
3. Find the registered tool.
4. Execute the tool.
5. Capture the result.
6. Return the result to the LLM.

Example architecture:

```text
LLM
 │
 ▼
Tool Call
 │
 ▼
Tool Dispatcher
 │
 ├── check_availability
 ├── create_reservation
 ├── add_order_item
 ├── list_menu
 └── ...
 │
 ▼
Restaurant API
```

---

## 7.2 Defensive Tool Handling

The agent must handle LLM misbehaviour gracefully.

Examples:

### Unknown tool

```json
{
  "tool": "book_restaurant",
  "arguments": {}
}
```

If `book_restaurant` does not exist, the agent should not crash.

---

### Malformed arguments

```json
{
  "tool": "check_availability",
  "arguments": {
    "party_size": "four"
  }
}
```

The dispatcher should reject invalid arguments safely.

---

### Missing arguments

```json
{
  "tool": "create_reservation",
  "arguments": {}
}
```

The agent should either:

* Ask the user for the missing information, or
* Return a structured tool error to the LLM.

---

### Runaway tool loop

The agent should have a maximum number of iterations per turn.

For example:

```python
MAX_AGENT_STEPS = 8
```

If the limit is reached:

```text
The agent should stop executing tools and return a safe response.
```

---

# 8. Customer Memory

Returning customers should not have to repeat information they have already provided.

The agent should remember relevant customer information such as:

* Seating preferences
* Dietary preferences
* Allergies
* Favourite dishes
* Previous orders
* Other useful restaurant-related preferences

---

## 8.1 Example

Suppose Priya has:

```json
{
  "seating_preference": "outdoor",
  "dietary_preferences": ["vegetarian"]
}
```

The customer says:

```text
Can I book a table for 3 tonight around 8?
```

The agent should be able to recognize:

```text
Customer prefers outdoor seating.
```

It could respond:

```text
Welcome back, Priya! I see you usually prefer outdoor seating.
Should I look for an outdoor table for 3 at 8:00 PM tonight?
```

---

# 9. Memory Storage

The backend provides:

```http
GET /customers/{id}
```

The customer object includes a JSON preferences blob.

The schema is intentionally open-ended.

You decide what information to store.

For example:

```json
{
  "seating_preference": "outdoor",
  "dietary_preferences": [
    "vegetarian"
  ],
  "allergies": [
    "nuts"
  ],
  "favourite_dishes": [
    "paneer tikka"
  ]
}
```

The backend also provides:

```http
PATCH /customers/{id}/preferences
```

The endpoint performs a shallow merge into the preferences JSON.

---

# 10. Memory Architecture

Separate:

### Durable Customer Memory

Information that should survive between conversations.

Examples:

```text
Customer preferences
Dietary restrictions
Allergies
Favourite dishes
```

### Conversation State

Information relevant only to the current conversation.

Examples:

```text
Current reservation
Current booking ID
Current requested date
Current party size
Last mentioned menu item
```

A recommended architecture is:

```text
                 ┌────────────────────┐
                 │  Customer Memory   │
                 │    PostgreSQL      │
                 └─────────┬──────────┘
                           │
                           ▼
Customer ──► Conversation State ──► Agent
                           │
                           ▼
                     Tool Calls
                           │
                           ▼
                  Restaurant API
```

---

# 11. Conversation Interface

The agent must provide an interface that supports **multi-turn conversations**.

The customer must be identifiable using:

* Phone
* Email

If neither is available, the agent should ask the customer to provide one.

---

## Option A: REST API

Example:

```http
POST /sessions
```

Create or retrieve a customer session.

Example request:

```json
{
  "phone": "+91-9876543210"
}
```

Then:

```http
POST /sessions/{session_id}/messages
```

Example:

```json
{
  "message": "Book me a table for 4 tomorrow at 7:30 PM."
}
```

---

## Option B: CLI

A CLI is also acceptable.

Example:

```text
Restaurant Reception Agent

Phone or email: +91-9876543210

You: Hi, can I book a table for 4 tomorrow at 7:30?

Agent: Certainly. Do you have a seating preference?

You: Outside please.

Agent: I found an outdoor table for 4 at 7:30 PM...
```

The customer only needs to identify themselves once at the beginning.

---

# 12. Business Rules

The backend enforces the following rules.

## Table Capacity

Tables cannot:

* Be double-booked.
* Be booked beyond their capacity.

---

## Reservation Time Slots

Reservations are available in:

```text
30-minute increments
```

Valid times range from:

```text
12:00
12:30
13:00
...
22:00
22:30
```

---

## Cancellation

Reservations cannot be cancelled within:

```text
2 hours
```

of the reservation slot.

---

## Customer Identification

Customers are identified using:

```text
Phone OR Email
```

If neither is provided, the agent should ask for one.

---

## Menu Availability

Unavailable menu items cannot be ordered.

---

## Reservation Orders

Orders can only be:

* Added
* Removed

before the reservation's slot time.

---

## Past Reservations

Past reservations are read-only.

---

## Reservation Status

Reservations can have:

```text
confirmed
cancelled
completed
```

Reservations are automatically marked as `completed` once their slot has passed.

---

# 13. Error Handling

Backend errors are real HTTP errors.

The agent must:

* Handle errors gracefully.
* Explain the issue to the customer.
* Avoid crashing.
* Never claim that an action succeeded if the backend rejected it.

Example:

```text
Customer:
Cancel my reservation.

Backend:
Reservation cannot be cancelled within 2 hours of the reservation.

Agent:
I'm sorry, that reservation can't be cancelled because it is less than
2 hours away.
```

---

# 14. Example Complete Interaction

### Customer

```text
Hi, this is Priya. Phone is +91-9876543210.
Can I book a table for 3 tonight around 8?
```

### Agent

```text
Welcome back, Priya! I see you usually prefer outdoor seating.
Should I look for an outdoor table for 3 at 8:00 PM tonight?
```

### Customer

```text
Yes please.
```

### Agent

```text
Booked Table 7 (outdoor, seats 4) at 8:00 PM tonight.

Reservation ID: 4

Would you like to pre-order?

Last time you had paneer tikka, dal makhani, and roti.
```

### Customer

```text
Add one paneer tikka and two dal makhani.
And one gulab jamun.
```

### Agent

```text
Added to reservation 4:

- Paneer Tikka × 1
- Dal Makhani × 2
- Gulab Jamun × 1

See you at 8!
```

---

# 15. Agent Flow

The complete interaction may look like:

```text
                  Customer
                     │
                     ▼
              Natural Language
                     │
                     ▼
              ┌──────────────┐
              │  LLM / Agent │
              └──────┬───────┘
                     │
             Decide next action
                     │
                     ▼
              ┌──────────────┐
              │ Tool Registry│
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │ Tool Executor│
              └──────┬───────┘
                     │
                     ▼
             Restaurant API
                     │
                     ▼
              Tool Result
                     │
                     ▼
              ┌──────────────┐
              │  Agent Loop  │
              └──────┬───────┘
                     │
              More action?
                /        \
              Yes         No
               │           │
               └─────┐     ▼
                     │   Response
                     │
                     └──► LLM
```

---

# 16. Suggested Implementation Stages

## Stage 1 — Walking Skeleton

Get a minimum end-to-end loop working.

Requirements:

* Conversation interface
* LLM client
* One read-only tool
* Example: `list_menu`

Goal:

```text
User
 ↓
LLM
 ↓
list_menu
 ↓
Restaurant API
 ↓
LLM
 ↓
Response
```

No memory or complex multi-turn state is required initially.

---

## Stage 2 — Multi-Turn Agent

Add:

* Conversation history
* `check_availability`
* `create_reservation`
* `add_order_item`

Example flow:

```text
User
 ↓
Agent
 ↓
Check availability
 ↓
Create reservation
 ↓
Add order
 ↓
Response
```

---

## Stage 3 — Customer Memory

On session start:

1. Identify customer.
2. Load stored preferences.
3. Load relevant recent order history.
4. Add relevant information to agent context.

The agent should then naturally use that information.

---

## Stage 4 — Hardening

Add tests for:

* Tool dispatch
* Invalid tool names
* Malformed tool arguments
* Backend errors
* Maximum agent iterations
* Missing customer information

Use a fake/stub LLM for testing.

---

## Stage 5 — Advanced Features

If time remains, implement one or more advanced features.

---

# 17. Advanced Feature — Smart Table Assignment

When the customer does not specify a table:

1. Find tables that can accommodate the party.
2. Respect the customer's seating/location preference.
3. Select the smallest suitable table.

Example:

```text
Party size: 3

Available tables:

Table 1 → capacity 2
Table 2 → capacity 4
Table 3 → capacity 6
Table 4 → capacity 8
```

The agent should select:

```text
Table 2
```

because it is the smallest table that can accommodate the party.

This improves seating utilisation.

---

# 18. Advanced Feature — Personalised Recommendations

When the customer asks:

```text
What should I get?
```

or:

```text
Any suggestions?
```

The agent can use:

* Order history
* Favourite dishes
* Dietary preferences
* Allergies
* Menu tags

to provide personalised recommendations.

Example:

```text
You previously enjoyed Paneer Tikka and Dal Makhani.
Since you prefer vegetarian dishes, I'd recommend Paneer Tikka
with Dal Makhani again. There's also a vegetarian dessert available.
```

---

# 19. Advanced Feature — Reasoning Trace

Implement a verbose/debug mode for restaurant managers.

The trace should expose the agent's intermediate decisions.

Example:

```text
[Agent]
Intent: Create reservation

[Agent]
Party size: 3
Time: 20:00
Seating preference: outdoor

[Tool]
check_availability(...)

[Result]
Table 7 available

[Tool]
create_reservation(...)

[Result]
Reservation ID: 4

[Agent]
Reservation successfully created.
```

The trace should help managers audit what the agent:

* Considered
* Called
* Observed
* Concluded

---

# 20. Evaluation Criteria

## 20.1 Architecture

The primary focus is the **harness built around the LLM**.

Evaluation includes:

### Agent Loop

Is the agent's decision-making:

* Structured?
* Inspectable?
* Testable?

### Tool Layer

Are tools:

* Clearly defined?
* Registered cleanly?
* Easily dispatched?
* Easy to extend?

Adding a new tool should ideally require only a small, isolated change.

### Memory

Is durable customer memory separated from temporary conversation state?

### Defensive Handling

Does the system handle:

* Unknown tools?
* Malformed arguments?
* Invalid JSON?
* Partial tool calls?
* Backend errors?
* Runaway loops?

### Separation of Responsibilities

Responsibilities should be cleanly separated between:

```text
LLM Client
Tool Layer
Agent Loop
HTTP Client
Conversation State
Customer Memory
Interface
```

---

# 21. What Is NOT Evaluated

## Model Choice

The specific LLM is not important.

You may use:

* OpenAI
* Anthropic
* Gemini
* Ollama
* llama.cpp
* Another suitable model

Choose whatever can be integrated quickly.

---

## Prompt Engineering

Prompt quality is not the primary evaluation criterion.

The prompt needs to work, but the evaluators will focus more heavily on:

* Architecture
* Agent loop
* Tool design
* Memory
* Testing
* Defensive programming

---

# 22. Code Quality

The implementation should demonstrate:

* Clear naming
* Sensible folder structure
* Type hints
* Docstrings
* SOLID principles
* Small focused modules
* Sensible exception handling
* Maintainable code

---

# 23. Testing Requirements

The following areas should be covered.

## Tool Layer

The tool layer should be unit-testable **without invoking a real LLM**.

Example:

```text
check_availability()
create_reservation()
cancel_reservation()
add_order_item()
```

should be testable independently.

---

## Agent Loop

The agent loop should be testable end-to-end using a:

```text
Fake LLM / Stub LLM
```

This allows deterministic tests without requiring an actual model.

---

## Critical Paths

Tests should cover:

### Booking

```text
User request
 → availability
 → reservation
 → confirmation
```

### Cancellation

```text
User request
 → reservation identification
 → cancellation
 → confirmation/error
```

### Memory Recall

```text
Customer identification
 → load preferences/history
 → agent uses memory
```

### Backend Error Propagation

```text
Backend error
 → tool layer
 → agent
 → natural-language response
```

---

# 24. Recommended Project Structure

A possible structure is:

```text
restaurant-agent/
│
├── app/
│   ├── __init__.py
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── loop.py
│   │   ├── state.py
│   │   └── prompts.py
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── models.py
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── menu.py
│   │   ├── availability.py
│   │   ├── reservations.py
│   │   ├── orders.py
│   │   └── customers.py
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   └── customer_memory.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py
│   │
│   └── config.py
│
├── tests/
│   ├── test_tools.py
│   ├── test_agent.py
│   ├── test_booking.py
│   ├── test_cancellation.py
│   └── test_memory.py
│
├── .env.example
├── requirements.txt
├── README.md
└── run.py
```

This is only a suggested structure. You may use a different architecture if it better demonstrates your design.

---

# 25. Important Separation

The project should maintain a clear boundary:

```text
restaurant-api/
    Existing backend
    DO NOT MODIFY
          ▲
          │ HTTP
          │
          ▼
restaurant-agent/
    Your implementation
```

The agent must treat the restaurant API as a **black box**.

---

# 26. Suggested Tool Architecture

A clean implementation could use a registry:

```python
tool_registry.register(check_availability)
tool_registry.register(create_reservation)
tool_registry.register(add_order_item)
tool_registry.register(list_menu)
```

The agent can then dispatch dynamically:

```python
tool = tool_registry.get(tool_name)

if tool is None:
    raise UnknownToolError(tool_name)

result = tool.execute(arguments)
```

Adding a new tool should not require modifying a large `if/elif` chain.

Avoid:

```python
if tool_name == "check_availability":
    ...
elif tool_name == "create_reservation":
    ...
elif tool_name == "add_order_item":
    ...
elif tool_name == "list_menu":
    ...
```

Prefer a registry-based design.

---

# 27. Suggested Agent Loop

A simplified implementation could follow:

```python
async def run_agent(message, state):

    state.add_user_message(message)

    for _ in range(MAX_AGENT_STEPS):

        response = await llm.generate(
            messages=state.messages,
            tools=tool_registry.schemas(),
        )

        if response.is_final:
            state.add_assistant_message(response.text)
            return response.text

        if response.is_tool_call:

            tool_call = response.tool_call

            try:
                tool = tool_registry.get(tool_call.name)

                if tool is None:
                    result = {
                        "error": "Unknown tool"
                    }
                else:
                    arguments = tool.validate(
                        tool_call.arguments
                    )

                    result = await tool.execute(arguments)

            except Exception as exc:
                result = {
                    "error": str(exc)
                }

            state.add_tool_result(
                tool_call,
                result,
            )

    return "I wasn't able to complete that request."
```

The exact implementation is up to you.

---

# 28. Configuration

Keep configuration outside the source code.

Example:

```env
RESTAURANT_API_URL=http://localhost:8000
LLM_API_KEY=your-key
LLM_MODEL=your-model
MAX_AGENT_STEPS=8
```

Do not commit real API keys.

Provide:

```text
.env.example
```

instead.

---

# 29. Documentation Requirements

The `README.md` should document:

## Architecture

Explain:

* Agent loop
* Tool layer
* Memory
* LLM integration
* Conversation state

## LLM Choice

Document:

```text
Which model was selected?
Why?
```

## Libraries

Document:

```text
Why were these libraries selected?
```

## Storage

Explain:

```text
Where is conversation state stored?
Where is durable customer memory stored?
```

## Assumptions

Document any decisions that were intentionally left open by the problem.

## Running the Application

Provide exact commands.

Example:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt

python run.py
```

## Running Tests

Example:

```bash
pytest
```

---

# 30. Source Control

Use **frequent, focused commits**.

Avoid one large final commit.

Example:

```text
feat: add restaurant API client
feat: add tool registry
feat: implement menu tool
feat: implement availability tool
feat: implement reservation flow
feat: add conversation state
feat: add customer memory
test: add tool dispatcher tests
test: add booking flow tests
docs: add architecture and setup instructions
```

Each commit should represent a meaningful piece of work.

---

# 31. Constraints

### Constraint 1

Do not modify the provided backend.

The backend must be treated as a black box accessible only through:

```text
http://localhost:8000
```

---

### Constraint 2

No UI is required.

You may implement either:

```text
CLI
```

or:

```text
REST API
```

---

# 32. Final Goal

The final system should demonstrate an autonomous restaurant agent capable of:

```text
                    Customer
                       │
                       ▼
              Natural-language input
                       │
                       ▼
                ┌─────────────┐
                │    Agent    │
                └──────┬──────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
      Customer      Restaurant    Conversation
       Memory          Tools         State
          │            │
          │            ▼
          │       Restaurant API
          │            │
          └────────────┴────────────┐
                                    ▼
                               Agent Result
                                    │
                                    ▼
                              Natural Response
```

The key objective is **not simply to call an LLM**.

The objective is to demonstrate that you can build a reliable **agentic harness around an LLM**, including:

* Tool calling
* Tool orchestration
* Multi-step reasoning
* Conversation state
* Durable customer memory
* Backend integration
* Error handling
* Defensive programming
* Testing
* Clean architecture
