# Release exceptions

Releases follow the maintainer's standard PyPI release policy with one exception: `validation.yml` is this repository's own rather than the shared `python-validation.yml` from wakamex/release-actions, because the tests use pytest and the shared workflow, like the release orchestrator, runs `unittest` discovery, which would find none of them. Prepare releases by hand.
