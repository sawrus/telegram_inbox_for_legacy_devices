---
agentic:
  generated_by: agentic
  source: "areas/software/backend/rules/testing.md"
  repository: "https://github.com/sawrus/agent-guides"
  created_by: "v0.4.0"
  updated_by: "v0.5.1"
---
# Rule: Backend Testing Pyramid

**Priority**: P1 — Missing critical-path coverage fails review.

## Testing layers

1. **Unit tests**
   - Isolated domain/application logic tests.
   - External dependencies must be mocked.

2. **Integration tests**
   - Validate real integration with databases/message systems.
   - Use realistic infrastructure (for example, Testcontainers).

3. **E2E/API tests**
   - Verify critical user and system flows through service interfaces.

4. **SVT/chaos (when relevant)**
   - Validate resilience under partial failure and degraded conditions.
