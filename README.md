# Actuary Career Match

A Django platform for matching actuarial candidates with internships and jobs.

## Source-available license (draft)

Copyright © 2026 Dawei Niu.

This project is **source-available, not OSI-approved open source**. The draft
[`LICENSE`](LICENSE) permits viewing and downloading the code and permits use,
modification, and sharing for defined personal-learning, non-commercial academic
research, teaching, and non-commercial educational purposes, subject to
attribution and license-retention conditions.

The draft license does **not** permit public hosting or deployment of the
Original Software or a Modified Work without prior written authorization, even
when access is free and the activity is educational, research-oriented,
portfolio-based, or otherwise non-commercial. Local, private non-commercial use
and compliant source-code redistribution remain permitted. Publishing source in
a repository is distinct from operating a publicly accessible instance.

Commercial use—including internal business use, commercial deployment, paid
services, consulting, and incorporation into a commercial product or service—
requires the copyright holder's prior written permission. See the
[`Licensing FAQ`](docs/LICENSING_FAQ.md) for examples and unresolved edge cases.
Commercial licensing requests may be sent to
[actuarycareermatch@gmail.com](mailto:actuarycareermatch@gmail.com). The custom
license remains a draft and requires legal review before the repository is made
public or the terms are treated as final. It has not received independent legal
review, and no legal validity or approval is claimed.

Downstream recipients receive rights in Dawei Niu's original code directly from
Dawei Niu, so permitted redistribution is not sublicensing. Authors of
independent modifications retain their copyrights and must directly license
their distributed modifications under the same non-commercial terms. Dawei Niu
may commercially license only code he owns or for which he has separately
obtained sufficient rights.

Third-party job postings, employer-authored content, company names and marks,
external datasets, linked content, and separately licensed dependencies are not
licensed by the project license. Required attribution does not imply endorsement,
sponsorship, or affiliation.

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
set -a
source .env
set +a
python manage.py migrate
python manage.py runserver
```

Settings read environment variables directly. The `set -a` sequence exports the
values from `.env`; `.env` is intentionally excluded from Git.

`DJANGO_ENVIRONMENT=development` is required for local development. With no
environment selection, the application assumes production and fails closed
until its required settings are supplied.

## Testing email verification locally

The default email backend is Django's console backend. Register a user, then copy
the verification URL printed in the `runserver` terminal and open it in the same
browser. No real email is sent. Automated tests use Django's in-memory email
backend.

## Testing phone verification locally

Keep `PHONE_VERIFICATION_BACKEND=console` and `DEBUG=True`. After adding an E.164
phone number such as `+12025550123`, the six-digit OTP is printed in the
`runserver` terminal. Enter that code in the browser. Only a secure password hash
of the code is stored, and issuing a replacement invalidates the previous code.

Twilio is not contacted unless `PHONE_VERIFICATION_BACKEND=twilio` is explicitly
set and all Twilio Verify credentials are supplied. Install the optional `twilio`
dependency before enabling that backend.

## Security flow

Registration requires email verification, then phone verification. Normal login
validates username/email and password first but does not create an authenticated
Django session. A session is created only after a valid phone OTP or unused
recovery code succeeds. In local `DEBUG` mode only, staff and superusers bypass
the second step to prevent development lockout.

## Validation

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py test
```

GitHub Actions runs these checks, dependency consistency, and `pip-audit` for
pushes to `main` and pull requests. Dependabot is configured to propose weekly
Python and GitHub Actions updates. Neither workflow deploys the application,
changes repository visibility, or sends real email/SMS.

## Current automation boundaries

Resume analysis is user-initiated and defaults to a deterministic local mock
provider. It proposes review items for the user to accept or ignore; it does not
automatically rewrite or update a resume document. Configuring a different
analysis provider requires explicit implementation and credentials.

Job source adapters and management commands can refresh authorized public job
sources when an operator runs them. This repository does not currently include
Celery, cron, or another scheduler, so job postings are not refreshed
automatically after deployment unless an operator configures external scheduling.

## Phase 3 job sources

External job sources are isolated behind `jobs.sources.BaseJobSourceAdapter`.
Concrete adapters must be written for one explicitly authorized official API or
public structured feed. They must identify the application, use timeouts and
source-specific rate limits, and stop when terms, robots directives, access
controls, authentication, CAPTCHA, or anti-bot restrictions prohibit collection.
There is intentionally no generic crawler or restriction-bypass mechanism.

`JobSource` controls enablement and records synchronization status. `ImportRun`
records counts and errors for each attempt. Disabled sources are recorded as
skipped without calling their adapters. Source/external-ID uniqueness prevents
repeat inserts; records lacking a reliable ID use a conservative company, title,
location, and source-URL identity.

For local UI data only, first seed Phase 2 reference tables and then the clearly
fictional public demonstration jobs:

```bash
python manage.py seed_reference_data
python manage.py seed_demo_jobs
```

