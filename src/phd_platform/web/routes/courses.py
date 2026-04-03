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
    "economics": {
        "icon": "account_balance",
        "desc": "A rigorous path through economic theory and empirical methods, modeled on PhD programs at Harvard, MIT, Stanford, Princeton, and Berkeley. From supply and demand through advanced econometrics, mechanism design, and original dissertation research.",
        "highlights": ["Causal inference & IV estimation", "Game theory & mechanism design", "DSGE modeling", "Journal defense (AER, QJE, Econometrica)"],
        "programs": "Harvard, MIT, Stanford, Princeton, Berkeley",
    },
    "data_science": {
        "icon": "query_stats",
        "desc": "Bridge statistical theory and practical engineering. Covers mathematical statistics, machine learning, causal inference, Bayesian methods, and data systems — sourced from Berkeley Statistics, Stanford, CMU, and MIT.",
        "highlights": ["Statistical learning theory", "Bayesian MCMC methods", "Causal DAGs & experimental design", "Data engineering at scale"],
        "programs": "Berkeley, Stanford, CMU, MIT",
    },
    "computer_science": {
        "icon": "computer",
        "desc": "From algorithms and complexity through distributed systems, compilers, and formal verification. Designed around curricula from Stanford CS, MIT EECS, CMU SCS, and Berkeley EECS.",
        "highlights": ["NP-completeness & approximation", "Distributed consensus (Paxos, Raft)", "Type systems & verification", "Systems research methodology"],
        "programs": "Stanford, MIT, CMU, Berkeley",
    },
    "ai_ml": {
        "icon": "psychology",
        "desc": "Deep learning theory and practice from foundations through frontier research. Covers transformers, reinforcement learning, generative models, and AI safety — based on Stanford AI Lab, MIT, CMU ML, and Berkeley AI programs.",
        "highlights": ["Transformer architectures from scratch", "RLHF & alignment", "Diffusion models & VAEs", "Mechanistic interpretability"],
        "programs": "Stanford, MIT, CMU, Berkeley",
    },
    "financial_engineering": {
        "icon": "trending_up",
        "desc": "Mathematical finance from stochastic calculus through derivatives pricing, risk management, and algorithmic trading. Sourced from Princeton ORF, Stanford MS&E, MIT Sloan, Berkeley MFE, and Columbia IEOR.",
        "highlights": ["Ito calculus & Black-Scholes", "Monte Carlo & numerical methods", "Market microstructure", "ML in quantitative finance"],
        "programs": "Princeton, Stanford, MIT, Berkeley, Columbia",
    },
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
            "highlights": meta.get("highlights", []),
            "programs": meta.get("programs", ""),
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
