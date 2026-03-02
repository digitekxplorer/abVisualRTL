from dataclasses import dataclass, field
from typing import List, Dict, Any
from nugui.models.ports import Port

@dataclass
class ProjectSettings:
    project_name: str = "MyFSM"
    clock_name: str = "clk"
    reset_name: str = "rst_n"
    reset_active_low: bool = True
    is_synchronous_reset: bool = False
    ports: List[Port] = field(default_factory=list)

    def add_port(self, port: Port):
        self.ports.append(port)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "clock_name": self.clock_name,
            "reset_name": self.reset_name,
            "reset_active_low": self.reset_active_low,
            "is_synchronous_reset": self.is_synchronous_reset,
            "ports": [p.to_dict() for p in self.ports]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProjectSettings':
        settings = cls(
            project_name=data.get("project_name", "MyFSM"),
            clock_name=data.get("clock_name", "clk"),
            reset_name=data.get("reset_name", "rst_n"),
            reset_active_low=data.get("reset_active_low", True),
            is_synchronous_reset=data.get("is_synchronous_reset", False)
        )
        if "ports" in data:
            settings.ports = [Port.from_dict(p) for p in data["ports"]]
        return settings
