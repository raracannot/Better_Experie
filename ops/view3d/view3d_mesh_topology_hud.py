# 拓扑结构HUD检查器 - 实时可视化网格拓扑问题

import bpy
import gpu
import blf
import math
import time
import bmesh
import mathutils
import numpy as np
from gpu_extras.batch import batch_for_shader

SHADER = gpu.shader.from_builtin('UNIFORM_COLOR')

# ==========================================
# 自定义面偏移着色器 (用于动态法线偏移)
# ==========================================
face_shader_info = gpu.types.GPUShaderCreateInfo()
face_shader_info.push_constant('MAT4', "ModelViewProjMatrix")
face_shader_info.push_constant('VEC4', "color")
face_shader_info.push_constant('FLOAT', "offset_amount")

face_shader_info.vertex_in(0, 'VEC3', "pos")
face_shader_info.vertex_in(1, 'VEC3', "normal")
face_shader_info.fragment_out(0, 'VEC4', "fragColor")

face_shader_info.vertex_source('''
    void main() {
        // 在 GPU 端实时沿法线方向偏移顶点
        vec3 offset_pos = pos + normal * offset_amount;
        gl_Position = ModelViewProjMatrix * vec4(offset_pos, 1.0);
    }
''')
face_shader_info.fragment_source('''
    void main() {
        fragColor = color;
    }
''')
FACE_OFFSET_SHADER = gpu.shader.create_from_info(face_shader_info)

# ==========================================
# 自定义广告牌(Billboard)圆片着色器
# ==========================================
shader_info = gpu.types.GPUShaderCreateInfo()
shader_info.push_constant('MAT4', "ModelViewProjMatrix")
shader_info.push_constant('VEC2', "viewportSize")
shader_info.push_constant('FLOAT', "pointSize")
shader_info.push_constant('VEC4', "color")

shader_info.vertex_in(0, 'VEC3', "center")
shader_info.vertex_in(1, 'VEC2', "offset")

iface = gpu.types.GPUStageInterfaceInfo("billboard_iface")
iface.smooth('VEC2', "v_uv")
shader_info.vertex_out(iface)

shader_info.fragment_out(0, 'VEC4', "fragColor")

shader_info.vertex_source('''
    void main() {
        v_uv = offset;
        vec4 clip_pos = ModelViewProjMatrix * vec4(center, 1.0);
        vec2 ndc_offset = (offset * pointSize * 2.0) / viewportSize;
        clip_pos.xy += ndc_offset * clip_pos.w;
        gl_Position = clip_pos;
    }
''')
shader_info.fragment_source('''
    void main() {
        if (length(v_uv) > 1.0) discard;
        fragColor = color;
    }
''')

BILLBOARD_SHADER = gpu.shader.create_from_info(shader_info)

# ==========================================
# 属性更新回调函数
# ==========================================
def update_hud_state_cb(self, context):
    any_active = any([
        self.show_isolated_verts,
        self.show_wire_edges,
        self.show_tris,
        self.show_ngons,
        self.show_sharp_verts,
        self.show_boundary_edges,
        self.show_non_manifold,
        self.show_complex_poles,
        self.show_nonplanar_quads,
        self.show_flipped_normals
    ])
    
    if any_active:
        if not hud_manager.is_running:
            hud_manager.start(context)
    else:
        if hud_manager.is_running:
            hud_manager.stop(context)

def update_sharp_verts_cb(self, context):
    if hud_manager.is_running:
        hud_manager.recalc_sharp_verts(context)

def update_complex_poles_cb(self, context):
    if hud_manager.is_running:
        hud_manager.recalc_complex_poles(context)

def update_flipped_normals_cb(self, context):
    if hud_manager.is_running:
        hud_manager.recalc_flipped_normals(context)

def update_nonplanar_quads_cb(self, context):
    if hud_manager.is_running:
        hud_manager.recalc_nonplanar_quads(context)

