import tkinter as tk
import math
from nugui.utils.constants import (
    ToolType, GRID_SIZE, BUBBLE_RADIUS,
    COLOR_BG, COLOR_GRID, COLOR_STATE_FILL, COLOR_STATE_OUTLINE,
    COLOR_LINE, COLOR_TEMP_LINE, COLOR_SELECTED, COLOR_ANNOTATION
)
from nugui.models.elements import StateNode, TransitionLine, TextAnnotation
from nugui.models.diagram import Diagram
from nugui.ui.dialogs.state_editor import StateEditor
from nugui.ui.dialogs.transition_editor import TransitionEditor
from nugui.ui.dialogs.text_editor import TextAnnotationEditor
from nugui.utils.history import CommandManager
from nugui.ui.commands import (
    AddStateCommand, AddTransitionCommand, AddAnnotationCommand, AddGroupCommand,
    DeleteCommand, MoveCommand, GroupMoveCommand, EditPropertyCommand
)


class GraphCanvas(tk.Canvas):
    def __init__(self, master, **kwargs):
        super().__init__(master, bg=COLOR_BG, **kwargs)

        # Application State
        self.current_tool = ToolType.SELECT
        # FIX 3.1: the data model lives in a GUI-free Diagram; the canvas
        # only renders and edits it. nodes/lines properties below keep the
        # existing call sites (commands, main.py) working unchanged.
        self.diagram = Diagram()
        self.selected_line = None
        self.selected_node = None
        self.selected_annotation = None  # FEATURE: text annotations
        # FEATURE: multi-select. The set is the source of truth; the three
        # singular fields above are kept in sync (anchor of each type) so the
        # existing drag/edit code that reads them keeps working.
        self.selected_items = []
        # FEATURE: rubber-band (marquee) selection state
        self._marquee_start = None   # (cx, cy) canvas coords while dragging
        self._marquee_rect = None    # live rubber-band canvas item id
        # FEATURE: group-move state
        self._group_anchor = None    # object whose snap drives the group
        self._group_initial = []     # [(item_type, obj, old_state)]
        # FEATURE: clipboard for group copy/paste (serialized snapshots)
        self._clipboard = None

        # View Settings
        self.show_details = False
        self.snap_to_grid = True
        self.grid_style = "Dots"
        self.zoom_scale = 1.0
        self.base_font_size = 10

        # Undo/Redo Manager
        self.history = CommandManager()

        # Interaction State
        self.drag_data = {
            "item": None, "type": None, "line_obj": None, "node_obj": None,
            "subtype": None, "x": 0, "y": 0,
            "start_node": None, "initial_state": None, "annot_obj": None
        }
        self.temp_line_id = None

        # Draw Background Grid
        self._draw_grid()
        self.update_scrollregion()

        # Event Bindings
        self.bind("<Button-1>", self.on_mouse_down)
        self.bind("<B1-Motion>", self.on_mouse_drag)
        self.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.bind("<Double-Button-1>", self.on_double_click)
        # Redraw the viewport-local dot grid when the widget resizes
        self.bind("<Configure>", lambda e: self._draw_grid())

    # ==========================================
    # Public API
    # ==========================================

    @property
    def nodes(self):
        return self.diagram.nodes

    @property
    def lines(self):
        return self.diagram.lines

    @property
    def annotations(self):
        return self.diagram.annotations

    def set_tool(self, tool: ToolType):
        self.current_tool = tool
        if tool != ToolType.SELECT:
            self._select_line(None)
            self._select_node(None)
            self._select_annotation(None)
            # Cancel any in-progress marquee when leaving the Select tool
            self._marquee_start = None
            self.delete("marquee")
            self._marquee_rect = None

    def toggle_details(self, show_details: bool):
        self.show_details = show_details
        state = tk.NORMAL if show_details else tk.HIDDEN
        self.itemconfig("details", state=state)

    def set_grid_style(self, style: str):
        self.grid_style = style
        self._draw_grid()

    def set_zoom(self, factor):
        """Sets zoom level and redraws the canvas."""
        # Clamp zoom
        if factor < 0.2: factor = 0.2
        if factor > 5.0: factor = 5.0

        self.zoom_scale = factor
        self.redraw_all()
        self.update_scrollregion()

    def redraw_all(self):
        """Clears and redraws everything based on current zoom."""
        self.delete("all")
        self._draw_grid()

        for node in self.nodes.values():
            self._draw_loaded_node(node)

        for line in self.lines:
            self._draw_loaded_line(line)

        for ann in self.annotations.values():
            self._draw_loaded_annotation(ann)

        self.toggle_details(self.show_details)

    def update_scrollregion(self):
        """Dynamically updates the scroll region based on content."""
        bbox = self.bbox("all")
        if bbox:
            # Add padding
            x1, y1, x2, y2 = bbox
            # Ensure we always start at 0,0 minimum
            x1 = min(0, x1 - 100)
            y1 = min(0, y1 - 100)
            x2 += 100
            y2 += 100
            self.configure(scrollregion=(x1, y1, x2, y2))
        else:
            # Default area if empty
            dim = 2000 * self.zoom_scale
            self.configure(scrollregion=(0, 0, dim, dim))

    def _notify_change(self):
        self.event_generate("<<DiagramChanged>>")

    # FIX 1.4: only notify (and dirty the project) when the stack
    # actually had something to undo/redo.
    def undo(self):
        if not self.history.undo_stack:
            return
        self.history.undo()
        self._notify_change()
        self.update_scrollregion()

    def redo(self):
        if not self.history.redo_stack:
            return
        self.history.redo()
        self._notify_change()
        self.update_scrollregion()

    def delete_selected(self):
        if not self.selected_items:
            return
        nodes_to_del = []
        lines_to_del = []
        annots_to_del = []
        for obj in self.selected_items:
            if isinstance(obj, StateNode):
                if obj not in nodes_to_del:
                    nodes_to_del.append(obj)
            elif isinstance(obj, TransitionLine):
                if obj not in lines_to_del:
                    lines_to_del.append(obj)
            elif isinstance(obj, TextAnnotation):
                annots_to_del.append(obj)

        # Cascade: any transition touching a deleted state must go too.
        for node in nodes_to_del:
            for line in self.diagram.lines_touching(node.id):
                if line not in lines_to_del:
                    lines_to_del.append(line)

        self._clear_selection()
        cmd = DeleteCommand(self, nodes_to_del, lines_to_del, annots_to_del)
        self.history.execute(cmd)
        self._notify_change()
        self.update_scrollregion()

    # ==========================================
    # Helper: Coordinate Scaling
    # ==========================================

    def _to_screen(self, val):
        return val * self.zoom_scale

    def _to_logic(self, val):
        if self.zoom_scale == 0: return 0
        return val / self.zoom_scale

    # ==========================================
    # Grid & Snapping
    # ==========================================

    def _draw_grid(self):
        self.delete("grid")
        if self.grid_style == "Hidden": return

        step = self._to_screen(GRID_SIZE)
        if step < 1: return  # Avoid infinite loops at extreme zoom-out

        # Determine grid size based on current scrollregion or default
        # We need a large enough grid to cover potential expansion
        w = 5000 * self.zoom_scale
        h = 5000 * self.zoom_scale

        if self.grid_style == "Lines":
            x = 0
            while x < w:
                self.create_line(x, 0, x, h, fill=COLOR_GRID, tags="grid")
                x += step
            y = 0
            while y < h:
                self.create_line(0, y, w, y, fill=COLOR_GRID, tags="grid")
                y += step

        elif self.grid_style == "Dots":
            # FIX 4.1 (rev 2): Windows ignores fine dash patterns, so draw
            # real dot items — but only inside the visible viewport
            # (a few thousand items max instead of ~62,500 for the whole
            # logical area). xview/yview overrides below redraw on scroll.
            vx0 = self.canvasx(0)
            vy0 = self.canvasy(0)
            vx1 = self.canvasx(self.winfo_width())
            vy1 = self.canvasy(self.winfo_height())
            x = max(0, math.floor(vx0 / step) * step)
            y_start = max(0, math.floor(vy0 / step) * step)
            x_end = min(w, vx1 + step)
            y_end = min(h, vy1 + step)
            while x < x_end:
                y = y_start
                while y < y_end:
                    self.create_line(x, y, x + 1, y, fill="#b0b0b0", tags="grid")
                    y += step
                x += step

        self.tag_lower("grid")

    # Scrollbars call xview/yview; redraw the viewport-local grid on scroll.
    def xview(self, *args):
        result = super().xview(*args)
        if args: self._draw_grid()
        return result

    def yview(self, *args):
        result = super().yview(*args)
        if args: self._draw_grid()
        return result

    def _snap(self, val):
        if not self.snap_to_grid: return val
        return round(val / GRID_SIZE) * GRID_SIZE

    # ==========================================
    # Persistence
    # ==========================================

    def clear_canvas(self):
        self.delete("all")
        self._draw_grid()
        self.diagram.clear()
        self.selected_line = None
        self.selected_node = None
        self.selected_annotation = None
        self.selected_items = []
        self.history = CommandManager()

    def save_data_snapshot(self):
        # Data is already stored in Logic Coordinates in self.nodes/self.lines
        # NOTE (3.4): returns live references, not copies.
        return self.nodes, self.lines, self.annotations

    def load_from_data(self, nodes: dict, lines: list, annotations: dict = None):
        self.clear_canvas()
        self.zoom_scale = 1.0  # Reset zoom

        # FIX 3.1: the Diagram owns the data and re-syncs the ID counters
        self.diagram.load(nodes, lines, annotations)
        for node in self.nodes.values():
            self._draw_loaded_node(node)
        for line in self.lines:
            self._draw_loaded_line(line)
        for ann in self.annotations.values():
            self._draw_loaded_annotation(ann)
        self.toggle_details(self.show_details)
        self.update_scrollregion()
        self._notify_change()

    def restore_node(self, node):
        self.diagram.add_node(node)
        self._draw_loaded_node(node)
        self.toggle_details(self.show_details)
        self.update_scrollregion()

    def restore_line(self, line):
        self.diagram.add_line(line)
        self._draw_loaded_line(line)
        self.toggle_details(self.show_details)

    # ---- FEATURE: text annotations ----
    def restore_annotation(self, ann):
        self.diagram.add_annotation(ann)
        self._draw_loaded_annotation(ann)
        self.update_scrollregion()

    def _remove_annotation(self, ann_id: int):
        ann = self.annotations.get(ann_id)
        if not ann:
            return
        self.delete(ann.canvas_item_id)
        self.diagram.remove_annotation(ann_id)
        if self.selected_annotation is ann:
            self.selected_annotation = None

    def _redraw_annotation(self, ann):
        """Delete and redraw an annotation in place (used by move undo/redo)."""
        self.delete(ann.canvas_item_id)
        self._draw_loaded_annotation(ann)
        if self.selected_annotation is ann:
            self.itemconfig(ann.canvas_item_id, fill=COLOR_SELECTED)

    def _remove_node(self, node_id: int):
        node = self.nodes.get(node_id)
        if not node: return
        self._remove_node_visuals(node)
        self.diagram.remove_node(node_id)

    def _remove_line(self, line: TransitionLine):
        self.delete(line.canvas_item_id)
        self.delete(line.handle_id)
        self.delete(line.text_item_id)
        self.diagram.remove_line(line)

    def _remove_node_visuals(self, node):
        self.delete(node.canvas_item_id)
        self.delete(node.text_item_id)
        self.delete(node.details_item_id)

    def refresh_visuals(self, obj):
        if isinstance(obj, StateNode):
            self.itemconfig(obj.text_item_id, text=obj.name)
            details_txt = "\n".join(obj.actions)
            self.itemconfig(obj.details_item_id, text=details_txt)
        elif isinstance(obj, TransitionLine):
            disp_text = f"[{obj.condition}]"
            if obj.action: disp_text += f" / {obj.action}"
            self.itemconfig(obj.text_item_id, text=disp_text)
        elif isinstance(obj, TextAnnotation):
            self.itemconfig(obj.canvas_item_id, text=obj.text,
                            font=self._annotation_font(obj),
                            justify=self._tk_justify(obj))

    # ==========================================
    # State Capture
    # ==========================================

    def _capture_node_state(self, node):
        return {
            'x': node.x, 'y': node.y,
            'name_offset_x': node.name_offset_x, 'name_offset_y': node.name_offset_y,
            'details_offset_x': node.details_offset_x, 'details_offset_y': node.details_offset_y
        }

    def _capture_line_state(self, line):
        return {'curvature': line.curvature, 'loop_angle': line.loop_angle}

    def _capture_text_state(self, obj):
        if isinstance(obj, TransitionLine):
            return {'text_offset_x': obj.text_offset_x, 'text_offset_y': obj.text_offset_y}
        return self._capture_node_state(obj)

    # ==========================================
    # Event Handlers
    # ==========================================

    def _get_canvas_coords(self, event):
        """Converts screen coordinates to canvas coordinates (accounting for scroll)."""
        return self.canvasx(event.x), self.canvasy(event.y)

    def on_mouse_down(self, event):
        cx, cy = self._get_canvas_coords(event)
        clicked_items = self.find_overlapping(cx - 2, cy - 2, cx + 2, cy + 2)

        # FEATURE: Shift-click toggles an object in the multi-selection (no
        # drag). Plain clicks fall through to single-select + drag as before.
        if self.current_tool == ToolType.SELECT and (event.state & 0x0001):
            obj = self._object_at(clicked_items)
            if obj is not None:
                self._toggle_selection(obj)
            return

        # FEATURE: group move — a plain press on a member of a multi-selection
        # drags the whole group. Press outside the group falls through and
        # collapses to normal single-select / marquee behavior.
        if self.current_tool == ToolType.SELECT and len(self.selected_items) > 1:
            obj = self._object_at(clicked_items)
            if obj in self.selected_items:
                self.drag_data["type"] = "group_move"
                self.drag_data["x"], self.drag_data["y"] = cx, cy
                self._group_initial = []
                for o in self.selected_items:
                    if isinstance(o, StateNode):
                        self._group_initial.append(("node", o, self._capture_node_state(o)))
                    elif isinstance(o, TextAnnotation):
                        self._group_initial.append(("annotation", o, {'x': o.x, 'y': o.y}))
                # Anchor drives grid-snap; if a transition was grabbed, snap to
                # the first movable member instead.
                self._group_anchor = obj if isinstance(obj, (StateNode, TextAnnotation)) else None
                if self._group_anchor is None:
                    self._group_anchor = next((o for (_, o, _s) in self._group_initial), None)
                return

        handle_line = self._get_line_from_handle(clicked_items)
        if handle_line:
            self.drag_data["type"] = "handle"
            self.drag_data["line_obj"] = handle_line
            self.drag_data["initial_state"] = self._capture_line_state(handle_line)
            self._select_line(handle_line)
            return

        # FEATURE: annotation drag (SELECT tool). Checked before generic text
        # items so a click on annotation text starts an annotation move.
        annot = self._get_annotation_from_items(clicked_items)
        if annot and self.current_tool == ToolType.SELECT:
            self.drag_data["type"] = "annotation"
            self.drag_data["item"] = annot.id
            self.drag_data["annot_obj"] = annot
            self.drag_data["x"], self.drag_data["y"] = cx, cy
            self.drag_data["initial_state"] = {'x': annot.x, 'y': annot.y}
            self._select_annotation(annot)
            return

        text_obj, text_type, text_item_id = self._get_object_from_text_item(clicked_items)
        if text_obj and self.current_tool == ToolType.SELECT:
            self.drag_data["type"] = "text"
            self.drag_data["subtype"] = text_type
            self.drag_data["item"] = text_item_id
            self.drag_data["node_obj"] = text_obj if isinstance(text_obj, StateNode) else None
            self.drag_data["line_obj"] = text_obj if isinstance(text_obj, TransitionLine) else None
            self.drag_data["x"], self.drag_data["y"] = cx, cy

            if isinstance(text_obj, TransitionLine):
                self.drag_data["initial_state"] = self._capture_text_state(text_obj)
                self._select_line(text_obj)
            elif isinstance(text_obj, StateNode):
                self.drag_data["initial_state"] = self._capture_node_state(text_obj)
                self._select_node(text_obj)
            return

        clicked_node_id = self._get_node_id_from_items(clicked_items)

        if self.current_tool == ToolType.STATE:
            lx, ly = self._to_logic(cx), self._to_logic(cy)
            sx, sy = self._snap(lx), self._snap(ly)
            if clicked_node_id is None:
                self.create_state(sx, sy)

        elif self.current_tool == ToolType.TEXT:
            # FEATURE: drop a new text annotation at the clicked point
            lx, ly = self._to_logic(cx), self._to_logic(cy)
            sx, sy = self._snap(lx), self._snap(ly)
            self.create_annotation(sx, sy)

        elif self.current_tool == ToolType.SELECT:
            if clicked_node_id is not None:
                self.drag_data["type"] = "node"
                self.drag_data["item"] = clicked_node_id
                self.drag_data["x"], self.drag_data["y"] = cx, cy

                node = self.nodes[clicked_node_id]
                self.drag_data["initial_state"] = self._capture_node_state(node)
                self._select_annotation(None)
                self._select_node(node)
            else:
                line_clicked = self._get_line_from_items(clicked_items)
                if line_clicked:
                    self._select_annotation(None)
                    self._select_line(line_clicked)
                else:
                    self._select_node(None)
                    self._select_line(None)
                    self._select_annotation(None)
                    # FEATURE: begin a rubber-band marquee (group select)
                    self.drag_data["type"] = "marquee"
                    self._marquee_start = (cx, cy)
                    if self._marquee_rect is not None:
                        self.delete(self._marquee_rect)
                        self._marquee_rect = None

        elif self.current_tool == ToolType.LINE:
            if clicked_node_id is not None:
                self.drag_data["start_node"] = clicked_node_id
                node = self.nodes[clicked_node_id]
                nx, ny = self._to_screen(node.x), self._to_screen(node.y)
                self.temp_line_id = self.create_line(
                    nx, ny, cx, cy, fill=COLOR_TEMP_LINE, dash=(4, 2)
                )

    def on_mouse_drag(self, event):
        cx, cy = self._get_canvas_coords(event)
        dx = cx - self.drag_data["x"]
        dy = cy - self.drag_data["y"]

        ldx = self._to_logic(dx)
        ldy = self._to_logic(dy)

        if self.drag_data["type"] == "marquee":
            x0, y0 = self._marquee_start
            self._update_marquee(x0, y0, cx, cy)
            return

        if self.drag_data["type"] == "group_move":
            self._drag_group_move(cx, cy)
            return

        if self.drag_data["type"] == "text":
            text_id = self.drag_data["item"]
            subtype = self.drag_data["subtype"]
            self.move(text_id, dx, dy)
            if subtype == 'name':
                node = self.drag_data["node_obj"]
                node.name_offset_x += ldx
                node.name_offset_y += ldy
            elif subtype == 'details':
                node = self.drag_data["node_obj"]
                node.details_offset_x += ldx
                node.details_offset_y += ldy
            elif subtype == 'trans':
                line = self.drag_data["line_obj"]
                line.text_offset_x += ldx
                line.text_offset_y += ldy
            self.drag_data["x"], self.drag_data["y"] = cx, cy

        elif self.drag_data["type"] == "annotation":
            ann = self.drag_data["annot_obj"]
            raw_lx = ann.x + ldx
            raw_ly = ann.y + ldy
            snapped_lx = self._snap(raw_lx)
            snapped_ly = self._snap(raw_ly)
            apply_ldx = snapped_lx - ann.x
            apply_ldy = snapped_ly - ann.y
            if apply_ldx != 0 or apply_ldy != 0:
                ann.x = snapped_lx
                ann.y = snapped_ly
                sdx = self._to_screen(apply_ldx)
                sdy = self._to_screen(apply_ldy)
                self.move(ann.canvas_item_id, sdx, sdy)
                self.drag_data["x"] += sdx
                self.drag_data["y"] += sdy
                self.update_scrollregion()

        elif self.drag_data["type"] == "handle":
            line = self.drag_data["line_obj"]
            if line.start_state_id == line.end_state_id:
                node = self.nodes[line.start_state_id]
                nx, ny = self._to_screen(node.x), self._to_screen(node.y)
                dx_l, dy_l = cx - nx, cy - ny
                line.loop_angle = math.atan2(dy_l, dx_l)
                dist_screen = math.sqrt(dx_l ** 2 + dy_l ** 2)
                line.curvature = max(20, (dist_screen / self.zoom_scale) - BUBBLE_RADIUS)
            else:
                n1, n2 = self.nodes[line.start_state_id], self.nodes[line.end_state_id]
                sn1x, sn1y = self._to_screen(n1.x), self._to_screen(n1.y)
                sn2x, sn2y = self._to_screen(n2.x), self._to_screen(n2.y)
                screen_curv = self.calculate_curvature_from_mouse(
                    sn1x, sn1y, sn2x, sn2y, cx, cy)
                line.curvature = self._to_logic(screen_curv)
            self._update_specific_line(line)

        elif self.drag_data["type"] == "node" and self.drag_data["item"] is not None:
            node = self.nodes[self.drag_data["item"]]
            raw_target_lx = node.x + ldx
            raw_target_ly = node.y + ldy
            snapped_lx = self._snap(raw_target_lx)
            snapped_ly = self._snap(raw_target_ly)

            apply_ldx = snapped_lx - node.x
            apply_ldy = snapped_ly - node.y

            if apply_ldx != 0 or apply_ldy != 0:
                node.x = snapped_lx
                node.y = snapped_ly

                sdx = self._to_screen(apply_ldx)
                sdy = self._to_screen(apply_ldy)

                self.move(node.canvas_item_id, sdx, sdy)
                self.move(node.text_item_id, sdx, sdy)
                self.move(node.details_item_id, sdx, sdy)
                self._update_lines_for_node(self.drag_data["item"])

                self.drag_data["x"] += sdx
                self.drag_data["y"] += sdy

                self.update_scrollregion()

        elif self.current_tool == ToolType.LINE and self.temp_line_id:
            start_node = self.nodes[self.drag_data["start_node"]]
            sx, sy = self._to_screen(start_node.x), self._to_screen(start_node.y)
            self.coords(self.temp_line_id, sx, sy, cx, cy)

    def on_mouse_up(self, event):
        cx, cy = self._get_canvas_coords(event)
        did_something = False

        # FEATURE: finish a rubber-band marquee selection
        if self.drag_data["type"] == "marquee":
            self._finish_marquee(cx, cy)
            self.drag_data = {
                "item": None, "type": None, "line_obj": None, "node_obj": None, "subtype": None,
                "x": 0, "y": 0, "start_node": None, "initial_state": None, "annot_obj": None
            }
            return

        # FEATURE: finish a group move
        if self.drag_data["type"] == "group_move":
            self._finish_group_move()
            self.drag_data = {
                "item": None, "type": None, "line_obj": None, "node_obj": None, "subtype": None,
                "x": 0, "y": 0, "start_node": None, "initial_state": None, "annot_obj": None
            }
            return

        if self.drag_data["initial_state"]:
            item_type = self.drag_data["type"]
            current_state = None
            obj = None
            cmd_type = None

            if item_type == "node":
                obj = self.nodes[self.drag_data["item"]]
                current_state = self._capture_node_state(obj)
                cmd_type = "node"
            elif item_type == "handle":
                obj = self.drag_data["line_obj"]
                current_state = self._capture_line_state(obj)
                cmd_type = "handle"
            elif item_type == "text":
                if self.drag_data["line_obj"]:
                    obj = self.drag_data["line_obj"]
                    current_state = self._capture_text_state(obj)
                    cmd_type = "text_trans"
                else:
                    obj = self.drag_data["node_obj"]
                    current_state = self._capture_node_state(obj)
                    cmd_type = "node"
            elif item_type == "annotation":
                obj = self.drag_data["annot_obj"]
                current_state = {'x': obj.x, 'y': obj.y}
                cmd_type = "annotation"

            if current_state and current_state != self.drag_data["initial_state"]:
                cmd = MoveCommand(self, cmd_type, obj, self.drag_data["initial_state"], current_state)
                self.history.execute(cmd)
                did_something = True

        if self.current_tool == ToolType.LINE and self.temp_line_id:
            released_items = self.find_overlapping(cx - 1, cy - 1, cx + 1, cy + 1)
            target_id = self._get_node_id_from_items(released_items)

            if target_id is not None:
                self.create_transition(self.drag_data["start_node"], target_id)

            self.delete(self.temp_line_id)
            self.temp_line_id = None

        self.drag_data = {
            "item": None, "type": None, "line_obj": None, "node_obj": None, "subtype": None,
            "x": 0, "y": 0, "start_node": None, "initial_state": None, "annot_obj": None
        }

        if did_something:
            self._notify_change()
            self.update_scrollregion()

    def on_double_click(self, event):
        cx, cy = self._get_canvas_coords(event)
        clicked_items = self.find_overlapping(cx - 2, cy - 2, cx + 2, cy + 2)

        # FEATURE: edit a text annotation on double-click
        annot = self._get_annotation_from_items(clicked_items)
        if annot:
            fields = ('text', 'font_family', 'font_size', 'bold', 'italic', 'align')
            old_data = {k: getattr(annot, k) for k in fields}
            editor = TextAnnotationEditor(self.winfo_toplevel(), annot)
            if editor._was_confirmed:
                new_data = {k: getattr(annot, k) for k in fields}
                self.refresh_visuals(annot)
                cmd = EditPropertyCommand(self, annot, old_data, new_data)
                self.history.execute(cmd)
                self._notify_change()
            return

        node_id = self._get_node_id_from_items(clicked_items)
        if node_id is None:
            obj, _, _ = self._get_object_from_text_item(clicked_items)
            if isinstance(obj, StateNode): node_id = obj.id

        if node_id is not None:
            node = self.nodes[node_id]
            old_data = {'name': node.name, 'is_reset_state': node.is_reset_state, 'actions': node.actions[:]}

            other_names = [n.name for n in self.nodes.values() if n.id != node.id]
            editor = StateEditor(self.winfo_toplevel(), node, existing_names=other_names)
            if editor._was_confirmed:
                # FIX 1.6: at most one reset state. If this node was just
                # made the reset state, clear the flag on every other node.
                if node.is_reset_state:
                    # FIX 1.6 via Diagram (3.1): exactly one reset state
                    self.diagram.set_reset_state(node.id)
                new_data = {'name': node.name, 'is_reset_state': node.is_reset_state, 'actions': node.actions[:]}
                self.itemconfig(node.text_item_id, text=node.name)
                details_txt = "\n".join(node.actions)
                self.itemconfig(node.details_item_id, text=details_txt)

                cmd = EditPropertyCommand(self, node, old_data, new_data)
                self.history.execute(cmd)
                self._notify_change()
            return

        line = self._get_line_from_items(clicked_items)
        if not line: line = self._get_line_from_handle(clicked_items)
        if not line:
            obj, _, _ = self._get_object_from_text_item(clicked_items)
            if isinstance(obj, TransitionLine): line = obj

        if line:
            old_data = {'condition': line.condition, 'priority': line.priority, 'action': line.action}
            editor = TransitionEditor(self.winfo_toplevel(), line)
            if editor._was_confirmed:
                disp_text = f"[{line.condition}]"
                if line.action: disp_text += f" / {line.action}"
                self.itemconfig(line.text_item_id, text=disp_text)

                new_data = {'condition': line.condition, 'priority': line.priority, 'action': line.action}
                cmd = EditPropertyCommand(self, line, old_data, new_data)
                self.history.execute(cmd)
                self._notify_change()
            return

    # ==========================================
    # Creation Methods
    # ==========================================

    def create_state(self, x, y):
        # FIX 3.1: the Diagram allocates the id/name and reset flag
        new_node = self.diagram.new_state(x, y)
        # Offsets are logic distances
        new_node.details_offset_x = BUBBLE_RADIUS + 5
        new_node.details_offset_y = -BUBBLE_RADIUS

        cmd = AddStateCommand(self, new_node)
        self.history.execute(cmd)
        self._notify_change()
        self.update_scrollregion()

    def create_transition(self, start_id, end_id):
        is_loop = (start_id == end_id)
        # FIX 3.1: the Diagram allocates the id
        new_transition = self.diagram.new_transition(
            start_id, end_id,
            curvature=50 if is_loop else -40,  # Logic units
            loop_angle=-math.pi / 2 if is_loop else 0,
            text_offset_y=-15.0  # Logic unit offset
        )

        cmd = AddTransitionCommand(self, new_transition)
        self.history.execute(cmd)
        self._select_line(new_transition)
        self._notify_change()

    def create_annotation(self, x, y):
        """FEATURE: create a text annotation. Prompts for the text first;
        if the user cancels or leaves it empty, nothing is added."""
        new_ann = self.diagram.new_annotation(x, y, color=COLOR_ANNOTATION)
        editor = TextAnnotationEditor(self.winfo_toplevel(), new_ann)
        if not editor._was_confirmed:
            # Roll back the id counter so ids stay contiguous
            self.diagram.annotation_counter -= 1
            return
        cmd = AddAnnotationCommand(self, new_ann)
        self.history.execute(cmd)
        # Do NOT keep it selected: the red selection highlight looks like a
        # font color. Leave it drawn in its real (black) color.
        self._notify_change()
        self.update_scrollregion()

    # ==========================================
    # Drawing (UPDATED FOR ZOOM)
    # ==========================================

    def _draw_loaded_node(self, node):
        r = self._to_screen(BUBBLE_RADIUS)
        sx, sy = self._to_screen(node.x), self._to_screen(node.y)

        node.canvas_item_id = self.create_oval(
            sx - r, sy - r, sx + r, sy + r,
            fill=COLOR_STATE_FILL, outline=COLOR_STATE_OUTLINE,
            width=2, tags=(f"node_{node.id}", "state")
        )

        font_size = int(self.base_font_size * self.zoom_scale)
        font_spec = f"Arial {max(1, font_size)}"

        soff_x = self._to_screen(node.name_offset_x)
        soff_y = self._to_screen(node.name_offset_y)

        node.text_item_id = self.create_text(
            sx + soff_x, sy + soff_y,
            text=node.name, tags=(f"node_{node.id}", "state_text"),
            font=font_spec
        )

        doff_x = self._to_screen(node.details_offset_x)
        doff_y = self._to_screen(node.details_offset_y)

        details_txt = "\n".join(node.actions)
        node.details_item_id = self.create_text(
            sx + doff_x, sy + doff_y,
            text=details_txt, anchor="nw", fill="blue",
            font=f"Arial {max(1, int(8 * self.zoom_scale))}",
            state=tk.NORMAL if self.show_details else tk.HIDDEN,
            tags=(f"node_{node.id}", "details")
        )

    def _draw_loaded_annotation(self, ann):
        """FEATURE: render a free-floating text annotation (logic coords,
        centered on its point, scaled with zoom, with font style/align)."""
        sx, sy = self._to_screen(ann.x), self._to_screen(ann.y)
        ann.canvas_item_id = self.create_text(
            sx, sy, text=ann.text, fill=ann.color, anchor="center",
            font=self._annotation_font(ann), justify=self._tk_justify(ann),
            tags=(f"annot_{ann.id}", "annotation")
        )

    def _annotation_font(self, ann):
        """Build a Tk font tuple honoring family, size (zoomed), bold, italic."""
        size = max(1, int(ann.font_size * self.zoom_scale))
        styles = []
        if getattr(ann, "bold", False): styles.append("bold")
        if getattr(ann, "italic", False): styles.append("italic")
        family = getattr(ann, "font_family", "Arial")
        return (family, size, " ".join(styles)) if styles else (family, size)

    @staticmethod
    def _tk_justify(ann):
        return {"left": "left", "center": "center", "right": "right"}.get(
            getattr(ann, "align", "left"), "left")

    def _draw_loaded_line(self, line):
        line.canvas_item_id = self.create_line(0, 0, 0, 0, fill=COLOR_LINE, width=2, arrow=tk.LAST, smooth=True,
                                               splinesteps=36)
        line.handle_id = self.create_oval(0, 0, 0, 0, fill="white", outline=COLOR_LINE, tags=("handle",),
                                          state=tk.HIDDEN)

        lbl_tag = f"line_{line.id}"
        disp_text = f"[{line.condition}]"
        if line.action: disp_text += f" / {line.action}"

        font_size = int(8 * self.zoom_scale)
        line.text_item_id = self.create_text(
            0, 0, text=disp_text, fill="blue",
            font=f"Arial {max(1, font_size)}",
            state=tk.HIDDEN, tags=("trans_text", "details", lbl_tag)
        )
        self._update_specific_line(line)

    def _update_specific_line(self, line):
        hx, hy = 0, 0
        if line.start_state_id == line.end_state_id:
            node = self.nodes[line.start_state_id]
            pts, hx, hy = self._get_self_loop_points(node, line.curvature, line.loop_angle)
            self.coords(line.canvas_item_id, pts)
        else:
            n1, n2 = self.nodes[line.start_state_id], self.nodes[line.end_state_id]
            sn1x, sn1y = self._to_screen(n1.x), self._to_screen(n1.y)
            sn2x, sn2y = self._to_screen(n2.x), self._to_screen(n2.y)
            scurv = self._to_screen(line.curvature)

            cp_x, cp_y = self.get_arc_control_point(sn1x, sn1y, sn2x, sn2y, scurv)
            p1x, p1y = self._edge_point_screen(sn1x, sn1y, cp_x, cp_y)
            p2x, p2y = self._edge_point_screen(sn2x, sn2y, cp_x, cp_y)
            self.coords(line.canvas_item_id, [p1x, p1y, cp_x, cp_y, p2x, p2y])
            hx, hy = cp_x, cp_y

        r = 4
        self.coords(line.handle_id, hx - r, hy - r, hx + r, hy + r)

        toff_x = self._to_screen(line.text_offset_x)
        toff_y = self._to_screen(line.text_offset_y)
        self.coords(line.text_item_id, hx + toff_x, hy + toff_y)

    # FIX 1.1: this method was defined twice; the duplicate at the end
    # of the file has been removed.
    def _update_lines_for_node(self, node_id):
        for line in self.diagram.lines_touching(node_id):
            self._update_specific_line(line)

    # --- Math & Lookup Helpers ---
    def _get_node_id_from_items(self, items):
        for item in items:
            tags = self.gettags(item)
            for tag in tags:
                if tag.startswith("node_"): return int(tag.split("_")[1])
        return None

    def _get_line_from_items(self, items):
        for item in items:
            for line in self.lines:
                if line.canvas_item_id == item: return line
        return None

    def _get_line_from_handle(self, items):
        for item in items:
            for line in self.lines:
                if hasattr(line, 'handle_id') and line.handle_id == item: return line
        return None

    def _get_object_from_text_item(self, items):
        for item in items:
            tags = self.gettags(item)
            if "state_text" in tags:
                node_id = self._get_id_from_tags(tags, "node_")
                if node_id is not None: return self.nodes[node_id], "name", item
            if "details" in tags and any(t.startswith("node_") for t in tags):
                node_id = self._get_id_from_tags(tags, "node_")
                if node_id is not None: return self.nodes[node_id], "details", item
            if "trans_text" in tags:
                line_id = self._get_id_from_tags(tags, "line_")
                if line_id is not None:
                    for line in self.lines:
                        if line.id == line_id: return line, "trans", item
        return None, None, None

    def _get_annotation_from_items(self, items):
        for item in items:
            tags = self.gettags(item)
            if "annotation" in tags:
                ann_id = self._get_id_from_tags(tags, "annot_")
                if ann_id is not None and ann_id in self.annotations:
                    return self.annotations[ann_id]
        return None

    def _get_id_from_tags(self, tags, prefix):
        for tag in tags:
            if tag.startswith(prefix): return int(tag.split("_")[1])
        return None

    def _select_line(self, line_obj):
        self._select_single(line_obj)

    def _select_node(self, node_obj):
        self._select_single(node_obj)

    def _select_annotation(self, ann):
        self._select_single(ann)

    # ---- FEATURE: unified selection model (single + multi) ----
    def _apply_highlight(self, obj, on):
        """Show/hide the red selection highlight for any object type."""
        if isinstance(obj, StateNode):
            if obj.id in self.nodes:
                self.itemconfig(obj.canvas_item_id,
                                outline=COLOR_SELECTED if on else COLOR_STATE_OUTLINE)
        elif isinstance(obj, TransitionLine):
            if on:
                self.itemconfig(obj.handle_id, state=tk.NORMAL,
                                fill=COLOR_SELECTED, outline=COLOR_SELECTED)
            else:
                self.itemconfig(obj.handle_id, state=tk.HIDDEN,
                                fill="white", outline=COLOR_LINE)
        elif isinstance(obj, TextAnnotation):
            if obj.id in self.annotations:
                self.itemconfig(obj.canvas_item_id,
                                fill=COLOR_SELECTED if on else obj.color)

    def _sync_singular(self):
        """Keep the legacy singular fields pointing at the anchor of each type
        so existing drag/edit code (which reads them) still works."""
        self.selected_node = next((o for o in self.selected_items
                                   if isinstance(o, StateNode)), None)
        self.selected_line = next((o for o in self.selected_items
                                   if isinstance(o, TransitionLine)), None)
        self.selected_annotation = next((o for o in self.selected_items
                                         if isinstance(o, TextAnnotation)), None)

    def _clear_selection(self):
        for o in self.selected_items:
            self._apply_highlight(o, False)
        self.selected_items = []
        self.selected_node = None
        self.selected_line = None
        self.selected_annotation = None

    def _select_single(self, obj):
        """Replace the whole selection with just `obj` (or clear if None)."""
        self._clear_selection()
        if obj is not None:
            self.selected_items = [obj]
            self._apply_highlight(obj, True)
            self._sync_singular()

    def _toggle_selection(self, obj):
        """Add/remove `obj` from the multi-selection (Shift-click)."""
        if obj in self.selected_items:
            self.selected_items.remove(obj)
            self._apply_highlight(obj, False)
        else:
            self.selected_items.append(obj)
            self._apply_highlight(obj, True)
        self._sync_singular()

    def _object_at(self, items):
        """Topmost selectable object under a click (annotation > line handle >
        node > line body > text label), or None."""
        annot = self._get_annotation_from_items(items)
        if annot:
            return annot
        line = self._get_line_from_handle(items)
        if line:
            return line
        nid = self._get_node_id_from_items(items)
        if nid is not None:
            return self.nodes[nid]
        line = self._get_line_from_items(items)
        if line:
            return line
        obj, _, _ = self._get_object_from_text_item(items)
        return obj

    # ---- FEATURE: rubber-band (marquee) selection ----
    def _update_marquee(self, x0, y0, x, y):
        """Draw/refresh the dashed green rubber-band rectangle."""
        if self._marquee_rect is not None:
            self.delete(self._marquee_rect)
        self._marquee_rect = self.create_rectangle(
            x0, y0, x, y, outline="#2e8b57", dash=(4, 3), width=1,
            fill="", tags="marquee")

    def _finish_marquee(self, x, y):
        """Select every object the marquee box touches (overlap semantics)."""
        if self._marquee_start is None:
            return
        x0, y0 = self._marquee_start
        self._marquee_start = None
        if self._marquee_rect is not None:
            self.delete(self._marquee_rect)
            self._marquee_rect = None
        self.delete("marquee")

        rx1, ry1 = min(x0, x), min(y0, y)
        rx2, ry2 = max(x0, x), max(y0, y)
        # A tiny box is really a click on empty space: clear the selection.
        if (rx2 - rx1) < 3 and (ry2 - ry1) < 3:
            self._clear_selection()
            return

        objs = self._objects_in_rect(rx1, ry1, rx2, ry2)
        self._clear_selection()
        for o in objs:
            self.selected_items.append(o)
            self._apply_highlight(o, True)
        self._sync_singular()

    def _objects_in_rect(self, rx1, ry1, rx2, ry2):
        """All nodes/lines/annotations whose canvas items overlap the rect."""
        items = self.find_overlapping(rx1, ry1, rx2, ry2)
        result = []
        node_ids, line_ids, ann_ids = set(), set(), set()
        for item in items:
            tags = self.gettags(item)
            if "grid" in tags:
                continue
            nid = self._get_id_from_tags(tags, "node_")
            if nid is not None and nid in self.nodes:
                if nid not in node_ids:
                    node_ids.add(nid)
                    result.append(self.nodes[nid])
                continue
            if "annotation" in tags:
                aid = self._get_id_from_tags(tags, "annot_")
                if aid is not None and aid in self.annotations and aid not in ann_ids:
                    ann_ids.add(aid)
                    result.append(self.annotations[aid])
                continue
            for line in self.lines:
                if line.id in line_ids:
                    continue
                if item in (line.canvas_item_id, line.text_item_id):
                    line_ids.add(line.id)
                    result.append(line)
                    break
        return result

    # ---- FEATURE: group move ----
    def _drag_group_move(self, cx, cy):
        anchor = self._group_anchor
        if anchor is None:
            return
        ldx = self._to_logic(cx - self.drag_data["x"])
        ldy = self._to_logic(cy - self.drag_data["y"])
        # Snap the anchor to grid; apply the SAME delta to every member so the
        # group keeps its relative spacing.
        apply_ldx = self._snap(anchor.x + ldx) - anchor.x
        apply_ldy = self._snap(anchor.y + ldy) - anchor.y
        if apply_ldx == 0 and apply_ldy == 0:
            return
        sdx = self._to_screen(apply_ldx)
        sdy = self._to_screen(apply_ldy)
        for (t, o, _old) in self._group_initial:
            o.x += apply_ldx
            o.y += apply_ldy
            self.move(o.canvas_item_id, sdx, sdy)
            if t == "node":
                self.move(o.text_item_id, sdx, sdy)
                self.move(o.details_item_id, sdx, sdy)
        for nid in {o.id for (t, o, _o) in self._group_initial if t == "node"}:
            self._update_lines_for_node(nid)
        self.drag_data["x"] += sdx
        self.drag_data["y"] += sdy
        self.update_scrollregion()

    def _finish_group_move(self):
        moves = []
        changed = False
        for (t, o, old) in self._group_initial:
            new = self._capture_node_state(o) if t == "node" else {'x': o.x, 'y': o.y}
            if new != old:
                changed = True
            moves.append(MoveCommand(self, t, o, old, new))
        self._group_initial = []
        self._group_anchor = None
        if changed and moves:
            cmd = GroupMoveCommand(moves)
            self.history.execute(cmd)
            # Node redraws in MoveCommand reset outlines; restore highlights.
            self._reapply_selection_highlight()
            self._notify_change()
            self.update_scrollregion()

    def _reapply_selection_highlight(self):
        for o in self.selected_items:
            self._apply_highlight(o, True)

    # ---- FEATURE: group copy / paste ----
    def copy_selection(self):
        """Snapshot the current selection to the clipboard. Transitions whose
        BOTH endpoints are among the copied states come along automatically
        (a sub-machine duplicates coherently); dangling transitions are
        dropped since they can't be rewired."""
        nodes = [o for o in self.selected_items if isinstance(o, StateNode)]
        anns = [o for o in self.selected_items if isinstance(o, TextAnnotation)]
        node_ids = {n.id for n in nodes}
        lines = [l for l in self.lines
                 if l.start_state_id in node_ids and l.end_state_id in node_ids]
        if not nodes and not anns:
            return
        self._clipboard = {
            "nodes": [n.to_dict() for n in nodes],
            "lines": [l.to_dict() for l in lines],
            "annotations": [a.to_dict() for a in anns],
        }

    def paste_clipboard(self):
        if not self._clipboard:
            return
        off = GRID_SIZE * 2
        existing = {n.name.lower() for n in self.nodes.values()}

        id_map = {}
        new_nodes = []
        for nd in self._clipboard["nodes"]:
            node = StateNode.from_dict(nd)
            old_id = node.id
            node.id = self.diagram.node_counter
            self.diagram.node_counter += 1
            id_map[old_id] = node.id
            node.x += off
            node.y += off
            node.is_reset_state = False  # never introduce a 2nd reset state
            node.name = self._unique_state_name(node.name, existing)
            existing.add(node.name.lower())
            node.canvas_item_id = node.text_item_id = node.details_item_id = None
            new_nodes.append(node)

        new_lines = []
        for ld in self._clipboard["lines"]:
            line = TransitionLine.from_dict(ld)
            if line.start_state_id not in id_map or line.end_state_id not in id_map:
                continue
            line.id = self.diagram.line_counter
            self.diagram.line_counter += 1
            line.start_state_id = id_map[line.start_state_id]
            line.end_state_id = id_map[line.end_state_id]
            line.canvas_item_id = line.handle_id = line.text_item_id = None
            new_lines.append(line)

        new_anns = []
        for ad in self._clipboard["annotations"]:
            ann = TextAnnotation.from_dict(ad)
            ann.id = self.diagram.annotation_counter
            self.diagram.annotation_counter += 1
            ann.x += off
            ann.y += off
            ann.canvas_item_id = None
            new_anns.append(ann)

        if not (new_nodes or new_anns):
            return
        cmd = AddGroupCommand(self, new_nodes, new_lines, new_anns)
        self.history.execute(cmd)

        # Select the freshly pasted group so it can be moved/deleted at once
        self._clear_selection()
        self.selected_items = list(new_nodes) + list(new_lines) + list(new_anns)
        for o in self.selected_items:
            self._apply_highlight(o, True)
        self._sync_singular()
        self._notify_change()
        self.update_scrollregion()

    def _unique_state_name(self, base, existing_lower):
        cand = f"{base}_copy"
        i = 2
        while cand.lower() in existing_lower:
            cand = f"{base}_copy{i}"
            i += 1
        return cand

    # --- Math Helpers (Scalable) ---
    def _get_self_loop_points(self, node, loop_size, loop_angle):
        # Scale to Screen
        nx, ny = self._to_screen(node.x), self._to_screen(node.y)
        r = self._to_screen(BUBBLE_RADIUS)
        ls = self._to_screen(loop_size)

        spread = math.radians(40)
        exit_a = loop_angle - spread
        entry_a = loop_angle + spread
        p1x = nx + math.cos(exit_a) * r
        p1y = ny + math.sin(exit_a) * r
        p2x = nx + math.cos(entry_a) * r
        p2y = ny + math.sin(entry_a) * r
        cp1x = nx + math.cos(exit_a) * (r + ls)
        cp1y = ny + math.sin(exit_a) * (r + ls)
        cp2x = nx + math.cos(entry_a) * (r + ls)
        cp2y = ny + math.sin(entry_a) * (r + ls)
        hx = nx + math.cos(loop_angle) * (r + ls)
        hy = ny + math.sin(loop_angle) * (r + ls)
        return [p1x, p1y, cp1x, cp1y, cp2x, cp2y, p2x, p2y], hx, hy

    def _edge_point_screen(self, cx, cy, tx, ty):
        dx, dy = tx - cx, ty - cy
        dist = math.sqrt(dx * dx + dy * dy)
        if dist == 0: return cx, cy
        r = self._to_screen(BUBBLE_RADIUS)
        return cx + (dx / dist) * r, cy + (dy / dist) * r

    def calculate_curvature_from_mouse(self, n1_x, n1_y, n2_x, n2_y, mx, my):
        dx, dy = n2_x - n1_x, n2_y - n1_y
        dist = math.sqrt(dx ** 2 + dy ** 2)
        if dist == 0: return 0
        return ((n1_y - n2_y) * mx + (n2_x - n1_x) * my + (n1_x * n2_y - n2_x * n1_y)) / dist

    def get_arc_control_point(self, n1_x, n1_y, n2_x, n2_y, curvature):
        mid_x, mid_y = (n1_x + n2_x) / 2, (n1_y + n2_y) / 2
        dx, dy = n2_x - n1_x, n2_y - n1_y
        dist = math.sqrt(dx ** 2 + dy ** 2)
        if dist == 0: return mid_x, mid_y
        return mid_x + ((-dy / dist) * curvature), mid_y + ((dx / dist) * curvature)
