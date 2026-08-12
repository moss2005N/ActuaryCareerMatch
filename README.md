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