# ==========================================
# 属性组：用于存储所有自定义设置
# ==========================================
class BetterExperie_TopologyHUDProps(bpy.types.PropertyGroup):

    show_topology_hud: bpy.props.BoolProperty(name="显示拓扑辅助HUD", description="绘制时带遮挡关系", default=False)
    
    show_xray: bpy.props.BoolProperty(name="绘制深度", description="绘制时带遮挡关系", default=True)
    face_offset: bpy.props.FloatProperty(name="面偏移", description="微微偏移面避免遮挡", min=-0.1, max=0.1, default=0.001, update=lambda s,c: c.area.tag_redraw() if c.area else None)
    verts_radius: bpy.props.FloatProperty(name="圆点半径", description="顶点圆点的屏幕像素半径", min=1.0, max=50.0, default=6.0, update=lambda s,c: c.area.tag_redraw() if c.area else None)

    show_isolated_verts: bpy.props.BoolProperty(name="孤立顶点", description="没有连接任何边的顶点", default=True, update=update_hud_state_cb)
    col_isolated_verts: bpy.props.FloatVectorProperty(name="颜色", subtype='COLOR', default=(1.0, 0.2, 0.2, 1.0), size=4, min=0.0, max=1.0)
    
    show_wire_edges: bpy.props.BoolProperty(name="无面边", description="没有连接任何面的边", default=True, update=update_hud_state_cb)
    col_wire_edges: bpy.props.FloatVectorProperty(name="颜色", subtype='COLOR', default=(1.0, 1.0, 0.2, 1.0), size=4, min=0.0, max=1.0)
    
    show_tris: bpy.props.BoolProperty(name="三角面", description="边数量为三的面", default=True, update=update_hud_state_cb)
    col_tris: bpy.props.FloatVectorProperty(name="颜色", subtype='COLOR', default=(0.2, 1.0, 1.0, 0.4), size=4, min=0.0, max=1.0)
    
    show_ngons: bpy.props.BoolProperty(name="多边面", description="边数量大于四的面", default=True, update=update_hud_state_cb)
    col_ngons: bpy.props.FloatVectorProperty(name="颜色", subtype='COLOR', default=(1.0, 0.2, 1.0, 0.4), size=4, min=0.0, max=1.0)

    show_sharp_verts: bpy.props.BoolProperty(name="边缘点 (锐角)", description="邻边夹角小于阈值的顶点", default=False, update=update_hud_state_cb)
    col_sharp_verts: bpy.props.FloatVectorProperty(name="颜色", subtype='COLOR', default=(1.0, 0.5, 0.0, 1.0), size=4, min=0.0, max=1.0)
    thr_sharp_verts: bpy.props.FloatProperty(name="角度阈值", default=math.radians(60), min=0.0, max=math.pi, subtype='ANGLE', update=update_sharp_verts_cb)

    show_boundary_edges: bpy.props.BoolProperty(name="边界边", description="面边缘处的边（邻面为1的边）", default=False, update=update_hud_state_cb)
    col_boundary_edges: bpy.props.FloatVectorProperty(name="颜色", subtype='COLOR', default=(0.0, 1.0, 0.0, 1.0), size=4, min=0.0, max=1.0)

    show_non_manifold: bpy.props.BoolProperty(name="非流形边", description="邻面大于2的边", default=False, update=update_hud_state_cb)
    col_non_manifold: bpy.props.FloatVectorProperty(name="颜色", subtype='COLOR', default=(1.0, 0.0, 0.0, 1.0), size=4, min=0.0, max=1.0)

    show_complex_poles: bpy.props.BoolProperty(name="复杂极点", description="邻边大于阈值的点", default=False, update=update_hud_state_cb)
    col_complex_poles: bpy.props.FloatVectorProperty(name="颜色", subtype='COLOR', default=(0.0, 0.5, 1.0, 1.0), size=4, min=0.0, max=1.0)
    thr_complex_poles: bpy.props.IntProperty(name="边数阈值", default=6, min=3, max=20, update=update_complex_poles_cb)

    show_nonplanar_quads: bpy.props.BoolProperty(name="非平面四边面", description="对角线劈开两三角面法线夹角大于阈值", default=False, update=update_hud_state_cb)
    col_nonplanar_quads: bpy.props.FloatVectorProperty(name="颜色", subtype='COLOR', default=(1.0, 0.6, 0.0, 1.0), size=4, min=0.0, max=1.0)
    thr_nonplanar_quads: bpy.props.FloatProperty(name="角度阈值", default=math.radians(5), min=0.0, max=math.pi, subtype='ANGLE', update=update_nonplanar_quads_cb)

    show_flipped_normals: bpy.props.BoolProperty(name="法线突变面", description="相邻面法线夹角大于阈值的面", default=False, update=update_hud_state_cb)
    col_flipped_normals: bpy.props.FloatVectorProperty(name="颜色", subtype='COLOR', default=(0.8, 0.0, 0.0, 0.5), size=4, min=0.0, max=1.0)
    thr_flipped_normals: bpy.props.FloatProperty(name="角度阈值", default=math.radians(90), min=0.0, max=math.pi, subtype='ANGLE', update=update_flipped_normals_cb)


