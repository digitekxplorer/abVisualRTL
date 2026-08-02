"""FIX 3.1: GUI-free diagram model.

Owns the FSM data (states, transitions, ID counters) so generators,
file-IO, validation, and tests never need a live Tk canvas. The canvas
renders a Diagram and mutates it through these methods.
"""
from typing import Dict, List, Optional
from nugui.models.elements import StateNode, TransitionLine, TextAnnotation


class Diagram:
    def __init__(self):
        self.nodes: Dict[int, StateNode] = {}
        self.lines: List[TransitionLine] = []
        # FEATURE: free-floating text annotations (cosmetic, not part of FSM)
        self.annotations: Dict[int, TextAnnotation] = {}
        self.node_counter: int = 0
        self.line_counter: int = 0
        self.annotation_counter: int = 0

    # ---- Creation ----

    def new_state(self, x, y) -> StateNode:
        """Creates (but does not add) the next state with a unique id/name.
        First state ever created becomes the reset state."""
        node_id = self.node_counter
        self.node_counter += 1
        return StateNode(id=node_id, name=f"S{node_id}", x=x, y=y,
                         is_reset_state=(node_id == 0))

    def new_transition(self, start_id: int, end_id: int, **kw) -> TransitionLine:
        """Creates (but does not add) the next transition with a unique id."""
        line_id = self.line_counter
        self.line_counter += 1
        return TransitionLine(id=line_id, start_state_id=start_id,
                              end_state_id=end_id, **kw)

    def new_annotation(self, x, y, **kw) -> TextAnnotation:
        """Creates (but does not add) the next text annotation."""
        ann_id = self.annotation_counter
        self.annotation_counter += 1
        return TextAnnotation(id=ann_id, x=x, y=y, **kw)

    # ---- Mutation ----

    def add_node(self, node: StateNode):
        self.nodes[node.id] = node

    def add_line(self, line: TransitionLine):
        self.lines.append(line)

    def add_annotation(self, ann: TextAnnotation):
        self.annotations[ann.id] = ann

    def remove_node(self, node_id: int) -> Optional[StateNode]:
        return self.nodes.pop(node_id, None)

    def remove_line(self, line: TransitionLine):
        if line in self.lines:
            self.lines.remove(line)

    def remove_annotation(self, ann_id: int) -> Optional[TextAnnotation]:
        return self.annotations.pop(ann_id, None)

    def clear(self):
        self.nodes = {}
        self.lines = []
        self.annotations = {}
        self.node_counter = 0
        self.line_counter = 0
        self.annotation_counter = 0

    def load(self, nodes: Dict[int, StateNode], lines: List[TransitionLine],
             annotations: Optional[Dict[int, TextAnnotation]] = None):
        """Replaces contents and re-syncs the ID counters."""
        self.nodes = dict(nodes)
        self.lines = list(lines)
        self.annotations = dict(annotations or {})
        self.node_counter = max(self.nodes.keys(), default=-1) + 1
        self.line_counter = max((l.id for l in self.lines), default=-1) + 1
        self.annotation_counter = max(self.annotations.keys(), default=-1) + 1

    # ---- Queries ----

    def lines_touching(self, node_id: int) -> List[TransitionLine]:
        return [l for l in self.lines
                if l.start_state_id == node_id or l.end_state_id == node_id]

    def outgoing(self, node_id: int) -> List[TransitionLine]:
        return [l for l in self.lines if l.start_state_id == node_id]

    def reset_node(self) -> Optional[StateNode]:
        return next((n for n in self.nodes.values() if n.is_reset_state),
                    next(iter(self.nodes.values()), None))

    def set_reset_state(self, node_id: int):
        """Marks exactly one node as the reset state (FIX 1.6)."""
        for n in self.nodes.values():
            n.is_reset_state = (n.id == node_id)
