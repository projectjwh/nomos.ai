"""PhD Platform CLI entry point — read-only queries + interactive learning commands."""

from __future__ import annotations

import argparse
import asyncio
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from phd_platform.core.enums import Discipline, Level
from phd_platform.curriculum.loader import CurriculumLoader

console = Console()

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
DISC_CHOICES = [d.value for d in Discipline]
LEVEL_CHOICES = [l.value for l in Level]


def _parse_discipline(value: str) -> Discipline:
    try:
        return Discipline(value)
    except ValueError:
        console.print(f"[red]Unknown discipline: {value}[/red]")
        console.print(f"Options: {', '.join(DISC_CHOICES)}")
        sys.exit(1)


def _parse_level(value: str) -> Level:
    try:
        return Level(value)
    except ValueError:
        console.print(f"[red]Unknown level: {value}[/red]")
        console.print(f"Options: {', '.join(LEVEL_CHOICES)}")
        sys.exit(1)


def _get_loader() -> CurriculumLoader:
    loader = CurriculumLoader()
    loader.load()
    return loader


def _run_async(coro):
    """Run an async function from sync context."""
    return asyncio.run(coro)


def _score_color(score: float) -> str:
    if score >= 0.95:
        return "bold green"
    elif score >= 0.90:
        return "green"
    elif score >= 0.80:
        return "yellow"
    elif score >= 0.60:
        return "red"
    return "bold red"


# ---------------------------------------------------------------------------
# Read-only commands (no AI, no database)
# ---------------------------------------------------------------------------
def cmd_info(args: argparse.Namespace) -> None:
    """Display platform overview and curriculum statistics."""
    loader = _get_loader()

    table = Table(title="PhD Platform -- Curriculum Overview", show_lines=True)
    table.add_column("Discipline", style="cyan", width=24)
    table.add_column("Foundation", justify="center")
    table.add_column("Undergraduate", justify="center")
    table.add_column("Masters", justify="center")
    table.add_column("Doctoral", justify="center")
    table.add_column("Total", justify="center", style="bold")

    for disc in Discipline:
        row = [disc.value.replace("_", " ").title()]
        total = 0
        for level in Level:
            modules = loader.get_modules_for_level(disc, level)
            count = len(modules)
            total += count
            row.append(str(count))
        row.append(str(total))
        table.add_row(*row)

    console.print(table)
    console.print(f"\n[bold]Total modules:[/bold] {loader.total_modules}")
    console.print("[bold]Disciplines:[/bold] 5")
    console.print("[bold]Academic tiers:[/bold] Foundation -> Undergraduate -> Masters -> Doctoral")

    console.print(Panel(
        "[yellow]Foundation -> Undergraduate:[/yellow] 90% mastery diagnostic\n"
        "[green]Undergraduate -> Masters:[/green] 95% mastery + capstone defense (2 reviewers)\n"
        "[orange1]Masters -> Doctoral:[/orange1] 95% mastery + thesis defense (3 reviewers)\n"
        "[red]Doctoral Completion:[/red] Dissertation defense (5 reviewers, 3/5 Accept)",
        title="Gate Requirements",
        border_style="yellow",
    ))


def cmd_modules(args: argparse.Namespace) -> None:
    """List modules for a discipline and level."""
    loader = _get_loader()
    disc = _parse_discipline(args.discipline)
    level = _parse_level(args.level)

    modules = loader.get_modules_for_level(disc, level)
    if not modules:
        console.print(f"[yellow]No modules found for {disc.value} / {level.value}[/yellow]")
        return

    table = Table(title=f"{disc.value.replace('_', ' ').title()} -- {level.value.title()}")
    table.add_column("ID", style="dim")
    table.add_column("Module", style="cyan")
    table.add_column("Weeks", justify="center")
    table.add_column("Prerequisites", style="dim")

    for mod in modules:
        prereqs = ", ".join(mod.prerequisites) if mod.prerequisites else "--"
        table.add_row(mod.id, mod.name, str(mod.weeks), prereqs)

    console.print(table)

    if args.verbose:
        for mod in modules:
            console.print(f"\n[bold cyan]{mod.id}[/bold cyan] -- {mod.name}")
            for obj in mod.objectives:
                console.print(f"  - {obj}")


