# Contributing

- Run `python -m pytest -q` before opening a pull request. Tests must not use the network.
- Keep modules under 300 lines, type-hinted, with frozen dataclasses where natural.
- No numbers in prose unless a script in this repository computed them on the synthetic fixture and the text says so.
- Flag messages describe a change to review. Accusatory vocabulary is rejected by `load_flag_rules`.
- Do not commit anything fetched from EDGAR. `cache/` is git-ignored.
- Never call `eval` or `exec`; never unpickle input.
