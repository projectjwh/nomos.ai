"""Capstone routes — generate proposals, submit paper."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.core.enums import Discipline
from phd_platform.persistence.repository import StudentRepository
from phd_platform.web.app import render
from phd_platform.web.deps import get_current_user_optional, get_curriculum, get_db, get_llm

router = APIRouter()


@router.get("/{discipline}", response_class=HTMLResponse)
async def capstone_page(
    request: Request,
    discipline: str,
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login")

    try:
        disc = Discipline(discipline)
    except ValueError:
        return RedirectResponse("/dashboard")

    repo = StudentRepository(db)
    student = await repo.get_student(user.student_id) if user.student_id else None
    if not student:
        return RedirectResponse("/register")

    progress = student.get_progress(disc)
    client = get_llm()

    proposals = None
    if not client.is_offline:
        from phd_platform.capstone.generator import CapstoneGenerator
        loader = get_curriculum()
        gen = CapstoneGenerator(client, loader)
        try:
            proposals = await gen.generate_proposals(student, disc, progress.current_level)
        except Exception:
            proposals = None

    return render(request, "capstone.html", {
        "user": user,
        "discipline": disc.value.replace("_", " ").title(),
        "discipline_id": disc.value,
        "level": progress.current_level.value.title(),
        "proposals": proposals,
        "offline": client.is_offline,
    })


@router.post("/{discipline}/submit", response_class=HTMLResponse)
async def capstone_submit(
    request: Request,
    discipline: str,
    title: str = Form(""),
    abstract: str = Form(""),
    paper_text: str = Form(""),
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login")

    disc = Discipline(discipline)
    repo = StudentRepository(db)
    student = await repo.get_student(user.student_id)
    progress = student.get_progress(disc)

    capstone_id = await repo.save_capstone(
        student_id=user.student_id,
        discipline=disc,
        level=progress.current_level,
        title=title,
        abstract=abstract,
        paper_text=paper_text,
    )

    return render(request, "partials/capstone_saved.html", {
        "capstone_id": capstone_id,
        "title": title,
        "discipline": discipline,
    })