def cmd_prereqs(args: argparse.Namespace) -> None:
    """Show prerequisite chain for a module."""
    loader = _get_loader()
    try:
        chain = loader.get_prerequisite_chain(args.module_id)
    except Exception:
        console.print(f"[red]Module not found: {args.module_id}[/red]")
        sys.exit(1)

    if not chain:
        console.print(f"[yellow]{args.module_id} has no prerequisites[/yellow]")
        return

    console.print(f"[bold]Prerequisite chain for {args.module_id}:[/bold]\n")
    for i, mod in enumerate(chain):
        indent = "  " * i
        prefix = "+-- " if i > 0 else ""
        console.print(f"{indent}{prefix}{mod.id} -- {mod.name}")


# ---------------------------------------------------------------------------
# Interactive commands (require AI + database)
# ---------------------------------------------------------------------------
def _get_async_client():
    """Create an AsyncAnthropic client."""
    from phd_platform.llm.client import get_llm_client
    return get_llm_client()


def _get_db_engine():
    """Create the database engine and init tables."""
    from phd_platform.persistence.database import get_engine, init_db
    engine = get_engine()
    asyncio.run(init_db(engine))
    return engine


async def _get_repo(engine):
    """Get a repository with a session."""
    from phd_platform.persistence.database import get_session
    from phd_platform.persistence.repository import StudentRepository
    async with get_session(engine) as session:
        yield StudentRepository(session)


async def _load_or_create_student(engine) -> tuple:
    """Load existing student or prompt to register. Returns (student_pydantic, student_id_str)."""
    from phd_platform.persistence.database import get_session
    from phd_platform.persistence.repository import StudentRepository

    async with get_session(engine) as session:
        repo = StudentRepository(session)
        students = await repo.list_students()

        if students:
            console.print("\n[bold]Existing students:[/bold]")
            for i, s in enumerate(students):
                console.print(f"  [{i + 1}] {s['name']} ({s['email'] or 'no email'})")
            console.print(f"  [0] Register new student")

            choice = Prompt.ask("Select student", default="1")
            if choice == "0":
                return await _register_student_interactive(repo)
            idx = int(choice) - 1
            if 0 <= idx < len(students):
                student = await repo.get_student(students[idx]["id"])
                return student, students[idx]["id"]

        console.print("[yellow]No students found. Let's register you.[/yellow]")
        return await _register_student_interactive(repo)


async def _register_student_interactive(repo) -> tuple:
    """Interactive student registration."""
    name = Prompt.ask("[bold]Your name[/bold]")
    email = Prompt.ask("Email (optional)", default="")
    interests_raw = Prompt.ask("Interests (comma-separated)", default="")
    interests = [i.strip() for i in interests_raw.split(",") if i.strip()]

    console.print("\n[bold]Available disciplines:[/bold]")
    for i, d in enumerate(Discipline):
        console.print(f"  [{i + 1}] {d.value.replace('_', ' ').title()}")

    disc_raw = Prompt.ask("Enroll in (numbers, comma-separated)", default="1")
    disc_indices = [int(x.strip()) - 1 for x in disc_raw.split(",") if x.strip().isdigit()]

    student = await repo.create_student(name=name, email=email, interests=interests)
    student_id = str(student.id)

    for idx in disc_indices:
        if 0 <= idx < len(list(Discipline)):
            disc = list(Discipline)[idx]
            await repo.enroll(student_id, disc)
            student.enrolled_disciplines.append(disc)
            console.print(f"  [green]Enrolled in {disc.value.replace('_', ' ').title()}[/green]")

    console.print(f"\n[bold green]Registered![/bold green] Student ID: {student_id}")
    return student, student_id


def cmd_register(args: argparse.Namespace) -> None:
    """Register a new student."""
    engine = _get_db_engine()

    async def _run():
        from phd_platform.persistence.database import get_session
        from phd_platform.persistence.repository import StudentRepository
        async with get_session(engine) as session:
            repo = StudentRepository(session)
            await _register_student_interactive(repo)

    _run_async(_run())


