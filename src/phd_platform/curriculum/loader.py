"""Load and resolve curriculum definitions from YAML configuration."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import yaml

from phd_platform.core.enums import Discipline, Level
from phd_platform.core.models import DisciplineCurriculum, Gate, LevelCurriculum, Module

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


class CurriculumLoader:
    """Loads curriculum YAML and builds the prerequisite dependency graph."""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or CONFIG_DIR / "curriculum.yaml"
        self._raw: dict = {}
        self._disciplines: dict[str, DisciplineCurriculum] = {}
        self._modules: dict[str, Module] = {}
        self._graph: nx.DiGraph = nx.DiGraph()

    def load(self) -> None:
        with open(self.config_path) as f:
            self._raw = yaml.safe_load(f)
        self._parse_disciplines()
        self._build_graph()

    def _parse_disciplines(self) -> None:
        for disc_key in Discipline:
            disc_data = self._raw.get(disc_key.value, {})
            if not disc_data:
                continue

            levels = {}
            for level_key in Level:
                level_data = disc_data.get("levels", {}).get(level_key.value, {})
                if not level_data:
                    continue

                gate_data = level_data.get("gate", {})
                gate = Gate(
                    name=gate_data.get("name", f"{level_key.value} gate"),
                    required_score=gate_data.get("required_score", level_key.mastery_threshold),
                    format=gate_data.get("format", ""),
                    capstone=gate_data.get("capstone", ""),
                    panel_size=gate_data.get("defense", {}).get("panel_size", 0),
                    journals=gate_data.get("defense", {}).get("journals", []),
                    pass_criteria=gate_data.get("defense", {}).get("pass_criteria", ""),
                )

                modules = []
                for mod_data in level_data.get("modules", []):
                    mod = Module(
                        id=mod_data["id"],
                        name=mod_data["name"],
                        description=mod_data.get("description", ""),
                        objectives=mod_data.get("objectives", []),
                        textbooks=mod_data.get("textbooks", []),
                        prerequisites=mod_data.get("prerequisites", []),
                        assessment=mod_data.get("assessment", ""),
                        weeks=mod_data.get("weeks", 4),
                        discipline=disc_key,
                        level=level_key,
                    )
                    modules.append(mod)
                    self._modules[mod.id] = mod

                levels[level_key.value] = LevelCurriculum(
                    name=level_data.get("name", level_key.value),
                    description=level_data.get("description", ""),
                    duration_weeks=str(level_data.get("duration_weeks", "")),
                    gate=gate,
                    modules=modules,
                )

            self._disciplines[disc_key.value] = DisciplineCurriculum(
                name=disc_data.get("name", disc_key.value),
                reference_programs=disc_data.get("reference_programs", []),
                levels=levels,
            )

    def _build_graph(self) -> None:
        """Build a directed acyclic graph of module prerequisites."""
        self._graph.clear()
        for mod_id, mod in self._modules.items():
            self._graph.add_node(mod_id, module=mod)
            for prereq_id in mod.prerequisites:
                if prereq_id in self._modules:
                    self._graph.add_edge(prereq_id, mod_id)

    # --- Public API ---

    def get_discipline(self, disc: Discipline) -> DisciplineCurriculum:
        return self._disciplines[disc.value]

    def get_module(self, module_id: str) -> Module:
        return self._modules[module_id]

    def get_modules_for_level(self, disc: Discipline, level: Level) -> list[Module]:
        curriculum = self._disciplines.get(disc.value)
        if not curriculum:
            return []
        level_data = curriculum.levels.get(level.value)
        return level_data.modules if level_data else []

    def get_prerequisites(self, module_id: str) -> list[Module]:
        """Get direct prerequisites for a module."""
        return [
            self._modules[pred]
            for pred in self._graph.predecessors(module_id)
            if pred in self._modules
        ]

    def get_prerequisite_chain(self, module_id: str) -> list[Module]:
        """Get the full transitive prerequisite chain (topologically sorted)."""
        ancestors = nx.ancestors(self._graph, module_id)
        subgraph = self._graph.subgraph(ancestors)
        return [self._modules[n] for n in nx.topological_sort(subgraph)]

    def get_all_modules(self) -> dict[str, Module]:
        return dict(self._modules)

    def get_dependency_graph(self) -> nx.DiGraph:
        return self._graph.copy()

    @property
    def total_modules(self) -> int:
        return len(self._modules)

    @property
    def disciplines(self) -> dict[str, DisciplineCurriculum]:
        return dict(self._disciplines)
