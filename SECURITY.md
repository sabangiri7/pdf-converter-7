# Security Policy

## Supported versions

Security fixes are applied on the `main` branch of this repository.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security bugs.

Email the maintainer via GitHub: [@sabangiri7](https://github.com/sabangiri7) (use a private contact channel / security advisory if available).

Include:

- affected version / commit
- reproduction steps
- impact assessment (who can exploit, what they gain)

You should receive an acknowledgement within a reasonable time. Please give us time to patch before public disclosure.

## Deployment posture

| Mode | Safe? | Notes |
|---|---|---|
| Local (`127.0.0.1`, `PDF_TOOLS_CONFIG=development`) | Yes | Default bind is localhost; weak `SECRET_KEY` allowed only here |
| Private LAN / VPN + Docker compose defaults | Conditionally | Strong `PDF_TOOLS_SECRET_KEY` required; keep `PUBLIC_DEPLOY=false`; prefer binding publish port to `127.0.0.1` + reverse proxy |
| Public internet | Not fully hardened | Needs TLS terminator, auth/SSO or network ACL, monitoring, and acceptance of residual PDF parser risk (see `docs/SECURITY_AUDIT.md`) |

Default: **`PUBLIC_DEPLOY=false`**. Do not set it to `true` without HTTPS, a strong secret, and a threat-model review.

Required for any non-local deploy:

```bash
export PDF_TOOLS_SECRET_KEY="$(openssl rand -hex 32)"   # >= 32 chars
export PDF_TOOLS_CONFIG=production
export PUBLIC_DEPLOY=false   # keep false unless intentionally public
```

See README **Production security** and `docs/SECURITY_AUDIT.md` for limits and remaining risks.
