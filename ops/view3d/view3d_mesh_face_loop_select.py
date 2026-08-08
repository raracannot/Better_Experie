# 循环面扩选
# OlphaZ 提供

import bpy
import bmesh

def _get_opposite_edge(face, edge):
    for e in face.edges:
        if e == edge:
            continue
        e1_verts = {edge.verts[0], edge.verts[1]}
        e2_verts = {e.verts[0], e.verts[1]}
        if e1_verts.isdisjoint(e2_verts):
            return e
    return None


class BetterExperie_OT_FaceLoopSelect(bpy.types.Operator):
    bl_idname = "better_experie.face_loop_select"
    bl_label = "循环面扩选"
    bl_description = "从选中的面出发沿 U/V 方向扩选连续四边面，支持滑动、侧移与间隔模式"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH' and context.mode == 'EDIT_MESH'

    direction: bpy.props.EnumProperty(
        name="UV 方向",
        items=(('U', "U 向", "沿 U 方向选择"), ('V', "V 向", "沿 V 方向选择")),
        default='U')

    expand_count: bpy.props.IntProperty(
        name="扩选次数", description="正数向设定方向扩选，负数向反方向扩选，0不扩选",
        default=100, min=-1000, max=1000)

    offset: bpy.props.IntProperty(
        name="滑动偏移", description="正数向 DIR1 偏移选区，负数向 DIR2 偏移选区",
        default=0, min=-1000, max=1000)

    lateral_offset: bpy.props.IntProperty(
        name="侧向滑动", description="正数向一侧平移选区，负数向另一侧平移",
        default=0, min=-100, max=100)

    pattern_select: bpy.props.IntProperty(
        name="选取 (N)", description="模式选择：连续选中的面数",
        default=1, min=1, max=100)

    pattern_skip: bpy.props.IntProperty(
        name="弃选 (M)", description="模式选择：跳过的面数",
        default=0, min=0, max=100)

    expand_direction: bpy.props.EnumProperty(
        name="扩选方向", description="选择循环面扩选的方向",
        items=[
            ('BOTH', "双向扩选", "向两侧同时扩选", 'ARROW_LEFTRIGHT', 0),
            ('DIR1', "A向扩选", "仅向一侧扩选", 'BACK', 1),
            ('DIR2', "B向扩选", "仅向另一侧扩选", 'FORWARD', 2),
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

    def _select_face_loop(self, bm, start_face):
        if start_face is None:
            return set()

        if len(start_face.verts) != 4:
            return {start_face}

        edges = list(start_face.edges)
        if len(edges) < 2:
            return {start_face}

        if len(edges) == 4:
            u_edge = edges[0]
            u_opposite = _get_opposite_edge(start_face, u_edge)
            if u_opposite is not None:
                v_candidates = [e for e in edges if e != u_edge and e != u_opposite]
                v_edge = v_candidates[0] if v_candidates else edges[1]
            else:
                v_edge = edges[1]
        else:
            return {start_face}

        current_start = start_face
        current_main_edge = u_edge if self.direction == 'U' else v_edge
        lat_edge = v_edge if self.direction == 'U' else u_edge

        if self.lateral_offset != 0:
            lat_opp = _get_opposite_edge(start_face, lat_edge)
            walk_edge = lat_edge if self.lateral_offset > 0 else lat_opp
            steps_to_walk = abs(self.lateral_offset)

            for _ in range(steps_to_walk):
                if not walk_edge:
                    current_start = None
                    break
                next_f = next((f for f in walk_edge.link_faces if f != current_start), None)
                if next_f is None or len(next_f.verts) != 4:
                    current_start = None
                    break

                exit_edge = _get_opposite_edge(next_f, walk_edge)
                new_main_candidates = [e for e in next_f.edges if e != walk_edge and e != exit_edge]

                shared_verts = set(current_main_edge.verts).intersection(set(walk_edge.verts))
                if shared_verts and new_main_candidates:
                    v_target = list(shared_verts)[0]
                    current_main_edge = next((e for e in new_main_candidates if v_target in e.verts), new_main_candidates[0])
                elif new_main_candidates:
                    current_main_edge = new_main_candidates[0]

                current_start = next_f
                walk_edge = exit_edge

            if current_start is None or current_main_edge is None:
                return set()

        actual_dir = self.expand_direction
        actual_count = self.expand_count
        if self.expand_count < 0:
            actual_count = abs(self.expand_count)
            if self.expand_direction == 'DIR1':
                actual_dir = 'DIR2'
            elif self.expand_direction == 'DIR2':
                actual_dir = 'DIR1'

        if actual_dir == 'DIR1':
            start_idx = 0
            end_idx = actual_count
        elif actual_dir == 'DIR2':
            start_idx = -actual_count
            end_idx = 0
        else:
            start_idx = -actual_count
            end_idx = actual_count

        start_idx += self.offset
        end_idx += self.offset

        selected = set()
        cycle_length = self.pattern_select + self.pattern_skip

        def should_select(idx):
            if not (start_idx <= idx <= end_idx):
                return False
            if cycle_length <= 0:
                return True
            local_idx = idx - start_idx
            return (local_idx % cycle_length) < self.pattern_select

        if should_select(0):
            selected.add(current_start)

        start_edge = current_main_edge
        opposite_start_edge = _get_opposite_edge(current_start, start_edge)

        def walk(first_edge, max_steps, is_dir1):
            curr_f = current_start
            crossing_edge = first_edge
            steps = 0
            visited = {current_start}

            while crossing_edge and steps < max_steps:
                next_face = next(
                    (f for f in crossing_edge.link_faces
                     if f != curr_f and f not in visited),
                    None,
                )
                if next_face is None or len(next_face.verts) != 4:
                    break
                exit_edge = _get_opposite_edge(next_face, crossing_edge)
                visited.add(next_face)
                steps += 1

                idx = steps if is_dir1 else -steps
                if should_select(idx):
                    selected.add(next_face)

                if exit_edge is None:
                    break
                curr_f = next_face
                crossing_edge = exit_edge

        max_dir1_steps = max(0, end_idx)
        if max_dir1_steps > 0 and start_edge:
            walk(start_edge, max_dir1_steps, is_dir1=True)

        max_dir2_steps = max(0, -start_idx)
        if max_dir2_steps > 0 and opposite_start_edge:
            walk(opposite_start_edge, max_dir2_steps, is_dir1=False)

        return selected

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({"WARNING"}, "请选择一个网格对象")
            return {"CANCELLED"}

        if context.mode != 'EDIT_MESH':
            self.report({"WARNING"}, "请在编辑模式下使用")
            return {"CANCELLED"}

        bm = bmesh.from_edit_mesh(obj.data)

        selected_faces = [f for f in bm.faces if f.select]

        if not selected_faces:
            self.report({"WARNING"}, "请至少选择一个面")
            return {"CANCELLED"}

        all_selected = set()
        for face in selected_faces:
            loop_faces = self._select_face_loop(bm, face)
            all_selected.update(loop_faces)

        for f in bm.faces:
            f.select = f in all_selected

        bmesh.update_edit_mesh(obj.data)
        return {"FINISHED"}


classes = (
    BetterExperie_OT_FaceLoopSelect,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
