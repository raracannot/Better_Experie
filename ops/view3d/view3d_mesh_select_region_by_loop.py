# 选择闭合区域

import bpy
import bmesh
import gpu
import traceback
from gpu_extras.batch import batch_for_shader
import mathutils
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils
import random
from ...utils.modal_border import add_modal_border, remove_modal_border

# 新版本使用 'UNIFORM_COLOR'
shader_3d = gpu.shader.from_builtin('UNIFORM_COLOR')

def get_random_color():
    # 生成明亮且饱和的随机颜色
    h = random.random()
    s = 0.8 + random.random() * 0.2
    v = 0.8 + random.random() * 0.2
    c = mathutils.Color()
    c.hsv = h, s, v
    return (c.r, c.g, c.b, 0.4) # 带有透明度

class BetterExperie_OT_SelectEnclosedRegions(bpy.types.Operator):
    bl_idname = "better_experie.select_enclosed_regions"
    bl_label = "选择闭合区域"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "按已选网格进行划分，按区域选取"
    
    @classmethod
    def poll(cls, context):
        return context.active_object and context.mode == 'EDIT_MESH'

    def invoke(self, context, event):
        try:
            self.obj = context.active_object
            self.bm = bmesh.from_edit_mesh(self.obj.data)
            
            self.bm.verts.ensure_lookup_table()
            self.bm.edges.ensure_lookup_table()
            self.bm.faces.ensure_lookup_table()

            # 1. 记录并定义边界（隔离墙）
            self.barrier_edges = set(e for e in self.bm.edges if e.select)
            self.barrier_faces = set(f for f in self.bm.faces if f.select)
            
            # 如果选中了面，面的边界边也作为隔离墙
            for f in self.barrier_faces:
                for e in f.edges:
                    self.barrier_edges.add(e)

            # 取消所有选中状态
            for v in self.bm.verts: v.select = False
            for e in self.bm.edges: e.select = False
            for f in self.bm.faces: f.select = False

            # 2. 泛洪算法 (Flood Fill) 划分面域
            self.regions = [] # 存储每个面域包含的 face 列表
            self.region_colors = []
            self.face_to_region = {} # 映射：face -> region_index
            
            visited = set()
            
            for f in self.bm.faces:
                if f in self.barrier_faces or f in visited:
                    continue
                    
                # 发现新面域
                current_region = []
                queue = [f]
                visited.add(f)
                
                while queue:
                    curr_f = queue.pop(0)
                    current_region.append(curr_f)
                    
                    for loop in curr_f.loops:
                        edge = loop.edge
                        if edge in self.barrier_edges:
                            continue # 遇到隔离墙，停止蔓延
                            
                        # 获取相邻面
                        adj_face = loop.link_loop_radial_next.face if loop.link_loop_radial_next else None
                        if adj_face and adj_face != curr_f and adj_face not in visited and adj_face not in self.barrier_faces:
                            visited.add(adj_face)
                            queue.append(adj_face)
                            
                if current_region:
                    region_idx = len(self.regions)
                    self.regions.append(current_region)
                    self.region_colors.append(get_random_color())
                    for rf in current_region:
                        self.face_to_region[rf] = region_idx

            if not self.regions:
                self.report({'WARNING'}, "没有找到可划分的面域！")
                return {'CANCELLED'}

            # 3. 构建 GPU 绘制批次
            self.batches = []
            for region in self.regions:
                coords = []
                indices = []
                idx_offset = 0
                
                for f in region:
                    f_verts = f.verts[:]
                    f_coords = [v.co for v in f_verts]
                    
                    if len(f_verts) == 3:
                        tri_indices = [(0, 1, 2)]
                    else:
                        tri_indices = mathutils.geometry.tessellate_polygon([f_coords])
                    
                    for tri in tri_indices:
                        coords.extend([f_coords[i].copy() for i in tri])
                        indices.append((idx_offset, idx_offset+1, idx_offset+2))
                        idx_offset += 3
                        
                if coords:
                    batch = batch_for_shader(shader_3d, 'TRIS', {"pos": coords}, indices=indices)
                    self.batches.append(batch)
                else:
                    self.batches.append(None)

            # 记录当前选中的面域索引
            self.selected_region_indices = set()

            # 【核心修复】：基于当前的 BMesh 构建 BVH 树，确保射线检测的面索引绝对准确
            self.bvh = BVHTree.FromBMesh(self.bm)

            bmesh.update_edit_mesh(self.obj.data)

            # 4. 注册绘制和事件回调
            self._handle_3d = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_3d, (context,), 'WINDOW', 'POST_VIEW')
            self._handle_2d = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_2d, (context,), 'WINDOW', 'POST_PIXEL')
            add_modal_border(self, context)
            
            context.window_manager.modal_handler_add(self)
            context.area.tag_redraw()
            context.workspace.status_text_set(
                "面域选择 | 左键单选 | Shift加选 Ctrl减选 | Enter确认 | 右键/ESC退出")
            return {'RUNNING_MODAL'}
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            return {'CANCELLED'}

    def modal(self, context, event):
        try:
            context.area.tag_redraw()

            if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                # 射线投射检测点击了哪个面
                region = context.region
                rv3d = context.region_data
                coord = event.mouse_region_x, event.mouse_region_y
                
                view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
                ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
                
                # 将射线转换到物体的局部坐标系
                matrix_inv = self.obj.matrix_world.inverted()
                ray_origin_obj = matrix_inv @ ray_origin
                # BVH ray_cast 需要的是方向向量，而不是目标点
                ray_dir_obj = (matrix_inv @ (ray_origin + view_vector)) - ray_origin_obj
                ray_dir_obj.normalize()
                
                # 使用 BVH 树进行精准射线检测
                location, normal, index, distance = self.bvh.ray_cast(ray_origin_obj, ray_dir_obj)
                
                if location is not None and index is not None:
                    clicked_face = self.bm.faces[index]
                    if clicked_face in self.face_to_region:
                        reg_idx = self.face_to_region[clicked_face]
                        
                        if event.shift:
                            # Shift: 加选
                            self.selected_region_indices.add(reg_idx)
                        elif event.ctrl or event.oskey:
                            # Ctrl: 减选
                            self.selected_region_indices.discard(reg_idx)
                        else:
                            # 单击: 清空并单选
                            self.selected_region_indices.clear()
                            self.selected_region_indices.add(reg_idx)
                            
                        self.update_mesh_selection()
                else:
                    # 点击空白处，如果没有按修饰键则清空
                    if not event.shift and not event.ctrl:
                        self.selected_region_indices.clear()
                        self.update_mesh_selection()
                        
                return {'RUNNING_MODAL'}

            elif event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
                self._cleanup(context)
                return {'FINISHED'}
            elif event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
                self._cleanup(context)
                return {'FINISHED'}

            return {'PASS_THROUGH'}
        except Exception:
            traceback.print_exc()
            self._cleanup(context)
            return {'CANCELLED'}

    def update_mesh_selection(self):
        for f in self.bm.faces:
            f.select = False
            
        for reg_idx in self.selected_region_indices:
            for f in self.regions[reg_idx]:
                f.select = True
                
        bmesh.update_edit_mesh(self.obj.data)

    def draw_callback_3d(self, context):
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('LESS_EQUAL')
        
        obj_mat = self.obj.matrix_world
        shader_3d.bind()
        
        gpu.matrix.push()
        gpu.matrix.multiply_matrix(obj_mat)
        
        for i, batch in enumerate(self.batches):
            if not batch: continue
            
            color = list(self.region_colors[i])
            # 如果该区域被选中，高亮显示（增加不透明度和亮度）
            if i in self.selected_region_indices:
                color[3] = 0.8 
            else:
                color[3] = 0.2
                
            shader_3d.uniform_float("color", color)
            batch.draw(shader_3d)
            
        gpu.matrix.pop()
        gpu.state.blend_set('NONE')

    def draw_callback_2d(self, context):
        # 操作说明已移至 workspace.status_text_set，此回调保留为空
        pass

    def _cleanup(self, context):
        try:
            if hasattr(self, '_handle_3d') and self._handle_3d:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle_3d, 'WINDOW')
                self._handle_3d = None
        except Exception:
            pass
        try:
            if hasattr(self, '_handle_2d') and self._handle_2d:
                bpy.types.SpaceView3D.draw_handler_remove(self._handle_2d, 'WINDOW')
                self._handle_2d = None
        except Exception:
            pass
        remove_modal_border(self)
        try:
            if context and context.workspace:
                context.workspace.status_text_set(None)
        except Exception:
            pass
        try:
            if context and context.area:
                context.area.tag_redraw()
        except Exception:
            pass


classes = (
    BetterExperie_OT_SelectEnclosedRegions,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

