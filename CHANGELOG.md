# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Formal MIT LICENSE file
- SECURITY.md with vulnerability reporting policy
- Structured logging throughout core modules
- Unified exception hierarchy for all subpackages
- Docker multi-stage build with lockfile
- `CHANGELOG.md` for version tracking

### Fixed
- 42 failing tests in `test_skill_signer.py` — skill_signer API aligned with test expectations
- Chinese error messages restored (were replaced with `???????`)
- SkillRuntime now generates PoE records when `poe_client` is provided
- Content hash verification on skill execution (tamper detection)
- `SkillRegistry.get_content()` returns `None` on hash mismatch
- License reference in README now points to actual LICENSE file
- Dockerfile builder stage properly used

### Changed
- `sign_skill()` accepts `dependencies` keyword argument
- `SkillRegistry.register()` makes `content` parameter optional
- `SkillRegistry.revoke()` requires `signer` parameter
- `SkillAttributionTracker.record()` accepts `AttributionRecord` objects
- `SkillRuntime.execute()` uses `json.dumps` for dict/list results
- SkillRuntime stdout capture for no-main skills

## [0.1.0] - 2024-11-01

### Added
- DID identity layer (`did:aid:` method, Ed25519 keys)
- TwinBrain agent engine (LLM + Tools + Loop)
- Skill signing, verification, registry, and runtime
- Skill attribution tracking and reputation scoring
- Proof of Execution (PoE) with chain support
- Decentralized skill repository protocol
- Multi-agent collaboration (DID mutual auth, skill call chain)
- Web demo (FastAPI + Vue 3)
- Desktop Fairy悬浮球 assistant
- CLI scaffold via `aid scaffold init`
