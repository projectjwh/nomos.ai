# PhD Platform

## Overview

Adaptive PhD-level education platform sourcing curricula from top universities (Harvard, MIT, Stanford, Princeton, Berkeley, CMU, Columbia). Covers 5 disciplines: Economics, Data Science, Computer Science, AI/ML, and Financial Engineering.

## Architecture

- **Adaptive Assessment**: Placement diagnostics identify weakness areas from high school through college level. Students must demonstrate A+ mastery (≥95%) before advancing.
- **4-Tier Progression**: Foundation → Undergraduate → Masters → Doctoral. Each tier has gate requirements, capstone projects, and defense checkpoints.
- **Defense System**: AI agents roleplay as journal reviewers (AER, NeurIPS, JACM, Journal of Finance, etc.) evaluating student work with discipline-specific rubrics.
- **Capstone Engine**: Generates personalized research projects based on student interests and strengths, with AI consultation throughout.

## Project Structure

```
config/           — YAML curriculum definitions, defense personas, milestone configs
docs/             — Interactive milestone visualization (milestones.html)
src/phd_platform/ — Core platform source code
  core/           — Data models, enums, shared types
  assessment/     — Placement tests, progression gates, adaptive remediation
  curriculum/     — YAML loader, module resolution, prerequisite graph
  defense/        — Journal reviewer agents, defense sessions, rubrics
  capstone/       — Project generation, AI consultation, evaluation
  tutor/          — Interactive tutoring engine, weakness targeting
tests/            — pytest test suite
```

## Commands

- Install: `pip install -e ".[dev]"`
- Run: `python -m phd_platform`
- Test: `pytest tests/ -v`
- Lint: `ruff check src/`
- Type check: `mypy src/`

## Key Design Decisions

- Curriculum data lives in YAML (`config/curriculum.yaml`) — the source of truth for all modules, prerequisites, and learning objectives. Code reads from YAML, never hardcodes curriculum.
- Defense personas in `config/defense_personas.yaml` define reviewer behavior, biases, and evaluation criteria per journal.
- The milestone visualization (`docs/milestones.html`) is a standalone HTML file with embedded D3.js — no build step needed.
- All AI interactions use the Anthropic SDK. Defense agents use system prompts from persona configs.
- Mastery thresholds: Foundation→Undergrad (90%), Undergrad→Masters (95%), Masters→Doctoral (95%), Doctoral completion (defense pass with majority accept).
