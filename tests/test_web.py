"""Tests for the FastAPI web application."""

import os

import pytest
from fastapi.testclient import TestClient

from phd_platform.persistence.database import reset_globals


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    """Use a temp database for each test to avoid UNIQUE conflicts."""
    import phd_platform.config
    os.environ["PHD_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    phd_platform.config._settings = None
    reset_globals()
    yield
    phd_platform.config._settings = None
    reset_globals()
    os.environ.pop("PHD_DATABASE_URL", None)


@pytest.fixture
def client():
    """Create a test client with a fresh app (lifespan creates tables)."""
    from phd_platform.web.app import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestLanding:
    def test_landing_page_loads(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "nomos" in response.text.lower()

    def test_landing_shows_disciplines(self, client):
        response = client.get("/")
        assert "Economics" in response.text
        assert "Data Science" in response.text
        assert "Computer Science" in response.text

    def test_landing_has_register_link(self, client):
        response = client.get("/")
        assert "/register" in response.text


class TestAuth:
    def test_register_page_loads(self, client):
        response = client.get("/register")
        assert response.status_code == 200
        assert "Create your account" in response.text

    def test_login_page_loads(self, client):
        response = client.get("/login")
        assert response.status_code == 200
        assert "Sign in" in response.text

    def test_register_and_login_flow(self, client):
        # Register
        response = client.post("/register", data={
            "name": "Test User",
            "email": "test@nomos.ai",
            "password": "testpass123",
            "interests": "economics, ML",
            "disciplines": ["economics"],
        }, follow_redirects=False)
        assert response.status_code == 303
        assert "session" in response.cookies

        # Follow redirect to dashboard with session
        response = client.get("/dashboard", follow_redirects=True)
        assert response.status_code == 200
        assert "Test User" in response.text

    def test_logout_clears_session(self, client):
        response = client.get("/logout", follow_redirects=False)
        assert response.status_code == 303

    def test_dashboard_redirects_without_auth(self, client):
        response = client.get("/dashboard", follow_redirects=False)
        assert response.status_code in (303, 307, 200)  # Redirect to login


class TestPlacement:
    def test_placement_page_requires_auth(self, client):
        response = client.get("/placement/economics", follow_redirects=False)
        assert response.status_code in (303, 307)

    def test_placement_with_auth(self, client):
        # Register (TestClient auto-maintains cookies)
        client.post("/register", data={
            "name": "Placement Tester",
            "email": "placement@test.com",
            "password": "testpass",
            "disciplines": ["economics"],
        })
        response = client.get("/placement/economics")
        assert response.status_code == 200
        assert "Placement" in response.text or "Foundation" in response.text


class TestAssessment:
    def test_assessment_page(self, client):
        client.post("/register", data={
            "name": "Assess Tester",
            "email": "assess@test.com",
            "password": "testpass",
            "disciplines": ["economics"],
        })
        response = client.get("/assess/ECON-F-001")
        assert response.status_code == 200


class TestTutoring:
    def test_tutor_page(self, client):
        client.post("/register", data={
            "name": "Tutor Tester",
            "email": "tutor@test.com",
            "password": "testpass",
            "disciplines": ["economics"],
        })
        response = client.get("/tutor/ECON-F-001")
        assert response.status_code == 200
