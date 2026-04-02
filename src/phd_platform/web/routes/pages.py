"""Page routes — HTML views for landing, auth, dashboard, curriculum."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.core.enums import Discipline, Level
from phd_platform.web.app import render
from phd_platform.web.auth import authenticate_user, register_user
from phd_platform.web.deps import (
    get_curriculum,
    get_current_user,
    get_current_user_optional,
    get_db,
    get_repo,
    get_serializer,
)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request, user=Depends(get_current_user_optional)):
    """Landing page with discipline cards."""
    loader = get_curriculum()
    disciplines = []
    for disc in Discipline:
        total = sum(
            len(loader.get_modules_for_level(disc, level)) for level in Level
        )
        disciplines.append({
            "id": disc.value,
            "name": disc.value.replace("_", " ").title(),
            "modules": total,
        })
    return render(request, "landing.html", { "user": user, "disciplines": disciplines,
    })


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return render(request, "register.html", { "disciplines": [d.value for d in Discipline],
    })


@router.post("/register")
async def register_submit(
    request: Request,
    name: str = Form(),
    email: str = Form(),
    password: str = Form(),
    interests: str = Form(""),
    disciplines: list[str] = Form([]),
    db: AsyncSession = Depends(get_db),
):
    """Handle registration form submission."""
    try:
        user = await register_user(db, email, password, name, interests, disciplines)
    except Exception:
        return render(request, "register.html", {            "error": "Registration failed. Email may already be in use.",
            "disciplines": [d.value for d in Discipline],
        })

    # Set session cookie and redirect to dashboard
    serializer = get_serializer()
    token = serializer.dumps(user.id)
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("session", token, httponly=True, max_age=86400)
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return render(request, "login.html")


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(),
    password: str = Form(),
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, email, password)
    if not user:
        return render(request, "login.html", { "error": "Invalid email or password.",
        })
    serializer = get_serializer()
    token = serializer.dumps(user.id)
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie("session", token, httponly=True, max_age=86400)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("session")
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login")

    from phd_platform.persistence.repository import StudentRepository
    from phd_platform.assessment.progression import ProgressionGate

    repo = StudentRepository(db)
    student = await repo.get_student(user.student_id) if user.student_id else None

    if not student:
        return RedirectResponse("/register")

    loader = get_curriculum()
    gate = ProgressionGate(loader)

    disc_progress = []
    for disc in student.enrolled_disciplines:
        progress = student.get_progress(disc)
        level_modules = loader.get_modules_for_level(disc, progress.current_level)
        scored = len(progress.module_scores)
        total = len(level_modules)
        gate_status = gate.evaluate_gate(student, disc, progress.current_level)
        blocking = gate.get_blocking_modules(student, disc, progress.current_level)

        modules_detail = []
        for mod in level_modules:
            score_data = progress.module_scores.get(mod.id)
            modules_detail.append({
                "id": mod.id,
                "name": mod.name,
                "score": score_data.score if score_data else None,
                "passed": score_data.score >= progress.current_level.mastery_threshold if score_data else False,
            })

        disc_progress.append({
            "id": disc.value,
            "name": disc.value.replace("_", " ").title(),
            "level": progress.current_level.value.title(),
            "scored": scored,
            "total": total,
            "gate_status": gate_status.value.replace("_", " ").upper(),
            "blocking_count": len(blocking),
            "modules": modules_detail,
        })

    return render(request, "dashboard.html", {        "user": user,
        "student": student,
        "disciplines": disc_progress,
    })
