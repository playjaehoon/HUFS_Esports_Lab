# Project guidance

Read README.md and the relevant documents in docs/ before editing. These documents
distinguish the initial implementation from proposed behavior; do not claim a
planned feature already exists.

## Product intent

- Philips Evnia sponsors this HUFS lab. Preserve the supplied brand assets and
  distinguish proposed design choices from official brand guidance.
- Target flow: immediate signup, reservation, student reservation history,
  student-card comparison at each visit, staff check-in and checkout.
- Students need their own reservation details/cancellation and profile editing.
  Keep history and restrictions linked to an immutable student primary key.

## Engineering

- Prefer incremental changes to the existing Flask/Jinja application.
- Enforce roles and record ownership on the server. Hiding admin links is not
  authorization. Validate availability and reservation creation consistently.
- Never store or display plaintext passwords/PINs. Keep credentials, databases,
  backups, and private configuration out of Git and logs.
- Use Korea time for business dates and explicit time-zone conversion for
  timestamps. Read operating limits from one shared source of truth.
- Protect reservation allocation with database constraints and transactions.
- Version schema changes and preserve existing data. create_all is not a schema
  migration. Check the deployed schema before proposing an operational migration.
- Use synthetic data and isolated databases for development and tests.
  tools/audit_snapshot.py records initial behavior; it is not a release test.
- Add meaningful regression checks for authentication, ownership, booking rules,
  concurrency, state transitions, and migrations when those behaviors change.
  Check desktop/mobile views for interface changes.
- Update the corresponding documentation with changed behavior, validation, and
  any deployment requirements. Distinguish local changes from deployed changes.

## Known context

The initial audit is based on e0681a0. The public site is
https://hufsesports.pythonanywhere.com/. Hosting account access and the exact
deployed version/configuration were not available during the initial audit.
The critical issues in the initial code are recorded in docs/01-audit.md as
historical findings. Local fixes and remaining deployment steps are tracked in
docs/07-progress.md. Never equate a local commit with a deployed release.
