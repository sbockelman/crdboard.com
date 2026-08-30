from __future__ import annotations

from dataclasses import dataclass

from .main_db import MainRepository


@dataclass(frozen=True)
class TableServerAssignment:
    table_id: int
    host: str
    port: int
    status: str
    container_name: str

    @property
    def http_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return self.http_url


class TableServerCoordinator:
    """Lightweight coordinator that tracks per-table server assignment.

    This MVP stores assignment state and deterministic ports so an external
    orchestrator can start/stop the actual container process.
    """

    def __init__(self, repository: MainRepository, host: str, base_port: int) -> None:
        self.repository = repository
        self.host = host
        self.base_port = base_port

    def assign(self, table_id: int) -> TableServerAssignment:
        existing = self.repository.get_assignment(table_id)
        if existing:
            return TableServerAssignment(
                table_id=int(existing["table_id"]),
                host=existing["host"],
                port=int(existing["port"]),
                status=existing["status"],
                container_name=existing["container_name"] or f"table-server-{table_id}",
            )
        port = self.base_port + table_id
        container_name = f"table-server-{table_id}"
        self.repository.upsert_assignment(
            table_id=table_id,
            host=self.host,
            port=port,
            status="assigned",
            container_name=container_name,
        )
        return TableServerAssignment(table_id, self.host, port, "assigned", container_name)

    def mark_running(self, table_id: int) -> None:
        assignment = self.assign(table_id)
        self.repository.upsert_assignment(
            table_id=table_id,
            host=assignment.host,
            port=assignment.port,
            status="running",
            container_name=assignment.container_name,
        )

    def mark_stopped(self, table_id: int) -> None:
        assignment = self.assign(table_id)
        self.repository.upsert_assignment(
            table_id=table_id,
            host=assignment.host,
            port=assignment.port,
            status="stopped",
            container_name=assignment.container_name,
        )