# ==========================================
# 核心类：HUD 缓存与状态管理器
# ==========================================
class TopologyHUDManager:
    def __init__(self):
        self.is_running = False
        self._handle_2d = None
        self._handle_3d = None
        
        self.avg_edge_len = 0.1 
        
        self.batch_wire_edges = None
        self.batch_boundary_edges = None
        self.batch_non_manifold = None
        self.batch_tris = None
        self.batch_ngons = None
        self.batch_flipped_normals = None
        self.batch_nonplanar_quads = None
        
        self.pts_isolated = []
        self.pts_sharp = []
        self.pts_poles = []
        self.faces_flipped_data = [] 
        
        self.pts_sharp_data = [] 
        self.pts_poles_data = [] 
        self._np_quad_starts = None
        self._np_loop_verts = None
        self._np_verts_co = None
        self._np_quad_angles = None
        
        self.counts = {
            "isolated_verts": 0, "wire_edges": 0, "tris": 0, "ngons": 0,
            "sharp_verts": 0, "boundary_edges": 0, "non_manifold": 0,
            "complex_poles": 0, "flipped_normals": 0, "nonplanar_quads": 0
        }
        self.last_update_time = ""

    def clear_cache(self):
        self.batch_wire_edges = None
        self.batch_boundary_edges = None
        self.batch_non_manifold = None
        self.batch_tris = None
        self.batch_ngons = None
        self.batch_flipped_normals = None
        self.batch_nonplanar_quads = None
        
        self.batch_isolated = None
        self.batch_sharp = None
        self.batch_poles = None
        
        self.pts_isolated.clear()
        self.pts_sharp.clear()
        self.pts_poles.clear()
        
        self.pts_sharp_data.clear()
        self.pts_poles_data.clear()
        self.faces_flipped_data.clear() 
        self._np_quad_starts = None
        self._np_loop_verts = None
        self._np_verts_co = None
        self._np_quad_angles = None
        
        for k in self.counts: self.counts[k] = 0

    def _get_bmesh(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return None
        if obj.mode == 'EDIT':
            bm_orig = bmesh.from_edit_mesh(obj.data)
            bm = bm_orig.copy()
        else:
            bm = bmesh.new()
            bm.from_mesh(obj.data)
        bm.transform(obj.matrix_world)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        return bm

    # === 使用 Numpy 瞬间完成顶点展开 ===
    def _make_billboard_batch(self, points):
        if not points: return None
        n = len(points)
        
        # 1. 坐标重复4次 (n, 3) -> (n*4, 3)
        pts_arr = np.array(points, dtype=np.float32)
        centers = np.repeat(pts_arr, 4, axis=0).tolist()
        
        # 2. 偏移量平铺 (4, 2) -> (n*4, 2)
        base_offsets = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], dtype=np.float32)
        offsets = np.tile(base_offsets, (n, 1)).tolist()
        
        # 3. 索引计算 (n*2, 3)
        base_indices = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
        offsets_idx = (np.arange(n, dtype=np.int32) * 4).reshape(-1, 1, 1)
        indices = (base_indices + offsets_idx).reshape(-1, 3).tolist()
        
        return batch_for_shader(
            BILLBOARD_SHADER, 'TRIS', 
            {"center": centers, "offset": offsets}, 
            indices=indices
        )

    def recalc_sharp_verts(self, context):
        settings = context.scene.better_experie_topology_hud_props
        thr = settings.thr_sharp_verts
        self.pts_sharp = [co for co, angle in self.pts_sharp_data if angle < thr]
        self.counts["sharp_verts"] = len(self.pts_sharp)
        self.batch_sharp = self._make_billboard_batch(self.pts_sharp)

    def recalc_complex_poles(self, context):
        settings = context.scene.better_experie_topology_hud_props
        thr = settings.thr_complex_poles
        self.pts_poles = [co for co, count in self.pts_poles_data if count >= thr]
        self.counts["complex_poles"] = len(self.pts_poles)
        self.batch_poles = self._make_billboard_batch(self.pts_poles)

    def recalc_flipped_normals(self, context):
        settings = context.scene.better_experie_topology_hud_props
        thr = settings.thr_flipped_normals
        
        co_flipped = []
        no_flipped = []
        count_flipped = 0
        
        for max_angle, co_list, no_list in self.faces_flipped_data:
            if max_angle > thr:
                co_flipped.extend(co_list)
                no_flipped.extend(no_list)
                count_flipped += 1
                
        self.counts["flipped_normals"] = count_flipped
        if co_flipped:
            self.batch_flipped_normals = batch_for_shader(FACE_OFFSET_SHADER, 'TRIS', {"pos": co_flipped, "normal": no_flipped})
        else:
            self.batch_flipped_normals = None

    def recalc_nonplanar_quads(self, context):
        if self._np_quad_angles is None:
            return
        settings = context.scene.better_experie_topology_hud_props
        thr = settings.thr_nonplanar_quads
        mask = self._np_quad_angles > thr
        self.counts["nonplanar_quads"] = int(np.sum(mask))
        if np.any(mask):
            np_starts = self._np_quad_starts[mask]
            edge_offsets = np.array([[0, 1], [1, 2], [2, 3], [3, 0]], dtype=np.int32)
            np_loops = (np_starts[:, None, None] + edge_offsets).reshape(-1, 2)
            np_vert_pairs = self._np_loop_verts[np_loops]
            np_line_verts = np_vert_pairs.ravel()
            np_line_pos = self._np_verts_co[np_line_verts].tolist()
            self.batch_nonplanar_quads = batch_for_shader(SHADER, 'LINES', {"pos": np_line_pos})
        else:
            self.batch_nonplanar_quads = None

    def update_cache(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH': return

        settings = context.scene.better_experie_topology_hud_props
        self.clear_cache()

        # 如果在编辑模式，必须先将 EditMesh 的数据同步到底层 Mesh，否则 foreach_get 读到的是旧数据
        if obj.mode == 'EDIT':
            obj.update_from_editmode()
            
        mesh = obj.data
        num_verts = len(mesh.vertices)
        num_edges = len(mesh.edges)
        num_polys = len(mesh.polygons)
        num_loops = len(mesh.loops)

        if num_verts == 0: return

        # ==========================================
        # 使用 foreach_get + Numpy 瞬间提取全量数据
        # ==========================================
        # 提取顶点坐标 (N, 3)
        verts_co = np.empty(num_verts * 3, dtype=np.float32)
        mesh.vertices.foreach_get('co', verts_co)
        verts_co = verts_co.reshape(-1, 3)
        
        # 应用物体的世界矩阵
        world_mat = np.array(obj.matrix_world, dtype=np.float32)
        verts_co_homo = np.hstack((verts_co, np.ones((num_verts, 1), dtype=np.float32)))
        verts_co = (verts_co_homo @ world_mat.T)[:, :3]

        # 提取边连接的顶点索引 (E, 2)
        edges_v = np.empty(num_edges * 2, dtype=np.int32)
        mesh.edges.foreach_get('vertices', edges_v)
        edges_v = edges_v.reshape(-1, 2)

        # 提取 Loop 对应的 Edge 索引 (L,)
        loop_edges = np.empty(num_loops, dtype=np.int32)
        mesh.loops.foreach_get('edge_index', loop_edges)

        # 提取面的边数 (P,)
        poly_totals = np.empty(num_polys, dtype=np.int32)
        mesh.polygons.foreach_get('loop_total', poly_totals)

        # ==========================================
        # 利用 Numpy 向量化运算瞬间完成拓扑统计
        # ==========================================
        # 统计每个顶点连接了多少条边
        vert_edge_counts = np.bincount(edges_v.ravel(), minlength=num_verts)
        
        # 孤立顶点：连接边数为 0
        isolated_mask = vert_edge_counts == 0
        self.pts_isolated = verts_co[isolated_mask].tolist()
        
        # 复杂极点：连接边数 >= 3 (先全量缓存，后续由 recalc 过滤)
        poles_mask = vert_edge_counts >= 3
        if np.any(poles_mask):
            poles_co = verts_co[poles_mask]
            poles_counts = vert_edge_counts[poles_mask]
            self.pts_poles_data = list(zip(poles_co.tolist(), poles_counts.tolist()))

        # 统计每条边连接了多少个面 (通过 loop_edges 统计)
        edge_face_counts = np.bincount(loop_edges, minlength=num_edges)
        
        # 无面边(0)、边界边(1)、非流形边(>=3)
        wire_mask = edge_face_counts == 0
        bound_mask = edge_face_counts == 1
        nonman_mask = edge_face_counts >= 3

        def make_line_batch(mask):
            if not np.any(mask): return None
            # 获取符合条件的边的顶点索引，并展平提取坐标
            line_indices = edges_v[mask].ravel()
            line_coords = verts_co[line_indices].tolist()
            return batch_for_shader(SHADER, 'LINES', {"pos": line_coords})

        self.batch_wire_edges = make_line_batch(wire_mask)
        self.batch_boundary_edges = make_line_batch(bound_mask)
        self.batch_non_manifold = make_line_batch(nonman_mask)

        # 统计计数器
        self.counts["isolated_verts"] = int(np.sum(isolated_mask))
        self.counts["wire_edges"] = int(np.sum(wire_mask))
        self.counts["boundary_edges"] = int(np.sum(bound_mask))
        self.counts["non_manifold"] = int(np.sum(nonman_mask))
        self.counts["tris"] = int(np.sum(poly_totals == 3))
        self.counts["ngons"] = int(np.sum(poly_totals > 4))

        # 计算平均边长 (用于面偏移)
        if num_edges > 0:
            v1_co = verts_co[edges_v[:, 0]]
            v2_co = verts_co[edges_v[:, 1]]
            self.avg_edge_len = float(np.mean(np.linalg.norm(v1_co - v2_co, axis=1)))
        else:
            self.avg_edge_len = 0.1

        # ==========================================
        # NP 加速：三角面 / 多边面 Batch（纯 NumPy，无 BMesh 剖分）
        # ==========================================
        loop_start = np.empty(num_polys, dtype=np.int32)
        mesh.polygons.foreach_get('loop_start', loop_start)

        face_normals = np.empty(num_polys * 3, dtype=np.float32)
        mesh.polygons.foreach_get('normal', face_normals)
        face_normals = face_normals.reshape(-1, 3)

        loop_verts = np.empty(num_loops, dtype=np.int32)
        mesh.loops.foreach_get('vertex_index', loop_verts)

        # 三角面
        tri_mask = poly_totals == 3
        if np.any(tri_mask):
            tri_indices = np.where(tri_mask)[0]
            tri_starts = loop_start[tri_indices]
            offsets_tri = np.array([0, 1, 2], dtype=np.int32)
            tri_verts_idx = loop_verts[(tri_starts[:, None] + offsets_tri).ravel()].reshape(-1, 3).ravel()
            tri_pos = verts_co[tri_verts_idx].tolist()
            tri_normals = np.repeat(face_normals[tri_indices], 3, axis=0).tolist()
            self.batch_tris = batch_for_shader(FACE_OFFSET_SHADER, 'TRIS', {"pos": tri_pos, "normal": tri_normals})

        # 多边面（利用 loop_triangles 内置三角剖分）
        ngon_mask = poly_totals > 4
        if np.any(ngon_mask):
            mesh.calc_loop_triangles()
            num_loop_tris = len(mesh.loop_triangles)
            if num_loop_tris > 0:
                tri_verts_flat = np.empty(num_loop_tris * 3, dtype=np.int32)
                mesh.loop_triangles.foreach_get('vertices', tri_verts_flat)
                tri_verts = tri_verts_flat.reshape(-1, 3)
                tri_poly_idx = np.empty(num_loop_tris, dtype=np.int32)
                mesh.loop_triangles.foreach_get('polygon_index', tri_poly_idx)
                ngon_tri_mask = ngon_mask[tri_poly_idx]
                if np.any(ngon_tri_mask):
                    ngon_verts = tri_verts[ngon_tri_mask].ravel()
                    ngon_pos = verts_co[ngon_verts].tolist()
                    ngon_poly_idx = tri_poly_idx[ngon_tri_mask]
                    ngon_normals = np.repeat(face_normals[ngon_poly_idx], 3, axis=0).tolist()
                    self.batch_ngons = batch_for_shader(FACE_OFFSET_SHADER, 'TRIS', {"pos": ngon_pos, "normal": ngon_normals})

        # 非平面四边面检测（对角线劈开两三角，计算法线夹角）
        quad_mask = poly_totals == 4
        if np.any(quad_mask):
            quad_indices = np.where(quad_mask)[0]
            quad_starts = loop_start[quad_indices]
            offsets4 = np.array([0, 1, 2, 3], dtype=np.int32)
            quad_verts = loop_verts[(quad_starts[:, None] + offsets4).ravel()].reshape(-1, 4)
            v0 = verts_co[quad_verts[:, 0]]
            v1 = verts_co[quad_verts[:, 1]]
            v2 = verts_co[quad_verts[:, 2]]
            v3 = verts_co[quad_verts[:, 3]]
            nA = np.cross(v1 - v0, v2 - v0)
            nB = np.cross(v2 - v0, v3 - v0)
            nA_len = np.linalg.norm(nA, axis=1)
            nB_len = np.linalg.norm(nB, axis=1)
            nA_norm = np.zeros_like(nA)
            nB_norm = np.zeros_like(nB)
            valid = (nA_len > 1e-10) & (nB_len > 1e-10)
            if np.any(valid):
                nA_norm[valid] = nA[valid] / nA_len[valid, None]
                nB_norm[valid] = nB[valid] / nB_len[valid, None]
            dot_prod = np.abs(np.sum(nA_norm * nB_norm, axis=1))
            dot_prod = np.clip(dot_prod, 0.0, 1.0)
            angles = np.arccos(dot_prod)
            self._np_quad_starts = quad_starts
            self._np_loop_verts = loop_verts
            self._np_verts_co = verts_co
            self._np_quad_angles = angles

        # ==========================================
        # 复杂拓扑 (夹角计算) 仍使用 BMesh 处理
        # ==========================================
        bm = self._get_bmesh(context)
        if not bm: return

        for v in bm.verts:
            edge_count = len(v.link_edges)
            if edge_count >= 2:
                min_angle = math.pi
                for i in range(edge_count):
                    for j in range(i + 1, edge_count):
                        e1, e2 = v.link_edges[i], v.link_edges[j]
                        v1 = e1.other_vert(v).co - v.co
                        v2 = e2.other_vert(v).co - v.co
                        if v1.length > 0 and v2.length > 0:
                            angle = v1.angle(v2, 0.0)
                            if angle < min_angle:
                                min_angle = angle
                if min_angle < math.pi:
                    self.pts_sharp_data.append((tuple(v.co), min_angle))

        for f in bm.faces:
            max_angle = 0.0
            has_adj = False
            for e in f.edges:
                for adj_f in e.link_faces:
                    if adj_f != f:
                        angle = f.normal.angle(adj_f.normal, 0.0)
                        if angle > max_angle:
                            max_angle = angle
                        has_adj = True

            if has_adj:
                temp_co, temp_no = [], []
                coords = [tuple(v.co) for v in f.verts]
                normal = tuple(f.normal)
                indices = mathutils.geometry.tessellate_polygon([coords])
                for tri in indices:
                    temp_co.extend([coords[i] for i in tri])
                    temp_no.extend([normal for _ in tri])
                self.faces_flipped_data.append((max_angle, temp_co, temp_no))

        bm.free()

        self.batch_isolated = self._make_billboard_batch(self.pts_isolated)

        # 初始化阈值过滤
        self.recalc_sharp_verts(context)
        self.recalc_complex_poles(context)
        self.recalc_flipped_normals(context)
        self.recalc_nonplanar_quads(context)
        
        update_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.last_update_time = f"[{obj.name}]{update_time}"
        self.update_tag_redraw(context)

    def start(self, context):
        if self.is_running: return
        self.update_cache(context)
        self._handle_2d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_2d, (self, context), 'WINDOW', 'POST_PIXEL')
        self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d, (self, context), 'WINDOW', 'POST_VIEW')
        self.is_running = True
        self.update_tag_redraw(context)

    def stop(self, context):
        if not self.is_running: return
        if self._handle_2d: bpy.types.SpaceView3D.draw_handler_remove(self._handle_2d, 'WINDOW')
        if self._handle_3d: bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
        self._handle_2d = None
        self._handle_3d = None
        self.is_running = False
        self.clear_cache()
        self.update_tag_redraw(context)

    def update_tag_redraw(self, context):
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