def cmd_progress(args: argparse.Namespace) -> None:
    """Show student progress dashboard."""
    engine = _get_db_engine()
    loader = _get_loader()

    async def _run():
        student, student_id = await _load_or_create_student(engine)
        if not student:
            return

        disc_filter = _parse_discipline(args.discipline) if args.discipline else None
        disciplines = [disc_filter] if disc_filter else student.enrolled_disciplines

        if not disciplines:
            console.print("[yellow]Not enrolled in any disciplines. Use 'register' first.[/yellow]")
            return

        for disc in disciplines:
            progress = student.get_progress(disc)
            disc_name = disc.value.replace("_", " ").title()

            console.print(Panel(
                f"[bold]{disc_name}[/bold]\n"
                f"Current Level: [cyan]{progress.current_level.value.title()}[/cyan]\n"
                f"Modules Scored: {len(progress.module_scores)}\n"
                f"Capstones: {len(progress.capstones)} | Defenses: {len(progress.defenses)}",
                title=f"Progress -- {disc_name}",
                border_style="cyan",
            ))

            # Module scores table
            level_modules = loader.get_modules_for_level(disc, progress.current_level)
            if level_modules:
                table = Table(
                    title=f"{progress.current_level.value.title()} Modules",
                    show_lines=False,
                )
                table.add_column("ID", style="dim", width=14)
                table.add_column("Module", width=40)
                table.add_column("Score", justify="center", width=10)
                table.add_column("Status", width=12)

                for mod in level_modules:
                    score_data = progress.module_scores.get(mod.id)
                    if score_data:
                        score_str = f"[{_score_color(score_data.score)}]{score_data.score:.0%}[/]"
                        threshold = progress.current_level.mastery_threshold
                        status = "[green]PASS[/green]" if score_data.score >= threshold else "[red]BELOW[/red]"
                    else:
                        score_str = "[dim]--[/dim]"
                        status = "[dim]NOT TAKEN[/dim]"
                    table.add_row(mod.id, mod.name, score_str, status)

                console.print(table)

            # Gate status
            from phd_platform.assessment.progression import ProgressionGate
            gate = ProgressionGate(loader)
            gate_status = gate.evaluate_gate(student, disc, progress.current_level)
            blocking = gate.get_blocking_modules(student, disc, progress.current_level)

            gate_color = {
                "passed": "green",
                "ready_for_assessment": "yellow",
                "in_progress": "cyan",
                "locked": "dim",
                "failed_retakeable": "red",
            }.get(gate_status.value, "white")

            console.print(f"\nGate Status: [{gate_color}]{gate_status.value.replace('_', ' ').upper()}[/]")
            if blocking:
                console.print(f"Blocking modules: [red]{', '.join(blocking[:5])}[/red]"
                              + (f" (+{len(blocking) - 5} more)" if len(blocking) > 5 else ""))
            console.print()

    _run_async(_run())


