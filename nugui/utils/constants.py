from enum import Enum

class ToolType(Enum):
    SELECT = 1
    STATE = 2
    LINE = 3

# Geometry
BUBBLE_RADIUS = 30
BUBBLE_DIAMETER = BUBBLE_RADIUS * 2

# Colors
COLOR_BG = "white"
COLOR_STATE_OUTLINE = "black"
COLOR_STATE_FILL = "#f0f0f0"
COLOR_LINE = "black"
COLOR_SELECTED = "red"
COLOR_TEMP_LINE = "gray"

# Grid Settings
GRID_SIZE = 20
COLOR_GRID = "#e0e0e0"
