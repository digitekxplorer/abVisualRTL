import json
from typing import Dict, Any, List
from nugui.models.project import ProjectSettings
from nugui.models.elements import StateNode, TransitionLine

FILE_VERSION = "1.0"
SUPPORTED_VERSIONS = {"1.0"}


class ProjectFileError(Exception):
    """Raised when a project file is malformed or unsupported (FIX 3.6)."""
    pass


class FileManager:
    @staticmethod
    def save_project(filepath: str, settings: ProjectSettings,
                     nodes: Dict[int, StateNode], lines: List[TransitionLine]):
        """Saves current state to a JSON file."""
        data = {
            "version": FILE_VERSION,
            "settings": settings.to_dict(),
            "nodes": [node.to_dict() for node in nodes.values()],
            "lines": [line.to_dict() for line in lines]
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4)

    @staticmethod
    def load_project(filepath: str) -> Dict[str, Any]:
        """Loads JSON file and returns deserialized objects.

        FIX 3.6: validates the schema and version before deserializing so a
        corrupt or foreign JSON file produces a clear message instead of a
        raw KeyError/TypeError."""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ProjectFileError(f"Not a valid JSON file:\n{e}") from e

        if not isinstance(data, dict):
            raise ProjectFileError("Not an abVisualRTL project file.")

        version = data.get("version")
        if version is None:
            raise ProjectFileError("Missing 'version' — not an abVisualRTL project file.")
        if version not in SUPPORTED_VERSIONS:
            raise ProjectFileError(
                f"Unsupported project file version '{version}' "
                f"(this build reads: {', '.join(sorted(SUPPORTED_VERSIONS))}).")

        for key, typ in (("settings", dict), ("nodes", list), ("lines", list)):
            if key not in data:
                raise ProjectFileError(f"Project file is missing the '{key}' section.")
            if not isinstance(data[key], typ):
                raise ProjectFileError(f"Project file section '{key}' has the wrong type.")

        try:
            settings = ProjectSettings.from_dict(data["settings"])

            nodes = {}
            for n_data in data["nodes"]:
                node = StateNode.from_dict(n_data)
                nodes[node.id] = node

            lines = []
            for l_data in data["lines"]:
                lines.append(TransitionLine.from_dict(l_data))
        except (KeyError, TypeError, ValueError) as e:
            raise ProjectFileError(f"Project file contains invalid data:\n{e!r}") from e

        # Referential integrity: every transition must point at real states
        for line in lines:
            if line.start_state_id not in nodes or line.end_state_id not in nodes:
                raise ProjectFileError(
                    f"Transition {line.id} references a state that does not exist.")

        return {
            "settings": settings,
            "nodes": nodes,
            "lines": lines
        }
