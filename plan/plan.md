# POC Build Plan: Self-Hosted AI Chat with Ollama + Caddy

## Objective

Build a simple web-based chat interface that lets a user send prompts to a locally hosted Ollama model and stream the response back in real time. The proof of concept should run with the model:

- `hf.co/DevQuasar/google.medgemma-4b-it-GGUF:Q4_K_M`

The app should be built in a way that is easy to extend later for persistence, auth, and stricter production hardening.

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

## Architecture Summary

The system should be split into three logical parts:

1. Public web edge
   - Caddy handles TLS and routes a public subdomain
   - Example: `chat.example.com`
   - Only the web app is exposed publicly

2. Application server
   - Python app serves the frontend and API
   - Handles conversation and chat request flow
   - Calls the Ollama API
   - Streams model output back to browser

3. Ollama host
   - Runs the model locally
   - Accepts HTTP requests from the app server
   - Does not need to be publicly exposed

---

## Recommended Implementation Order

### Phase 1: Get the model running on Ollama

Goal: verify the model is available and usable locally.

Tasks:

- confirm Ollama is installed on the model box
- pull or configure the target model
- verify the model can respond through the Ollama API
- test the default local endpoint on the model host

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

### Phase 2: Build the Python backend

Goal: create the chat API that communicates with Ollama.

Choose one framework:

- `FastAPI` is preferred for this use case
- `Flask` is acceptable if you want something lighter

Core responsibilities:

- expose a `/api/chat` endpoint
- accept a list of messages from the browser
- call Ollama with `stream=true`
- forward partial output back to the browser as a stream
- return an error message if the underlying model call fails

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

### Phase 3: Build the frontend chat page

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

### Phase 4: Add Caddy routing

Goal: expose the web app externally and reverse proxy it cleanly.

Caddy should do the following:

- handle the site domain
- provide TLS termination
- forward requests to the Python app backend
- leave the Ollama service internal-only

Example concept:

```caddy
chat.example.com {
    reverse_proxy localhost:8000
}
```

If the app is running in Docker, the upstream may be something like:

```caddy
chat.example.com {
    reverse_proxy app:8000
}
```

Notes:

- no need to add authentication yet
- no need to harden this for production yet
- keep it simple and testable
- make sure the app port is not directly exposed to the internet

Deliverable:

- working Caddy config that points the public domain to the app backend

---

### Phase 5: Connect frontend and backend to Ollama

Goal: make the app actually produce answers from the local model.

Tasks:

- define request payload shape
- create a Python client that calls Ollama
- pass the conversation history as a sequence of messages
- stream the token output back to the browser
- map errors to a friendly frontend message

Suggested request contract:

```json
{
  "messages": [
    {"role": "user", "content": "Tell me about this setup"}
  ],
  "stream": true,
  "temperature": 0.7,
  "max_tokens": 512
}
```

Suggested backend logic:

- build message list from the conversation state
- send to Ollama `/api/chat`
- parse chunked response
- emit the content to the browser incrementally

Important note:

- the browser should not wait for the full model response before it starts rendering
- streaming is the main UX improvement here

Deliverable:

- end-to-end chat flow: browser -> app -> Ollama -> browser

---

### Phase 6: Test and debug the POC

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

### Phase 7: Document the next iteration path

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
