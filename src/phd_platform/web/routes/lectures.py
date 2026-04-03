"""Lecture routes — profile page (Coursera-style) + learning view with checkpoints."""

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
async def lecture_profile(
    request: Request,
    module_id: str,
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Coursera-style lecture profile page — summary, syllabus, goals."""
    if not user:
        return RedirectResponse("/login")

    loader = get_curriculum()
    try:
        module = loader.get_module(module_id)
    except KeyError:
        return RedirectResponse("/dashboard")

    repo = StudentRepository(db)
    lecture = await repo.get_lecture(module_id)

    # Load student progress
    progress = None
    if user.student_id:
        progress = await repo.get_lecture_progress(user.student_id, module_id)

    blocks_completed = progress["blocks_completed"] if progress else 0
    total_blocks = len(lecture["content_blocks"]) if lecture else 0

    # Build syllabus (table of contents from block types)
    syllabus = []
    if lecture:
        for i, block in enumerate(lecture["content_blocks"]):
            btype = block.get("type", "exposition")
            # Extract title from content for exposition blocks
            content = block.get("content", "")
            title = ""
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("## "):
                    title = line[3:].strip()
                    break
                elif line.startswith("### "):
                    title = line[4:].strip()
                    break
            if not title:
                type_labels = {"exposition": "Reading", "checkpoint": "Checkpoint", "worked_example": "Worked Example", "try_it": "Practice", "reflection": "Reflection"}
                title = type_labels.get(btype, btype.title())

            syllabus.append({
                "index": i,
                "type": btype,
                "title": title,
                "completed": i < blocks_completed,
            })

    # Prerequisites with completion status
    prereqs = []
    student = await repo.get_student(user.student_id) if user.student_id else None
    if module.prerequisites and student and module.discipline:
        student_progress = student.get_progress(module.discipline)
        for pid in module.prerequisites:
            try:
                pmod = loader.get_module(pid)
                score = student_progress.module_scores.get(pid)
                prereqs.append({
                    "id": pid,
                    "name": pmod.name,
                    "completed": score is not None and score.score >= 0.80,
                    "score": round(score.score * 100) if score else None,
                })
            except KeyError:
                pass

    return render(request, "lecture_profile.html", {
        "user": user,
        "module": module,
        "lecture": lecture,
        "syllabus": syllabus,
        "prereqs": prereqs,
        "blocks_completed": blocks_completed,
        "total_blocks": total_blocks,
        "started": progress is not None,
    })


@router.get("/{module_id}/learn", response_class=HTMLResponse)
async def lecture_learn(
    request: Request,
    module_id: str,
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Learning view — actual lecture content with checkpoints."""
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
        return RedirectResponse(f"/lecture/{module_id}")

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

    result = grader.grade("short_answer", answer, expected_answer, expected_answer)
    score = result.score if result else 0.5
    feedback = result.feedback if result else "Answer recorded."

    if result is None:
        score = 0.7
        feedback = "Your answer has been recorded. A full evaluation requires the tutor."

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