# 实例化全局管理器
hud_manager = TopologyHUDManager()


# ==========================================
# 3D 绘制回调函数
# ==========================================
def draw_callback_3d(manager, context):
    
    if not manager.is_running: return
    if not context.space_data.overlay.show_overlays: return
    edge_width = 4.0
    
    settings = context.scene.better_experie_topology_hud_props
    gpu.state.blend_set('ALPHA')
    
    if settings.show_xray:
        gpu.state.depth_test_set('NONE')
    else:
        gpu.state.depth_test_set('LESS_EQUAL')
        
    # === 绘制面 (使用自定义偏移着色器) ===
    face_batches = []
    if settings.show_tris and manager.batch_tris: face_batches.append((manager.batch_tris, settings.col_tris))
    if settings.show_ngons and manager.batch_ngons: face_batches.append((manager.batch_ngons, settings.col_ngons))
    if settings.show_flipped_normals and manager.batch_flipped_normals: face_batches.append((manager.batch_flipped_normals, settings.col_flipped_normals))

    if face_batches:
        FACE_OFFSET_SHADER.bind()
        
        # 传递 MVP 矩阵
        mv_mat = gpu.matrix.get_model_view_matrix()
        proj_mat = gpu.matrix.get_projection_matrix()
        mvp_mat = proj_mat @ mv_mat
        FACE_OFFSET_SHADER.uniform_float("ModelViewProjMatrix", mvp_mat)
        
        # 实时计算并传递偏移量
        actual_offset = manager.avg_edge_len * settings.face_offset
        FACE_OFFSET_SHADER.uniform_float("offset_amount", actual_offset)
        
        for batch, color in face_batches:
            FACE_OFFSET_SHADER.uniform_float("color", color)
            batch.draw(FACE_OFFSET_SHADER)

    # === 绘制线 ===
    edge_batches = []
    if settings.show_wire_edges and manager.batch_wire_edges: edge_batches.append((manager.batch_wire_edges, settings.col_wire_edges))
    if settings.show_boundary_edges and manager.batch_boundary_edges: edge_batches.append((manager.batch_boundary_edges, settings.col_boundary_edges))
    if settings.show_non_manifold and manager.batch_non_manifold: edge_batches.append((manager.batch_non_manifold, settings.col_non_manifold))
    if settings.show_nonplanar_quads and manager.batch_nonplanar_quads: edge_batches.append((manager.batch_nonplanar_quads, settings.col_nonplanar_quads))

    for batch, color in edge_batches:
        gpu.state.line_width_set(edge_width)
        SHADER.bind()
        SHADER.uniform_float("color", color)
        batch.draw(SHADER)

    # === 绘制点 ===
    point_batches = []
    if settings.show_isolated_verts and manager.batch_isolated: 
        point_batches.append((manager.batch_isolated, settings.col_isolated_verts))
    if settings.show_sharp_verts and manager.batch_sharp: 
        point_batches.append((manager.batch_sharp, settings.col_sharp_verts))
    if settings.show_complex_poles and manager.batch_poles: 
        point_batches.append((manager.batch_poles, settings.col_complex_poles))

    if point_batches:
        BILLBOARD_SHADER.bind()
        
        mv_mat = gpu.matrix.get_model_view_matrix()
        proj_mat = gpu.matrix.get_projection_matrix()
        mvp_mat = proj_mat @ mv_mat
        
        BILLBOARD_SHADER.uniform_float("ModelViewProjMatrix", mvp_mat)
        BILLBOARD_SHADER.uniform_float("viewportSize", (context.region.width, context.region.height))
        
        for batch, color in point_batches:
            BILLBOARD_SHADER.uniform_float("color", color)
            BILLBOARD_SHADER.uniform_float("pointSize", settings.verts_radius)
            batch.draw(BILLBOARD_SHADER)
            
    gpu.state.line_width_set(1.0)
    gpu.state.point_size_set(1.0)
    gpu.state.blend_set('NONE')
    gpu.state.depth_test_set('LESS_EQUAL')


