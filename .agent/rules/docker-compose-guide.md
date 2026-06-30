---
trigger: always_on
glob: docker-compose-guide
description: Docker Compose best practices for local multi-service development
agentic:
  generated_by: agentic
  source: "areas/software/general/rules/docker-compose-guide.md"
  repository: "https://github.com/sawrus/agent-guides"
  created_by: "v0.4.0"
  updated_by: "v0.5.1"
---

# Docker Compose Rule

**Rules:**

- Use `docker-compose.yml` for local development environment definition.
- Separate configs: `docker-compose.yml` (base) + `docker-compose.override.yml` (local dev overrides).
- All service configuration via environment variables — never hardcode in images.
- Use `.env` file for local variable defaults; add `.env` to `.gitignore`.
- Define `healthcheck:` for all stateful services (databases, caches, queues).
- Dependent services use `depends_on: condition: service_healthy` (not just `depends_on`).
- Use named volumes for persistent data; bind mounts only for source code in dev.
- Pin image versions explicitly — never use `latest` tag in committed configs.
- Define a custom network instead of relying on default bridge network for clarity.
- Expose only necessary ports to the host; internal service communication via service names.

**Violations:**

- Using `latest` image tags in committed compose files.
- Hardcoded credentials in `docker-compose.yml`.
- Missing health checks causing race conditions on startup.
- Bind-mounting entire home directory or system paths.
