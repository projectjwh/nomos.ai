"""Tutoring routes — Socratic chat interface (requires LLM)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.persistence.repository import StudentRepository
from phd_platform.tutor.engine import TutoringEngine
from phd_platform.web.app import render
from phd_platform.web.deps import get_current_user_optional, get_curriculum, get_db, get_llm

router = APIRouter()

# In-memory tutor sessions (keyed by user_id:module_id)
_tutor_sessions: dict[str, TutoringEngine] = {}


@router.get("/{module_id}", response_class=HTMLResponse)
async def tutor_page(
    request: Request,
    module_id: str,
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Tutoring chat page for a module."""
    if not user:
        return RedirectResponse("/login")

    loader = get_curriculum()
    try:
        module = loader.get_module(module_id)
    except KeyError:
        return RedirectResponse("/dashboard")

    client = get_llm()
    if client.is_offline:
        return render(request, "tutor.html", { "user": user, "module": module,
            "offline": True, "messages": [],
        })

    # Load prior conversation
    repo = StudentRepository(db)
    prior = await repo.load_tutoring_session(user.student_id, module_id)
    messages = prior or []

    # Initialize tutor engine
    session_key = f"{user.id}:{module_id}"
    if session_key not in _tutor_sessions:
        _tutor_sessions[session_key] = TutoringEngine(client)
        if prior:
            _tutor_sessions[session_key].conversation_history = prior

    return render(request, "tutor.html", { "user": user, "module": module,
        "offline": False, "messages": messages,
    })


@router.post("/{module_id}/message", response_class=HTMLResponse)
async def tutor_message(
    request: Request,
    module_id: str,
    message: str = Form(""),
    user=Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the tutor and get a response (HTMX partial)."""
    if not user or not message.strip():
        return HTMLResponse("")

    loader = get_curriculum()
    module = loader.get_module(module_id)
    client = get_llm()

    if client.is_offline:
        return render(request, "partials/chat_msg.html", { "role": "assistant",
            "content": "Tutoring requires an LLM. Install Ollama and run: ollama pull llama3.1:8b",
        })

    session_key = f"{user.id}:{module_id}"
    if session_key not in _tutor_sessions:
        _tutor_sessions[session_key] = TutoringEngine(client)

    tutor = _tutor_sessions[session_key]
    level = module.level or loader.get_module(module_id).level

    response_text = await tutor.teach(module, level, message)

    # Save conversation to DB
    repo = StudentRepository(db)
    await repo.save_tutoring_session(
        user.student_id, module_id, tutor.conversation_history,
    )

    # Return both messages as HTMX fragment (student + tutor)
    return render(request, "partials/chat_msg.html", {        "student_msg": message,
        "tutor_msg": response_text,
    })
