"""abVisualRTL — a Python-based CAD tool for visually designing Finite
State Machines (FSMs) and generating synthesizable SystemVerilog and
VHDL code. Features a drag-and-drop editor with B-spline transitions,
live HDL preview, Moore/Mealy actions with transition priorities,
undo/redo, JSON persistence, and PNG/PDF diagram export.

History
-------
2026-07  Code-review update:
  - Fixed VHDL generator bugs: empty sensitivity list with no input
    ports; dangling else / stray "end if" on default transitions.
  - Latch prevention: outputs get per-port default values at the top of
    the combinational block in both generators.
  - Validation: HDL identifier + reserved-word checks (SV and VHDL),
    duplicate state/port names, clock/reset collisions, duplicate
    transition priorities — enforced in dialogs and at generation.
  - Exact state-register bit-width via bit_length() (no float log2).
  - Single reset state enforced; dirty-flag and preview-focus fixes.
  - PNG/PDF export rewritten as a pure-Pillow off-screen renderer
    (HiDPI-safe, full diagram, no Ghostscript).
  - Grid drawing limited to visible region (was ~62k canvas items).
  - Architecture: Diagram data model extracted from the canvas; shared
    generator helpers deduplicated; project-file schema validation on
    load; pytest suite for the generators (25 tests).
"""
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import os

# Image Library for Export (FIX 5.1 rev 2: pure-Pillow renderer, no
# screen grab and no Ghostscript)
try:
    from nugui.utils.diagram_export import export_diagram
except ImportError:
    export_diagram = None

# UI Components
from nugui.ui.canvas import GraphCanvas
from nugui.ui.dialogs.settings import ProjectSettingsDialog

# Utilities & Constants
from nugui.utils.constants import ToolType
from nugui.utils.file_io import FileManager

# Data Models
from nugui.models.project import ProjectSettings

# Generators
from nugui.generators.system_verilog import SystemVerilogGenerator
from nugui.generators.vhdl import VHDLGenerator


class abVisualRTLApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.app_name = "abVisualRTL"
        self.title(self.app_name)
        self.geometry("1400x800")

        # --- Data Model ---
        self.project_settings = ProjectSettings()

        # --- State Tracking ---
        self.current_filepath = None
        self.is_modified = False

        # --- UI Initialization ---
        self._setup_menus()
        self._setup_toolbar()

        # --- Layout Engine ---
        self.paned_window = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=4, bg="#d9d9d9")
        self.paned_window.pack(fill=tk.BOTH, expand=True)

        # 1. Left Pane: Canvas
        self.canvas_frame = tk.Frame(self.paned_window)
        self.paned_window.add(self.canvas_frame, stretch="always")

        # Scrollbars
        self.v_scroll = tk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL)
        self.h_scroll = tk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL)

        # Canvas
        self.canvas = GraphCanvas(
            self.canvas_frame,
            yscrollcommand=self.v_scroll.set,
            xscrollcommand=self.h_scroll.set
        )

        self.v_scroll.config(command=self.canvas.yview)
        self.h_scroll.config(command=self.canvas.xview)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll.grid(row=1, column=0, sticky="ew")

        self.canvas_frame.grid_rowconfigure(0, weight=1)
        self.canvas_frame.grid_columnconfigure(0, weight=1)

        # 2. Right Pane: Code Preview
        self.preview_frame = tk.Frame(self.paned_window, width=400, bg="white")
        self._setup_preview_panel()

        # --- Bindings ---
        # FIX 1.5: guard destructive shortcuts so they don't fire while the
        # user is focused in a text-entry widget.
        self.bind("<Delete>", lambda event: self._shortcut(self.delete_selection))
        self.bind("<BackSpace>", lambda event: self._shortcut(self.delete_selection))
        self.bind("<Control-z>", lambda event: self._shortcut(self.undo))
        self.bind("<Control-y>", lambda event: self._shortcut(self.redo))
        # FIX 5.3: redo alias + file accelerators
        self.bind("<Control-Shift-Z>", lambda event: self._shortcut(self.redo))
        self.bind("<Control-s>", lambda event: self.save_project())
        self.bind("<Control-o>", lambda event: self.open_project())
        self.bind("<Control-n>", lambda event: self.new_project())

        # The canvas triggers this event whenever data changes
        self.canvas.bind("<<DiagramChanged>>", self.on_diagram_changed)

        # Intercept Window Close Button (X)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _shortcut(self, action):
        """Runs a destructive shortcut only when focus is not in a
        text-entry widget (FIX 1.5)."""
        widget = self.focus_get()
        if isinstance(widget, (tk.Text, tk.Entry, ttk.Entry, tk.Spinbox, ttk.Spinbox)):
            return
        action()

    def _setup_menus(self):
        self.menubar = tk.Menu(self)
        self.config(menu=self.menubar)

        # File Menu
        file_menu = tk.Menu(self.menubar, tearoff=0)
        file_menu.add_command(label="New Project", command=self.new_project, accelerator="Ctrl+N")
        file_menu.add_command(label="Open Project...", command=self.open_project, accelerator="Ctrl+O")
        file_menu.add_command(label="Save Project", command=self.save_project, accelerator="Ctrl+S")
        file_menu.add_command(label="Save Project As...", command=self.save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="Export Diagram (PNG / PDF)...", command=self.export_image)
        file_menu.add_separator()
        file_menu.add_command(label="Generate SystemVerilog...", command=self.generate_sv)
        file_menu.add_command(label="Generate VHDL...", command=self.generate_vhdl)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        self.menubar.add_cascade(label="File", menu=file_menu)

        # Edit Menu
        edit_menu = tk.Menu(self.menubar, tearoff=0)
        edit_menu.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", command=self.redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Delete", command=self.delete_selection, accelerator="Del")
        self.menubar.add_cascade(label="Edit", menu=edit_menu)

        # Project Menu
        project_menu = tk.Menu(self.menubar, tearoff=0)
        project_menu.add_command(label="Settings & Ports...", command=self.open_settings)
        self.menubar.add_cascade(label="Project", menu=project_menu)

    def _setup_toolbar(self):
        self.toolbar = tk.Frame(self, bd=1, relief=tk.RAISED)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)

        # Tool Buttons
        self.btn_select = tk.Button(self.toolbar, text="Select / Move",
                                    command=lambda: self.set_tool(ToolType.SELECT))
        self.btn_select.pack(side=tk.LEFT, padx=2, pady=2)

        self.btn_state = tk.Button(self.toolbar, text="Add State",
                                   command=lambda: self.set_tool(ToolType.STATE))
        self.btn_state.pack(side=tk.LEFT, padx=2, pady=2)

        self.btn_line = tk.Button(self.toolbar, text="Add Transition",
                                  command=lambda: self.set_tool(ToolType.LINE))
        self.btn_line.pack(side=tk.LEFT, padx=2, pady=2)

        self.btn_delete = tk.Button(self.toolbar, text="Delete", fg="red",
                                    command=self.delete_selection)
        self.btn_delete.pack(side=tk.LEFT, padx=10, pady=2)

        tk.Frame(self.toolbar, width=20).pack(side=tk.LEFT)

        # Zoom
        tk.Button(self.toolbar, text="Zoom In (+)",
                  command=lambda: self.canvas.set_zoom(self.canvas.zoom_scale * 1.1)).pack(side=tk.LEFT, padx=2)
        tk.Button(self.toolbar, text="Zoom Out (-)",
                  command=lambda: self.canvas.set_zoom(self.canvas.zoom_scale * 0.9)).pack(side=tk.LEFT, padx=2)

        tk.Frame(self.toolbar, width=20).pack(side=tk.LEFT)

        # View Toggles
        self.var_show_details = tk.BooleanVar(value=False)
        self.chk_details = tk.Checkbutton(self.toolbar, text="Show Actions",
                                          variable=self.var_show_details,
                                          command=self.toggle_details)
        self.chk_details.pack(side=tk.LEFT, padx=5, pady=2)

        self.var_snap = tk.BooleanVar(value=True)
        self.chk_snap = tk.Checkbutton(self.toolbar, text="Snap to Grid",
                                       variable=self.var_snap,
                                       command=self.toggle_snap)
        self.chk_snap.pack(side=tk.LEFT, padx=5, pady=2)

        # Grid Style
        tk.Label(self.toolbar, text="Grid:").pack(side=tk.LEFT, padx=(10, 2))
        self.cb_grid_style = ttk.Combobox(self.toolbar, values=["Dots", "Lines", "Hidden"],
                                          state="readonly", width=8)
        self.cb_grid_style.set("Dots")
        self.cb_grid_style.pack(side=tk.LEFT, padx=2)
        self.cb_grid_style.bind("<<ComboboxSelected>>", self.change_grid_style)

        # Code Toggle
        self.var_show_code = tk.BooleanVar(value=False)
        self.chk_code = tk.Checkbutton(self.toolbar, text="Show Code",
                                       variable=self.var_show_code,
                                       command=self.toggle_code_view)
        self.chk_code.pack(side=tk.LEFT, padx=5, pady=2)

        self.lbl_status = tk.Label(self.toolbar, text="Mode: SELECT", fg="blue")
        self.lbl_status.pack(side=tk.RIGHT, padx=10)

    def _setup_preview_panel(self):
        ctrl_frame = tk.Frame(self.preview_frame, bg="#f0f0f0", height=30)
        ctrl_frame.pack(side=tk.TOP, fill=tk.X)

        tk.Label(ctrl_frame, text="Live Preview:", bg="#f0f0f0").pack(side=tk.LEFT, padx=5, pady=5)

        self.preview_lang = tk.StringVar(value="SystemVerilog")
        lang_cb = ttk.Combobox(ctrl_frame, textvariable=self.preview_lang,
                               values=["SystemVerilog", "VHDL"], state="readonly", width=15)
        lang_cb.pack(side=tk.LEFT, padx=5)
        lang_cb.bind("<<ComboboxSelected>>", self.update_code_preview)

        tk.Button(ctrl_frame, text="Refresh", command=lambda: self.update_code_preview(None)).pack(side=tk.RIGHT,
                                                                                                   padx=5)

        # FIX 1.5: the preview is read-only. Text is inserted via
        # _set_preview_text, which temporarily re-enables the widget.
        self.txt_preview = tk.Text(self.preview_frame, bg="#fafafa", font=("Consolas", 10))
        self.txt_preview.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._set_preview_text("// Draw a state machine to see code here...")

    def _set_preview_text(self, text):
        """Replaces preview contents; keeps the widget read-only otherwise."""
        self.txt_preview.config(state=tk.NORMAL)
        self.txt_preview.delete("1.0", tk.END)
        self.txt_preview.insert("1.0", text)
        self.txt_preview.config(state=tk.DISABLED)

    # ==========================================
    # Modification & State Handling
    # ==========================================

    def mark_modified(self, modified=True):
        self.is_modified = modified
        title = self.app_name

        if self.current_filepath:
            title += f" - {os.path.basename(self.current_filepath)}"
        else:
            title += " - Untitled"

        if self.is_modified:
            title += "*"

        self.title(title)

    def prompt_save_if_needed(self):
        """Returns True if it's safe to proceed (Saved or Discarded). Returns False if Cancelled."""
        if not self.is_modified:
            return True

        response = messagebox.askyesnocancel("Unsaved Changes", "Do you want to save changes to the current project?")

        if response is None:  # Cancel
            return False

        if response:  # Yes
            return self.save_project()  # Returns True if saved, False if cancelled in dialog

        return True  # No (Discard changes)

    def on_diagram_changed(self, event):
        """Called whenever the canvas data changes."""
        self.mark_modified(True)
        self.update_code_preview(event)

    def on_closing(self):
        if self.prompt_save_if_needed():
            # FIX 5.3: destroy() tears the window down cleanly;
            # quit() only exits mainloop and can leave the window alive.
            self.destroy()

    # ==========================================
    # Logic Handlers
    # ==========================================

    def toggle_code_view(self):
        if self.var_show_code.get():
            self.paned_window.add(self.preview_frame, width=400, stretch="never")
            self.update_code_preview(None)
        else:
            self.paned_window.forget(self.preview_frame)

    def toggle_snap(self):
        self.canvas.snap_to_grid = self.var_snap.get()

    def change_grid_style(self, event):
        self.canvas.set_grid_style(self.cb_grid_style.get())

    def update_code_preview(self, event):
        if not self.var_show_code.get(): return
        if not self.canvas.nodes:
            self._set_preview_text("// No states defined.")
            return

        lang = self.preview_lang.get()
        if lang == "SystemVerilog":
            generator = SystemVerilogGenerator(self.project_settings, self.canvas.nodes, self.canvas.lines)
        else:
            generator = VHDLGenerator(self.project_settings, self.canvas.nodes, self.canvas.lines)

        try:
            self._set_preview_text(generator.generate())
        except Exception as e:
            self._set_preview_text(f"// Error generating preview:\n// {str(e)}")

    def set_tool(self, tool):
        self.canvas.set_tool(tool)
        self.lbl_status.config(text=f"Mode: {tool.name}")

    def toggle_details(self):
        self.canvas.toggle_details(self.var_show_details.get())

    def open_settings(self):
        # FIX 1.4: only mark modified if the user confirmed the dialog.
        dialog = ProjectSettingsDialog(self, self.project_settings)
        if getattr(dialog, "_was_confirmed", False):
            self.mark_modified(True)
            self.update_code_preview(None)

    def delete_selection(self):
        self.canvas.delete_selected()

    def undo(self):
        self.canvas.undo()

    def redo(self):
        self.canvas.redo()

    def generate_sv(self):
        self._generate_file("SystemVerilog", ".sv", SystemVerilogGenerator)

    def generate_vhdl(self):
        self._generate_file("VHDL", ".vhd", VHDLGenerator)

    def _generate_file(self, lang_name, ext, generator_cls):
        if not self.canvas.nodes:
            messagebox.showwarning("Generation Error", "No states defined.")
            return

        generator = generator_cls(self.project_settings, self.canvas.nodes, self.canvas.lines)
        try:
            code = generator.generate()
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        default_name = f"{self.project_settings.project_name}{ext}"
        file_path = filedialog.asksaveasfilename(defaultextension=ext, initialfile=default_name,
                                                 filetypes=[(f"{lang_name} Files", f"*{ext}"), ("All Files", "*.*")])
        if file_path:
            with open(file_path, "w") as f: f.write(code)
            messagebox.showinfo("Success", f"Saved to {file_path}")

    def export_image(self):
        """FIX 5.1 (rev 2): render the FULL diagram off-screen with Pillow
        from the data model - HiDPI-safe, no Ghostscript, no window
        overlap, not limited to the visible viewport. PNG or PDF."""
        if export_diagram is None:
            messagebox.showerror("Missing Library", "The 'Pillow' library is required.\nPlease run: pip install Pillow")
            return

        if not self.canvas.nodes:
            messagebox.showwarning("Export Error", "Canvas is empty.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            initialfile=self.project_settings.project_name,
            filetypes=[("PNG Image", "*.png"), ("PDF Document", "*.pdf")],
            title="Export Diagram")
        if not file_path: return

        try:
            export_diagram(file_path, self.canvas.nodes, self.canvas.lines,
                           show_details=self.var_show_details.get())
            messagebox.showinfo("Success", f"Exported to {file_path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    # ==========================================
    # Project File I/O
    # ==========================================

    def new_project(self):
        if not self.prompt_save_if_needed():
            return

        self.project_settings = ProjectSettings()
        self.canvas.clear_canvas()
        self.current_filepath = None
        self.mark_modified(False)
        self.update_code_preview(None)

    def save_project(self):
        if self.current_filepath:
            return self._perform_save(self.current_filepath)
        else:
            return self.save_project_as()

    def save_project_as(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("abVisualRTL Project", "*.json"), ("All Files", "*.*")],
            title="Save Project"
        )
        if file_path:
            return self._perform_save(file_path)
        return False

    def _perform_save(self, path):
        try:
            nodes, lines = self.canvas.save_data_snapshot()
            FileManager.save_project(path, self.project_settings, nodes, lines)

            self.current_filepath = path
            self.mark_modified(False)
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")
            return False

    def open_project(self):
        if not self.prompt_save_if_needed():
            return

        file_path = filedialog.askopenfilename(
            filetypes=[("abVisualRTL Project", "*.json"), ("All Files", "*.*")],
            title="Open Project"
        )
        if file_path:
            try:
                data = FileManager.load_project(file_path)
                self.project_settings = data["settings"]
                self.canvas.load_from_data(data["nodes"], data["lines"])

                self.current_filepath = file_path
                self.mark_modified(False)
                self.update_code_preview(None)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load:\n{e}")


if __name__ == "__main__":
    app = abVisualRTLApp()
    app.mainloop()
