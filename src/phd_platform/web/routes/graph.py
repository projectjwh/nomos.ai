"""Knowledge Graph tech tree — gamified prerequisite visualization."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.core.enums import Discipline, Level
from phd_platform.persistence.repository import StudentRepository
from phd_platform.web.app import render
from phd_platform.web.deps import get_current_user_optional, get_curriculum, get_db

router = APIRouter()

LEVEL_Y = {"foundation": 0, "undergraduate": 1, "masters": 2, "doctoral": 3}
CANVAS_W = 1100
CANVAS_H = 800
LEVEL_SPACING = 190
TOP_PAD = 60


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

    # Load student scores
    student = await repo.get_student(user.student_id) if user.student_id else None
    student_scores = {}
    current_level = Level.FOUNDATION
    if student:
        progress = student.get_progress(disc)
        current_level = progress.current_level
        student_scores = {mid: s.score for mid, s in progress.module_scores.items()}

    threshold = current_level.mastery_threshold

    # Build nodes with positions
    nodes = []
    focus_node_id = None
    completed_count = 0
    total_count = 0

    for level in Level:
        level_idx = LEVEL_Y[level.value]
        modules = loader.get_modules_for_level(disc, level)
        total_count += len(modules)
        count = len(modules)

        for mod_idx, mod in enumerate(modules):
            # Position: spread evenly across canvas width per level
            x = int((mod_idx + 1) * CANVAS_W / (count + 1))
            y = TOP_PAD + level_idx * LEVEL_SPACING

            score = student_scores.get(mod.id)
            if score is not None and score >= threshold:
                status = "completed"
                completed_count += 1
            elif score is not None:
                status = "in_progress"
            else:
                # Check if prerequisites are met
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
                "level_idx": level_idx,
                "x": x,
                "y": y,
                "status": status,
                "score": round(score * 100) if score is not None else None,
                "prereqs": mod.prerequisites,
                "weeks": mod.weeks,
            })

    # Build edges
    node_positions = {n["id"]: (n["x"], n["y"]) for n in nodes}
    edges = []
    for node in nodes:
        for prereq_id in node["prereqs"]:
            if prereq_id in node_positions:
                fx, fy = node_positions[prereq_id]
                tx, ty = node_positions[node["id"]]
                # Determine if this edge is on the completed path
                prereq_score = student_scores.get(prereq_id, 0)
                edge_status = "active" if prereq_score >= 0.80 else "inactive"
                edges.append({
                    "from_x": fx, "from_y": fy + 20,
                    "to_x": tx, "to_y": ty - 20,
                    "status": edge_status,
                })

    progress_pct = round(completed_count / total_count * 100) if total_count > 0 else 0

    return render(request, "graph.html", {
        "user": user,
        "discipline": disc.value.replace("_", " ").title(),
        "discipline_id": disc.value,
        "nodes": nodes,
        "edges": edges,
        "focus_node_id": focus_node_id,
        "progress_pct": progress_pct,
        "completed_count": completed_count,
        "total_count": total_count,
        "current_level": current_level.value.title(),
        "canvas_w": CANVAS_W,
        "canvas_h": CANVAS_H,
    })
