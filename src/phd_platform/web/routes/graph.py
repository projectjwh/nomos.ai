"""Knowledge Graph tech tree — horizontal scrolling prerequisite visualization."""

from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.core.enums import Discipline, Level
from phd_platform.persistence.repository import StudentRepository
from phd_platform.web.app import render
from phd_platform.web.deps import get_current_user_optional, get_curriculum, get_db

router = APIRouter()

# Horizontal layout constants
NODE_W = 170
NODE_H = 80
H_GAP = 50
V_GAP = 110
LEVEL_GAP = 180
ROWS_PER_LEVEL = 3
TOP_PAD = 40
LEFT_PAD = 80

GATE_REQS = {
    "foundation": "90% Mastery",
    "undergraduate": "95% + 2-Reviewer Defense",
    "masters": "95% + 3-Reviewer Defense",
}

LEVEL_ORDER = [Level.FOUNDATION, Level.UNDERGRADUATE, Level.MASTERS, Level.DOCTORAL]


@router.get("/{discipline}", response_class=HTMLResponse)
async def knowledge_graph(
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
        return RedirectResponse("/courses")

    loader = get_curriculum()
    repo = StudentRepository(db)

    student = await repo.get_student(user.student_id) if user.student_id else None
    student_scores = {}
    current_level = Level.FOUNDATION
    if student:
        progress = student.get_progress(disc)
        current_level = progress.current_level
        student_scores = {mid: s.score for mid, s in progress.module_scores.items()}

    threshold = current_level.mastery_threshold

    # Build nodes with HORIZONTAL positions
    nodes = []
    gates = []
    focus_node_id = None
    completed_count = 0
    total_count = 0
    x_cursor = LEFT_PAD

    for level_idx, level in enumerate(LEVEL_ORDER):
        modules = loader.get_modules_for_level(disc, level)
        total_count += len(modules)
        count = len(modules)
        level_start_x = x_cursor

        for i, mod in enumerate(modules):
            col = i // ROWS_PER_LEVEL
            row = i % ROWS_PER_LEVEL
            x = x_cursor + col * (NODE_W + H_GAP)
            y = TOP_PAD + row * V_GAP

            score = student_scores.get(mod.id)
            if score is not None and score >= threshold:
                status = "completed"
                completed_count += 1
            elif score is not None:
                status = "in_progress"
            else:
                prereqs_met = all(
                    student_scores.get(p, 0) >= 0.80
                    for p in mod.prerequisites
                ) if mod.prerequisites else True
                if prereqs_met and level.value == current_level.value:
                    status = "available"
                    if focus_node_id is None:
                        focus_node_id = mod.id
                else:
                    status = "locked"

            nodes.append({
                "id": mod.id,
                "name": mod.name,
                "level": level.value,
                "level_label": level.value.title(),
                "x": x,
                "y": y,
                "status": status,
                "score": round(score * 100) if score is not None else None,
                "prereqs": mod.prerequisites,
                "weeks": mod.weeks,
                "is_focus": mod.id == focus_node_id if focus_node_id else False,
            })

        # Advance cursor past this level's nodes
        cols = ceil(count / ROWS_PER_LEVEL) if count > 0 else 1
        x_cursor += cols * (NODE_W + H_GAP)

        # Add gate divider (except after doctoral)
        if level_idx < len(LEVEL_ORDER) - 1:
            next_level = LEVEL_ORDER[level_idx + 1]
            gates.append({
                "x": x_cursor + 20,
                "level_from": level.value.title(),
                "level_to": next_level.value.title(),
                "requirement": GATE_REQS.get(level.value, ""),
            })
            x_cursor += LEVEL_GAP

    canvas_w = x_cursor + 200
    canvas_h = TOP_PAD + ROWS_PER_LEVEL * V_GAP + 40

    # Build edges
    node_positions = {n["id"]: (n["x"] + NODE_W // 2, n["y"] + NODE_H // 2) for n in nodes}
    edges = []
    for node in nodes:
        for prereq_id in node["prereqs"]:
            if prereq_id in node_positions:
                fx, fy = node_positions[prereq_id]
                tx, ty = node_positions[node["id"]]
                prereq_score = student_scores.get(prereq_id, 0)
                edge_status = "active" if prereq_score >= 0.80 else "inactive"
                edges.append({
                    "from_x": fx + NODE_W // 2 - 10,
                    "from_y": fy,
                    "to_x": tx - NODE_W // 2 + 10,
                    "to_y": ty,
                    "status": edge_status,
                })

    progress_pct = round(completed_count / total_count * 100) if total_count > 0 else 0

    return render(request, "graph.html", {
        "user": user,
        "discipline": disc.value.replace("_", " ").title(),
        "discipline_id": disc.value,
        "nodes": nodes,
        "edges": edges,
        "gates": gates,
        "focus_node_id": focus_node_id,
        "progress_pct": progress_pct,
        "completed_count": completed_count,
        "total_count": total_count,
        "current_level": current_level.value.title(),
        "canvas_w": canvas_w,
        "canvas_h": canvas_h,
    })
