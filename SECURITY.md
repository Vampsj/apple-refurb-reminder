# Security Policy

## Reporting a vulnerability

Please do not open a public issue for vulnerabilities, exposed notification
credentials, or reports that contain private logs. Use GitHub's private
security advisory reporting for this repository.

Never include a Discord webhook, SMTP password, application password, `.env`
file, state file, or unredacted diagnostic bundle in an issue.

## Credential handling

Version 0.1 stores credentials in a local `.env` file with restrictive
permissions. The upcoming public V1 stores secrets in macOS Keychain by
default. The project does not collect telemetry.

If a credential is accidentally disclosed, revoke it at the provider before
reporting the incident.
