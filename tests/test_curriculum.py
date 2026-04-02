"""Tests for curriculum loading and prerequisite resolution."""

import pytest

from phd_platform.core.enums import Discipline, Level
from phd_platform.curriculum.loader import CurriculumLoader


@pytest.fixture
def loader():
    cl = CurriculumLoader()
    cl.load()
    return cl


class TestCurriculumLoader:
    def test_load_all_disciplines(self, loader: CurriculumLoader):
        for disc in Discipline:
            curriculum = loader.get_discipline(disc)
            assert curriculum.name, f"Missing name for {disc.value}"

    def test_all_levels_have_modules(self, loader: CurriculumLoader):
        for disc in Discipline:
            for level in Level:
                modules = loader.get_modules_for_level(disc, level)
                assert len(modules) > 0, f"No modules for {disc.value}/{level.value}"

    def test_module_ids_are_unique(self, loader: CurriculumLoader):
        all_modules = loader.get_all_modules()
        ids = list(all_modules.keys())
        assert len(ids) == len(set(ids)), "Duplicate module IDs found"

    def test_module_has_objectives(self, loader: CurriculumLoader):
        for mod_id, mod in loader.get_all_modules().items():
            assert len(mod.objectives) > 0, f"Module {mod_id} has no objectives"

    def test_prerequisites_exist(self, loader: CurriculumLoader):
        all_ids = set(loader.get_all_modules().keys())
        for mod_id, mod in loader.get_all_modules().items():
            for prereq in mod.prerequisites:
                assert prereq in all_ids, (
                    f"Module {mod_id} has nonexistent prerequisite {prereq}"
                )

    def test_prerequisite_chain(self, loader: CurriculumLoader):
        # ECON-U-009 (Econometrics II) should have ECON-U-008 in its chain
        chain = loader.get_prerequisite_chain("ECON-U-009")
        chain_ids = [m.id for m in chain]
        assert "ECON-U-008" in chain_ids

    def test_dependency_graph_is_acyclic(self, loader: CurriculumLoader):
        import networkx as nx
        graph = loader.get_dependency_graph()
        assert nx.is_directed_acyclic_graph(graph), "Prerequisite graph has cycles"

    def test_total_modules_count(self, loader: CurriculumLoader):
        assert loader.total_modules > 80, (
            f"Expected 80+ modules, got {loader.total_modules}"
        )

    def test_foundation_modules_have_no_cross_level_prereqs(self, loader: CurriculumLoader):
        """Foundation modules should only depend on other foundation modules."""
        for disc in Discipline:
            foundation_modules = loader.get_modules_for_level(disc, Level.FOUNDATION)
            foundation_ids = {m.id for m in foundation_modules}
            for mod in foundation_modules:
                for prereq in mod.prerequisites:
                    assert prereq in foundation_ids, (
                        f"Foundation module {mod.id} depends on non-foundation {prereq}"
                    )


class TestEnums:
    def test_level_ordering(self):
        assert Level.FOUNDATION.next == Level.UNDERGRADUATE
        assert Level.UNDERGRADUATE.next == Level.MASTERS
        assert Level.MASTERS.next == Level.DOCTORAL
        assert Level.DOCTORAL.next is None

    def test_mastery_thresholds(self):
        assert Level.FOUNDATION.mastery_threshold == 0.90
        assert Level.UNDERGRADUATE.mastery_threshold == 0.95
        assert Level.MASTERS.mastery_threshold == 0.95

    def test_defense_panel_sizes(self):
        assert Level.FOUNDATION.defense_panel_size == 0
        assert Level.UNDERGRADUATE.defense_panel_size == 2
        assert Level.MASTERS.defense_panel_size == 3
        assert Level.DOCTORAL.defense_panel_size == 5
