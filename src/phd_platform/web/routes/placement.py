"""Placement routes — offline-first diagnostic using question bank + local grader."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.assessment.local_grader import LocalGrader
from phd_platform.core.enums import Discipline, Level
from phd_platform.core.models import DiagnosticQuestion, ModuleScore
from phd_platform.persistence.repository import StudentRepository
from phd_platform.web.app import render
from phd_platform.web.deps import get_current_user_optional, get_curriculum, get_db

router = APIRouter()
grader = LocalGrader()


@router.get("/{discipline}", response_class=HTMLResponse)
async def placement_start(
    request: Request,
    discipline: str,
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Start placement test — load first module's questions from bank."""
    if not user:
        return RedirectResponse("/login")

    try:
        disc = Discipline(discipline)
    except ValueError:
        return RedirectResponse("/dashboard")

    loader = get_curriculum()
    foundation = loader.get_modules_for_level(disc, Level.FOUNDATION)
    if not foundation:
        return RedirectResponse("/dashboard")

    # Load questions for first module
    repo = StudentRepository(db)
    first_mod = foundation[0]
    bank = await repo.get_questions(first_mod.id, limit=2)

    questions = [
        {"question": q["question"], "type": q["type"], "difficulty": q["difficulty"],
         "correct_answer": q["correct_answer"], "rubric": q["rubric"]}
        for q in bank
    ]

    # Store placement state in session via cookie
    state = {
        "discipline": discipline,
        "modules": [m.id for m in foundation],
        "current_module_idx": 0,
        "current_question_idx": 0,
        "questions": questions,
        "scores": {},
    }

    return render(request, "placement.html", {        "user": user,
        "discipline": disc.value.replace("_", " ").title(),
        "module_name": first_mod.name,
        "module_id": first_mod.id,
        "question": questions[0] if questions else None,
        "question_idx": 0,
        "total_questions": len(questions),
        "module_idx": 0,
        "total_modules": len(foundation),
        "state_json": json.dumps(state),
    })


@router.post("/{discipline}/answer", response_class=HTMLResponse)
async def placement_answer(
    request: Request,
    discipline: str,
    answer: str = Form(""),
    state_json: str = Form("{}"),
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Grade an answer and return next question or results."""
    if not user:
        return RedirectResponse("/login")

    state = json.loads(state_json)
    questions = state.get("questions", [])
    q_idx = state.get("current_question_idx", 0)
    mod_idx = state.get("current_module_idx", 0)
    modules = state.get("modules", [])
    scores = state.get("scores", {})

    # Grade current question
    if q_idx < len(questions):
        q = questions[q_idx]
        result = grader.grade(q["type"], answer, q["correct_answer"], q.get("rubric", ""))
        score = result.score if result else 0.5
        feedback = result.feedback if result else "Pending review"

        current_mod = modules[mod_idx] if mod_idx < len(modules) else ""
        if current_mod not in scores:
            scores[current_mod] = []
        scores[current_mod].append(score)

    # Move to next question or next module
    q_idx += 1
    if q_idx >= len(questions):
        # Save module score
        if current_mod and current_mod in scores:
            avg = sum(scores[current_mod]) / len(scores[current_mod])
            repo = StudentRepository(db)
            await repo.save_module_score(
                user.student_id, Discipline(discipline),
                ModuleScore(module_id=current_mod, score=avg),
            )

        # Move to next module
        mod_idx += 1
        q_idx = 0
        if mod_idx < len(modules):
            next_mod_id = modules[mod_idx]
            repo = StudentRepository(db)
            bank = await repo.get_questions(next_mod_id, limit=2)
            questions = [
                {"question": q["question"], "type": q["type"], "difficulty": q["difficulty"],
                 "correct_answer": q["correct_answer"], "rubric": q["rubric"]}
                for q in bank
            ]
        else:
            # Placement complete — determine starting level
            from phd_platform.assessment.placement import PlacementEngine
            from phd_platform.llm.client import get_llm_client
            loader = get_curriculum()
            client = get_llm_client()
            engine = PlacementEngine(client, loader)

            flat_scores = {}
            for mod_id, score_list in scores.items():
                flat_scores[mod_id] = sum(score_list) / len(score_list) if score_list else 0.0

            from phd_platform.core.models import Student
            student = await repo.get_student(user.student_id)
            starting_level = engine.determine_starting_level(
                student, Discipline(discipline), flat_scores
            )
            await repo.update_level(user.student_id, Discipline(discipline), starting_level)
            await repo.save_placement_result(
                user.student_id, Discipline(discipline), starting_level,
                engine.identify_gaps(flat_scores), flat_scores,
            )

            return render(request, "partials/placement_result.html", {                "starting_level": starting_level.value.title(),
                "scores": flat_scores,
                "discipline": discipline,
            })

    # Update state
    state["current_question_idx"] = q_idx
    state["current_module_idx"] = mod_idx
    state["questions"] = questions
    state["scores"] = scores

    loader = get_curriculum()
    current_mod_obj = loader.get_module(modules[mod_idx]) if mod_idx < len(modules) else None

    return render(request, "partials/question.html", {        "question": questions[q_idx] if q_idx < len(questions) else None,
        "question_idx": q_idx,
        "total_questions": len(questions),
        "module_name": current_mod_obj.name if current_mod_obj else "",
        "module_id": modules[mod_idx] if mod_idx < len(modules) else "",
        "module_idx": mod_idx,
        "total_modules": len(modules),
        "last_score": score,
        "last_feedback": feedback,
        "state_json": json.dumps(state),
        "discipline": discipline,
    })