def cmd_learn(args: argparse.Namespace) -> None:
    """Interactive Socratic tutoring session for a module."""
    engine = _get_db_engine()
    loader = _get_loader()
    client = _get_async_client()

    if client.is_offline:
        console.print("[red]Tutoring requires an LLM.[/red]")
        console.print("Either: (1) install Ollama and run 'ollama pull llama3.1:8b'")
        console.print("    or: (2) set PHD_LLM_PROVIDER=anthropic with your API key")
        return

    async def _run():
        student, student_id = await _load_or_create_student(engine)
        if not student:
            return

        module_id = args.module_id
        try:
            module = loader.get_module(module_id)
        except KeyError:
            console.print(f"[red]Module not found: {module_id}[/red]")
            return

        disc_name = module.discipline.value.replace("_", " ").title() if module.discipline else "Unknown"
        level = module.level or Level.FOUNDATION

        console.print(Panel(
            f"[bold]{module.name}[/bold] ({module.id})\n"
            f"Discipline: {disc_name} | Level: {level.value.title()} | Duration: {module.weeks} weeks\n\n"
            f"[dim]Objectives:[/dim]\n" + "\n".join(f"  - {obj}" for obj in module.objectives),
            title="Tutoring Session",
            border_style="cyan",
        ))
        console.print("[dim]Commands: /hint, /problem, /objectives, /quit[/dim]\n")

        # Load prior conversation if any
        from phd_platform.persistence.database import get_session
        from phd_platform.persistence.repository import StudentRepository
        from phd_platform.tutor.engine import TutoringEngine

        tutor = TutoringEngine(client)

        async with get_session(engine) as session:
            repo = StudentRepository(session)
            prior = await repo.load_tutoring_session(student_id, module_id)
            if prior:
                tutor.conversation_history = prior
                console.print(f"[dim]Resuming session ({len(prior)} messages)[/dim]\n")

        # Get weakness areas
        progress = student.get_progress(module.discipline) if module.discipline else None
        weakness_areas = None
        if progress:
            score_data = progress.module_scores.get(module_id)
            if score_data:
                weakness_areas = score_data.weakness_areas

        # Tutoring loop
        while True:
            try:
                user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
            except (KeyboardInterrupt, EOFError):
                break

            if not user_input.strip():
                continue

            if user_input.strip() == "/quit":
                break
            elif user_input.strip() == "/hint":
                user_input = "Can you give me a hint about the current topic?"
            elif user_input.strip() == "/problem":
                console.print("[dim]Generating practice problem...[/dim]")
                problem = await tutor.generate_practice_problem(module, level)
                console.print(Panel(Markdown(problem), title="Practice Problem", border_style="yellow"))
                continue
            elif user_input.strip() == "/objectives":
                for obj in module.objectives:
                    console.print(f"  - {obj}")
                continue

            console.print("[dim]Thinking...[/dim]")
            response = await tutor.teach(module, level, user_input, weakness_areas)
            weakness_areas = None  # Only pass on first message

            console.print(Panel(Markdown(response), title="Tutor", border_style="green"))

        # Save conversation
        if tutor.conversation_history:
            async with get_session(engine) as session:
                repo = StudentRepository(session)
                await repo.save_tutoring_session(
                    student_id, module_id, tutor.conversation_history
                )
            console.print(f"[dim]Session saved ({len(tutor.conversation_history)} messages)[/dim]")

    _run_async(_run())


def cmd_assess(args: argparse.Namespace) -> None:
    """Run a module assessment — offline-first using question bank + local grader."""
    engine = _get_db_engine()
    loader = _get_loader()

    async def _run():
        student, student_id = await _load_or_create_student(engine)
        if not student:
            return

        module_id = args.module_id
        try:
            module = loader.get_module(module_id)
        except KeyError:
            console.print(f"[red]Module not found: {module_id}[/red]")
            return

        disc = module.discipline or Discipline.ECONOMICS
        console.print(Panel(
            f"[bold]Assessment: {module.name}[/bold] ({module.id})\n"
            f"You will be asked diagnostic questions. Answer each one carefully.",
            title="Module Assessment",
            border_style="yellow",
        ))

        # Pull questions from local bank first
        from phd_platform.persistence.database import get_session
        from phd_platform.persistence.repository import StudentRepository
        from phd_platform.assessment.local_grader import LocalGrader
        from phd_platform.core.models import DiagnosticQuestion, ModuleScore

        grader = LocalGrader()
        questions: list[DiagnosticQuestion] = []

        async with get_session(engine) as session:
            repo = StudentRepository(session)
            bank = await repo.get_questions(module_id, limit=3)

        if bank:
            console.print(f"[dim]Loaded {len(bank)} questions from local bank[/dim]")
            questions = [
                DiagnosticQuestion(
                    question=q["question"], type=q["type"],
                    difficulty=q["difficulty"], correct_answer=q["correct_answer"],
                    rubric=q["rubric"],
                )
                for q in bank
            ]
        else:
            # Fallback to LLM generation if no bank
            client = _get_async_client()
            if client.is_offline:
                console.print("[red]No questions in bank and no LLM configured.[/red]")
                console.print("Run: python scripts/seed_local.py")
                return
            from phd_platform.assessment.placement import PlacementEngine
            placement = PlacementEngine(client, loader)
            console.print("[dim]Generating questions via LLM...[/dim]")
            questions = await placement.generate_diagnostic(disc, module, num_questions=3)

        total_score = 0.0
        all_weaknesses: list[str] = []

        for i, q in enumerate(questions):
            console.print(Panel(
                f"[bold]Q{i + 1}/{len(questions)}[/bold] [{q.type}] (difficulty {q.difficulty}/5)\n\n{q.question}",
                border_style="cyan",
            ))
            answer = Prompt.ask("[bold]Your answer[/bold]")

            # Try local grading first
            local_result = grader.grade(q.type, answer, q.correct_answer, q.rubric)
            if local_result:
                total_score += local_result.score
                all_weaknesses.extend(local_result.weakness_areas)
                color = _score_color(local_result.score)
                console.print(f"  Score: [{color}]{local_result.score:.0%}[/]")
                if local_result.feedback:
                    console.print(f"  [dim]{local_result.feedback}[/dim]")
            else:
                # Open-ended — try LLM, or give 50% default
                client = _get_async_client()
                if not client.is_offline:
                    from phd_platform.assessment.placement import PlacementEngine
                    placement = PlacementEngine(client, loader)
                    console.print("[dim]Evaluating via LLM...[/dim]")
                    score = await placement.evaluate_response(q, answer, module)
                    total_score += score.score
                    all_weaknesses.extend(score.weakness_areas)
                    console.print(f"  Score: [{_score_color(score.score)}]{score.score:.0%}[/]")
                else:
                    console.print("  [yellow]Open-ended question — scored as pending review[/yellow]")
                    total_score += 0.5  # Placeholder for offline

        avg_score = total_score / len(questions) if questions else 0.0
        final_score = ModuleScore(
            module_id=module_id,
            score=avg_score,
            weakness_areas=list(set(all_weaknesses)),
        )

        # Save score
        async with get_session(engine) as session:
            repo = StudentRepository(session)
            await repo.save_module_score(student_id, disc, final_score)

        color = _score_color(avg_score)
        threshold = module.level.mastery_threshold if module.level else 0.90
        passed = avg_score >= threshold

        console.print(Panel(
            f"[bold]Final Score: [{color}]{avg_score:.0%}[/][/bold]\n"
            f"Threshold: {threshold:.0%}\n"
            f"Result: {'[green]PASSED[/green]' if passed else '[red]BELOW THRESHOLD[/red]'}"
            + (f"\nWeakness areas: {', '.join(set(all_weaknesses))}" if all_weaknesses else ""),
            title="Assessment Result",
            border_style="green" if passed else "red",
        ))

    _run_async(_run())


