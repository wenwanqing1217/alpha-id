# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take the security of AID seriously. If you believe you have found a
security vulnerability, please **do not** open a public issue.

Instead, send a report to the maintainers via:

- **Email**: (coming soon)
- **Direct message**: (contact maintainers through project channels)

Please include as much detail as possible:

- Type of issue (e.g., buffer overflow, SQL injection, cross-site scripting)
- Full paths of source file(s) related to the manifestation of the issue
- The location of the affected source code (tag/branch/commit or direct URL)
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

## Response Timeline

- **24 hours**: Acknowledgment of receipt
- **7 days**: Initial assessment and severity classification
- **30 days**: Fix deployed (critical) / 90 days (moderate)

## Disclosure Policy

When a vulnerability is reported, we:

1. Confirm receipt within 24 hours
2. Assess the issue and assign a severity level
3. Develop and test a fix
4. Release a security update and announce the fix
5. Credit the reporter (if desired)

## Scope

This security policy covers:

- The `aid` CLI tool
- The `alpha_id` Python SDK
- The FastAPI web application
- The TwinBrain agent engine
- Skill registry and runtime components

Out of scope:

- Third-party dependencies (report upstream)
- Applications using AID as a library (follow their policies)
