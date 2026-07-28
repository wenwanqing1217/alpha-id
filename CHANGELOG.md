# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] - 2026-07-28

### Fixed
- **Test infrastructure**: Fixed `app.state.container` divergence from `Container.instance()` in registration tests — fixture now saves/restores the app state container to prevent cross-test contamination
- **Debug cleanup**: Removed all debug `print` statements from `container.py`, `registration.py`, and test files

### CI/CD
- Added GitHub Actions workflow (`.github/workflows/publish.yml`) for automated PyPI publishing via OIDC trusted publishing on tag push

## [0.4.0] - 2026-07-28

### Added
- **PyPI publish**: `alpha-id-zix` is now available on PyPI — `pip install alpha-id-zix`
- **CLI entry points**: `aid`, `aid-api`, `aid-mcp`, `aid-daemon`
- **README**: Full project documentation with architecture overview, quick start, and contributing guide

### Features
- **Alpha-ID core**: Decentralized identity (DID) resolution, JWT authentication, skill signing
- **Brain CLI**: Interactive identity management via Typer
- **Agent network**: A2A protocol support, agent skill repository
- **Web layer**: FastAPI endpoints for identity, registration (SMS verify), web dashboard
- **Storage**: SQLite (WAL mode) + PostgreSQL via SQLAlchemy + Alembic migrations
- **Security**: CSRF protection, token store, rate limiting, secrets encryption
- **Observability**: Prometheus metrics, structured logging (structlog)

### Dependencies
- FastAPI + Uvicorn for web layer
- SQLAlchemy + Alembic for ORM and migrations
- ChromaDB for vector search
- Cryptography, PyJWT for security
- Pydantic v2 for settings and validation
- Typer for CLI

[0.4.1]: https://github.com/wenwanqing1217/alpha-id/releases/tag/v0.4.1
[0.4.0]: https://github.com/wenwanqing1217/alpha-id/releases/tag/v0.4.0
