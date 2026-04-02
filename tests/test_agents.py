"""Tests for the subagent system — registry, personas, and pipeline."""

import pytest

from phd_platform.agents.base import Agent, AgentRegistry, AgentRole, CognitiveProfile, PROFILE_TO_MODEL
from phd_platform.agents.runner import build_registry, ContentPipeline, ThoughtTrace
from phd_platform.agents.students import STUDENT_AGENTS
from phd_platform.agents.teachers import TEACHER_AGENTS
from phd_platform.agents.professors import PROFESSOR_AGENTS
from phd_platform.agents.reviewers import REVIEWER_AGENTS


class TestAgentRegistry:
    def test_build_full_registry(self):
        registry = build_registry()
        assert len(registry.all()) == 21  # 6 students + 5 teachers + 5 professors + 5 reviewers

    def test_filter_by_role(self):
        registry = build_registry()
        assert len(registry.students) == 6
        assert len(registry.teachers) == 5
        assert len(registry.professors) == 5
        assert len(registry.reviewers) == 5

    def test_filter_by_discipline(self):
        registry = build_registry()
        econ_agents = registry.by_discipline("economics")
        assert len(econ_agents) >= 5  # At least teacher, students, professors, reviewers

    def test_get_by_id(self):
        registry = build_registry()
        maria = registry.get("student-maria")
        assert maria.name == "Maria Santos"
        assert maria.role == AgentRole.STUDENT

    def test_all_ids_unique(self):
        registry = build_registry()
        ids = [a.id for a in registry.all()]
        assert len(ids) == len(set(ids))


class TestStudentPersonas:
    def test_all_students_have_system_prompt(self):
        for student in STUDENT_AGENTS:
            assert student.system_prompt, f"{student.id} missing system prompt"
            assert len(student.system_prompt) > 100, f"{student.id} system prompt too short"

    def test_all_students_have_backstory(self):
        for student in STUDENT_AGENTS:
            assert student.backstory, f"{student.id} missing backstory"

    def test_cognitive_profiles_varied(self):
        profiles = {s.profile for s in STUDENT_AGENTS}
        assert CognitiveProfile.STRUGGLING in profiles
        assert CognitiveProfile.DEVELOPING in profiles
        assert CognitiveProfile.GIFTED in profiles

    def test_model_hints_correct(self):
        struggling = [s for s in STUDENT_AGENTS if s.profile == CognitiveProfile.STRUGGLING]
        assert all(s.model_hint == "haiku" for s in struggling)
        gifted = [s for s in STUDENT_AGENTS if s.profile == CognitiveProfile.GIFTED]
        assert all(s.model_hint == "opus" for s in gifted)

    def test_disciplines_covered(self):
        all_disciplines = set()
        for s in STUDENT_AGENTS:
            all_disciplines.update(s.disciplines)
        for disc in ["economics", "data_science", "computer_science", "ai_ml", "financial_engineering"]:
            assert disc in all_disciplines, f"No student covers {disc}"


class TestTeacherPersonas:
    def test_one_per_discipline(self):
        covered = {t.disciplines[0] for t in TEACHER_AGENTS}
        expected = {"economics", "data_science", "computer_science", "ai_ml", "financial_engineering"}
        assert covered == expected

    def test_all_teachers_gifted(self):
        for t in TEACHER_AGENTS:
            assert t.profile == CognitiveProfile.GIFTED

    def test_all_have_expertise_tags(self):
        for t in TEACHER_AGENTS:
            assert len(t.expertise_tags) >= 4, f"{t.id} needs more expertise tags"


class TestProfessorPersonas:
    def test_five_professors(self):
        assert len(PROFESSOR_AGENTS) == 5

    def test_interdisciplinary_professor_covers_all(self):
        interdisc = [p for p in PROFESSOR_AGENTS if "interdisciplinary" in p.id]
        assert len(interdisc) == 1
        assert len(interdisc[0].disciplines) >= 4

    def test_unique_research_foci(self):
        foci = [p.expertise_tags[0] for p in PROFESSOR_AGENTS]
        assert len(foci) == len(set(foci)), "Professor research foci should be unique"


class TestReviewerPersonas:
    def test_five_reviewers(self):
        assert len(REVIEWER_AGENTS) == 5

    def test_complementary_expertise(self):
        """Reviewers should cover different aspects of paper quality."""
        all_tags = set()
        for r in REVIEWER_AGENTS:
            all_tags.update(r.expertise_tags)
        # Should cover: methodology, theory, significance, reproducibility, writing
        assert "causal-identification" in all_tags
        assert "mathematical-proofs" in all_tags
        assert "reproducibility" in all_tags
        assert "academic-writing" in all_tags

    def test_all_have_behavioral_notes(self):
        for r in REVIEWER_AGENTS:
            assert r.behavioral_notes, f"{r.id} missing behavioral notes"


class TestContentPipeline:
    def test_extract_section(self):
        text = "APPROACH: I'll use the quadratic formula\nWORKING: Step 1..."
        result = ContentPipeline._extract_section(text, "APPROACH")
        assert "quadratic" in result

    def test_extract_list(self):
        text = "STUCK POINTS:\n- Can't simplify the integral\n- Forgot chain rule\nFINAL:"
        items = ContentPipeline._extract_list(text, "STUCK")
        assert len(items) >= 1

    def test_thought_trace_structure(self):
        trace = ThoughtTrace(
            student_id="student-maria",
            student_name="Maria Santos",
            module_id="ECON-F-001",
            question="Solve 2x + 3 = 7",
            approach="I'll isolate x",
            working="2x + 3 = 7, so 2x = 4, so x = 2",
            stuck_points=[],
            wrong_turns=[],
            final_answer="x = 2",
            followup_questions=["What if there were two variables?"],
            confidence="high",
            cognitive_profile="struggling",
        )
        assert trace.student_name == "Maria Santos"
        assert trace.confidence == "high"