def cmd_placement(args: argparse.Namespace) -> None:
    """Run placement diagnostic — offline-first using question bank + local grader."""
    engine = _get_db_engine()
    loader = _get_loader()
    disc = _parse_discipline(args.discipline)

    async def _run():
        student, student_id = await _load_or_create_student(engine)
        if not student:
            return

        disc_name = disc.value.replace("_", " ").title()
        console.print(Panel(
            f"[bold]Placement Diagnostic: {disc_name}[/bold]\n\n"
            "You'll be tested on foundation modules to determine your starting level.\n"
            "Score 90%+ on all modules to skip to Undergraduate.",
            title="Placement Test",
            border_style="yellow",
        ))

        from phd_platform.persistence.database import get_session
        from phd_platform.persistence.repository import StudentRepository
        from phd_platform.assessment.local_grader import LocalGrader
        from phd_platform.assessment.placement import PlacementEngine
        from phd_platform.core.models import DiagnosticQuestion

        grader = LocalGrader()
        foundation_modules = loader.get_modules_for_level(disc, Level.FOUNDATION)
        all_scores: dict[str, float] = {}

        for mod in foundation_modules:
            console.print(f"\n[bold cyan]--- {mod.name} ({mod.id}) ---[/bold cyan]")

            # Pull from local bank
            async with get_session(engine) as session:
                repo = StudentRepository(session)
                bank = await repo.get_questions(mod.id, limit=2)

            if bank:
                questions = [
                    DiagnosticQuestion(
                        question=q["question"], type=q["type"],
                        difficulty=q["difficulty"], correct_answer=q["correct_answer"],
                        rubric=q["rubric"],
                    )
                    for q in bank
                ]
            else:
                # No bank — try LLM
                client = _get_async_client()
                if client.is_offline:
                    console.print(f"  [yellow]No questions for {mod.id} — skipping[/yellow]")
                    all_scores[mod.id] = 0.0
                    continue
                placement = PlacementEngine(client, loader)
                questions = await placement.generate_diagnostic(disc, mod, num_questions=2)

            mod_total = 0.0
            for i, q in enumerate(questions):
                console.print(f"\n[bold]Q{i + 1}[/bold]: {q.question}")
                answer = Prompt.ask("[bold]Answer[/bold]")

                # Local grading first
                local_result = grader.grade(q.type, answer, q.correct_answer, q.rubric)
                if local_result:
                    mod_total += local_result.score
                    console.print(f"  [{_score_color(local_result.score)}]{local_result.score:.0%}[/]")
                    if local_result.feedback:
                        console.print(f"  [dim]{local_result.feedback}[/dim]")
                else:
                    # Open-ended — try LLM or default
                    client = _get_async_client()
                    if not client.is_offline:
                        placement = PlacementEngine(client, loader)
                        score = await placement.evaluate_response(q, answer, mod)
                        mod_total += score.score
                        console.print(f"  [{_score_color(score.score)}]{score.score:.0%}[/]")
                    else:
                        console.print("  [yellow]Pending review (no LLM)[/yellow]")
                        mod_total += 0.5

            avg = mod_total / len(questions) if questions else 0.0
            all_scores[mod.id] = avg
            console.print(f"  Module average: [{_score_color(avg)}]{avg:.0%}[/]")

        # Determine level
        starting_level = placement.determine_starting_level(student, disc, all_scores)
        gaps = placement.identify_gaps(all_scores)

        # Save results
        from phd_platform.persistence.database import get_session
        from phd_platform.persistence.repository import StudentRepository
        async with get_session(engine) as session:
            repo = StudentRepository(session)
            await repo.save_placement_result(
                student_id, disc, starting_level, gaps, all_scores
            )
            await repo.update_level(student_id, disc, starting_level)
            # Save individual module scores
            from phd_platform.core.models import ModuleScore
            for mod_id, score_val in all_scores.items():
                await repo.save_module_score(
                    student_id, disc,
                    ModuleScore(module_id=mod_id, score=score_val),
                )

        console.print(Panel(
            f"[bold]Starting Level: [cyan]{starting_level.value.title()}[/cyan][/bold]\n"
            + (f"Gap modules: [red]{', '.join(gaps)}[/red]" if gaps else "[green]No gaps detected![/green]"),
            title="Placement Result",
            border_style="green",
        ))

    _run_async(_run())


