# Repository instructions for coding agents

## Environment

- Use Python 3.12 and uv for Python versions, virtual environments, and dependencies.
- Use uv for every dependency change. Never use pip, Poetry, or Conda.
- Follow the existing project structure. Add dependencies only with clear justification.

## Code

- Prefer simple, readable, maintainable Python with type hints where appropriate.
- Keep functions focused and modular. Avoid unnecessary abstractions and overengineering.
- Use Ruff for linting and formatting. Write tests for new functionality.

## Collaboration

- Work only on assigned tasks. Do not modify unrelated files.
- Avoid editing files owned by other teammates without coordination.
- Agree on shared API contracts before changing them.
- Coordinate edits to `pyproject.toml`, `uv.lock`, and other shared dependency files.
- Use feature branches. Never commit directly to `main`.
- Do not perform destructive Git operations without explicit approval.

## Safety

- Never commit secrets, API keys, or `.env` files.
- Do not expose environment variables containing credentials.
- Do not deploy without explicit approval.
- Do not silently change the project architecture.

## Completion

Before reporting a task complete, run relevant tests, `uv run --locked ruff check .`,
and `uv run --locked ruff format --check .`. Report files modified, failures or
unresolved issues, and assumptions that affect integration.
