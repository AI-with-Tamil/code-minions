"""DockerEnv — full runtime isolation. One container per run. Production primary."""

from __future__ import annotations

import io
import shlex
import socket
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

from codeminions.core.context import ExecResult


def _load_env_file(path: str) -> dict[str, str]:
    """Parse a .env file into a dict. Skips comments and blank lines."""
    env: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"DockerEnv env_file not found: {path}")
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def _find_free_port(port_range: tuple[int, int]) -> int:
    """Return first available TCP port in range. Raises RuntimeError if none free."""
    start, end = port_range
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port in range {start}-{end}")


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

    startup_commands: list[str] = field(default_factory=list)

    # Runtime state
    _container_id: str | None = field(default=None, init=False, repr=False)
    _reserved_port: int | None = field(default=None, init=False, repr=False)

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
        env_vars = _load_env_file(self.env_file) if self.env_file else {}
        self._reserved_port = _find_free_port(self.port_range)
        container = client.containers.run(
            self.image,
            command="sleep infinity",
            detach=True,
            working_dir=self.working_dir,
            volumes=volumes,
            network_mode=self.network,
            mem_limit=self.memory_limit,
            nano_cpus=int(self.cpu_limit * 1e9),
            environment=env_vars,
        )
        self._container_id = container.id

        for cmd in self.startup_commands:
            result = await self.exec(cmd)
            if result.exit_code != 0:
                await self.cleanup()
                raise RuntimeError(
                    f"DockerEnv startup command failed (exit {result.exit_code}): {cmd!r}\n"
                    f"stderr: {result.stderr.strip()}"
                )

    async def read(self, path: str) -> str:
        result = await self.exec(f"cat {shlex.quote(path)}")
        if result.exit_code != 0:
            raise FileNotFoundError(f"File not found in container: {path}")
        return result.stdout

    async def write(self, path: str, content: str) -> None:
        if not self._container_id:
            raise RuntimeError("DockerEnv not set up. Call setup() first.")
        try:
            import docker
        except ImportError:
            raise ImportError("DockerEnv requires the 'docker' package.")
        client = docker.from_env()
        container = client.containers.get(self._container_id)
        abs_path = path if path.startswith("/") else f"{self.working_dir}/{path}"
        parent = str(Path(abs_path).parent)
        container.exec_run(["mkdir", "-p", parent])
        data = content.encode("utf-8")
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name=Path(abs_path).name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        buf.seek(0)
        container.put_archive(parent, buf.getvalue())

    async def edit(self, path: str, old: str, new: str) -> None:
        content = await self.read(path)
        if old not in content:
            raise ValueError(f"old_string not found in {path}")
        content = content.replace(old, new, 1)
        await self.write(path, content)

    async def exec(self, cmd: str, cwd: str | None = None) -> ExecResult:
        """Run a shell command inside the container.

        cmd is passed to sh -c. Callers must use shlex.quote() for any
        user-supplied values embedded in cmd. Container isolation bounds the
        blast radius of untrusted input.
        """
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
