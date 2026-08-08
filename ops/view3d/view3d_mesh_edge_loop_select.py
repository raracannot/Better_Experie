# 循环/并排边扩选

import bpy
import bmesh

def _get_opposite_edge_in_face(edge, face):
    if len(face.verts) != 4:
        return None
    for e in face.edges:
        if e == edge:
            continue
        if set(e.verts).isdisjoint(set(edge.verts)):
            return e
    return None


def _get_opposite_edge_across_vert(edge, vert):
    if len(vert.link_edges) != 4:
        return None
    edge_faces = set(edge.link_faces)
    for e in vert.link_edges:
        if e == edge:
            continue
        if set(e.link_faces).isdisjoint(edge_faces):
            return e
    return None


class BetterExperie_OT_EdgeLoopSelect(bpy.types.Operator):
    bl_idname = "better_experie.edge_loop_select"
    bl_label = "循环/并排边扩选"
    bl_description = "沿Loop（循环边）或Ring（并排边）方向扩选，支持滑动、侧移与间隔模式"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH' and context.mode == 'EDIT_MESH'

    direction: bpy.props.EnumProperty(
        name="选择模式",
        items=(
            ('LOOP', "Loop (循环边)", "首尾相连的边"),
            ('RING', "Ring (并排边)", "平行排列的边"),
        ), default='LOOP')

    expand_count: bpy.props.IntProperty(name="扩选次数", default=100, min=-1000, max=1000)
    offset: bpy.props.IntProperty(name="滑动偏移", default=0, min=-1000, max=1000)
    lateral_offset: bpy.props.IntProperty(name="侧向滑动", default=0, min=-100, max=100)
    pattern_select: bpy.props.IntProperty(name="选取 (N)", default=1, min=1, max=100)
    pattern_skip: bpy.props.IntProperty(name="弃选 (M)", default=0, min=0, max=100)

    expand_direction: bpy.props.EnumProperty(
        name="扩选方向",
        items=[
            ('BOTH', "双向", "向两侧同时扩选"),
            ('DIR1', "方向 1", "仅向一侧扩选"),
            ('DIR2', "方向 2", "仅向另一侧扩选"),
        ], default='BOTH')

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)
        col.label(text="基础设置:")
        row = col.row()
        row.prop(self, "direction", expand=True)

        row = col.row(align=True)
        row.prop(self, "expand_direction", text="")
        row.prop(self, "expand_count")

        layout.separator()

        col = layout.column(align=True)
        col.label(text="偏移控制:")

        row = col.row()
        row.label(text="", icon="ARROW_LEFTRIGHT")
        row.prop(self, "offset")
        row = col.row()
        row.label(text="", icon="COLLAPSEMENU")
        row.prop(self, "lateral_offset")

        layout.separator()

        col = layout.column(align=True)
        col.label(text="间隔模式:")
        row = col.row(align=True)
        row.prop(self, "pattern_select")
        row.prop(self, "pattern_skip")

    def _get_next_edge(self, current_edge, node, is_loop):
        if is_loop:
            return _get_opposite_edge_across_vert(current_edge, node)
        else:
            return _get_opposite_edge_in_face(current_edge, node)

    def _select_edge_loop(self, bm, start_edge):
        if start_edge is None:
            return set()

        is_loop = (self.direction == 'LOOP')

        if is_loop:
            nodes = list(start_edge.verts)
        else:
            nodes = list(start_edge.link_faces)

        if not nodes:
            return {start_edge}

        node1 = nodes[0]
        node2 = nodes[1] if len(nodes) > 1 else None

        current_start = start_edge
        if self.lateral_offset != 0:
            lat_is_loop = not is_loop
            lat_nodes = list(current_start.verts) if lat_is_loop else list(current_start.link_faces)

            if lat_nodes:
                walk_node = lat_nodes[0] if self.lateral_offset > 0 else (lat_nodes[1] if len(lat_nodes) > 1 else lat_nodes[0])
                steps_to_walk = abs(self.lateral_offset)

                for _ in range(steps_to_walk):
                    next_e = self._get_next_edge(current_start, walk_node, lat_is_loop)
                    if not next_e:
                        break
                    current_start = next_e
                    new_lat_nodes = list(current_start.verts) if lat_is_loop else list(current_start.link_faces)
                    walk_node = next((n for n in new_lat_nodes if n != walk_node), None)
                    if not walk_node:
                        break

                if is_loop:
                    nodes = list(current_start.verts)
                else:
                    nodes = list(current_start.link_faces)
                if nodes:
                    node1 = nodes[0]
                    node2 = nodes[1] if len(nodes) > 1 else None

        actual_dir = self.expand_direction
        actual_count = self.expand_count
        if self.expand_count < 0:
            actual_count = abs(self.expand_count)
            if self.expand_direction == 'DIR1':
                actual_dir = 'DIR2'
            elif self.expand_direction == 'DIR2':
                actual_dir = 'DIR1'

        if actual_dir == 'DIR1':
            start_idx, end_idx = 0, actual_count
        elif actual_dir == 'DIR2':
            start_idx, end_idx = -actual_count, 0
        else:
            start_idx, end_idx = -actual_count, actual_count

        start_idx += self.offset
        end_idx += self.offset

        selected = set()
        cycle_length = self.pattern_select + self.pattern_skip

        def should_select(idx):
            if not (start_idx <= idx <= end_idx):
                return False
            if cycle_length <= 0:
                return True
            return ((idx - start_idx) % cycle_length) < self.pattern_select

        if should_select(0):
            selected.add(current_start)

        def walk(start_node, max_steps, is_dir1):
            curr_e = current_start
            curr_node = start_node
            steps = 0
            visited = {current_start}

            while curr_node and steps < max_steps:
                next_e = self._get_next_edge(curr_e, curr_node, is_loop)
                if not next_e or next_e in visited:
                    break

                visited.add(next_e)
                steps += 1

                idx = steps if is_dir1 else -steps
                if should_select(idx):
                    selected.add(next_e)

                next_nodes = list(next_e.verts) if is_loop else list(next_e.link_faces)
                curr_node = next((n for n in next_nodes if n != curr_node), None)
                curr_e = next_e

        max_dir1_steps = max(0, end_idx)
        if max_dir1_steps > 0 and node1:
            walk(node1, max_dir1_steps, is_dir1=True)

        max_dir2_steps = max(0, -start_idx)
        if max_dir2_steps > 0 and node2:
            walk(node2, max_dir2_steps, is_dir1=False)

        return selected

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return {"CANCELLED"}
        if context.mode != 'EDIT_MESH':
            self.report({"WARNING"}, "请在编辑模式下使用")
            return {"CANCELLED"}

        bm = bmesh.from_edit_mesh(obj.data)
        selected_edges = [e for e in bm.edges if e.select]

        if not selected_edges:
            self.report({"WARNING"}, "请至少选择一条边")
            return {"CANCELLED"}

        all_selected = set()
        for edge in selected_edges:
            loop_edges = self._select_edge_loop(bm, edge)
            all_selected.update(loop_edges)

        for e in bm.edges:
            e.select = e in all_selected

        bmesh.update_edit_mesh(obj.data)
        return {"FINISHED"}


classes = (
    BetterExperie_OT_EdgeLoopSelect,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
