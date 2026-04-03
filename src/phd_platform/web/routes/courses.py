"""Courses catalog — browse all disciplines and their modules."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.core.enums import Discipline, Level
from phd_platform.persistence.repository import StudentRepository
from phd_platform.web.app import render
from phd_platform.web.deps import get_current_user_optional, get_curriculum, get_db

router = APIRouter()

DISC_META = {
    "economics": {"icon": "account_balance", "desc": "Micro/macro theory, econometrics, causal inference, game theory, and policy evaluation from Harvard, MIT, Stanford, Princeton, and Berkeley PhD programs."},
    "data_science": {"icon": "query_stats", "desc": "Statistical learning, Bayesian methods, causal inference, data engineering, and experimental design from Berkeley, Stanford, CMU, and MIT."},
    "computer_science": {"icon": "computer", "desc": "Algorithms, systems, theory of computation, distributed systems, and formal methods from Stanford, MIT, CMU, and Berkeley."},
    "ai_ml": {"icon": "psychology", "desc": "Deep learning, transformers, reinforcement learning, generative models, AI safety, and optimization from Stanford, MIT, CMU, and Berkeley."},
    "financial_engineering": {"icon": "trending_up", "desc": "Stochastic calculus, derivatives pricing, risk management, market microstructure, and quantitative trading from Princeton, Stanford, MIT, Berkeley, and Columbia."},
}


@router.get("/", response_class=HTMLResponse)
async def courses_index(request: Request, user=Depends(get_current_user_optional)):
    """Courses catalog — bento grid of all 5 disciplines."""
    loader = get_curriculum()
    disciplines = []
    for disc in Discipline:
        meta = DISC_META.get(disc.value, {})
        total = sum(len(loader.get_modules_for_level(disc, level)) for level in Level)
        disciplines.append({
            "id": disc.value,
            "name": disc.value.replace("_", " ").title(),
            "icon": meta.get("icon", "school"),
            "desc": meta.get("desc", ""),
            "modules": total,
        })
    return render(request, "courses.html", {
        "user": user, "disciplines": disciplines,
    })


@router.get("/{discipline}", response_class=HTMLResponse)
async def course_detail(
    request: Request,
    discipline: str,
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Single discipline detail — modules grouped by level with student progress."""
    try:
        disc = Discipline(discipline)
    except ValueError:
        return RedirectResponse("/courses")

    loader = get_curriculum()
    meta = DISC_META.get(disc.value, {})
    disc_curriculum = loader.get_discipline(disc)

    # Load student progress if authenticated
    student_scores = {}
    current_level = Level.FOUNDATION
    enrolled = False
    if user and user.student_id:
        repo = StudentRepository(db)
        student = await repo.get_student(user.student_id)
        if student:
            progress = student.get_progress(disc)
            current_level = progress.current_level
            student_scores = {mid: s.score for mid, s in progress.module_scores.items()}
            enrolled = disc in student.enrolled_disciplines

    # Build level groups
    levels = []
    total_modules = 0
    completed_modules = 0
    next_module = None

    for level in Level:
        modules = loader.get_modules_for_level(disc, level)
        total_modules += len(modules)
        threshold = level.mastery_threshold
        level_mods = []

        for mod in modules:
            score = student_scores.get(mod.id)
            if score is not None and score >= threshold:
                status = "completed"
                completed_modules += 1
            elif score is not None:
                status = "in_progress"
            elif level.value == current_level.value:
                status = "available"
                if next_module is None:
                    next_module = mod
            else:
                status = "locked"

            level_mods.append({
                "id": mod.id,
                "name": mod.name,
                "weeks": mod.weeks,
                "status": status,
                "score": round(score * 100) if score is not None else None,
                "objectives": mod.objectives,
            })

        levels.append({
            "name": level.value.title(),
            "key": level.value,
            "modules": level_mods,
            "is_current": level.value == current_level.value,
        })

    progress_pct = round(completed_modules / total_modules * 100) if total_modules > 0 else 0

    return render(request, "course_detail.html", {
        "user": user,
        "discipline": disc.value.replace("_", " ").title(),
        "discipline_id": disc.value,
        "icon": meta.get("icon", "school"),
        "desc": meta.get("desc", ""),
        "levels": levels,
        "total_modules": total_modules,
        "completed_modules": completed_modules,
        "progress_pct": progress_pct,
        "current_level": current_level.value.title(),
        "next_module": next_module,
        "enrolled": enrolled,
        "reference_programs": disc_curriculum.reference_programs if disc_curriculum else [],
    })
