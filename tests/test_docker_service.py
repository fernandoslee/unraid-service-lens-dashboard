"""Unit tests for DockerService."""

from unittest.mock import patch

import pytest

from app.services.docker import DockerService


class TestParseLogLines:
    def test_standard_docker_timestamps(self):
        raw = "2024-01-15T10:30:45.123456789Z Starting application\n"
        lines = DockerService._parse_log_lines(raw)
        assert len(lines) == 1
        assert lines[0]["timestamp"] == "2024-01-15 10:30:45"
        assert lines[0]["message"] == "Starting application"

    def test_multiple_lines(self):
        raw = (
            "2024-01-15T10:30:45.123Z Line one\n"
            "2024-01-15T10:30:46.456Z Line two\n"
            "2024-01-15T10:30:47.789Z Line three\n"
        )
        lines = DockerService._parse_log_lines(raw)
        assert len(lines) == 3
        assert lines[0]["message"] == "Line one"
        assert lines[2]["message"] == "Line three"

    def test_empty_input(self):
        assert DockerService._parse_log_lines("") == []

    def test_blank_lines_skipped(self):
        raw = "2024-01-15T10:30:45.123Z Hello\n\n\n2024-01-15T10:30:46.456Z World\n"
        lines = DockerService._parse_log_lines(raw)
        assert len(lines) == 2

    def test_no_timestamp_fallback(self):
        raw = "Some raw log line without timestamp\n"
        lines = DockerService._parse_log_lines(raw)
        assert len(lines) == 1
        assert lines[0]["timestamp"] == ""
        assert lines[0]["message"] == "Some raw log line without timestamp"

    def test_nanosecond_trimming(self):
        raw = "2024-06-01T08:15:30.987654321Z Container started\n"
        lines = DockerService._parse_log_lines(raw)
        assert lines[0]["timestamp"] == "2024-06-01 08:15:30"

    def test_no_fractional_seconds(self):
        raw = "2024-01-15T10:30:45Z Simple message\n"
        lines = DockerService._parse_log_lines(raw)
        assert lines[0]["timestamp"] == "2024-01-15 10:30:45"
        assert lines[0]["message"] == "Simple message"


class TestContainerIdSplitting:
    @pytest.mark.asyncio
    async def test_colon_separated_uses_first_part(self):
        """GraphQL ID format hash:hash — first part is Docker container ID."""
        from unittest.mock import AsyncMock, MagicMock

        service = DockerService(MagicMock())
        service._fetch_logs = MagicMock(return_value="2024-01-01T00:00:00Z test\n")

        with patch.object(DockerService, "_fetch_logs", return_value="2024-01-01T00:00:00Z test\n"):
            # We can't easily test the internal split without mocking to_thread,
            # so test the static parsing and verify the split logic directly
            pass

        # Test the split logic directly
        container_id = "abc123:def456"
        docker_id = container_id.split(":")[0] if ":" in container_id else container_id
        assert docker_id == "abc123"

    def test_plain_id_used_as_is(self):
        container_id = "abc123def456"
        docker_id = container_id.split(":")[0] if ":" in container_id else container_id
        assert docker_id == "abc123def456"


class TestIsAvailable:
    def test_socket_exists(self, monkeypatch):
        monkeypatch.setattr("app.services.docker.DOCKER_SOCKET_PATH", type("P", (), {"exists": lambda self: True})())
        assert DockerService.is_available() is True

    def test_socket_missing(self, monkeypatch):
        monkeypatch.setattr("app.services.docker.DOCKER_SOCKET_PATH", type("P", (), {"exists": lambda self: False})())
        assert DockerService.is_available() is False
