import json
from typing import Dict, Any
from nugui.models.project import ProjectSettings
from nugui.models.elements import StateNode, TransitionLine


class FileManager:
    @staticmethod
    def save_project(filepath: str, settings: ProjectSettings,
                     nodes: Dict[int, StateNode], lines: list[TransitionLine]):
        """Saves current state to a JSON file."""
        data = {
            "version": "1.0",
            "settings": settings.to_dict(),
            "nodes": [node.to_dict() for node in nodes.values()],
            "lines": [line.to_dict() for line in lines]
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4)

    @staticmethod
    def load_project(filepath: str) -> Dict[str, Any]:
        """Loads JSON file and returns deserialized objects."""
        with open(filepath, 'r') as f:
            data = json.load(f)

        settings = ProjectSettings.from_dict(data["settings"])

        nodes = {}
        for n_data in data["nodes"]:
            node = StateNode.from_dict(n_data)
            nodes[node.id] = node

        lines = []
        for l_data in data["lines"]:
            line = TransitionLine.from_dict(l_data)
            lines.append(line)

        return {
            "settings": settings,
            "nodes": nodes,
            "lines": lines
        }
