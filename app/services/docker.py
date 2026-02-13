import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DOCKER_SOCKET_PATH = Path("/var/run/docker.sock")


class DockerService:
    """Fetches container logs via the Docker socket using docker-py."""

    def __init__(self, client):
        self._client = client

    @staticmethod
    def is_available() -> bool:
        return DOCKER_SOCKET_PATH.exists()

    @staticmethod
    def create() -> "DockerService | None":
        if not DockerService.is_available():
            logger.info("Docker socket not found at %s — container logs unavailable", DOCKER_SOCKET_PATH)
            return None
        try:
            import docker
            client = docker.DockerClient(base_url=f"unix://{DOCKER_SOCKET_PATH}")
            client.ping()
            logger.info("Docker socket connected — container logs available")
            return DockerService(client)
        except Exception as e:
            logger.warning("Docker socket found but connection failed: %s", e)
            return None

    async def get_container_logs(self, container_id: str, tail: int = 100) -> list[dict]:
        """Fetch recent log lines from a container.

        The GraphQL container ID format is ``hash:hash`` — the first part
        is the Docker container ID.
        """
        docker_id = container_id.split(":")[0] if ":" in container_id else container_id
        raw = await asyncio.to_thread(self._fetch_logs, docker_id, tail)
        return self._parse_log_lines(raw)

    def _fetch_logs(self, docker_id: str, tail: int) -> str:
        container = self._client.containers.get(docker_id)
        return container.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")

    @staticmethod
    def _parse_log_lines(raw: str) -> list[dict]:
        lines = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            # Docker timestamp format: 2024-01-15T10:30:45.123456789Z message
            if len(line) > 30 and line[4] == "-" and "T" in line[:20]:
                space_idx = line.find(" ", 20)
                if space_idx != -1:
                    ts = line[:space_idx]
                    # Trim nanoseconds — keep up to seconds
                    dot_idx = ts.find(".")
                    if dot_idx != -1:
                        # Keep everything before the dot + timezone indicator
                        tz_suffix = "Z" if ts.endswith("Z") else ""
                        ts = ts[:dot_idx] + tz_suffix
                    # Format: 2024-01-15T10:30:45Z → 2024-01-15 10:30:45
                    ts = ts.replace("T", " ").rstrip("Z")
                    lines.append({"timestamp": ts, "message": line[space_idx + 1:]})
                    continue
            # No recognizable timestamp — include line as-is
            lines.append({"timestamp": "", "message": line})
        return lines

    def close(self):
        if self._client:
            self._client.close()
