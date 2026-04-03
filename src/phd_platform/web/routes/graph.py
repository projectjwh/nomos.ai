"""Knowledge Graph tech tree — Civilization-style horizontal prerequisite map.

Design principles (Civ tech tree + Stitch glass aesthetic):
1. STRATEGIC VALUE: Every node shows what it costs AND what it unlocks
2. CRITICAL PATH: Keystone modules (high unlock count) are visually larger
3. ERA TRANSITIONS: Level gates feel like entering a new age
4. COST CLARITY: Time (weeks), effort (difficulty stars), prerequisites visible
5. UNLOCK CHAINS: Hover/click reveals what completing a module enables
6. FOG OF FUTURE: Locked nodes visible but faded — you see your whole journey
"""

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

NODE_W = 180
H_GAP = 55
V_GAP = 130
LEVEL_GAP = 220
ROWS = 3
TOP_PAD = 50
LEFT_PAD = 60

LEVEL_ORDER = [Level.FOUNDATION, Level.UNDERGRADUATE, Level.MASTERS, Level.DOCTORAL]
LEVEL_LABELS = {
    "foundation": {"era": "Foundation Era", "color": "#3b82f6", "icon": "school"},
    "undergraduate": {"era": "Undergraduate Era", "color": "#10b981", "icon": "menu_book"},
    "masters": {"era": "Masters Era", "color": "#f59e0b", "icon": "science"},
    "doctoral": {"era": "Doctoral Era", "color": "#ef4444", "icon": "workspace_premium"},
}
GATE_REQS = {
    "foundation": {"score": "90%", "defense": None},
    "undergraduate": {"score": "95%", "defense": "2-reviewer capstone defense"},
    "masters": {"score": "95%", "defense": "3-reviewer thesis defense"},
}


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

    # First pass: collect all modules and build reverse graph (what does X unlock?)
    all_modules = {}
    for level in LEVEL_ORDER:
        for mod in loader.get_modules_for_level(disc, level):
            all_modules[mod.id] = {
                "mod": mod, "level": level,
                "unlocks": [],  # modules that require this one
            }
    for mid, data in all_modules.items():
        for prereq_id in data["mod"].prerequisites:
            if prereq_id in all_modules:
                all_modules[prereq_id]["unlocks"].append(mid)

    # Second pass: position nodes horizontally, compute status + metadata
    nodes = []
    gates = []
    era_labels = []
    focus_node_id = None
    completed_count = 0
    total_count = 0
    total_weeks = 0
    completed_weeks = 0
    x_cursor = LEFT_PAD

    for level_idx, level in enumerate(LEVEL_ORDER):
        modules = loader.get_modules_for_level(disc, level)
        total_count += len(modules)
        count = len(modules)
        level_meta = LEVEL_LABELS.get(level.value, {})
        era_start_x = x_cursor

        for i, mod in enumerate(modules):
            col = i // ROWS
            row = i % ROWS
            x = x_cursor + col * (NODE_W + H_GAP)
            y = TOP_PAD + row * V_GAP

            score = student_scores.get(mod.id)
            total_weeks += mod.weeks

            if score is not None and score >= threshold:
                status = "completed"
                completed_count += 1
                completed_weeks += mod.weeks
            elif score is not None:
                status = "in_progress"
            else:
                prereqs_met = all(
                    student_scores.get(p, 0) >= 0.80 for p in mod.prerequisites
                ) if mod.prerequisites else True
                if prereqs_met and level.value == current_level.value:
                    status = "available"
                    if focus_node_id is None:
                        focus_node_id = mod.id
                else:
                    status = "locked"

            unlock_names = [
                all_modules[uid]["mod"].name for uid in all_modules[mod.id]["unlocks"]
            ]
            prereq_count = len(mod.prerequisites)
            unlock_count = len(unlock_names)

            # Difficulty: 1-5 based on level + weeks
            level_base = {"foundation": 1, "undergraduate": 2, "masters": 3, "doctoral": 4}
            difficulty = min(5, level_base.get(level.value, 2) + (1 if mod.weeks >= 5 else 0))

            # Keystone? (unlocks 3+ modules = strategically important)
            is_keystone = unlock_count >= 3

            nodes.append({
                "id": mod.id,
                "name": mod.name,
                "level": level.value,
                "x": x,
                "y": y,
                "status": status,
                "score": round(score * 100) if score is not None else None,
                "prereqs": mod.prerequisites,
                "prereq_count": prereq_count,
                "weeks": mod.weeks,
                "hours": mod.weeks * 10,
                "difficulty": difficulty,
                "unlock_count": unlock_count,
                "unlock_names": unlock_names[:4],  # Show first 4
                "is_keystone": is_keystone,
                "is_focus": (mod.id == focus_node_id),
                "era_color": level_meta.get("color", "#666"),
                "objectives_count": len(mod.objectives),
            })

        cols = ceil(count / ROWS) if count > 0 else 1
        x_cursor += cols * (NODE_W + H_GAP)

        # Era label at the start of each level section
        era_labels.append({
            "x": era_start_x - 10,
            "label": level_meta.get("era", level.value.title()),
            "icon": level_meta.get("icon", "school"),
            "color": level_meta.get("color", "#666"),
            "module_count": count,
        })

        # Gate divider between levels
        if level_idx < len(LEVEL_ORDER) - 1:
            gate_req = GATE_REQS.get(level.value, {})
            gates.append({
                "x": x_cursor + 30,
                "level_from": level.value.title(),
                "level_to": LEVEL_ORDER[level_idx + 1].value.title(),
                "score_req": gate_req.get("score", ""),
                "defense_req": gate_req.get("defense"),
                "color_from": level_meta.get("color", "#666"),
                "color_to": LEVEL_LABELS.get(LEVEL_ORDER[level_idx + 1].value, {}).get("color", "#666"),
            })
            x_cursor += LEVEL_GAP

    canvas_w = x_cursor + 200
    canvas_h = TOP_PAD + ROWS * V_GAP + 60

    # Build edges with status
    node_map = {n["id"]: n for n in nodes}
    edges = []
    for node in nodes:
        for prereq_id in node["prereqs"]:
            if prereq_id in node_map:
                fn = node_map[prereq_id]
                tn = node
                prereq_score = student_scores.get(prereq_id, 0)
                if prereq_score >= 0.80 and tn["status"] in ("completed", "in_progress", "available"):
                    edge_status = "active"
                elif prereq_score >= 0.80:
                    edge_status = "ready"
                else:
                    edge_status = "locked"
                edges.append({
                    "from_x": fn["x"] + NODE_W,
                    "from_y": fn["y"] + 45,
                    "to_x": tn["x"],
                    "to_y": tn["y"] + 45,
                    "status": edge_status,
                })

    progress_pct = round(completed_count / total_count * 100) if total_count > 0 else 0
    weeks_remaining = total_weeks - completed_weeks

    return render(request, "graph.html", {
        "user": user,
        "discipline": disc.value.replace("_", " ").title(),
        "discipline_id": disc.value,
        "nodes": nodes,
        "edges": edges,
        "gates": gates,
        "era_labels": era_labels,
        "focus_node_id": focus_node_id,
        "progress_pct": progress_pct,
        "completed_count": completed_count,
        "total_count": total_count,
        "current_level": current_level.value.title(),
        "canvas_w": canvas_w,
        "canvas_h": canvas_h,
        "total_weeks": total_weeks,
        "completed_weeks": completed_weeks,
        "weeks_remaining": weeks_remaining,
    })
