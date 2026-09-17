# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |

## Reporting a Vulnerability

Please report security vulnerabilities privately.

- Email: mastaan66@github (via GitHub Security Advisories preferred)
- Do not open a public issue for security reports.

We aim to acknowledge reports within 48 hours and provide a fix or mitigation within 14 days.

## Security Design

- All SQL uses parameterized queries (`?` placeholders).
- PRAGMA inputs are validated via strict regex.
- JSON inputs are validated before storage.
- No network calls in core; offline by default.
- WAL mode with RLock for thread safety; `health_check()` validates integrity.