def cmd_capstone(args: argparse.Namespace) -> None:
    """Generate capstone project proposals."""
    engine = _get_db_engine()
    loader = _get_loader()
    client = _get_async_client()
    disc = _parse_discipline(args.discipline)

    async def _run():
        student, student_id = await _load_or_create_student(engine)
        if not student:
            return

        progress = student.get_progress(disc)
        level = progress.current_level
        disc_name = disc.value.replace("_", " ").title()

        console.print(Panel(
            f"[bold]Capstone Proposal Generation[/bold]\n"
            f"Discipline: {disc_name} | Level: {level.value.title()}",
            title="Capstone",
            border_style="magenta",
        ))

        from phd_platform.capstone.generator import CapstoneGenerator
        generator = CapstoneGenerator(client, loader)

        console.print("[dim]Generating personalized proposals...[/dim]")
        proposals = await generator.generate_proposals(student, disc, level)

        for i, prop in enumerate(proposals):
            console.print(Panel(
                f"[bold]{prop.title}[/bold]\n\n"
                f"[cyan]Research Question:[/cyan] {prop.research_question}\n\n"
                f"[cyan]Methodology:[/cyan] {prop.methodology}\n\n"
                f"[cyan]Data Sources:[/cyan] {prop.data_sources}\n\n"
                f"[cyan]Contribution:[/cyan] {prop.contribution}\n\n"
                f"[cyan]Risks:[/cyan] {prop.risks}",
                title=f"Proposal {i + 1}",
                border_style="magenta",
            ))

        if proposals:
            choice = Prompt.ask(
                f"Select a proposal to start (1-{len(proposals)}) or 'skip'",
                default="skip",
            )
            if choice.isdigit() and 1 <= int(choice) <= len(proposals):
                selected = proposals[int(choice) - 1]
                from phd_platform.persistence.database import get_session
                from phd_platform.persistence.repository import StudentRepository
                async with get_session(engine) as session:
                    repo = StudentRepository(session)
                    cap_id = await repo.save_capstone(
                        student_id, disc, level,
                        title=selected.title,
                        abstract=selected.research_question,
                    )
                console.print(f"[green]Capstone started![/green] ID: {cap_id}")

    _run_async(_run())


