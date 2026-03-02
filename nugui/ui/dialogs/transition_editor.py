import tkinter as tk
from tkinter import ttk
from nugui.ui.dialogs.base import BaseDialog
from nugui.models.elements import TransitionLine


class TransitionEditor(BaseDialog):
    def __init__(self, parent, line: TransitionLine):
        self.line = line
        self.cond_var = tk.StringVar(value=line.condition)
        self.prio_var = tk.IntVar(value=line.priority)
        self.action_str = line.action

        super().__init__(parent, title="Edit Transition")

    def create_widgets(self):
        # Condition
        ttk.Label(self.body_frame, text="Condition (HDL):").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.body_frame, textvariable=self.cond_var, width=30).grid(row=0, column=1, pady=5)

        # Priority
        ttk.Label(self.body_frame, text="Priority (1=High):").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(self.body_frame, from_=1, to=99, textvariable=self.prio_var, width=5).grid(row=1, column=1,
                                                                                               sticky="w", pady=5)

        # Action (Mealy)
        ttk.Label(self.body_frame, text="Action (Mealy):").grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.txt_action = tk.Text(self.body_frame, height=4, width=40)
        self.txt_action.insert("1.0", self.action_str)
        self.txt_action.grid(row=3, column=0, columnspan=2, pady=5)

    def apply(self):
        self.line.condition = self.cond_var.get().strip()
        try:
            self.line.priority = self.prio_var.get()
        except tk.TclError:
            self.line.priority = 1  # Default fallback

        self.line.action = self.txt_action.get("1.0", tk.END).strip()
