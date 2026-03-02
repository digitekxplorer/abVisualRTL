from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Dict


class PortDirection(Enum):
    IN = "input"
    OUT = "output"
    INOUT = "inout"


@dataclass
class Port:
    name: str
    direction: PortDirection
    width: int = 1
    default_value: str = "0"

    def get_sv_decl(self) -> str:
        dir_str = self.direction.value
        width_str = "" if self.width == 1 else f"[{self.width - 1}:0] "
        return f"{dir_str} logic {width_str}{self.name}"

    def get_vhdl_decl(self) -> str:
        dir_map = {PortDirection.IN: "in", PortDirection.OUT: "out", PortDirection.INOUT: "inout"}
        dir_str = dir_map[self.direction]
        type_str = "std_logic" if self.width == 1 else f"std_logic_vector({self.width - 1} downto 0)"
        return f"{self.name} : {dir_str} {type_str}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "direction": self.direction.value,  # Save string value
            "width": self.width,
            "default_value": self.default_value
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Port':
        return cls(
            name=data["name"],
            direction=PortDirection(data["direction"]),  # Convert string back to Enum
            width=data["width"],
            default_value=data.get("default_value", "0")
        )
