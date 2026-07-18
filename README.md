# abVisualRTL

A Python-based CAD tool for visually designing Finite State Machines (FSMs) and automatically generating synthesizable **SystemVerilog** and **VHDL** code.

abVisualRTL bridges the gap between whiteboard logic design and hardware implementation, letting engineers focus on state behavior rather than syntax errors.

## Features

- **Visual Editor** — Drag-and-drop interface for creating states and transitions, with smooth B-spline curves and grid snapping.
- **Multi-Language Support** — Generates production-ready SystemVerilog and VHDL.
- **Live Preview** — Split-screen view updates the HDL code in real time as you draw.
- **Logic Definition** — Moore actions (inside states), Mealy actions (on transitions), and complex transition logic with priority handling.
- **Correct-by-Construction HDL** — Latch prevention via per-port default output values, identifier validation against SystemVerilog *and* VHDL reserved words, duplicate-name and priority-conflict detection before generation.
- **Modern Workflow** — Undo/Redo history, JSON file persistence with schema validation, and PNG/PDF diagram export for documentation (no Ghostscript required).

## Requirements

- Python 3.9+
- [Pillow](https://pypi.org/project/Pillow/) (diagram export)
- Tkinter (bundled with most Python installations)

```bash
pip install Pillow
```

## Installation

```bash
git clone https://github.com/digitekxplorer/abVisualRTL.git
cd abVisualRTL
pip install Pillow
python main.py
```

## Usage

1. **Draw states** — Select the State tool and click on the canvas. Double-click a state to name it, mark it as the reset state, and add Moore actions (one per line, e.g. `led = 1`).
2. **Connect states** — Select the Line tool and drag from one state to another (or to itself for a self-loop). Double-click a transition to set its condition, Mealy action, and priority.
3. **Configure the module** — Open Settings to set the module name, clock/reset signals, and I/O ports. Each output port takes a default value, emitted at the top of the combinational block to prevent latch inference.
4. **Generate code** — The live preview updates as you draw. Export SystemVerilog or VHDL from the File menu.
5. **Document** — Export the diagram as PNG or PDF.

## Project Structure

```
abVisualRTL/
├── main.py                  # Application entry point
├── nugui/
│   ├── models/              # Diagram, states, transitions, ports, settings
│   ├── generators/          # SystemVerilog & VHDL code generators
│   ├── ui/                  # Canvas, dialogs, undo/redo commands
│   └── utils/               # Validation, file I/O, diagram export, constants
└── tests/                   # Generator unit tests (pytest)
```

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.