The demonstration command refuses to run unless `DEBUG=True`. Its companies,
postings, identifiers, descriptions, and `.example.test` URLs are synthetic and
do not represent real employers or vacancies. Real imported job records belong
in the deployment database, not in the publicly distributed source dataset.

### Configuring an authorized real job source

Create the company first, then add a `JobSource` in Django admin. Every source is
disabled by default. Review the applicable terms and robots policy and record both
statuses as **Reviewed and allowed** (or **Not applicable** only when genuinely
inapplicable) before enabling it.

- Greenhouse: choose `Greenhouse public feed` and enter the public board token in
  `board_identifier`. The adapter calls only the public Greenhouse Job Board API.
- Lever: choose `Lever public feed` and enter the public site identifier in
  `board_identifier`. The adapter calls only the public Lever postings endpoint.
- Authorized JSON: choose `Authorized ATS/API` or `Other authorized API`, provide
  the documented HTTPS feed URL, and configure `field_mapping` with dotted paths.
  Required mappings are `external_job_id`, `title`, `description`, and
  `source_url`; `list_path` is optional.

Set conservative timeout, request interval, and missing-sync threshold values.
Then run `python manage.py sync_job_source SOURCE_ID --dry-run --verbose` before a
real sync. No source is contacted while disabled or while either policy review is
pending/disallowed.

Local Greenhouse and Lever fixtures make no network request:

```bash
python manage.py seed_fixture_job_sources
# Use the two source IDs printed above:
python manage.py sync_job_source GREENHOUSE_SOURCE_ID --fixture jobs/fixtures/greenhouse_sample.json --verbose
python manage.py sync_job_source LEVER_SOURCE_ID --fixture jobs/fixtures/lever_sample.json --verbose
```

The source type must match the fixture. Add `--dry-run` to validate without any
database writes. These fixtures are synthetic and make no live hiring claims.

## Production security configuration

This technical configuration guidance does not grant permission to host or
deploy the Software. Public hosting or deployment requires the prior written
authorization described in the draft license, including for free and
non-commercial instances.

Production requires all of the following to be explicit:

- `DJANGO_ENVIRONMENT=production`, `DEBUG=False`, a random `SECRET_KEY` of at
  least 50 characters, and concrete `ALLOWED_HOSTS` without a wildcard.
- `DB_ENGINE` and its database settings. PostgreSQL is recommended for a hosted
  deployment; install the optional `psycopg` dependency before selecting it.
- A delivery-capable `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, and explicit SMTP
  host when using Django's SMTP backend.
- `PHONE_VERIFICATION_BACKEND=twilio`, all three Twilio Verify credentials, and
  the optional `twilio` dependency. Console email/SMS backends are rejected in
  production.

HTTPS redirect and secure session/CSRF cookies default on in production. Set
`CSRF_TRUSTED_ORIGINS` to HTTPS origins only when cross-origin POST handling is
actually needed. `SECURE_HSTS_SECONDS` defaults to zero because HSTS can lock a
domain into HTTPS; enable it only after HTTPS works reliably, then consider
subdomains and preload separately.

`TRUST_X_FORWARDED_PROTO=True` sets Django's trusted proxy header to exactly
`X-Forwarded-Proto: https`. Enable it only when a trusted reverse proxy removes
any client-supplied copy and sets the header itself. The application does not
accept an arbitrary forwarded-header name from configuration.

Before deployment, run `collectstatic`, apply migrations, configure persistent
private storage for resumes, choose a production WSGI/ASGI server and reverse
proxy, and run `python manage.py check --deploy` with the real production
environment. This repository does not currently provide a complete hosting or
backup solution.

## Stored data and deletion behavior

The application stores account identifiers, email and verified phone state,
candidate profile data, education, exams, skills, work experience, job saves and
application tracking. Uploaded PDF resumes are stored in private media. Resume
analysis records may contain extracted contact, education and work information;
suggestions also contain structured payloads and source snippets from the PDF.

Deleting a resume removes the authenticated user's stored PDF, every associated
resume analysis, extracted analysis JSON, suggestions, suggestion payloads and
source snippets. Structured profile information previously accepted by the user
is retained because it is part of the profile and may have been edited after
acceptance. Other users' files and analysis records are not affected.

Current limitations: replacing a resume does not immediately purge analyses for
older uploads; those records are removed when the user uses resume deletion.
Application tracking and other profile records have no automatic retention
period. Database backups, infrastructure logs and storage snapshots are outside
the application's deletion workflow. There is not yet a self-service full
account deletion feature. These behaviors are documented facts, not a claim of
GDPR or other regulatory compliance.

## Contributing and security

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before proposing a change. In
particular, contributor relicensing rights have not been resolved, so substantial
third-party code should not be accepted until appropriate contributor terms have
received legal review. Report vulnerabilities privately as described in
[`SECURITY.md`](SECURITY.md).
