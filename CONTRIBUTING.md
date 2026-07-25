# Contributing

Bug reports, parser breakage reports, documentation improvements, and pull
requests are welcome.

Before submitting a change:

```bash
.venv/bin/pytest
.venv/bin/ruff check .
```

Do not commit live Apple responses that contain personal data, notification
credentials, `.env` files, state files, or logs. Parser fixtures should be
minimal and contain only the markup required by the test.

Large feature proposals should begin as an issue so that product semantics and
the supported-region matrix can be agreed before implementation.
