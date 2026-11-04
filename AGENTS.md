# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Domain

This is a MCP server for ODM Decision Server runtime REST APIs.
It is compliant to the MCP SDK v2.

---
## Project Setup and Management

- Python version: 3.13 or 3.14. Don't use newer syntax.
- Dependency management: `uv` and `pyproject.toml`. Never use `pip` or a `requirements.txt` file.
- Add a dependency with `uv add <package>`. Never use `uv pip` for dependencies.
- Branch from `main` as `feature/<name>` and use Conventional Commits.
- Do not stage changes. Don't commit to `main` or push without being asked.

---
## Commands

```bash
# Run all tests (use tests/ subdir — root-level test_*.py files are integration tests that require a live ODM server)
uv run pytest tests/

# Run a single test
uv run pytest tests/test_decision_mcp_server.py::test_server_initialization

# Run the MCP server
uv run ibm-odm-decision-mcp-server --url http://localhost:9060/res

# Upgrade the dependency to a specific package 'package_name'
uv lock --upgrade-package <package_name>

# look for secrets inadvertently introduced and update the file .secrets.baseline with findings
detect-secrets scan --update .secrets.baseline
```

---
## Coding Conventions

- Type-hint public functions and methods, including their return types.
- Use `pathlib` for path management. Don't use `os.path`.
- Prefer f-strings over `str.format()` or `%` formatting.
- Follow EAFP: handle exceptions rather than checking conditions up front.
- Write Google-style docstrings for every public function and method.
- Validate request bodies with Pydantic models.
- Embrace idiomatic Python like comprehensions, generators, and decorators.

---
## Project Structure

- The source are in the src/ folder.
- The tests are in the tests/ folder.
- Don't create new packages or new files without being asked.

---
## Quality Gates

A task is done only when all of these pass:

- `uv run pytest` passes, with a test added for every new feature.

---
## Constraints

- Ask before adding any external dependency.
- Declare a task done only after the gates pass and docstrings are updated.

---
## Ignore

Treat everything in `.gitignore` as off-limits to read or edit. On top of
that, never open:

- Secrets and `.env` files
