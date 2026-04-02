"""Seed the local question bank by generating questions for all modules.

Run once with a powerful LLM (Claude or large Llama), then use the local bank
for assessments without needing live LLM calls.

Usage:
    python scripts/seed_questions.py                       # All modules
    python scripts/seed_questions.py --discipline economics  # One discipline
    python scripts/seed_questions.py --module ECON-F-001     # One module
    python scripts/seed_questions.py --questions 10          # 10 per module
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rich.console import Console
from rich.progress import Progress as RichProgress

from phd_platform.config import get_settings
from phd_platform.core.enums import Discipline, Level
from phd_platform.core.parsing import parse_diagnostic_questions
from phd_platform.curriculum.loader import CurriculumLoader
from phd_platform.llm.client import get_llm_client
from phd_platform.persistence.database import get_engine, get_session, init_db
from phd_platform.persistence.repository import StudentRepository

console = Console()


async def seed_module(
    client, module, discipline, repo, num_questions: int
) -> int:
    """Generate and store questions for a single module."""
    # Check if questions already exist
    existing = await repo.question_count(module.id)
    if existing >= num_questions:
        return 0

    settings = get_settings()
    objectives_text = "\n".join(f"- {obj}" for obj in module.objectives)
    prompt = f"""Generate {num_questions} assessment questions for:
"{module.name}" ({module.id})

Learning objectives:
{objectives_text}

Level: {module.level.value if module.level else 'intermediate'}

Return ONLY a JSON array with fields: question, type (mcq|short_answer|proof|computation),
difficulty (1-5), objective_index, correct_answer, rubric, partial_credit_criteria

Make questions progressively harder (difficulty 1 to 5).
Each question should test a different learning objective where possible."""

    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    questions = parse_diagnostic_questions(response.content[0].text)
    q_dicts = [
        {
            "question": q.question,
            "type": q.type,
            "difficulty": q.difficulty,
            "objective_index": q.objective_index,
            "correct_answer": q.correct_answer,
            "rubric": q.rubric,
            "partial_credit_criteria": q.partial_credit_criteria,
        }
        for q in questions
    ]

    added = await repo.add_questions(module.id, q_dicts)
    return added


async def main_async(args):
    loader = CurriculumLoader()
    loader.load()

    engine = get_engine()
    await init_db(engine)
    client = get_llm_client()

    # Determine which modules to seed
    if args.module:
        try:
            module = loader.get_module(args.module)
            modules = [(module.discipline or Discipline.ECONOMICS, module)]
        except KeyError:
            console.print(f"[red]Module not found: {args.module}[/red]")
            return
    elif args.discipline:
        try:
            disc = Discipline(args.discipline)
        except ValueError:
            console.print(f"[red]Unknown discipline: {args.discipline}[/red]")
            return
        modules = []
        for level in Level:
            for mod in loader.get_modules_for_level(disc, level):
                modules.append((disc, mod))
    else:
        modules = []
        for disc in Discipline:
            for level in Level:
                for mod in loader.get_modules_for_level(disc, level):
                    modules.append((disc, mod))

    console.print(f"[bold]Seeding question bank for {len(modules)} modules "
                  f"({args.questions} questions each)[/bold]\n")

    total_added = 0
    with RichProgress() as progress:
        task = progress.add_task("Generating...", total=len(modules))
        async with get_session(engine) as session:
            repo = StudentRepository(session)
            for disc, module in modules:
                progress.update(task, description=f"{module.id}")
                try:
                    added = await seed_module(
                        client, module, disc, repo, args.questions
                    )
                    total_added += added
                    if added > 0:
                        console.print(f"  [green]+{added}[/green] {module.id} -- {module.name}")
                except Exception as e:
                    console.print(f"  [red]FAILED[/red] {module.id}: {e}")
                progress.advance(task)

    console.print(f"\n[bold green]Done![/bold green] Added {total_added} questions to the bank.")


def main():
    parser = argparse.ArgumentParser(description="Seed the local question bank")
    parser.add_argument("--discipline", help="Seed one discipline only")
    parser.add_argument("--module", help="Seed one module only")
    parser.add_argument("--questions", type=int, default=5, help="Questions per module (default: 5)")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
