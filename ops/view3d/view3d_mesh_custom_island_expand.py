# 自定义孤岛扩选：按阶数扩选/收缩，可启用屏障边把网格划分为孤岛，
# 扩选不跨越屏障，收缩时以选区与屏障的并集边缘为边界向内剥层

import bpy
import bmesh

_UV_EPS = 1e-5


def _is_uv_seam_edge(edge, uv_layer):
    """判断一条边是否为活动 UV 岛的边界（共享边两侧 UV 不连续）"""
    loops = list(edge.link_loops)
    if len(loops) < 2:
        return True
    l1, l2 = loops[0], loops[1]
    u1a = l1[uv_layer].uv
    u1b = l1.link_loop_next[uv_layer].uv
    u2a = l2[uv_layer].uv
    u2b = l2.link_loop_next[uv_layer].uv
    # UV 连续：两个 loop 把同一条边的两端映射到相同 UV（交叉配对）
    if (u1a - u2b).length > _UV_EPS or (u1b - u2a).length > _UV_EPS:
        return True
    return False


class BetterExperie_OT_CustomIslandExpand(bpy.types.Operator):
    bl_idname = "better_experie.custom_island_expand"
    bl_label = "自定义孤岛扩选"
    bl_description = "按阶数向外扩选或向内收缩，可启用屏障边（法向/材质/缝合/锐边/UV）划分孤岛，扩选不跨越屏障"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (
            context.active_object is not None
            and context.active_object.type == 'MESH'
            and context.mode == 'EDIT_MESH'
        )

    expand_order: bpy.props.IntProperty(
        name="扩选阶数", description="正数向外扩选，负数向内收缩，0为无操作",
        default=1, min=-1000, max=1000)
    use_barrier: bpy.props.BoolProperty(
        name="划界", description="启用虚拟边界划分网格为多个孤岛，在孤岛内加选或减选",
        default=False)
    use_normal: bpy.props.BoolProperty(
        name="法向", description="法向骤变边：一个边连接两个法向反向的面", default=False)
    use_material: bpy.props.BoolProperty(
        name="材质", description="各材质槽边缘", default=False)
    use_seam: bpy.props.BoolProperty(
        name="缝合边", description="缝合边", default=False)
    use_sharp: bpy.props.BoolProperty(
        name="锐边", description="锐边", default=False)
    use_uv: bpy.props.BoolProperty(
        name="UV", description="活动UV岛的边缘", default=False)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, "expand_order")

        col.separator()
        col.prop(self, "use_barrier")
        if self.use_barrier:
            box = col.box()
            box.label(text="虚拟边界规则", icon='STICKY_UVS_LOC')
            box.prop(self, "use_normal")
            box.prop(self, "use_material")
            box.prop(self, "use_seam")
            box.prop(self, "use_sharp")
            box.prop(self, "use_uv")

    def _compute_barriers(self, bm):
        barriers = set()
        uv_layer = bm.loops.layers.uv.active if self.use_uv else None

        for e in bm.edges:
            if self.use_sharp and not e.smooth:
                barriers.add(e)
                continue
            if self.use_seam and e.seam:
                barriers.add(e)
                continue
            faces = e.link_faces
            if len(faces) == 2:
                f1, f2 = faces[0], faces[1]
                if self.use_normal and f1.normal.dot(f2.normal) < 0:
                    barriers.add(e)
                    continue
                if self.use_material and f1.material_index != f2.material_index:
                    barriers.add(e)
                    continue
                if self.use_uv and uv_layer and _is_uv_seam_edge(e, uv_layer):
                    barriers.add(e)
        return barriers

    # ---------- 扩选（正阶数） ----------
    def _expand_verts(self, bm, barriers, order, wall_verts):
        result = {v for v in bm.verts if v.select}
        frontier = set(result)
        for _ in range(order):
            next_frontier = set()
            for v in frontier:
                if v in wall_verts:
                    # 墙顶点一刀切：只选中不再外扩
                    continue
                for e in v.link_edges:
                    if e in barriers:
                        continue
                    other = e.other_vert(v)
                    if other not in result:
                        result.add(other)
                        next_frontier.add(other)
            frontier = next_frontier
            if not frontier:
                break
        for v in bm.verts:
            v.select = v in result

    def _expand_edges(self, bm, barriers, order, wall_verts):
        result = {e for e in bm.edges if e.select}
        frontier = set(result)
        for _ in range(order):
            next_frontier = set()
            for e in frontier:
                for v in e.verts:
                    for ne in v.link_edges:
                        if ne in result:
                            continue
                        if ne in barriers:
                            # 屏障边可选中（作边界），但不可继续穿过
                            result.add(ne)
                            continue
                        # 墙顶点处仅允许屏障边，其余非屏障边视为不可达（阻断跨侧）
                        if v in wall_verts:
                            continue
                        result.add(ne)
                        next_frontier.add(ne)
            frontier = next_frontier
            if not frontier:
                break
        for e in bm.edges:
            e.select = e in result

    def _expand_faces(self, bm, barriers, order):
        result = {f for f in bm.faces if f.select}
        frontier = set(result)
        for _ in range(order):
            next_frontier = set()
            for f in frontier:
                for e in f.edges:
                    if e in barriers:
                        continue
                    for nf in e.link_faces:
                        if nf != f and nf not in result:
                            result.add(nf)
                            next_frontier.add(nf)
            frontier = next_frontier
            if not frontier:
                break
        for f in bm.faces:
            f.select = f in result

    # ---------- 收缩（负阶数） ----------
    def _contract_verts(self, bm, barriers, order):
        for _ in range(order):
            selected = {v for v in bm.verts if v.select}
            if not selected:
                break
            boundary = set()
            for v in selected:
                is_b = False
                for e in v.link_edges:
                    if e in barriers:
                        is_b = True
                        break
                    if e.other_vert(v) not in selected:
                        is_b = True
                        break
                if is_b:
                    boundary.add(v)
            if not boundary:
                break
            for v in boundary:
                v.select = False

    def _contract_edges(self, bm, barriers, order):
        for _ in range(order):
            selected = {e for e in bm.edges if e.select and e not in barriers}
            if not selected:
                break
            boundary = set()
            for e in selected:
                is_b = False
                for v in e.verts:
                    for ne in v.link_edges:
                        if ne in barriers:
                            is_b = True
                            break
                        if ne not in selected:
                            is_b = True
                            break
                    if is_b:
                        break
                if is_b:
                    boundary.add(e)
            if not boundary:
                break
            for e in boundary:
                e.select = False

    def _contract_faces(self, bm, barriers, order):
        for _ in range(order):
            selected = {f for f in bm.faces if f.select}
            if not selected:
                break
            boundary = set()
            for f in selected:
                is_b = False
                for e in f.edges:
                    if e in barriers:
                        is_b = True
                        break
                    for nf in e.link_faces:
                        if nf != f and nf not in selected:
                            is_b = True
                            break
                    if is_b:
                        break
                if is_b:
                    boundary.add(f)
            if not boundary:
                break
            for f in boundary:
                f.select = False

    def execute(self, context):
        if self.expand_order == 0:
            return {'CANCELLED'}

        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        barriers = self._compute_barriers(bm) if self.use_barrier else set()

        # 墙顶点：挂有任意屏障边的顶点，扩选到此一刀切（可选中但不再穿透）
        wall_verts = set()
        for e in barriers:
            wall_verts.update(e.verts)

        mode = context.tool_settings.mesh_select_mode

        if self.expand_order > 0:
            if mode[0]:
                self._expand_verts(bm, barriers, self.expand_order, wall_verts)
            elif mode[1]:
                self._expand_edges(bm, barriers, self.expand_order, wall_verts)
            elif mode[2]:
                self._expand_faces(bm, barriers, self.expand_order)
        else:
            order = -self.expand_order
            if mode[0]:
                self._contract_verts(bm, barriers, order)
            elif mode[1]:
                self._contract_edges(bm, barriers, order)
            elif mode[2]:
                self._contract_faces(bm, barriers, order)

        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)
        return {'FINISHED'}


classes = (
    BetterExperie_OT_CustomIslandExpand,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
