import tkinter as tk
from tkinter import ttk


class BaseDialog(tk.Toplevel):
    def __init__(self, parent, title="Editor"):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.parent = parent
        self.result = None
        self._was_confirmed = False

        # Main content area
        self.body_frame = ttk.Frame(self, padding=10)
        self.body_frame.pack(fill=tk.BOTH, expand=True)

        # Create form widgets
        self.create_widgets()

        # Standard Buttons
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(btn_frame, text="OK", command=self.on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)

        # Center dialog relative to parent
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 50,
                                  parent.winfo_rooty() + 50))

        # Modal behavior setup
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window(self)

    def create_widgets(self):
        """Override this in subclasses."""
        pass

    def on_ok(self):
        if self.validate():
            self._was_confirmed = True
            self.apply()
            self.destroy()

    def validate(self):
        """Override to validate inputs. Return False to keep dialog open."""
        return True

    def apply(self):
        """Override to save data."""
        pass
    
