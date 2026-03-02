from abc import ABC, abstractmethod
from typing import Dict, List
from nugui.models.elements import StateNode, TransitionLine
from nugui.models.project import ProjectSettings

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

    def indent(self, level: int) -> str:
        return self.indent_char * level
