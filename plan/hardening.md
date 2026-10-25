# Security and Production Hardening

This document records work intentionally deferred during the proof of concept. The app is running and Caddy routing works, but TLS alone does not make an unauthenticated chat service safe for unrestricted public access.

## Current POC Risks

- The app has no authentication or user authorization. A session UUID is an identifier, not a complete access-control system.
- The app host is on the internal network and is not directly reachable from the public internet. Public requests reach the app through Caddy. Since the app has no authentication, anyone who can reach the Caddy hostname can use it unless Caddy applies an access restriction.
- Compose publishes the app on host port `9105` and PostgreSQL on host port `5432`. These ports are not directly internet-reachable under the current network boundary, but may be reachable by other hosts on permitted internal networks. PostgreSQL should only be reachable by the app and authorized administrators.
- The example environment file contains a placeholder database password. The deployed `.env` must use a unique strong secret and must remain outside version control.
- Chat content may contain sensitive health information. Retention, access, backup, and applicable privacy requirements have not been fully defined.
- Automated backups, restore tests, resource limits, and production monitoring are not yet established.

## Priority 0: Restrict Access and Protect Data

Complete these before allowing unrestricted public access or collecting sensitive personal/health information:

- Preserve the current boundary: app host ports must remain unavailable from the public internet, and direct access to `9105` should be limited to Caddy and trusted internal networks. Verify these rules after network or firewall changes.
- Remove the PostgreSQL host port mapping in production. Keep database access on the Compose network; if host administration is needed, bind it to loopback or use a private tunnel. Keep port `5432` blocked from untrusted internal clients as well.
- Add an access gate to the Caddy route before allowing unrestricted public use. Prefer application authentication; temporary Caddy authentication or IP/VPN restrictions can reduce exposure until app authentication is implemented. TLS alone does not restrict who can use the chat service.
- Add authentication and authorization to every relevant API route. Associate each session with an owner and verify ownership on session reads and chat requests; do not rely on UUID secrecy.
- Replace example credentials with unique strong secrets. Keep `.env` out of source control, limit its file permissions, and rotate secrets if exposed. Use a secrets manager where available.
- Define what data users may enter, how long chats are retained, who can access them, and how deletion works. Determine applicable privacy/legal requirements before storing real patient-identifiable data.
- Document that the model is not a substitute for professional medical advice, and define an appropriate escalation message for emergencies and high-risk situations.

## Priority 1: Edge and API Protections

- Keep Ollama private; permit model API traffic only from the app host/network. Never publish Ollama's port through Caddy or the public firewall.
- Configure Caddy for HTTPS, secure response headers, request-size limits, and streaming-compatible upstream timeouts. Confirm streams are not buffered and that disconnects/timeouts behave cleanly.
- Add rate limits and per-user or per-IP quotas for chat generation. Add concurrency limits so a small number of long requests cannot exhaust model, app, or database resources.
- Validate roles and payload shape server-side; set sensible maximum prompt size, conversation/context size, and generation parameters. Return generic client errors while keeping diagnostic details in server logs.
- Keep rendering untrusted model output as text unless a safe Markdown renderer with sanitization is deliberately introduced.
- Configure CORS narrowly if the frontend ever moves to a different origin. Keep CSRF protections in mind if authentication uses browser cookies.

## Priority 2: Data, Runtime, and Operations

- Create encrypted backups of PostgreSQL and test a restore procedure. Backups should follow the same access and retention rules as the live chat database.
- Use database migrations for schema changes. Give the app a least-privilege database role rather than broad administrative access when moving beyond the POC.
- Set an explicit retention/deletion policy and a supported way to delete a user's conversations.
- Run the production container as a non-root user, remove the source bind mount and development settings from production Compose, and apply only necessary container permissions.
- Pin and regularly update base images and Python dependencies. Review dependency/image security advisories and rebuild on updates.
- Add health checks for the app and Ollama dependency, graceful shutdown, request timeouts, and bounded database connections.
- Log operational metadata such as request IDs, duration, model, status, and errors. Do not log prompts, completions, credentials, or other sensitive content by default.
- Monitor service availability, disk/backup health, database growth, and Ollama failures; define who responds to alerts.

## Suggested Completion Order

1. Verify from both an external network and an untrusted internal client that direct app/database ports are blocked and only intended routes are reachable.
2. Add an access gate to Caddy and session ownership before unrestricted public use.
3. Define health-data privacy, retention, and deletion behavior before accepting sensitive data.
4. Add rate/concurrency limits, input bounds, and production-safe container settings.
5. Establish encrypted backups, restore tests, updates, and operational monitoring.

Treat this checklist as open work until each item is implemented and verified in the deployment. The POC checklist in `plan.md` tracks completion of documenting these deferrals, not completion of the hardening work itself.