def cmd_defense(args: argparse.Namespace) -> None:
    """Run an interactive defense session."""
    engine = _get_db_engine()
    loader = _get_loader()
    client = _get_async_client()

    async def _run():
        student, student_id = await _load_or_create_student(engine)
        if not student:
            return

        # Get capstone
        from phd_platform.persistence.database import get_session
        from phd_platform.persistence.repository import StudentRepository
        async with get_session(engine) as session:
            repo = StudentRepository(session)
            capstone = await repo.get_capstone(args.capstone_id)

        if not capstone:
            console.print(f"[red]Capstone not found: {args.capstone_id}[/red]")
            return

        level = Level(capstone["level"])
        disc = Discipline(capstone["discipline"])

        console.print(Panel(
            f"[bold]Defense Session[/bold]\n"
            f"Capstone: {capstone['title']}\n"
            f"Level: {level.value.title()} | Panel size: {level.defense_panel_size}",
            title="Defense",
            border_style="red",
        ))

        # Get paper text
        paper_text = capstone.get("paper_text", "")
        if not paper_text:
            console.print("[yellow]No paper text found. Please provide your paper.[/yellow]")
            paper_text = Prompt.ask("[bold]Paste your paper (or a summary)[/bold]")

        # Build panel
        from phd_platform.defense.agents import ReviewerPanel
        from phd_platform.defense.session import DefenseSession
        from uuid import UUID

        panel = ReviewerPanel(client)
        disc_curriculum = loader.get_discipline(disc)
        level_data = disc_curriculum.levels.get(level.value)
        journals = level_data.gate.journals if level_data else []
        agents = panel.assemble(journals, level)

        if not agents:
            console.print("[red]No reviewer agents could be assembled.[/red]")
            return

        console.print(f"\n[bold]Review panel ({len(agents)} reviewers):[/bold]")
        for agent in agents:
            console.print(f"  - {agent.persona_name} ({agent.journal})")

        session = DefenseSession(agents, level, UUID(capstone["id"]))

        # Phase 1: Reviews
        console.print("\n[dim]Reviewers reading your paper...[/dim]")
        reviews = await session.run_reviews(paper_text)
        for journal, review in reviews.items():
            console.print(Panel(
                Markdown(review["report"]),
                title=f"Review: {journal}",
                border_style="yellow",
            ))

        # Phase 2: Q&A
        console.print("\n[bold]Q&A Session[/bold]")
        console.print("[dim]Reviewers will ask questions. Answer each one.[/dim]\n")

        async def student_respond(question: str) -> str:
            console.print(Panel(question, title="Reviewer Question", border_style="yellow"))
            return Prompt.ask("[bold cyan]Your response[/bold cyan]")

        await session.run_qa(paper_text, student_respond)

        # Phase 3: Verdicts
        console.print("\n[dim]Reviewers deliberating...[/dim]")
        result = await session.run_verdicts(paper_text)

        # Display results
        verdict_table = Table(title="Defense Verdicts")
        verdict_table.add_column("Reviewer", style="cyan")
        verdict_table.add_column("Verdict", justify="center")

        for journal, verdict in result.reviewer_verdicts.items():
            v_color = {
                "Accept": "bold green",
                "Minor Revision": "green",
                "Major Revision": "yellow",
                "Reject": "bold red",
            }.get(verdict.value, "white")
            verdict_table.add_row(journal, f"[{v_color}]{verdict.value}[/]")

        console.print(verdict_table)

        pass_str = "[bold green]PASSED[/bold green]" if result.overall_pass else "[bold red]DID NOT PASS[/bold red]"
        console.print(f"\nOverall: {pass_str} ({result.passing_count}/{len(result.reviewer_verdicts)} passing)")

        # Save result
        async with get_session(engine) as db_session:
            repo = StudentRepository(db_session)
            await repo.save_defense_result(
                capstone_id=capstone["id"],
                level=level,
                reviewer_verdicts={j: v.value for j, v in result.reviewer_verdicts.items()},
                feedback=result.feedback,
                overall_pass=result.overall_pass,
                transcript=session.get_transcript(),
            )

        if result.overall_pass:
            console.print(Panel(
                "[bold green]Congratulations! You have passed the defense.[/bold green]\n"
                f"You may now advance to the next level.",
                border_style="green",
            ))

    _run_async(_run())


