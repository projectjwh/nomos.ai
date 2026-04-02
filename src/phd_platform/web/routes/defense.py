"""Defense routes — run interactive defense sessions in the browser."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.core.enums import Discipline, Level
from phd_platform.persistence.repository import StudentRepository
from phd_platform.web.app import render
from phd_platform.web.deps import get_current_user_optional, get_curriculum, get_db, get_llm

router = APIRouter()

# In-memory defense sessions (keyed by capstone_id)
_active_defenses: dict[str, dict] = {}


@router.get("/{capstone_id}", response_class=HTMLResponse)
async def defense_page(
    request: Request,
    capstone_id: str,
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Defense session page — shows reviews then Q&A."""
    if not user:
        return RedirectResponse("/login")

    repo = StudentRepository(db)
    capstone = await repo.get_capstone(capstone_id)
    if not capstone:
        return RedirectResponse("/dashboard")

    client = get_llm()
    if client.is_offline:
        return render(request, "defense.html", {
            "user": user, "capstone": capstone, "offline": True,
        })

    # Check if defense already completed
    existing = await repo.get_defense_results(capstone_id)
    if existing:
        return render(request, "defense.html", {
            "user": user, "capstone": capstone, "results": existing[0],
            "completed": True, "offline": False,
        })

    # Start defense — generate reviews
    level = Level(capstone["level"])
    disc = Discipline(capstone["discipline"])
    loader = get_curriculum()

    from phd_platform.defense.agents import ReviewerPanel
    panel_builder = ReviewerPanel(client)

    disc_curriculum = loader.get_discipline(disc)
    level_data = disc_curriculum.levels.get(level.value)
    journals = level_data.gate.journals if level_data else []
    agents = panel_builder.assemble(journals, level)

    if not agents:
        return render(request, "defense.html", {
            "user": user, "capstone": capstone, "offline": False,
            "error": "Could not assemble review panel.",
        })

    # Run reviews
    from phd_platform.defense.session import DefenseSession
    session = DefenseSession(agents, level, UUID(capstone_id))
    paper_text = capstone.get("paper_text", capstone.get("abstract", ""))
    reviews = await session.run_reviews(paper_text)

    # Store session for Q&A phase
    _active_defenses[capstone_id] = {
        "session": session,
        "paper_text": paper_text,
        "agents": agents,
        "qa_round": 0,
        "qa_agent_idx": 0,
        "level": level,
    }

    review_list = [
        {"journal": j, "report": r["report"]}
        for j, r in reviews.items()
    ]

    return render(request, "defense.html", {
        "user": user, "capstone": capstone, "offline": False,
        "reviews": review_list,
        "panel_size": len(agents),
        "phase": "qa",
    })


@router.post("/{capstone_id}/respond", response_class=HTMLResponse)
async def defense_respond(
    request: Request,
    capstone_id: str,
    answer: str = Form(""),
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Handle student response in Q&A, return next question or verdict."""
    if not user:
        return HTMLResponse("")

    state = _active_defenses.get(capstone_id)
    if not state:
        return render(request, "partials/defense_error.html", {
            "error": "Defense session expired. Please start again.",
        })

    session: "DefenseSession" = state["session"]
    agents = state["agents"]
    paper_text = state["paper_text"]
    level = state["level"]
    qa_round = state["qa_round"]
    qa_agent_idx = state["qa_agent_idx"]
    max_rounds = session.BASE_QA_ROUNDS.get(level, 3)

    # Record the student's answer to the current question
    if qa_round < max_rounds and qa_agent_idx < len(agents):
        agent = agents[qa_agent_idx]
        session.integrity_capture.mark_question_shown()  # Approximate
        event = session.integrity_capture.capture_response(answer)
        session.transcript.append({
            "phase": "qa", "round": qa_round + 1,
            "journal": agent.journal, "role": "student",
            "content": answer, "elapsed_seconds": (event.elapsed_ms or 0) / 1000.0,
        })

    # Advance to next agent/round
    qa_agent_idx += 1
    if qa_agent_idx >= len(agents):
        qa_agent_idx = 0
        qa_round += 1

    state["qa_round"] = qa_round
    state["qa_agent_idx"] = qa_agent_idx

    # Check if Q&A is done
    if qa_round >= max_rounds:
        # Run verdicts
        result = await session.run_verdicts(paper_text)

        # Save to DB
        repo = StudentRepository(db)
        await repo.save_defense_result(
            capstone_id=capstone_id,
            level=level,
            reviewer_verdicts={j: v.value for j, v in result.reviewer_verdicts.items()},
            feedback=result.feedback,
            overall_pass=result.overall_pass,
            transcript=session.get_transcript(),
        )
        del _active_defenses[capstone_id]

        verdicts = [
            {"journal": j, "verdict": v.value}
            for j, v in result.reviewer_verdicts.items()
        ]
        return render(request, "partials/defense_verdict.html", {
            "verdicts": verdicts,
            "overall_pass": result.overall_pass,
            "passing_count": result.passing_count,
            "total": len(result.reviewer_verdicts),
            "integrity": session.get_integrity_summary(),
        })

    # Generate next question
    agent = agents[qa_agent_idx]
    context = "\n".join(
        f"[{t['journal']} - {t['role']}]: {t['content']}"
        for t in session.transcript if t.get("phase") == "qa"
    )
    question = await agent.ask_question(context, paper_text)
    session.transcript.append({
        "phase": "qa", "round": qa_round + 1,
        "journal": agent.journal, "role": "reviewer",
        "content": question,
    })

    return render(request, "partials/defense_question.html", {
        "question": question,
        "journal": agent.journal,
        "round": qa_round + 1,
        "max_rounds": max_rounds,
        "capstone_id": capstone_id,
    })
