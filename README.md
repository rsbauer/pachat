# Pachat

Patient Advocate AI Chat is a FastAPI web app with PostgreSQL, deployed using Docker Compose. Ollama runs separately from Compose.

## Requirements

- Docker Engine and the Docker Compose plugin on the server
- The project files on the server
- An Ollama server reachable from the app container

## Initial Setup

From the project directory, create the local environment file:

```sh
cp .env.example .env
```

Edit `.env` before starting the stack. Replace the example `POSTGRES_PASSWORD` with a strong value. Set `OLLAMA_BASE_URL` to an address reachable from inside the app container. `localhost` refers to the app container itself. For Ollama running on the Docker host, use `http://host.docker.internal:11434`; for Ollama on another machine, use its private hostname or LAN address. Keep Ollama off the public internet.

Build and start the app and database:

```sh
docker compose up -d --build
```

The web app is served on port `9105`. Open `http://<server>:9105` from a browser that can reach the server. PostgreSQL is available to the app as `db:5432` on the Compose network. The Compose configuration builds the app's `DATABASE_URL` from the PostgreSQL variables in `.env`.

Chat sessions and messages are stored in PostgreSQL. The browser remembers the active session ID locally and reloads that session's history when the page is reopened. Starting a new chat creates a separate session; previous sessions remain in the database, but there is not yet a UI for browsing them.

Users can register with a unique username and a password of at least 12 characters, then sign in to use the app. Passwords are stored as Argon2id hashes, not reversible encrypted text. Login sessions use an HttpOnly cookie and expire after 12 hours. The app supports profile display-name changes, password changes, and per-account file listing, viewing, and deletion. Email and password recovery are not implemented. Existing chat sessions without an owner and files belonging to the old placeholder user are retained but are not available to registered accounts.

The intake form accepts multiple documents or ZIP archives. ZIP contents are unpacked in memory, unsupported files are rejected, and ClamAV must report each accepted document clean before it is saved. Files are stored under a per-user directory in the local `uploads_data/` directory next to `docker-compose.yml` and tracked in PostgreSQL. Docker Compose creates this directory if it does not exist. ClamAV starts with an empty virus database and can take a few minutes to become healthy; uploads fail closed until scanning is available. File encryption is off by default for testing. To enable it, set `FILE_ENCRYPTION_ENABLED=true` and provide a stable Fernet key in `FILE_ENCRYPTION_KEY`; keep that key only in the app's private environment and back it up securely.

For HTTPS deployments, set `APP_ENV=production` so the login cookie is marked Secure. This prototype does not yet include login rate limiting, password recovery, account deletion, or an admin interface. Do not use real patient information until access restrictions, privacy/retention policies, operational monitoring, and applicable compliance requirements have been reviewed.

If files were previously saved in the Docker-managed `uploads_data` volume, changing to the local directory does not copy them. The old volume remains intact until explicitly removed; copy its contents before deleting it if you need those files.

The app host is internal and is not directly reachable from the public internet; public traffic is routed through Caddy. Keep direct access to port `9105` limited to trusted internal networks, and keep PostgreSQL port `5432` unavailable to untrusted clients. Authentication is an additional control, not a substitute for these network restrictions.

## Managing the Stack

Show service status:

```sh
docker compose ps
```

Follow logs for both services, or one service:

```sh
docker compose logs -f
docker compose logs -f app
docker compose logs -f db
```

Restart services:

```sh
docker compose restart
```

Rebuild and apply app code or configuration changes:

```sh
docker compose up -d --build
```

Stop the services while preserving the PostgreSQL volume:

```sh
docker compose down
```

Start them again without rebuilding:

```sh
docker compose up -d
```

The database data is stored in the named `postgres_data` volume. **Do not run `docker compose down -v` unless you intend to permanently delete that database volume and its data.** The SQL initialization script runs when PostgreSQL creates a new data directory; editing it does not automatically rerun it against an existing volume.

The app applies its account/session and chat ownership schema updates at startup. Existing records are not deleted; legacy ownerless sessions cannot be opened through the authenticated API.

## Troubleshooting

- If startup reports `all predefined address pools have been fully subnetted`, inspect Docker networks with `docker network ls`. `docker network prune` removes unused networks and can free address ranges; it does not remove volumes or database data.
- If the page does not load, check `docker compose ps` and `docker compose logs -f app`, and confirm that server firewall rules allow the intended access to port `9105`.
- If the app cannot reach Ollama, verify `OLLAMA_BASE_URL` from the container's point of view and check that Ollama accepts connections from the Docker host/network.
