"""Tests for the subagent system — registry, personas, and pipeline."""

import pytest

from phd_platform.agents.base import Agent, AgentRegistry, AgentRole, CognitiveProfile, PROFILE_TO_MODEL
from phd_platform.agents.runner import build_registry, ContentPipeline, ThoughtTrace
from phd_platform.agents.counselors import COUNSELOR_AGENTS
from phd_platform.agents.students import STUDENT_AGENTS
from phd_platform.agents.teachers import TEACHER_AGENTS
from phd_platform.agents.professors import PROFESSOR_AGENTS
from phd_platform.agents.reviewers import REVIEWER_AGENTS
from phd_platform.agents.specialists import SPECIALIST_AGENTS


class TestAgentRegistry:
    def test_build_full_registry(self):
        registry = build_registry()
        # 6 students + 5 teachers + 5 professors + 5 reviewers + 5 specialists + 3 counselors
        assert len(registry.all()) == 29

    def test_filter_by_role(self):
        registry = build_registry()
        assert len(registry.students) == 6
        # Teachers include: 5 discipline teachers + 5 specialists + 3 counselors = 13
        assert len(registry.teachers) == 13
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


class TestSpecialistPersonas:
    def test_five_specialists(self):
        assert len(SPECIALIST_AGENTS) == 5

    def test_all_cover_all_disciplines(self):
        """Specialists must work across all disciplines (they standardize)."""
        for s in SPECIALIST_AGENTS:
            assert len(s.disciplines) == 5, f"{s.id} should cover all 5 disciplines"

    def test_unique_specialist_roles(self):
        ids = [s.id for s in SPECIALIST_AGENTS]
        expected = {
            "specialist-taxonomy", "specialist-fairness", "specialist-item-engineer",
            "specialist-alignment", "specialist-analytics",
        }
        assert set(ids) == expected

    def test_all_have_detailed_system_prompts(self):
        for s in SPECIALIST_AGENTS:
            assert len(s.system_prompt) > 500, f"{s.id} system prompt too short for specialist role"

    def test_taxonomy_has_tagging_keywords(self):
        taxonomy = [s for s in SPECIALIST_AGENTS if s.id == "specialist-taxonomy"][0]
        assert "concept_id" in taxonomy.system_prompt
        assert "bloom_level" in taxonomy.system_prompt

    def test_fairness_has_bias_keywords(self):
        fairness = [s for s in SPECIALIST_AGENTS if s.id == "specialist-fairness"][0]
        assert "bias" in fairness.system_prompt.lower()
        assert "construct_validity" in fairness.system_prompt


class TestCounselorPersonas:
    def test_three_counselors(self):
        assert len(COUNSELOR_AGENTS) == 3

    def test_different_achievement_tiers(self):
        ids = {c.id for c in COUNSELOR_AGENTS}
        assert "counselor-foundation" in ids      # below 80%
        assert "counselor-advancement" in ids     # 80-94%
        assert "counselor-excellence" in ids      # 95%+

    def test_foundation_counselor_focuses_on_gaps(self):
        foundation = [c for c in COUNSELOR_AGENTS if c.id == "counselor-foundation"][0]
        prompt = foundation.system_prompt.lower()
        assert "gap" in prompt
        assert "confidence" in prompt
        assert "dropout" in prompt or "prevent" in prompt

    def test_advancement_counselor_focuses_on_efficiency(self):
        advancement = [c for c in COUNSELOR_AGENTS if c.id == "counselor-advancement"][0]
        prompt = advancement.system_prompt.lower()
        assert "roi" in prompt
        assert "velocity" in prompt
        assert "gate" in prompt

    def test_excellence_counselor_focuses_on_research(self):
        excellence = [c for c in COUNSELOR_AGENTS if c.id == "counselor-excellence"][0]
        prompt = excellence.system_prompt.lower()
        assert "original" in prompt
        assert "research" in prompt
        assert "publish" in prompt or "publication" in prompt

    def test_all_counselors_cover_all_disciplines(self):
        for c in COUNSELOR_AGENTS:
            assert len(c.disciplines) == 5

    def test_all_counselors_have_escalation_protocol(self):
        for c in COUNSELOR_AGENTS:
            assert "monitor" in c.system_prompt.lower() or "follow" in c.system_prompt.lower(), \
                f"{c.id} must have monitoring/follow-up protocol"


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
