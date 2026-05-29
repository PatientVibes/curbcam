# Security Policy

## Supported versions

curbcam is pre-1.0 and ships from `main`. Security fixes land on `main` and the
latest tag (currently `v0.2.0-mvp-2`). Older tags are not maintained.

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue for an
unpatched vulnerability.

- Preferred: open a [GitHub private security advisory](https://github.com/PatientVibes/curbcam/security/advisories/new).
- Or email the maintainer at the address on the commit history.

Include the affected version/commit, reproduction steps, and impact. Expect an
acknowledgement within a few days; please allow reasonable time for a fix before
public disclosure.

## Threat model

curbcam is designed to run on a **LAN-only** device (typically a Raspberry Pi):

- The web app binds for local-network access and is **not** intended to be
  exposed to the public internet. Put it behind a VPN/reverse proxy with TLS if
  you need remote access.
- A **single admin password** (Argon2-hashed) gates the UI and APIs; the
  session cookie and stream tokens are signed with a per-install secret stored
  in `auth.json` (written owner-only). Event media is served only behind an
  authenticated session.
- **No data leaves the device**: no cloud sync, no telemetry, and no
  license-plate OCR is shipped.

### Privacy / responsible use

Speed cameras capture people and vehicles in public spaces. The legal status of
doing so varies by jurisdiction. **Check your local laws before pointing this at
a road or shared space.** See the design spec's *Responsible Use & Privacy*
section (§15) for the project's full stance.

Reports about the *privacy posture* (e.g. an endpoint that leaks event imagery
or stream tokens without authentication) are in scope and welcome.
