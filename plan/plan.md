# POC Build Plan: Self-Hosted AI Chat with Ollama + Caddy

## Objective

Build a simple web-based chat interface that lets a user send prompts to a locally hosted Ollama model and stream the response back in real time. The proof of concept should run with the model:

- `hf.co/DevQuasar/google.medgemma-4b-it-GGUF:Q4_K_M`

The app should be built in a way that is easy to extend later for persistence, auth, and stricter production hardening.

## Current Progress

- The Docker Compose app and PostgreSQL services are running on the server.
- The web app is reachable at `http://<server>:9105`.
- The FastAPI shell, browser UI, `/api/chat` streaming route, Ollama client, and initial PostgreSQL schema are implemented.
- End-to-end model streaming has been verified in the browser after setting `OLLAMA_BASE_URL` to an address reachable from the app container.
- PostgreSQL session/message storage and browser session restoration are implemented.
- Persistence against the deployed database still needs an end-to-end verification.

---

## Scope

This is a proof of concept and does not include:

- authentication
- user accounts
- rate limiting
- abuse protection
- production monitoring
- multi-user scaling
- advanced model orchestration

The initial version should focus on:

- user-facing chat page
- Python backend API
- Ollama inference integration
- streaming responses
- Caddy reverse proxy config
- working local deployment

---

## Todo Checklist

- [X] Confirm Ollama model is available and reachable from the app host
- [X] Decide the internal app port for the Compose service (port: 9105)
- [X] Create the Docker Compose stack for app + PostgreSQL
- [X] Build the FastAPI app shell and configuration loading
- [X] Create the initial PostgreSQL schema
- [X] Implement PostgreSQL storage/repository layer
- [X] Add chat session and message creation/retrieval logic
- [X] Implement the `/api/chat` streaming endpoint
- [X] Add the external Ollama API client
- [X] Build the simple HTML/JS chat frontend
- [X] Start the Compose services and verify browser access on port 9105
- [X] Verify end-to-end model streaming in the browser
- [ ] Test the app with persisted history and model streaming
- [ ] Add Caddy route later once the domain is ready
- [ ] Document and defer production hardening items

---

## Architecture Summary

The system should be split into three logical parts for the proof of concept:

1. Public web edge
   - Caddy handles TLS and routes a public subdomain
   - Example: `chat.example.com`
   - This is set up separately later, when the app is ready for the public domain

2. Docker Compose app stack
   - Python app container serves the frontend and API
   - PostgreSQL container stores chat sessions and messages
   - Docker Compose keeps the app environment reproducible
    - The app listens on port `9105` and is running on the server

3. External model host / inference layer
   - Ollama runs outside Docker and is already available
   - Accepts HTTP requests from the app server over the internal network
   - Does not need to be publicly exposed
   - Connection details are provided as configuration values when ready

4. Local data layer
   - PostgreSQL persists conversation history and settings
   - Keeps the app from losing session data when the process restarts

---

## Recommended Implementation Order

### Phase 1: Get the model running on Ollama

Goal: verify the model is available and usable locally outside Docker.

Tasks:

- confirm Ollama is installed on the model box
- configure or alias the model for the app
- verify the model can respond through the Ollama API
- test the default local endpoint on the model host
- capture the host/port the app will use from configuration

Example check:

- `curl http://localhost:11434/api/tags`
- `curl http://localhost:11434/api/generate -d '{"model":"medgemma:4b","prompt":"hello","stream":false}'`

Notes:

- If the exact `hf.co/...` model name is not directly accepted by your Ollama install, create a local tag or `Modelfile` alias first.
- The goal here is to prove model runtime before touching web app code.

Deliverable:

- working local model endpoint
- known good model name and generation parameters

---

### Phase 2: Create the Docker Compose stack

Goal: get the app and database running in a reproducible local environment.

Services to include:

- `app`: Python app container
- `db`: PostgreSQL container

External runtime not managed by Compose:

- Ollama: already running outside Docker
- Caddy: configured later on the edge box when the app is ready to expose the domain

Initial Compose responsibilities:

- expose the Python app on a single internal port: `9105`
- mount app source code for local development
- define PostgreSQL environment variables
- create a shared Docker network between the app and database
- define environment variables for the external Ollama host and port

Example service structure:

```yaml
services:
  app:
    build: ./app
    ports:
      - "9105:9105"
    environment:
      DATABASE_URL: postgres://app:secret@db:5432/pachat
      OLLAMA_BASE_URL: http://localhost:11434
      OLLAMA_MODEL: hf.co/DevQuasar/google.medgemma-4b-it-GGUF:Q4_K_M
    depends_on:
      - db

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: pachat
      POSTGRES_USER: app
      POSTGRES_PASSWORD: secret
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

Status: complete. The app and database start together with `docker compose up -d --build`; the app has been confirmed reachable at `http://<server>:9105`.

---

### Phase 3: Build the Python backend

Goal: create the chat API that communicates with Ollama.

Choose one framework:

- `FastAPI` is preferred for this use case
- `Flask` is acceptable if you want something lighter

Core responsibilities:

- expose a `/api/chat` endpoint
- accept a list of messages from the browser
- call the external Ollama service with `stream=true`
- forward partial output back to the browser as a stream
- return an error message if the underlying model call fails
- fetch session history from PostgreSQL and save messages back to it

Suggested endpoint behavior:

- `POST /api/chat`
- request body includes a message list and optional model config
- response is streamed using SSE or chunked JSON

Minimal backend feature set:

- health endpoint: `GET /api/health`
- chat endpoint: `POST /api/chat`
- optional model metadata endpoint: `GET /api/models`

Suggested file layout:

