import tkinter as tk
from tkinter import ttk, messagebox
from nugui.ui.dialogs.base import BaseDialog
from nugui.models.project import ProjectSettings
from nugui.models.ports import Port, PortDirection
from nugui.utils.hdl_validation import validate_identifier


class ProjectSettingsDialog(BaseDialog):
    def __init__(self, parent, settings: ProjectSettings):
        self.settings = settings

        # Temporary storage for ports so we can Cancel changes
        self.temp_ports = [
            Port(p.name, p.direction, p.width, p.default_value)
            for p in settings.ports
        ]

        super().__init__(parent, title="Project Settings")

    def create_widgets(self):
        # Use Tabs for organization
        tab_control = ttk.Notebook(self.body_frame)

        self.tab_general = ttk.Frame(tab_control, padding=10)
        self.tab_ports = ttk.Frame(tab_control, padding=10)

        tab_control.add(self.tab_general, text="General")
        tab_control.add(self.tab_ports, text="Ports / Signals")
        tab_control.pack(expand=1, fill="both")

        self._build_general_tab()
        self._build_ports_tab()

    def _build_general_tab(self):
        # Module Name
        ttk.Label(self.tab_general, text="Module Name:").grid(row=0, column=0, sticky="w", pady=5)
        self.var_name = tk.StringVar(value=self.settings.project_name)
        ttk.Entry(self.tab_general, textvariable=self.var_name).grid(row=0, column=1, sticky="ew")

        # Clock
        ttk.Label(self.tab_general, text="Clock Name:").grid(row=1, column=0, sticky="w", pady=5)
        self.var_clk = tk.StringVar(value=self.settings.clock_name)
        ttk.Entry(self.tab_general, textvariable=self.var_clk).grid(row=1, column=1, sticky="ew")

        # Reset
        ttk.Label(self.tab_general, text="Reset Name:").grid(row=2, column=0, sticky="w", pady=5)
        self.var_rst = tk.StringVar(value=self.settings.reset_name)
        ttk.Entry(self.tab_general, textvariable=self.var_rst).grid(row=2, column=1, sticky="ew")

        # Reset Config
        self.var_sync = tk.BooleanVar(value=self.settings.is_synchronous_reset)
        self.var_act_low = tk.BooleanVar(value=self.settings.reset_active_low)

        ttk.Checkbutton(self.tab_general, text="Synchronous Reset", variable=self.var_sync).grid(row=3, column=1,
                                                                                                 sticky="w")
        ttk.Checkbutton(self.tab_general, text="Active Low Reset", variable=self.var_act_low).grid(row=4, column=1,
                                                                                                   sticky="w")

    def _build_ports_tab(self):
        # 1. Input Fields for new Port
        frm_input = ttk.LabelFrame(self.tab_ports, text="Add/Edit Port", padding=5)
        frm_input.pack(fill="x", pady=(0, 10))

        ttk.Label(frm_input, text="Name:").pack(side="left")
        self.var_p_name = tk.StringVar()
        ttk.Entry(frm_input, textvariable=self.var_p_name, width=10).pack(side="left", padx=5)

        ttk.Label(frm_input, text="Dir:").pack(side="left")
        self.var_p_dir = tk.StringVar(value="input")
        ttk.Combobox(frm_input, textvariable=self.var_p_dir,
                     values=["input", "output", "inout"], width=6).pack(side="left", padx=5)

        ttk.Label(frm_input, text="Width:").pack(side="left")
        self.var_p_width = tk.IntVar(value=1)
        ttk.Spinbox(frm_input, from_=1, to=128, textvariable=self.var_p_width, width=3).pack(side="left", padx=5)

        # FIX 5.5: default value used for latch prevention (outputs only)
        ttk.Label(frm_input, text="Default:").pack(side="left")
        self.var_p_default = tk.StringVar(value="0")
        ttk.Entry(frm_input, textvariable=self.var_p_default, width=6).pack(side="left", padx=5)

        ttk.Button(frm_input, text="Add", command=self.on_add_port).pack(side="left", padx=10)
        ttk.Button(frm_input, text="Remove Selected", command=self.on_remove_port).pack(side="right")

        # 2. Treeview (List)
        cols = ("Name", "Direction", "Width", "Default")
        self.tree = ttk.Treeview(self.tab_ports, columns=cols, show="headings", height=8)

        self.tree.heading("Name", text="Name")
        self.tree.heading("Direction", text="Direction")
        self.tree.heading("Width", text="Width")
        self.tree.heading("Default", text="Default")

        self.tree.column("Name", width=100)
        self.tree.column("Direction", width=60)
        self.tree.column("Width", width=50)
        self.tree.column("Default", width=60)

        self.tree.pack(fill="both", expand=True)
        self._refresh_port_list()

    def _refresh_port_list(self):
        # Clear existing
        for i in self.tree.get_children():
            self.tree.delete(i)
        # Populate from temp_ports
        for p in self.temp_ports:
            self.tree.insert("", "end", values=(p.name, p.direction.value, p.width, p.default_value))

    def on_add_port(self):
        name = self.var_p_name.get().strip()
        # FIX 2.3: enforce a legal SV+VHDL identifier
        err = validate_identifier(name, "Port name")
        if err:
            messagebox.showerror("Error", err, parent=self)
            return

        # FIX 2.4: duplicates (case-insensitive - VHDL folds case) and
        # collisions with the clock/reset names
        low = name.lower()
        if any(p.name.lower() == low for p in self.temp_ports):
            messagebox.showerror("Error", "Port name already exists", parent=self)
            return
        if low in (self.var_clk.get().strip().lower(), self.var_rst.get().strip().lower()):
            messagebox.showerror("Error", f"'{name}' collides with the clock/reset name", parent=self)
            return

        direction_map = {
            "input": PortDirection.IN,
            "output": PortDirection.OUT,
            "inout": PortDirection.INOUT
        }

        new_port = Port(
            name=name,
            direction=direction_map[self.var_p_dir.get()],
            width=self.var_p_width.get(),
            default_value=self.var_p_default.get().strip() or "0"  # FIX 5.5
        )
        self.temp_ports.append(new_port)
        self._refresh_port_list()

        # Clear input
        self.var_p_name.set("")
        self.var_p_default.set("0")

    def on_remove_port(self):
        selected = self.tree.selection()
        if not selected: return

        # Treeview returns Item ID, need to find index
        # Simple approach: rebuild list excluding selected
        item = self.tree.item(selected[0])
        name_to_del = item['values'][0]

        self.temp_ports = [p for p in self.temp_ports if p.name != name_to_del]
        self._refresh_port_list()

    def validate(self):
        # FIX 2.3: module, clock, and reset names must be legal identifiers
        for value, what in [(self.var_name.get(), "Module name"),
                            (self.var_clk.get(), "Clock name"),
                            (self.var_rst.get(), "Reset name")]:
            err = validate_identifier(value.strip(), what)
            if err:
                messagebox.showerror("Error", err, parent=self)
                return False
        return True

    def apply(self):
        # Commit general settings
        self.settings.project_name = self.var_name.get()
        self.settings.clock_name = self.var_clk.get()
        self.settings.reset_name = self.var_rst.get()
        self.settings.is_synchronous_reset = self.var_sync.get()
        self.settings.reset_active_low = self.var_act_low.get()

        # Commit ports
        self.settings.ports = self.temp_ports
