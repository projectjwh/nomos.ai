"""Seed the question bank from local YAML files — no LLM needed.

Usage:
    python scripts/seed_local.py              # Seed all disciplines
    python scripts/seed_local.py economics    # Seed one discipline
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml
from rich.console import Console

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from phd_platform.persistence.database import get_engine, get_session, init_db
from phd_platform.persistence.repository import StudentRepository

console = Console()
SEEDS_DIR = Path(__file__).resolve().parent.parent / "seeds"


def load_seed_file(path: Path) -> dict[str, list[dict]]:
    """Load a YAML seed file and normalize to question dicts."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    modules = {}
    for module_id, questions in raw.items():
        if not isinstance(questions, list):
            continue
        normalized = []
        for q in questions:
            normalized.append({
                "question": q.get("q", ""),
                "type": q.get("type", "short_answer"),
                "difficulty": q.get("diff", 3),
                "objective_index": q.get("obj", 0),
                "correct_answer": q.get("answer", ""),
                "rubric": q.get("rubric", ""),
                "partial_credit_criteria": q.get("partial", ""),
            })
        modules[module_id] = normalized
    return modules


async def seed_discipline(engine, name: str, path: Path) -> int:
    """Seed all questions from a single discipline YAML file."""
    modules = load_seed_file(path)
    total = 0

    async with get_session(engine) as session:
        repo = StudentRepository(session)
        for module_id, questions in modules.items():
            existing = await repo.question_count(module_id)
            if existing >= len(questions):
                console.print(f"  [dim]{module_id}: {existing} already seeded, skipping[/dim]")
                continue
            added = await repo.add_questions(module_id, questions)
            total += added
            console.print(f"  [green]+{added}[/green] {module_id}")

    return total


async def main(disciplines: list[str] | None = None):
    engine = get_engine()
    await init_db(engine)

    seed_files = {
        "economics": SEEDS_DIR / "economics.yaml",
        "data_science": SEEDS_DIR / "data_science.yaml",
        "computer_science": SEEDS_DIR / "computer_science.yaml",
        "ai_ml": SEEDS_DIR / "ai_ml.yaml",
        "financial_engineering": SEEDS_DIR / "financial_engineering.yaml",
    }

    if disciplines:
        seed_files = {k: v for k, v in seed_files.items() if k in disciplines}

    grand_total = 0
    for name, path in seed_files.items():
        if not path.exists():
            console.print(f"[yellow]No seed file for {name}[/yellow]")
            continue
        console.print(f"\n[bold cyan]{name.replace('_', ' ').title()}[/bold cyan]")
        count = await seed_discipline(engine, name, path)
        grand_total += count

    console.print(f"\n[bold green]Done![/bold green] Seeded {grand_total} questions total.")

    # Show summary
    async with get_session(engine) as session:
        repo = StudentRepository(session)
        console.print("\n[bold]Question Bank Summary:[/bold]")
        for name in seed_files:
            # Count questions per discipline prefix
            from phd_platform.curriculum.loader import CurriculumLoader
            from phd_platform.core.enums import Discipline, Level
            loader = CurriculumLoader()
            loader.load()
            try:
                disc = Discipline(name)
            except ValueError:
                continue
            total = 0
            for level in Level:
                for mod in loader.get_modules_for_level(disc, level):
                    total += await repo.question_count(mod.id)
            console.print(f"  {name.replace('_', ' ').title()}: {total} questions")


if __name__ == "__main__":
    disc_args = sys.argv[1:] if len(sys.argv) > 1 else None
    asyncio.run(main(disc_args))
