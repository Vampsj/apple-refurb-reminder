# Release process

V1 must not leave Draft status until every item below passes.

## Automated gates

- CI passes on macOS 14 with Python 3.13.
- CI passes on Ubuntu with Python 3.13 and 3.14.
- All unit and integration tests pass.
- Ruff reports no violations.
- Every macOS shell script passes `bash -n`.
- `uv build` produces both a wheel and source distribution.
- The isolated macOS installation smoke test installs the built project into a
  fresh runtime and runs configuration validation.

## Functional gates

- JP, US, CN, and HK catalogs parse from stored representative fixtures.
- Mac, iPhone, and iPad each have matching and `Any`-criterion coverage.
- Discord-only, email-only, and combined TEST delivery paths pass.
- A failed notification test preserves the prior configuration.
- Three consecutive category failures open one incident; recovery sends once.
- Failed categories never accumulate product absence.
- Schema-v1 migration creates a backup and preserves deduplication state.
- Region changes archive prior rules and state while preserving notification settings.
- A fresh macOS install succeeds on a clean user account.
- A legacy v0.1 macOS installation upgrades successfully.
- A deliberately broken candidate update leaves the prior runtime active.

## Manual release steps

1. Update localized documentation and the changelog.
2. Confirm the version in `pyproject.toml`.
3. Confirm the Draft PR contains no secrets or real user data.
4. Mark the PR ready for review only after all gates pass.
5. Merge to `main`.
6. Create an annotated semantic-version Git tag.
7. Publish GitHub release notes describing supported regions, products, platforms,
   migration behavior, and known limitations.

Do not publish automatically from CI. Releases and updates are intentionally manual.