# ==========================================
# 2D 绘制回调函数 (文字与屏幕空间圆点)
# ==========================================
def draw_callback_2d(manager, context):
    if not context.space_data.overlay.show_overlays: return
    settings = context.scene.better_experie_topology_hud_props

    active_legends = []
    if settings.show_isolated_verts: active_legends.append((f"孤立顶点 ({manager.counts['isolated_verts']})", settings.col_isolated_verts))
    if settings.show_wire_edges: active_legends.append((f"无面边 ({manager.counts['wire_edges']})", settings.col_wire_edges))
    if settings.show_tris: active_legends.append((f"三角面 ({manager.counts['tris']})", settings.col_tris))
    if settings.show_ngons: active_legends.append((f"多边面 ({manager.counts['ngons']})", settings.col_ngons))
    if settings.show_sharp_verts: active_legends.append((f"边缘点/锐角 ({manager.counts['sharp_verts']})", settings.col_sharp_verts))
    if settings.show_boundary_edges: active_legends.append((f"边界边 ({manager.counts['boundary_edges']})", settings.col_boundary_edges))
    if settings.show_non_manifold: active_legends.append((f"非流形边 ({manager.counts['non_manifold']})", settings.col_non_manifold))
    if settings.show_complex_poles: active_legends.append((f"复杂极点 ({manager.counts['complex_poles']})", settings.col_complex_poles))
    if settings.show_flipped_normals: active_legends.append((f"法线突变面 ({manager.counts['flipped_normals']})", settings.col_flipped_normals))
    if settings.show_nonplanar_quads: active_legends.append((f"非平面四边面 ({manager.counts['nonplanar_quads']})", settings.col_nonplanar_quads))

    font_id = 0
    line_height = 22
    x = 80 
    y = 40 + (len(active_legends) * line_height) + 27 
    blf.size(font_id, 16)
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    blf.position(font_id, x, y, 0)
    blf.draw(font_id, "拓扑 HUD 检查器")
    y -= line_height + 5

    for label, color in active_legends:
        blf.color(font_id, *color)
        blf.position(font_id, x, y, 0)
        blf.draw(font_id, "■ " + label)
        y -= line_height


