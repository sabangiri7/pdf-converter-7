# Security audit report — PDF Tools

Date: 2026-09-19  
Scope: local checkout `clonefileconv` / remote `sabangiri7/pdf-converter-7`  
Auditor role: AppSec / DevSecOps hardening pass (in-repo fixes + CI)

## 1. Threat model (short)

| Asset | Threat | Actor |
|---|---|---|
| Uploaded documents | Confidentiality leak via guessable download URLs, path escape, TTL race | Remote unauthenticated user |
| Host filesystem / secrets | Path traversal, symlink escape, poisoned job manifest | Attacker with job creation |
| Server process | Command injection via LibreOffice/OCR options; DoS via bombs / concurrency | Remote user |
| Other tenants (public) | SSRF, CSRF state-changing posts, XSS via filenames/errors | Remote user |
| Supply chain | Vulnerable pinned deps / base image | Compromised package |

Trust boundary: all HTTP clients are untrusted. Job IDs are the only authorization token for downloads (capability URL). No per-user accounts.

## 2. Findings fixed (with locations)

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F1 | High | Weak default `SECRET_KEY` accepted in Docker/`default` config (`app/config.py`, Dockerfile) | `assert_secret_key` refuses weak keys outside local debug; Docker requires runtime secret; image no longer bakes a secret |
| F2 | High | Download served manifest `path` without jail under `OUTPUT_ROOT` (`app/jobs.py` download routes) | `confined_under()` + `_confined_output()`; outputs recorded only if under job outdir |
| F3 | Medium | No CSRF on multipart tool POSTs | Flask-WTF `CSRFProtect`; token in `_form.html`; CSRF error page |
| F4 | Medium | No security headers | `install_security_headers` (CSP, XFO, nosniff, Referrer-Policy, Permissions-Policy, conditional HSTS) |
| F5 | Medium | No rate limiting | Flask-Limiter; default + POST limits on tool blueprints; `/healthz` exempt |
| F6 | Medium | Unbounded concurrent heavy jobs (DoS) | `MAX_CONCURRENT_JOBS` semaphore in `run_job` |
| F7 | Medium | Pillow decompression bombs not explicitly capped | `Image.MAX_IMAGE_PIXELS` from config at startup |
| F8 | Low | Compose published on all interfaces; no container hardening | Bind `127.0.0.1`; `read_only`, `cap_drop: ALL`, `no-new-privileges`, mem/cpu/pids limits, tmpfs |
| F9 | Low | Redaction used default apply without explicit text/image removal flags | `apply_redactions` with `PDF_REDACT_TEXT_REMOVE` / image pixels / line-art; `garbage=4, clean=True`; regression extracts text after redact |
| F10 | Info | html→PDF remote-fetch risk | Already text-only; documented; skips script/style/iframe; SSRF regression test monkeypatches urlopen |
| F11 | Info | No CI / Dependabot / vulnerability reporting | `.github/workflows/ci.yml`, Dependabot, `SECURITY.md`, this audit |

Subprocess review: only `office_to_pdf.py` and `ocr_pdf.py` — argv lists, timeouts, **no** `shell=True`. Language allowlisted for OCR.

## 3. Findings remaining (accepted / deferred)

| ID | Severity | Issue | Why remaining |
|---|---|---|---|
| R1 | High (public) | **No authentication** — anyone who can reach the port can upload/convert/download by job UUID | Product is intentionally local/self-host; add reverse-proxy auth / SSO before public |
| R2 | High (public) | Capability URLs (`/dl/<job_id>/…`) are bearer tokens; UUID v4 is strong but leaks via Referer/logs if mis-proxied | Mitigate with short TTL (default 1h), HTTPS, `Referrer-Policy`; optional auth cookie binding deferred |
| R3 | Medium | LibreOffice + Tesseract parse untrusted files **in-process** as `appuser` (not gVisor / microVM) | Documented; compose CPU/mem caps; split network-none worker deferred |
| R4 | Medium | PDF parser engines (PyMuPDF / pikepdf / pypdf) historically have memory-corruption bugs | Keep deps updated via Dependabot + `pip-audit`; sandbox host |
| R5 | Low | Organize tool loads pdf.js from cdnjs (CSP allowlisted) | Prefer vendoring pdf.js later; SRI optional follow-up |
| R6 | Low | In-memory rate-limit storage (not Redis) — per-process only | Fine for single gunicorn host; multi-replica needs Redis URI |
| R7 | Low | Zip bomb / nested Office macros still execute inside LibreOffice | OS-level isolation recommended |

## 4. Behavior changes

- Production/Docker configs refuse to start without a strong `PDF_TOOLS_SECRET_KEY` (≥32 chars, not a known placeholder).
- All tool forms include CSRF tokens; bare POSTs fail when CSRF is enabled.
- Security headers on all responses.
- Concurrent jobs beyond `PDF_TOOLS_MAX_CONCURRENT_JOBS` (default 2) return a friendly busy error.
- Compose publishes only on `127.0.0.1` and runs the container read-only with dropped caps.
- `PDF_TOOLS_CONFIG=default` now maps to `ProductionConfig` (was a loose BaseConfig).

## 5. Required environment variables

| Variable | Required when | Notes |
|---|---|---|
| `PDF_TOOLS_SECRET_KEY` | production / Docker / `PUBLIC_DEPLOY` | `openssl rand -hex 32` |
| `PDF_TOOLS_CONFIG` | recommended | `development` local; `production` deploy |
| `PUBLIC_DEPLOY` | optional | default `false` |
| `PDF_TOOLS_COOKIE_SECURE` | HTTPS | set `true` behind TLS |
| `PDF_TOOLS_MAX_*` | optional | file MB, files, pages, concurrent jobs, image pixels |
| `PDF_TOOLS_RATELIMIT*` | optional | disable with `PDF_TOOLS_RATELIMIT=false` |

## 6. Deployment limitations

- Not a multi-tenant SaaS control plane.
- Bind localhost by default outside Docker; Docker compose binds host `127.0.0.1`.
- Put TLS + auth in a reverse proxy for any exposure beyond a trusted LAN.
- OCR / Office need system binaries; long gunicorn timeout (300s).
- Read-only container root still needs writable `instance` volume + `/tmp` tmpfs.

## 7. Prioritized remaining risks

1. Public exposure without auth (R1)  
2. Unsandboxed document converters (R3/R4)  
3. Capability-URL download model (R2)  
4. CDN script for organize preview (R5)

## 8. Verdict

| Target | Verdict |
|---|---|
| Local developer use (`127.0.0.1`) | **Safe** with defaults |
| Private LAN / VPN behind firewall + strong secret + compose hardening | **Acceptable** if operators accept residual PDF-parser risk |
| Public internet | **Not fully secure** — do not claim production-public-ready without auth, TLS, monitoring, and stronger sandboxing |

## 9. Tests & tooling (executed 2026-09-19)

- `pytest`: **527 passed**, 2 skipped, 0 failed; coverage **79.02%** (fail-under 55).
- `ruff check app tests scripts`: **All checks passed**.
- `pip-audit -r requirements.txt`: **No known vulnerabilities found**.
- `bandit`: CI runs on Python 3.12 (`bandit -r app -ll`). Local Python 3.14 hits a known `ast.Num` bandit bug — use CI / 3.12 for bandit.
- Trivy / gitleaks: configured in `.github/workflows/ci.yml` (run on GitHub Actions).
