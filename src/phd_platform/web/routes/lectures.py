"""Lecture routes — interactive structured content with embedded checkpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.assessment.local_grader import LocalGrader
from phd_platform.persistence.repository import StudentRepository
from phd_platform.web.app import render
from phd_platform.web.deps import get_current_user_optional, get_curriculum, get_db

router = APIRouter()
grader = LocalGrader()


@router.get("/{module_id}", response_class=HTMLResponse)
async def lecture_page(
    request: Request,
    module_id: str,
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Render the interactive lecture for a module."""
    if not user:
        return RedirectResponse("/login")

    loader = get_curriculum()
    try:
        module = loader.get_module(module_id)
    except KeyError:
        return RedirectResponse("/dashboard")

    repo = StudentRepository(db)
    lecture = await repo.get_lecture(module_id)

    if not lecture:
        return render(request, "lecture.html", {
            "user": user, "module": module, "lecture": None,
            "error": "No lecture available for this module yet.",
        })

    # Load student's progress through this lecture
    progress = None
    if user.student_id:
        progress = await repo.get_lecture_progress(user.student_id, module_id)

    blocks_completed = progress["blocks_completed"] if progress else 0
    checkpoint_scores = progress["checkpoint_scores"] if progress else []

    return render(request, "lecture.html", {
        "user": user,
        "module": module,
        "lecture": lecture,
        "blocks": lecture["content_blocks"],
        "blocks_completed": blocks_completed,
        "checkpoint_scores": {s["block_idx"]: s["score"] for s in checkpoint_scores},
        "total_blocks": len(lecture["content_blocks"]),
    })


@router.post("/{module_id}/checkpoint", response_class=HTMLResponse)
async def answer_checkpoint(
    request: Request,
    module_id: str,
    answer: str = Form(""),
    block_idx: int = Form(0),
    expected_answer: str = Form(""),
    concept: str = Form(""),
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Grade a lecture checkpoint answer and advance progress."""
    if not user:
        return HTMLResponse("")

    # Grade locally using keyword matching against expected answer
    result = grader.grade("short_answer", answer, expected_answer, expected_answer)
    score = result.score if result else 0.5
    feedback = result.feedback if result else "Answer recorded."

    # If local grading can't assess (returns None), give credit for engagement
    if result is None:
        score = 0.7  # Engaged but can't auto-grade
        feedback = "Your answer has been recorded. A full evaluation requires the tutor."

    # Save progress
    repo = StudentRepository(db)
    progress = await repo.get_lecture_progress(user.student_id, module_id)
    checkpoint_scores = progress["checkpoint_scores"] if progress else []
    checkpoint_scores.append({"block_idx": block_idx, "score": score})

    lecture = await repo.get_lecture(module_id)
    total_blocks = len(lecture["content_blocks"]) if lecture else 0
    new_completed = max(block_idx + 1, progress["blocks_completed"] if progress else 0)

    await repo.save_lecture_progress(
        student_id=user.student_id,
        module_id=module_id,
        blocks_completed=new_completed,
        blocks_total=total_blocks,
        checkpoint_scores=checkpoint_scores,
        completed=(new_completed >= total_blocks),
    )

    return render(request, "partials/checkpoint_result.html", {
        "score": score,
        "feedback": feedback,
        "block_idx": block_idx,
    })
