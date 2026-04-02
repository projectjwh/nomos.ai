"""Assessment routes — module-level testing with offline-first grading."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.assessment.local_grader import LocalGrader
from phd_platform.core.models import ModuleScore
from phd_platform.persistence.repository import StudentRepository
from phd_platform.web.app import render
from phd_platform.web.deps import get_current_user_optional, get_curriculum, get_db

router = APIRouter()
grader = LocalGrader()


@router.get("/{module_id}", response_class=HTMLResponse)
async def assess_start(
    request: Request,
    module_id: str,
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Start a module assessment — load questions from bank."""
    if not user:
        return RedirectResponse("/login")

    loader = get_curriculum()
    try:
        module = loader.get_module(module_id)
    except KeyError:
        return RedirectResponse("/dashboard")

    repo = StudentRepository(db)
    bank = await repo.get_questions(module_id, limit=3)

    if not bank:
        return render(request, "assessment.html", { "user": user, "module": module,
            "error": "No questions available for this module. Run seed_local.py first.",
        })

    questions = [
        {"question": q["question"], "type": q["type"], "difficulty": q["difficulty"],
         "correct_answer": q["correct_answer"], "rubric": q["rubric"]}
        for q in bank
    ]

    state = {"module_id": module_id, "questions": questions, "current": 0, "scores": []}

    return render(request, "assessment.html", { "user": user, "module": module,
        "question": questions[0],
        "question_idx": 0,
        "total": len(questions),
        "state_json": json.dumps(state),
    })


@router.post("/{module_id}/answer", response_class=HTMLResponse)
async def assess_answer(
    request: Request,
    module_id: str,
    answer: str = Form(""),
    state_json: str = Form("{}"),
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Grade an answer and return next question or final result."""
    if not user:
        return RedirectResponse("/login")

    state = json.loads(state_json)
    questions = state.get("questions", [])
    current = state.get("current", 0)
    score_list = state.get("scores", [])

    # Grade
    if current < len(questions):
        q = questions[current]
        result = grader.grade(q["type"], answer, q["correct_answer"], q.get("rubric", ""))
        score = result.score if result else 0.5
        feedback = result.feedback if result else "Pending review"
        score_list.append(score)

    current += 1
    state["current"] = current
    state["scores"] = score_list

    if current >= len(questions):
        # Assessment complete
        avg = sum(score_list) / len(score_list) if score_list else 0.0
        repo = StudentRepository(db)
        loader = get_curriculum()
        module = loader.get_module(module_id)
        disc = module.discipline

        if disc:
            await repo.save_module_score(
                user.student_id, disc,
                ModuleScore(module_id=module_id, score=avg),
            )

        threshold = module.level.mastery_threshold if module.level else 0.90
        return render(request, "partials/assess_result.html", {            "score": avg,
            "passed": avg >= threshold,
            "threshold": threshold,
            "module_name": module.name,
        })

    # Next question
    return render(request, "partials/question.html", {        "question": questions[current],
        "question_idx": current,
        "total_questions": len(questions),
        "last_score": score,
        "last_feedback": feedback,
        "state_json": json.dumps(state),
        "module_id": module_id,
        "discipline": "",
        "module_name": "",
        "module_idx": 0,
        "total_modules": 1,
    })