def cmd_status(args: argparse.Namespace) -> None:
    """Overall status across all disciplines."""
    engine = _get_db_engine()
    loader = _get_loader()

    async def _run():
        student, student_id = await _load_or_create_student(engine)
        if not student:
            return

        if not student.enrolled_disciplines:
            console.print("[yellow]Not enrolled in any disciplines.[/yellow]")
            return

        table = Table(title=f"Status: {student.name}", show_lines=True)
        table.add_column("Discipline", style="cyan", width=24)
        table.add_column("Level", width=16)
        table.add_column("Modules Scored", justify="center", width=16)
        table.add_column("Avg Mastery", justify="center", width=14)
        table.add_column("Gate", width=20)

        from phd_platform.assessment.progression import ProgressionGate
        gate = ProgressionGate(loader)

        for disc in student.enrolled_disciplines:
            progress = student.get_progress(disc)
            scored = len(progress.module_scores)
            total = len(loader.get_modules_for_level(disc, progress.current_level))
            mastery = progress.current_mastery
            gate_status = gate.evaluate_gate(student, disc, progress.current_level)

            gate_color = {
                "passed": "green", "ready_for_assessment": "yellow",
                "in_progress": "cyan", "locked": "dim", "failed_retakeable": "red",
            }.get(gate_status.value, "white")

            table.add_row(
                disc.value.replace("_", " ").title(),
                progress.current_level.value.title(),
                f"{scored}/{total}",
                f"[{_score_color(mastery)}]{mastery:.0%}[/]" if mastery > 0 else "[dim]--[/dim]",
                f"[{gate_color}]{gate_status.value.replace('_', ' ').upper()}[/]",
            )

        console.print(table)

    _run_async(_run())


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="phd-platform",
        description="PhD-level adaptive education platform",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Read-only commands
    subparsers.add_parser("info", help="Show curriculum overview")

    mod_parser = subparsers.add_parser("modules", help="List modules for a discipline/level")
    mod_parser.add_argument("discipline", help=f"Discipline ({', '.join(DISC_CHOICES)})")
    mod_parser.add_argument("level", help=f"Level ({', '.join(LEVEL_CHOICES)})")
    mod_parser.add_argument("-v", "--verbose", action="store_true")

    pre_parser = subparsers.add_parser("prereqs", help="Show prerequisite chain")
    pre_parser.add_argument("module_id", help="Module ID (e.g., ECON-M-001)")

    # Interactive commands
    subparsers.add_parser("register", help="Register a new student")

    prog_parser = subparsers.add_parser("progress", help="Show progress dashboard")
    prog_parser.add_argument("discipline", nargs="?", default=None, help="Filter by discipline")

    learn_parser = subparsers.add_parser("learn", help="Start a Socratic tutoring session")
    learn_parser.add_argument("module_id", help="Module ID to study (e.g., ECON-F-002)")

    assess_parser = subparsers.add_parser("assess", help="Take a module assessment")
    assess_parser.add_argument("module_id", help="Module ID to assess")

    place_parser = subparsers.add_parser("placement", help="Run placement diagnostic")
    place_parser.add_argument("discipline", help=f"Discipline ({', '.join(DISC_CHOICES)})")

    cap_parser = subparsers.add_parser("capstone", help="Generate capstone proposals")
    cap_parser.add_argument("discipline", help=f"Discipline ({', '.join(DISC_CHOICES)})")

    def_parser = subparsers.add_parser("defense", help="Run a defense session")
    def_parser.add_argument("capstone_id", help="Capstone ID to defend")

    subparsers.add_parser("status", help="Overall status across all disciplines")

    args = parser.parse_args()
    commands = {
        "info": cmd_info,
        "modules": cmd_modules,
        "prereqs": cmd_prereqs,
        "register": cmd_register,
        "progress": cmd_progress,
        "learn": cmd_learn,
        "assess": cmd_assess,
        "placement": cmd_placement,
        "capstone": cmd_capstone,
        "defense": cmd_defense,
        "status": cmd_status,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
