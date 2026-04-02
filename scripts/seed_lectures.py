"""Seed lectures from local YAML files into the database.

Usage:
    python scripts/seed_lectures.py              # All lecture files
    python scripts/seed_lectures.py ECON-F-006   # One lecture
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from phd_platform.persistence.database import get_engine, get_session, init_db
from phd_platform.persistence.repository import StudentRepository

console = Console()
LECTURES_DIR = Path(__file__).resolve().parent.parent / "seeds" / "lectures"


async def seed_lecture(engine, path: Path) -> bool:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    module_id = data["module_id"]
    async with get_session(engine) as session:
        repo = StudentRepository(session)
        existing = await repo.get_lecture(module_id)
        if existing:
            console.print(f"  [dim]{module_id}: already seeded, skipping[/dim]")
            return False

        await repo.save_lecture(
            module_id=module_id,
            title=data["title"],
            content_blocks=data.get("blocks", []),
            author_agent_id=data.get("author_agent_id", ""),
            level_tier=data.get("level_tier", "foundation"),
            estimated_minutes=data.get("estimated_minutes", 30),
            learning_objectives=data.get("learning_objectives", []),
            prerequisites_summary=data.get("prerequisites_summary", ""),
        )
        block_count = len(data.get("blocks", []))
        console.print(f"  [green]+{module_id}[/green]: {data['title']} ({block_count} blocks)")
        return True


async def main(module_filter: str | None = None):
    engine = get_engine()
    await init_db(engine)

    lecture_files = sorted(LECTURES_DIR.glob("*.yaml"))
    if module_filter:
        lecture_files = [f for f in lecture_files if module_filter in f.stem]

    if not lecture_files:
        console.print("[yellow]No lecture files found.[/yellow]")
        return

    console.print(f"[bold]Seeding {len(lecture_files)} lecture(s)[/bold]\n")
    count = 0
    for path in lecture_files:
        if await seed_lecture(engine, path):
            count += 1

    console.print(f"\n[bold green]Done![/bold green] Seeded {count} lecture(s).")


if __name__ == "__main__":
    module_filter = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(module_filter))
