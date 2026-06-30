---
trigger: always_on
glob: sdlc-methodology-guide
description: software development lifecycle phases and process discipline
agentic:
  generated_by: agentic
  source: "areas/software/general/rules/sdlc-methodology-guide.md"
  repository: "https://github.com/sawrus/agent-guides"
  created_by: "v0.4.0"
  updated_by: "v0.5.1"
---

# SDLC Methodology Rule

**Rules:**

- Follow structured phases: Requirements → Design → Implementation → Testing → Deployment → Maintenance.
- **Requirements:** Write user stories or specs before writing any code. Acceptance criteria must be defined.
- **Design:** For significant features, produce a design doc or ADR (Architecture Decision Record) before implementation.
- **Implementation:** Work in small increments; each increment must be independently deployable or testable.
- **Testing:** Automated tests are not optional — unit, integration, and E2E coverage required.
- **Deployment:** All deployments via CI/CD pipeline; no manual file transfers or SSH deployments.
- **Maintenance:** Monitor with alerts and dashboards; on-call runbooks must exist for production services.
- Use ADRs (`docs/adr/`) to document significant architectural decisions with context and consequences.
- Definition of Done: code merged, tests passing, documentation updated, deployed to staging.
- Conduct retrospectives after incidents to produce action items.

**Violations:**

- Starting implementation without defined requirements or acceptance criteria.
- Merging code without tests.
- Manual deployments to production.
- No runbook for a production service.