# ==========================================
# 核心操作符 (控制管理器)
# ==========================================
class BetterExperie_OT_TopologyHUD(bpy.types.Operator):
    bl_idname = "better_experie.topology_hud"
    bl_label = "拓扑 HUD 控制"
    bl_description = "在视口中实时显示网格拓扑信息，包括顶点数/边数/面数/非水密边/怍形面/翻转法线等\n\n【启动】点击启动 HUD 开始实时监控\n【全量刷新】重新计算所有拓扑数据\n【停止】停止 HUD 更新"
    bl_options = {'REGISTER', 'UNDO'}
    
    action: bpy.props.EnumProperty(
        items=[
            ('START', "Start", ""),
            ('STOP', "Stop", ""),
            ('REFRESH', "Refresh", "")
        ],
        default='START'
    )

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    @staticmethod
    def _switch_panel_category(context, category):
        """切换所有三维视口到指定侧栏分类（如 'View'）"""
        screens = getattr(bpy.context, 'screen', None)
        areas = []
        if screens:
            areas.extend([a for a in screens.areas if a.type == 'VIEW_3D'])
        if context.area and context.area.type == 'VIEW_3D':
            if context.area not in areas:
                areas.append(context.area)

        for area in areas:
            ui_region = None
            for region in area.regions:
                if region.type == 'UI':
                    ui_region = region
                    break
            if not ui_region:
                continue
            try:
                ui_region.active_panel_category = category
            except Exception:
                try:
                    override = {'area': area, 'region': ui_region}
                    bpy.ops.wm.context_set_string(override, data_path="ui_region.active_panel_category", value=category)
                except Exception:
                    pass
            area.tag_redraw()

    def invoke(self, context, event):
        if self.action == 'STOP':
            hud_manager.stop(context)
            settings = context.scene.better_experie_topology_hud_props
            settings.show_isolated_verts = False
            settings.show_wire_edges = False
            settings.show_tris = False
            settings.show_ngons = False
            settings.show_sharp_verts = False
            settings.show_boundary_edges = False
            settings.show_non_manifold = False
            settings.show_complex_poles = False
            settings.show_flipped_normals = False
            settings.show_nonplanar_quads = False
            return {'FINISHED'}
            
        if self.action == 'START':
            hud_manager.stop(context)
            settings = context.scene.better_experie_topology_hud_props
            settings.show_isolated_verts = True
            settings.show_wire_edges = True
            settings.show_tris = True
            settings.show_ngons = True
            settings.show_sharp_verts = True
            settings.show_boundary_edges = True
            settings.show_non_manifold = True
            settings.show_complex_poles = True
            settings.show_flipped_normals = True
            settings.show_nonplanar_quads = True
            # 自动切换到 'View' 分类，便于看到 HUD 开关面板
            self._switch_panel_category(context, 'View')

        if hud_manager.is_running:
            hud_manager.update_cache(context)
            return {'FINISHED'}
        else:
            hud_manager.start(context)
            return {'RUNNING_MODAL'}

