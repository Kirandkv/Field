"""In-memory agent registry — how Incident Commander discovers what peer agents can
do. Ephemeral by design in slice 1: a real service-discovery mechanism (Consul,
Kubernetes DNS, ...) is an infra concern, not something this application layer should
own. Discovery still crosses a real network boundary — see main.py's
POST /agents/discover, which fetches a peer's actual /.well-known/agent-card.
"""

from __future__ import annotations

from fieldforge_contracts import AgentCard


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentCard] = {}

    def register(self, card: AgentCard) -> None:
        self._agents[card.id] = card

    def get(self, agent_id: str) -> AgentCard | None:
        return self._agents.get(agent_id)

    def find_by_role(self, role: str) -> AgentCard | None:
        for card in self._agents.values():
            if card.role == role:
                return card
        return None

    def list(self) -> list[AgentCard]:
        return list(self._agents.values())
