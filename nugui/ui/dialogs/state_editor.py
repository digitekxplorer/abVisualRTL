import tkinter as tk
from tkinter import ttk, messagebox
from nugui.ui.dialogs.base import BaseDialog
from nugui.models.elements import StateNode
from nugui.utils.hdl_validation import validate_identifier


class StateEditor(BaseDialog):
    def __init__(self, parent, node: StateNode, existing_names=None):
        self.node = node
        # FIX 2.4: names of all OTHER states, for duplicate checking
        self.existing_names = {n.lower() for n in (existing_names or [])}
        # Initialize variables with current data
        self.name_var = tk.StringVar(value=node.name)
        self.is_reset_var = tk.BooleanVar(value=node.is_reset_state)
        # Join actions list into a single string for the Text widget
        self.actions_str = "\n".join(node.actions)

        super().__init__(parent, title=f"Edit State: {node.name}")

    def create_widgets(self):
        # Name
        ttk.Label(self.body_frame, text="State Name:").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.body_frame, textvariable=self.name_var, width=25).grid(row=0, column=1, pady=5)

        # Reset State Checkbox
        ttk.Checkbutton(self.body_frame, text="Is Reset State",
                        variable=self.is_reset_var).grid(row=1, column=1, sticky="w", pady=5)

        # Moore Actions
        ttk.Label(self.body_frame, text="Moore Actions (one per line):").grid(row=2, column=0, columnspan=2, sticky="w",
                                                                              pady=(10, 0))
        self.txt_actions = tk.Text(self.body_frame, height=5, width=40)
        self.txt_actions.insert("1.0", self.actions_str)
        self.txt_actions.grid(row=3, column=0, columnspan=2, pady=5)

        # Help Text
        lbl_help = ttk.Label(self.body_frame, text="Example: led = 1 (SystemVerilog)  or  led <= '1' (VHDL)",
                             font=("Arial", 8), foreground="gray")
        lbl_help.grid(row=4, column=0, columnspan=2, sticky="w")

    def validate(self):
        new_name = self.name_var.get().strip()
        # FIX 2.3: enforce a legal SV+VHDL identifier
        err = validate_identifier(new_name, "State name")
        if err:
            messagebox.showerror("Error", err, parent=self)
            return False
        # FIX 2.4: reject duplicates (case-insensitive — VHDL folds case)
        if new_name.lower() in self.existing_names:
            messagebox.showerror("Error", f"A state named '{new_name}' already exists.", parent=self)
            return False
        return True

    def apply(self):
        # Update Data Model
        self.node.name = self.name_var.get().strip()
        self.node.is_reset_state = self.is_reset_var.get()

        # Parse text area back into list
        raw_text = self.txt_actions.get("1.0", tk.END).strip()
        if raw_text:
            self.node.actions = [line.strip() for line in raw_text.split('\n') if line.strip()]
        else:
            self.node.actions = []
