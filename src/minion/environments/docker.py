"""DockerEnv — full runtime isolation. One container per run. Production primary."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field

from minion.core.context import ExecResult


@dataclass
class DockerEnv:
    """Full runtime isolation. One container per run.

    Ports, databases, services all isolated. Use this for production agents
    and any task that starts services.
    """

    image: str
    repo_path: str
    working_dir: str = "/workspace"
    env_file: str | None = None
    network: str = "none"
    port_range: tuple[int, int] = (40000, 50000)
    memory_limit: str = "4g"
    cpu_limit: float = 2.0

    # Runtime state
    _container_id: str | None = field(default=None, init=False, repr=False)

    @property
    def path(self) -> str:
        return self.working_dir

    async def setup(self) -> None:
        """Create and start the Docker container."""
        try:
            import docker
        except ImportError:
            raise ImportError(
                "DockerEnv requires the 'docker' package. "
                "Install with: uv add --optional docker docker"
            )
        client = docker.from_env()
        volumes = {self.repo_path: {"bind": self.working_dir, "mode": "rw"}}
        container = client.containers.run(
            self.image,
            command="sleep infinity",
            detach=True,
            working_dir=self.working_dir,
            volumes=volumes,
            network_mode=self.network,
            mem_limit=self.memory_limit,
            nano_cpus=int(self.cpu_limit * 1e9),
        )
        self._container_id = container.id

    async def read(self, path: str) -> str:
        result = await self.exec(f"cat {shlex.quote(path)}")
        if result.exit_code != 0:
            raise FileNotFoundError(f"File not found in container: {path}")
        return result.stdout

    async def write(self, path: str, content: str) -> None:
        # Use heredoc to write content
        escaped = content.replace("'", "'\\''")
        safe_path = shlex.quote(path)
        await self.exec(f"mkdir -p $(dirname {safe_path}) && printf '%s' '{escaped}' > {safe_path}")

    async def edit(self, path: str, old: str, new: str) -> None:
        content = await self.read(path)
        if old not in content:
            raise ValueError(f"old_string not found in {path}")
        content = content.replace(old, new, 1)
        await self.write(path, content)

    async def exec(self, cmd: str, cwd: str | None = None) -> ExecResult:
        if not self._container_id:
            raise RuntimeError("DockerEnv not set up. Call setup() first.")
        try:
            import docker
        except ImportError:
            raise ImportError("DockerEnv requires the 'docker' package.")
        client = docker.from_env()
        container = client.containers.get(self._container_id)
        work_dir = cwd or self.working_dir
        exit_code, output = container.exec_run(
            ["sh", "-c", cmd],
            workdir=work_dir,
            demux=True,
        )
        stdout = output[0].decode("utf-8", errors="replace") if output[0] else ""
        stderr = output[1].decode("utf-8", errors="replace") if output[1] else ""
        return ExecResult(stdout=stdout, stderr=stderr, exit_code=exit_code)

    async def glob(self, pattern: str) -> list[str]:
        safe_pattern = shlex.quote(f"{self.working_dir}/{pattern}")
        result = await self.exec(f"find {self.working_dir} -path {safe_pattern}")
        if not result.stdout.strip():
            return []
        return [
            line.replace(f"{self.working_dir}/", "")
            for line in result.stdout.strip().splitlines()
        ]

    async def exists(self, path: str) -> bool:
        safe_path = shlex.quote(path)
        result = await self.exec(f"test -e {safe_path} && echo yes || echo no")
        return result.stdout.strip() == "yes"

    async def cleanup(self) -> None:
        if self._container_id:
            try:
                import docker
                client = docker.from_env()
                container = client.containers.get(self._container_id)
                container.remove(force=True)
            except Exception:
                pass
            self._container_id = None
