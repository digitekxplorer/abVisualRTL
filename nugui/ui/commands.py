class Command:
    def execute(self): pass

    def undo(self): pass


class AddStateCommand(Command):
    def __init__(self, canvas, node):
        self.canvas = canvas
        self.node = node

    def execute(self):
        # In this specific flow, usually the canvas creates the node first,
        # then pushes this command. So execute might check if it exists.
        # However, for Redo, we need to ensure it exists.
        if self.node.id not in self.canvas.nodes:
            self.canvas.restore_node(self.node)

    def undo(self):
        self.canvas._remove_node(self.node.id)


class AddTransitionCommand(Command):
    def __init__(self, canvas, line):
        self.canvas = canvas
        self.line = line

    def execute(self):
        if self.line not in self.canvas.lines:
            self.canvas.restore_line(self.line)

    def undo(self):
        self.canvas._remove_line(self.line)


class AddAnnotationCommand(Command):
    """FEATURE: add a free-floating text annotation."""

    def __init__(self, canvas, annotation):
        self.canvas = canvas
        self.annotation = annotation

    def execute(self):
        if self.annotation.id not in self.canvas.annotations:
            self.canvas.restore_annotation(self.annotation)

    def undo(self):
        self.canvas._remove_annotation(self.annotation.id)


class DeleteCommand(Command):
    def __init__(self, canvas, nodes, lines, annotations=None):
        self.canvas = canvas
        self.nodes = nodes  # List of StateNode objects
        self.lines = lines  # List of TransitionLine objects
        self.annotations = annotations or []  # List of TextAnnotation objects

    def execute(self):
        for line in self.lines:
            self.canvas._remove_line(line)
        for node in self.nodes:
            self.canvas._remove_node(node.id)
        for ann in self.annotations:
            self.canvas._remove_annotation(ann.id)

    def undo(self):
        # Restore Nodes first
        for node in self.nodes:
            self.canvas.restore_node(node)
        # Restore Lines
        for line in self.lines:
            self.canvas.restore_line(line)
        # Restore Annotations
        for ann in self.annotations:
            self.canvas.restore_annotation(ann)


class AddGroupCommand(Command):
    """FEATURE: paste — add a group of nodes/lines/annotations as one
    undoable action (inverse of DeleteCommand)."""

    def __init__(self, canvas, nodes, lines, annotations):
        self.canvas = canvas
        self.nodes = nodes
        self.lines = lines
        self.annotations = annotations

    def execute(self):
        for node in self.nodes:
            if node.id not in self.canvas.nodes:
                self.canvas.restore_node(node)
        for line in self.lines:
            if line not in self.canvas.lines:
                self.canvas.restore_line(line)
        for ann in self.annotations:
            if ann.id not in self.canvas.annotations:
                self.canvas.restore_annotation(ann)

    def undo(self):
        for line in self.lines:
            self.canvas._remove_line(line)
        for node in self.nodes:
            self.canvas._remove_node(node.id)
        for ann in self.annotations:
            self.canvas._remove_annotation(ann.id)


class MoveCommand(Command):
    def __init__(self, canvas, item_type, item_obj, old_state, new_state):
        self.canvas = canvas
        self.item_type = item_type  # 'node', 'handle', 'text', 'annotation'
        self.item_obj = item_obj
        self.old_state = old_state  # Dict of relevant fields (x, y, offsets, etc)
        self.new_state = new_state

    def execute(self):
        self._apply_state(self.new_state)

    def undo(self):
        self._apply_state(self.old_state)

    def _apply_state(self, state):
        if self.item_type == 'node':
            # Update Data
            self.item_obj.x = state['x']
            self.item_obj.y = state['y']
            self.item_obj.name_offset_x = state.get('name_offset_x', 0)
            self.item_obj.name_offset_y = state.get('name_offset_y', 0)
            self.item_obj.details_offset_x = state.get('details_offset_x', 0)
            self.item_obj.details_offset_y = state.get('details_offset_y', 0)

            # Update Visuals
            # We can't just use move() because that's relative.
            # We must use coords() or delete/redraw.
            # Simple approach: Re-draw the node completely to snap to position
            self.canvas._remove_node_visuals(self.item_obj)  # Helper needed
            self.canvas._draw_loaded_node(self.item_obj)
            self.canvas._update_lines_for_node(self.item_obj.id)
            self.canvas.toggle_details(self.canvas.show_details)  # Refresh visibility

        elif self.item_type == 'handle':
            self.item_obj.curvature = state['curvature']
            self.item_obj.loop_angle = state['loop_angle']
            self.canvas._update_specific_line(self.item_obj)

        elif self.item_type == 'text_trans':
            self.item_obj.text_offset_x = state['text_offset_x']
            self.item_obj.text_offset_y = state['text_offset_y']
            self.canvas._update_specific_line(self.item_obj)

        elif self.item_type == 'annotation':
            self.item_obj.x = state['x']
            self.item_obj.y = state['y']
            self.canvas._redraw_annotation(self.item_obj)


class GroupMoveCommand(Command):
    """FEATURE: move several objects as one undoable action. Wraps a list of
    individual MoveCommands and applies/reverts them together."""

    def __init__(self, moves):
        self.moves = list(moves)  # list of MoveCommand

    def execute(self):
        for m in self.moves:
            m.execute()

    def undo(self):
        for m in self.moves:
            m.undo()


class EditPropertyCommand(Command):
    def __init__(self, canvas, obj, old_data_dict, new_data_dict):
        self.canvas = canvas
        self.obj = obj
        self.old_data = old_data_dict
        self.new_data = new_data_dict

    def execute(self):
        self._apply(self.new_data)

    def undo(self):
        self._apply(self.old_data)

    def _apply(self, data):
        # Update attributes dynamically
        for key, value in data.items():
            setattr(self.obj, key, value)

        # Refresh Visuals
        if hasattr(self.obj, 'text_item_id') or hasattr(self.obj, 'canvas_item_id'):
            # It's a node, line, or annotation
            self.canvas.refresh_visuals(self.obj)
