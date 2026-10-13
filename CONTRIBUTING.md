# Contributing

Thank you for your interest in ActuaryCareerMatch. The project is currently
source-available under a draft non-commercial license; it is not OSI-approved
open source. Read [`LICENSE`](LICENSE) and
[`docs/LICENSING_FAQ.md`](docs/LICENSING_FAQ.md) before using or contributing.

## Contribution status

Issue reports and suggestions are welcome. External code, documentation, test,
configuration, and other copyrightable contributions are **not accepted at this
time**. Please do not open a pull request or attach a patch to an issue. Pull
requests may be closed without review or merge.

No contributor license agreement or copyright assignment has been adopted. A
contributor would ordinarily retain copyright in their contribution, and the
project owner could not assume a right to offer that contribution under a
separate commercial license. Limiting community participation to reports and
ideas protects Dawei Niu's ability to maintain a consistent source-available
license and offer commercial licenses for owner-authored code while appropriate
contributor terms receive legal review.

Describe observed behavior, reproduction steps, expected behavior, or a proposed
outcome in ordinary language. Do not submit implementation code. The maintainer
may independently investigate and implement an idea. Reporting an issue or
suggestion does not transfer ownership of any separately submitted material and
does not guarantee implementation. This policy may change only after suitable
contributor terms have been reviewed and published.

## Development workflow

The commands below document the maintainer's development checks; they are not an
invitation to submit patches. Maintainers use Python 3.12, an isolated virtual
environment, and the local setup in [`README.md`](README.md):

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py test
pip check
git diff --check
```

Never include real credentials, `.env` files, database files, uploaded resumes,
personal data, or copied proprietary job content. Tests must use fictional data
and in-memory/console delivery backends; they must not send real email or SMS.

Report security and privacy issues using [`SECURITY.md`](SECURITY.md), not a
public issue containing exploit details or personal information.