# ==========================================
# 选择操作符 (点击加入选择)
# ==========================================
class BetterExperie_OT_TopologySelect(bpy.types.Operator):
    bl_idname = "better_experie.topology_select"
    bl_label = "选择拓扑"
    bl_description = "根据当前 HUD 检测结果，快速选中特定拓扑类型的元素（非水密边、怍形面、翻转法线面等）\n\n【点击】执行选择，根据当前拓扑类型快速定位"
    bl_options = {'REGISTER', 'UNDO'}

    topo_type: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
            
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        
        bpy.ops.mesh.select_all(action='DESELECT')
        
        settings = context.scene.better_experie_topology_hud_props

        if self.topo_type == 'isolated_verts':
            bm.select_mode = {'VERT'}
            for v in bm.verts:
                if len(v.link_edges) == 0: v.select = True
                
        elif self.topo_type == 'wire_edges':
            bm.select_mode = {'EDGE'}
            for e in bm.edges:
                if len(e.link_faces) == 0: e.select = True
                
        elif self.topo_type == 'tris':
            bm.select_mode = {'FACE'}
            for f in bm.faces:
                if len(f.verts) == 3: f.select = True
                
        elif self.topo_type == 'ngons':
            bm.select_mode = {'FACE'}
            for f in bm.faces:
                if len(f.verts) > 4: f.select = True
                
        elif self.topo_type == 'sharp_verts':
            bm.select_mode = {'VERT'}
            thr = settings.thr_sharp_verts
            for v in bm.verts:
                edge_count = len(v.link_edges)
                if edge_count >= 2:
                    for i in range(edge_count):
                        for j in range(i + 1, edge_count):
                            e1, e2 = v.link_edges[i], v.link_edges[j]
                            v1 = e1.other_vert(v).co - v.co
                            v2 = e2.other_vert(v).co - v.co
                            if v1.length > 0 and v2.length > 0:
                                if v1.angle(v2, 0.0) < thr:
                                    v.select = True
                                    break
                                    
        elif self.topo_type == 'boundary_edges':
            bm.select_mode = {'EDGE'}
            for e in bm.edges:
                if len(e.link_faces) == 1: e.select = True
                
        elif self.topo_type == 'non_manifold':
            bm.select_mode = {'EDGE'}
            for e in bm.edges:
                if len(e.link_faces) >= 3: e.select = True
                
        elif self.topo_type == 'complex_poles':
            bm.select_mode = {'VERT'}
            thr = settings.thr_complex_poles
            for v in bm.verts:
                if len(v.link_edges) >= thr: v.select = True
                
        elif self.topo_type == 'nonplanar_quads':
            bm.select_mode = {'FACE'}
            thr = settings.thr_nonplanar_quads
            for f in bm.faces:
                if len(f.verts) != 4:
                    continue
                vlist = list(f.verts)
                v0 = vlist[0].co
                v1 = vlist[1].co
                v2 = vlist[2].co
                v3 = vlist[3].co
                nA = (v1 - v0).cross(v2 - v0)
                nB = (v2 - v0).cross(v3 - v0)
                if nA.length < 1e-10 or nB.length < 1e-10:
                    continue
                angle = nA.normalized().angle(nB.normalized(), 0.0)
                if angle > thr:
                    f.select = True
                    
        elif self.topo_type == 'flipped_normals':
            bm.select_mode = {'FACE'}
            thr = settings.thr_flipped_normals
            for f in bm.faces:
                is_flipped = False
                for e in f.edges:
                    for adj_f in e.link_faces:
                        if adj_f != f:
                            if f.normal.angle(adj_f.normal, 0.0) > thr:
                                is_flipped = True
                                break
                    if is_flipped: break
                if is_flipped: f.select = True

        bmesh.update_edit_mesh(obj.data)
        context.area.tag_redraw()
        return {'FINISHED'}

