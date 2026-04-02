"""Tests for CLI commands — argument parsing and read-only commands."""

import subprocess
import sys

import pytest


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run the CLI and capture output."""
    return subprocess.run(
        [sys.executable, "-m", "phd_platform", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestReadOnlyCommands:
    def test_info_command(self):
        result = run_cli("info")
        assert result.returncode == 0
        assert "116" in result.stdout  # Total modules
        assert "Disciplines" in result.stdout

    def test_modules_command(self):
        result = run_cli("modules", "economics", "foundation")
        assert result.returncode == 0
        assert "ECON-F-001" in result.stdout

    def test_modules_verbose(self):
        result = run_cli("modules", "ai_ml", "foundation", "-v")
        assert result.returncode == 0
        assert "AI-F-001" in result.stdout

    def test_modules_invalid_discipline(self):
        result = run_cli("modules", "invalid_disc", "foundation")
        assert result.returncode != 0

    def test_prereqs_command(self):
        result = run_cli("prereqs", "ECON-U-009")
        assert result.returncode == 0
        assert "ECON-U-008" in result.stdout  # Direct prereq

    def test_prereqs_no_prereqs(self):
        result = run_cli("prereqs", "ECON-F-001")
        assert result.returncode == 0
        assert "no prerequisites" in result.stdout

    def test_help_shows_all_commands(self):
        result = run_cli("--help")
        assert result.returncode == 0
        for cmd in ["info", "modules", "prereqs", "register", "progress",
                     "learn", "assess", "placement", "capstone", "defense", "status"]:
            assert cmd in result.stdout

    def test_no_command_shows_help(self):
        result = run_cli()
        assert result.returncode == 0
        assert "phd-platform" in result.stdout or "PhD" in result.stdout
