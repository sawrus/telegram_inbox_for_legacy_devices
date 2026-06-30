---
trigger: always_on
glob: gitlab-ci-guide
description: GitLab CI/CD pipeline structure and best practices
agentic:
  generated_by: agentic
  source: "areas/software/general/rules/gitlab-ci-guide.md"
  repository: "https://github.com/sawrus/agent-guides"
  created_by: "v0.4.0"
  updated_by: "v0.5.1"
---

# GitLab CI/CD Rule

**Rules:**

- Define pipelines in `.gitlab-ci.yml` at the repository root.
- Structure pipeline into stages: `build` → `test` → `lint` → `deploy`.
- Use `include` to split large pipelines into reusable template files.
- Store secrets in GitLab CI/CD Variables — never in code.
- Use `rules:` instead of deprecated `only:`/`except:` for job conditions.
- Pin Docker images used in jobs to specific digest or version tag.
- Use `cache:` for dependency directories (e.g., `node_modules`, `.venv`) to speed up builds.
- Use `artifacts:` to pass build outputs between stages.
- Use environments and manual gates for production deployments.
- Protect `main` branch: require MR with at least one approval and passing pipeline.

**Violations:**

- Running all jobs on every branch without filtering.
- Using `when: manual` as a substitute for proper access controls.
- Storing sensitive variables in `.gitlab-ci.yml` directly.
- Missing `timeout:` on long-running jobs.
