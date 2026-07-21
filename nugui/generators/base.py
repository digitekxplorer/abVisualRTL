from abc import ABC, abstractmethod
from typing import Dict, List
from nugui.models.elements import StateNode, TransitionLine
from nugui.models.ports import PortDirection
from nugui.models.project import ProjectSettings
from nugui.utils.hdl_validation import validate_project

class CodeGenerator(ABC):
    def __init__(self, settings: ProjectSettings, nodes: Dict[int, StateNode], lines: List[TransitionLine]):
        self.settings = settings
        self.nodes = nodes
        self.lines = lines
        self.indent_char = "    "

    @abstractmethod
    def generate(self) -> str:
        """Returns the generated code as a string."""
        pass

    def check_names(self):
        """FIX 2.3/2.4: raises ValueError listing every invalid or
        duplicate identifier. Call at the top of generate()."""
        errors = validate_project(self.settings, self.nodes)
        errors += self._check_priorities()
        if errors:
            raise ValueError("Cannot generate:\n- " + "\n- ".join(errors))

    def _check_priorities(self):
        """FIX 2.6: two outgoing transitions from the same state with the
        same priority have no defined order — flag them."""
        errors = []
        for node in self.nodes.values():
            outgoing = [l for l in self.lines if l.start_state_id == node.id]
            seen = {}
            for line in outgoing:
                if line.priority in seen:
                    other = self.nodes[seen[line.priority].end_state_id].name
                    target = self.nodes[line.end_state_id].name
                    errors.append(
                        f"State '{node.name}': transitions to '{other}' and "
                        f"'{target}' share priority {line.priority}.")
                else:
                    seen[line.priority] = line
        return errors

    def indent(self, level: int) -> str:
        return self.indent_char * level

    # ---- FIX 3.2: shared helpers (were copy-pasted in both generators) ----

    def find_reset_node(self) -> StateNode:
        """The explicitly marked reset state, else the first state."""
        return next((n for n in self.nodes.values() if n.is_reset_state),
                    next(iter(self.nodes.values())))

    def outgoing_sorted(self, node) -> List[TransitionLine]:
        """Transitions leaving `node`, highest priority (lowest number) first."""
        outgoing = [l for l in self.lines if l.start_state_id == node.id]
        outgoing.sort(key=lambda x: x.priority)
        return outgoing

    def clean_condition(self, cond: str) -> str:
        """Strip; empty means unconditional ('1')."""
        return cond.strip() or "1"

    def clean_action(self, act: str) -> str:
        """Strip and ensure a trailing semicolon (empty stays empty)."""
        act = act.strip()
        if act and not act.endswith(';'):
            act += ";"
        return act

    def input_ports(self):
        return [p for p in self.settings.ports if p.direction == PortDirection.IN]

    def output_ports(self):
        return [p for p in self.settings.ports if p.direction == PortDirection.OUT]
