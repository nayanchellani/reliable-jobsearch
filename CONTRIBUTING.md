# Contributing to Job Aggregator

Thanks for your interest! This is an MIT-licensed, local-first project.

## How to add a connector

1. **Create connector file**: `app/connectors/my_source.py`
   - Inherit from `Connector` base class.
   - Implement `fetch(query, location, filters) -> List[Job]`.
   - Respect rate limits (`rate_limit_ms`), cache responses, handle errors gracefully.
   - Never crash the whole search if this connector fails.

2. **Add tests**: `tests/test_my_source.py`
   - Use saved fixtures (JSON) in `tests/fixtures/`.
   - Test normal case, edge cases, error handling.

3. **Register in config**: Add to `config.yaml` or `app/api/main.py`.

4. **Document**: Update README with source coverage and limits.

## Code style

- Python 3.12+, type hints everywhere.
- Run `ruff check .` and `mypy app/`.
- Follow existing patterns in `app/connectors/`.

## Pull requests

- One feature per PR.
- Include tests.
- Update README if adding a source.

## License

MIT. By contributing, you agree your code is MIT-licensed.