```text
project/
  app/
    main.py
    routes.py
    ollama_client.py
    config.py
  templates/
    index.html
  static/
    app.js
    styles.css
  requirements.txt
```

Key implementation decisions:

- keep the Ollama call in one adapter module
- keep request validation in the API layer
- avoid embedding model logic directly into the UI

Deliverable:

- backend API that can call Ollama and stream responses

---

### Phase 4: Add PostgreSQL persistence

Goal: persist chat sessions and message history.

Tasks:

- create the PostgreSQL schema
- add `chat_sessions`, `chat_messages`, and `app_settings` tables
- create repository/service functions for session creation and message insertion
- add retrieval methods for loading message history by session
- make sure the app can handle missing or empty sessions cleanly

Recommended initial schema:

```sql
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY,
    title TEXT,
    model_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE chat_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model_name TEXT,
    token_count INTEGER
);
```

This keeps the storage layer simple while supporting real conversation persistence and future multi-session expansion.

Deliverable:

- message history stored in PostgreSQL

---

### Phase 5: Build the frontend chat page

Goal: make a simple browser-based conversation UI.

Minimal UI requirements:

- message list
- textarea or input box
- send button
- loading state while waiting for model output
- error state if request fails
- auto-scroll behavior

For a proof of concept, plain HTML + JavaScript is perfectly acceptable.

Recommended flow:

1. User types a message
2. Browser sends JSON to `/api/chat`
3. Backend streams tokens back
4. Frontend appends stream chunks to the chat window
5. UI unlocks when stream ends

Optional enhancements for later:

- clear chat button
- conversation sidebar
- history retrieval
- model selector

Deliverable:

- working page at the public domain
- user can type and receive streamed responses

---

### Phase 6: Add Caddy routing later

Goal: prepare the app for public exposure once the domain is ready.

Caddy should do the following later:

- handle the site domain
- provide TLS termination
- forward requests to the Python app backend on the internal app port
- leave the Ollama service internal-only

Example concept for later:

```caddy
chat.example.com {
    reverse_proxy localhost:9105
}
```

Notes:

- no need to add authentication yet
- no need to harden this for production yet
- keep it simple and testable
- the POC focus is on local app and database behavior, not Caddy configuration details

Deliverable:

- a Caddy route ready to be added once the domain is configured

---

### Phase 7: Connect frontend and backend to Ollama

Goal: make the app actually produce answers from the local model.

Tasks:

- define request payload shape
- create a Python client that calls Ollama
- load persisted conversation history for the active session
- stream the token output back to the browser
- map errors to a friendly frontend message

Suggested request contract:

```json
{
  "session_id": null,
  "message": "Tell me about this setup",
  "stream": true,
  "temperature": 0.7
}
```

Suggested backend logic:

- create or load a session and persist the new user message
- build model context from persisted session messages
- send to Ollama `/api/chat`
- parse chunked response
- stream content to the browser and persist the completed assistant message

Important note:

- the browser should not wait for the full model response before it starts rendering
- streaming is the main UX improvement here

Deliverable:

- end-to-end chat flow: browser -> app -> Ollama -> browser

---

### Phase 8: Test and debug the POC

Goal: verify functionality and reliability before expanding.

Test checklist:

- request a simple prompt and receive a response
- handle empty user input safely
- verify the stream keeps updating in real time
- ensure the model call does not hang indefinitely
- confirm Caddy is routing correctly
- confirm the web app and Ollama do not expose sensitive ports publicly
- test a model error or unavailable state

Also confirm:

- the response is readable in the browser
- the connection survives large responses
- timeouts are reasonable for generation

Deliverable:

- functional proof-of-concept app running via Caddy

---

### Phase 9: Document the next iteration path

Goal: capture the next improvements clearly.

Planned later additions:

- chat history persistence
- session handling
- request logging
- error monitoring
- model selection UI
- authentication
- deployment automation
- more robust security and rate limiting

Deliverable:

- list of future features and priorities

---

## Proposed Folder Structure

```text
pachat/
  README.md
  architecture.md
  plan/
    plan.md
  app/
    main.py
    routes.py
    ollama_client.py
    config.py
    models.py
    storage.py
    chat_service.py
  templates/
    index.html
  static/
    app.js
    styles.css
  requirements.txt
  docker-compose.yml
  Caddyfile
```

---

## Suggested MVP Milestones

### Milestone 1: Local model works

- Ollama can run the model locally
- model endpoint responds successfully

### Milestone 2: Browser chat works

- frontend can send messages
- backend can call Ollama
- response is displayed in the UI

### Milestone 3: Public domain works via Caddy

- Caddy proxies the app on a public subdomain
- site responds over HTTPS
- app works without exposing Ollama publicly

### Milestone 4: POC is stable

- basic error handling in place
- streaming works reliably
- can demo the app end-to-end

---

## Notes on Caddy

Caddy is already installed, so the immediate work is mostly to add the application route rather than set up the reverse proxy from scratch.

A basic proof-of-concept setup should be enough:

- one subdomain pointing to the app host
- Caddy terminates TLS
- Caddy forwards to the Python app port
- model runtime stays internal

This is intentionally not production-level security; it is just enough to get the app working and visible from the browser.

---

## Recommended First Build

For a first pass, build exactly this:

- Python app using FastAPI
- one static page with an input box and streamed message responses
- one backend endpoint calling Ollama
- Caddy reverse proxy to the app
- local model runtime on a private host

This is the smallest architecture that still matches the goals of the project and gives an easy path to expand later.

---

## Final Goal

The final proof-of-concept should allow a user to:

- visit a public subdomain
- send a message through a web page
- have the message sent to a self-hosted Ollama model
- watch the response stream in real time
- get a working demo of a locally hosted AI chat application

That is the benchmark for the first successful version of this system.
