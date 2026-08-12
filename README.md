# Actuary Career Match

A Django platform for matching actuarial candidates with internships and jobs.

## Local setup

```bash
source /Users/david/.venv/bin/activate
cp .env.example .env
set -a
source .env
set +a
python manage.py migrate
python manage.py runserver
```

Settings read environment variables directly. The `set -a` sequence exports the
values from `.env`; `.env` is intentionally excluded from Git.

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

For local UI data only, first seed Phase 2 reference tables and then clearly
fictional jobs:

```bash
python manage.py seed_reference_data
python manage.py seed_development_jobs
```

The development job command refuses to run unless `DEBUG=True`.

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