# ==========================================
# UI 面板
# ==========================================
class BETTER_EXPERIE_PT_topology_hud(bpy.types.Panel):
    bl_label = "拓扑 HUD 设置"
    bl_idname = "BETTER_EXPERIE_PT_topology_hud"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'View'

    @classmethod  
    def poll(cls, context):
        return context.scene.better_experie_topology_hud_props.show_topology_hud

    def draw(self, context):
        layout = self.layout
        props = context.scene.better_experie_topology_hud_props

        def draw_item(prop_bool, prop_col, topo_type, prop_thr=None):
            box = layout.box()
            row = box.row(align=True)
            row.prop(props, prop_bool)
            row.prop(props, prop_col, text="")
            op = row.operator(BetterExperie_OT_TopologySelect.bl_idname, text="选择", icon='RESTRICT_SELECT_OFF')
            op.topo_type = topo_type
            if prop_thr:
                box.prop(props, prop_thr)

        draw_item("show_isolated_verts", "col_isolated_verts", "isolated_verts")
        draw_item("show_wire_edges", "col_wire_edges", "wire_edges")
        draw_item("show_tris", "col_tris", "tris")
        draw_item("show_ngons", "col_ngons", "ngons")
        draw_item("show_sharp_verts", "col_sharp_verts", "sharp_verts", "thr_sharp_verts")
        draw_item("show_boundary_edges", "col_boundary_edges", "boundary_edges")
        draw_item("show_non_manifold", "col_non_manifold", "non_manifold")
        draw_item("show_complex_poles", "col_complex_poles", "complex_poles", "thr_complex_poles")
        draw_item("show_flipped_normals", "col_flipped_normals", "flipped_normals", "thr_flipped_normals")
        draw_item("show_nonplanar_quads", "col_nonplanar_quads", "nonplanar_quads", "thr_nonplanar_quads")

        row = layout.row(align=True)
        row.prop(props, "show_xray")
        row.prop(props, "face_offset")
        row.prop(props, "verts_radius")
        
        if hud_manager.is_running:
            refresh_text = f"刷新缓存{hud_manager.last_update_time}" if hud_manager.last_update_time else "刷新缓存"
            layout.operator(BetterExperie_OT_TopologyHUD.bl_idname, text=refresh_text, icon='FILE_REFRESH').action = 'REFRESH'
            layout.operator(BetterExperie_OT_TopologyHUD.bl_idname, text="停止", icon='CANCEL').action = 'STOP'
        else:
            layout.operator(BetterExperie_OT_TopologyHUD.bl_idname, text="启动 HUD", icon='PLAY').action = 'START'

# 在 VIEW3D_PT_overlay_geometry 面板后添加自定义内容

classes = (
    BetterExperie_TopologyHUDProps,
    BetterExperie_OT_TopologyHUD,
    BetterExperie_OT_TopologySelect,
    BETTER_EXPERIE_PT_topology_hud,
)

def view3d_pt_overlay_geometry_draw(self, context):
    layout = self.layout
    props = context.scene.better_experie_topology_hud_props
    row = layout.row(align=True)
    row.prop(props, "show_topology_hud")
    if props.show_topology_hud:
        if hud_manager.is_running:
            op = row.operator(BetterExperie_OT_TopologyHUD.bl_idname, text="", icon='FILE_REFRESH')
            op.action = 'REFRESH'
            op2 = row.operator(BetterExperie_OT_TopologyHUD.bl_idname, text="", icon='CANCEL')
            op2.action = 'STOP'
        else:
            op = row.operator(BetterExperie_OT_TopologyHUD.bl_idname, text="", icon='PLAY')
            op.action = 'START'


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.better_experie_topology_hud_props = bpy.props.PointerProperty(type=BetterExperie_TopologyHUDProps)
    bpy.types.VIEW3D_PT_overlay_geometry.append(view3d_pt_overlay_geometry_draw)


def unregister():
    bpy.types.VIEW3D_PT_overlay_geometry.remove(view3d_pt_overlay_geometry_draw)
    hud_manager.stop(bpy.context)
    
    del bpy.types.Scene.better_experie_topology_hud_props
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
