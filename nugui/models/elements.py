from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import math


@dataclass
class StateNode:
    id: int
    name: str
    x: int
    y: int
    # Visual IDs (Transient - do not save)
    canvas_item_id: Optional[int] = field(default=None, repr=False)
    text_item_id: Optional[int] = field(default=None, repr=False)
    details_item_id: Optional[int] = field(default=None, repr=False)

    # Offsets
    name_offset_x: float = 0.0
    name_offset_y: float = 0.0
    details_offset_x: float = 0.0
    details_offset_y: float = 0.0

    # Logical
    is_reset_state: bool = False
    actions: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.name:
            self.name = f"S_{self.id}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "name_offset_x": self.name_offset_x,
            "name_offset_y": self.name_offset_y,
            "details_offset_x": self.details_offset_x,
            "details_offset_y": self.details_offset_y,
            "is_reset_state": self.is_reset_state,
            "actions": self.actions
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StateNode':
        # Create instance only with persistable data
        return cls(
            id=data["id"],
            name=data["name"],
            x=data["x"],
            y=data["y"],
            name_offset_x=data.get("name_offset_x", 0.0),
            name_offset_y=data.get("name_offset_y", 0.0),
            details_offset_x=data.get("details_offset_x", 0.0),
            details_offset_y=data.get("details_offset_y", 0.0),
            is_reset_state=data.get("is_reset_state", False),
            actions=data.get("actions", [])
        )


@dataclass
class TransitionLine:
    id: int
    start_state_id: int
    end_state_id: int
    # Visual IDs (Transient)
    canvas_item_id: Optional[int] = field(default=None, repr=False)
    handle_id: Optional[int] = field(default=None, repr=False)
    text_item_id: Optional[int] = field(default=None, repr=False)

    curvature: float = 0.0
    loop_angle: float = field(default=-math.pi / 2)
    text_offset_x: float = 0.0
    text_offset_y: float = -15.0

    # Logical
    condition: str = "1"
    priority: int = 1
    action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "start_state_id": self.start_state_id,
            "end_state_id": self.end_state_id,
            "curvature": self.curvature,
            "loop_angle": self.loop_angle,
            "text_offset_x": self.text_offset_x,
            "text_offset_y": self.text_offset_y,
            "condition": self.condition,
            "priority": self.priority,
            "action": self.action
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TransitionLine':
        return cls(
            id=data["id"],
            start_state_id=data["start_state_id"],
            end_state_id=data["end_state_id"],
            curvature=data.get("curvature", 0.0),
            loop_angle=data.get("loop_angle", -math.pi / 2),
            text_offset_x=data.get("text_offset_x", 0.0),
            text_offset_y=data.get("text_offset_y", -15.0),
            condition=data.get("condition", "1"),
            priority=data.get("priority", 1),
            action=data.get("action", "")
        )


@dataclass
class TextAnnotation:
    """FEATURE: a free-floating text label placed anywhere on the diagram.

    Purely cosmetic — it is not part of the FSM and never affects generated
    HDL. Position is stored in logic coordinates like states/transitions.
    """
    id: int
    x: float
    y: float
    text: str = "Text"
    font_family: str = "Arial"
    font_size: int = 12
    bold: bool = False
    italic: bool = False
    align: str = "left"  # left | center | right
    color: str = "#000000"
    # Visual ID (Transient - do not save)
    canvas_item_id: Optional[int] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "text": self.text,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "align": self.align,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TextAnnotation':
        return cls(
            id=data["id"],
            x=data["x"],
            y=data["y"],
            text=data.get("text", "Text"),
            font_family=data.get("font_family", "Arial"),
            font_size=data.get("font_size", 12),
            bold=data.get("bold", False),
            italic=data.get("italic", False),
            align=data.get("align", "left"),
            color=data.get("color", "#000000"),
        )
