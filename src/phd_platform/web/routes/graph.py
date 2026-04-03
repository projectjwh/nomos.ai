"""Knowledge Graph — Civ-style interactive tech tree with path planning.

Click any node (even locked) to see details + critical path.
Core modules form the spine. Electives branch off. Capstones are the goal.
"""

from __future__ import annotations

import json
from math import ceil

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from phd_platform.core.enums import Discipline, Level
from phd_platform.persistence.repository import StudentRepository
from phd_platform.web.app import render
from phd_platform.web.deps import get_current_user_optional, get_curriculum, get_db

router = APIRouter()

NODE_W = 175
H_GAP = 50
V_GAP = 125
LEVEL_GAP = 200
ROWS = 3
TOP_PAD = 55
LEFT_PAD = 60

LEVEL_ORDER = [Level.FOUNDATION, Level.UNDERGRADUATE, Level.MASTERS, Level.DOCTORAL]
LEVEL_META = {
    "foundation": {"label": "Foundation", "color": "#3b82f6", "icon": "school"},
    "undergraduate": {"label": "Undergraduate", "color": "#10b981", "icon": "menu_book"},
    "masters": {"label": "Masters", "color": "#f59e0b", "icon": "science"},
    "doctoral": {"label": "Doctoral", "color": "#ef4444", "icon": "workspace_premium"},
}
GATE_REQS = {
    "foundation": {"score": "90%", "defense": None},
    "undergraduate": {"score": "95%", "defense": "2-reviewer defense"},
    "masters": {"score": "95%", "defense": "3-reviewer defense"},
}


@router.get("/{discipline}", response_class=HTMLResponse)
async def knowledge_graph(
    request: Request, discipline: str,
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

    # Collect modules + reverse graph
    all_data = {}
    for level in LEVEL_ORDER:
        for mod in loader.get_modules_for_level(disc, level):
            all_data[mod.id] = {"mod": mod, "level": level, "unlocks": []}
    for mid, d in all_data.items():
        for p in d["mod"].prerequisites:
            if p in all_data:
                all_data[p]["unlocks"].append(mid)

    # Classify: CORE (has dependents), ELECTIVE (leaf), CAPSTONE (doctoral)
    def classify(mid):
        d = all_data[mid]
        if d["level"] == Level.DOCTORAL:
            return "capstone"
        return "core" if d["unlocks"] else "elective"

    # Position nodes horizontally
    nodes = []
    gates = []
    era_labels = []
    focus_node_id = None
    completed_count = 0
    total_count = 0
    total_weeks = 0
    completed_weeks = 0
    x_cursor = LEFT_PAD

    # Adjacency for JS path-finding
    adjacency = {}  # mid -> list of prereq mids

    for level_idx, level in enumerate(LEVEL_ORDER):
        modules = loader.get_modules_for_level(disc, level)
        total_count += len(modules)
        meta = LEVEL_META.get(level.value, {})
        era_start_x = x_cursor

        # Sort: core modules first, electives after
        sorted_mods = sorted(modules, key=lambda m: (0 if classify(m.id) == "core" else 1, m.id))

        for i, mod in enumerate(sorted_mods):
            col = i // ROWS
            row = i % ROWS
            x = x_cursor + col * (NODE_W + H_GAP)
            y = TOP_PAD + row * V_GAP
            total_weeks += mod.weeks

            score = student_scores.get(mod.id)
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

            cat = classify(mod.id)
            unlock_names = [all_data[u]["mod"].name for u in all_data[mod.id]["unlocks"]]
            difficulty = min(5, {"foundation": 1, "undergraduate": 2, "masters": 3, "doctoral": 4}.get(level.value, 2) + (1 if mod.weeks >= 5 else 0))

            adjacency[mod.id] = mod.prerequisites

            nodes.append({
                "id": mod.id, "name": mod.name, "level": level.value,
                "x": x, "y": y,
                "status": status,
                "score": round(score * 100) if score is not None else None,
                "prereqs": mod.prerequisites,
                "prereq_count": len(mod.prerequisites),
                "weeks": mod.weeks, "hours": mod.weeks * 10,
                "difficulty": difficulty,
                "unlock_count": len(unlock_names),
                "unlock_names": unlock_names[:5],
                "category": cat,
                "is_keystone": len(unlock_names) >= 3,
                "is_focus": (mod.id == focus_node_id),
                "era_color": meta.get("color", "#666"),
                "objectives": [o[:60] for o in mod.objectives[:3]],
            })

        cols = ceil(len(modules) / ROWS) if modules else 1
        x_cursor += cols * (NODE_W + H_GAP)

        era_labels.append({
            "x": era_start_x - 5, "label": meta.get("label", level.value.title()),
            "icon": meta.get("icon", "school"), "color": meta.get("color", "#666"),
            "count": len(modules),
        })

        if level_idx < len(LEVEL_ORDER) - 1:
            gate_req = GATE_REQS.get(level.value, {})
            gates.append({
                "x": x_cursor + 25,
                "level_from": level.value.title(),
                "level_to": LEVEL_ORDER[level_idx + 1].value.title(),
                "score_req": gate_req.get("score", ""),
                "defense_req": gate_req.get("defense"),
                "color": LEVEL_META.get(LEVEL_ORDER[level_idx + 1].value, {}).get("color", "#666"),
            })
            x_cursor += LEVEL_GAP

    canvas_w = x_cursor + 200
    canvas_h = TOP_PAD + ROWS * V_GAP + 60

    # Edges
    node_map = {n["id"]: n for n in nodes}
    edges = []
    for node in nodes:
        for pid in node["prereqs"]:
            if pid in node_map:
                fn, tn = node_map[pid], node
                ps = student_scores.get(pid, 0)
                if ps >= 0.80 and tn["status"] in ("completed", "in_progress", "available"):
                    es = "active"
                elif ps >= 0.80:
                    es = "ready"
                else:
                    es = "locked"
                edges.append({
                    "from": pid, "to": node["id"],
                    "from_x": fn["x"] + NODE_W, "from_y": fn["y"] + 45,
                    "to_x": tn["x"], "to_y": tn["y"] + 45,
                    "status": es,
                })

    progress_pct = round(completed_count / total_count * 100) if total_count > 0 else 0

    # JSON data for JS interactivity
    graph_json = json.dumps({
        "nodes": {n["id"]: {"prereqs": n["prereqs"], "status": n["status"], "name": n["name"]} for n in nodes},
        "adjacency": adjacency,
    })

    return render(request, "graph.html", {
        "user": user,
        "discipline": disc.value.replace("_", " ").title(),
        "discipline_id": disc.value,
        "nodes": nodes, "edges": edges, "gates": gates, "era_labels": era_labels,
        "focus_node_id": focus_node_id,
        "progress_pct": progress_pct,
        "completed_count": completed_count, "total_count": total_count,
        "current_level": current_level.value.title(),
        "canvas_w": canvas_w, "canvas_h": canvas_h,
        "total_weeks": total_weeks, "weeks_remaining": total_weeks - completed_weeks,
        "graph_json": graph_json,
    })
