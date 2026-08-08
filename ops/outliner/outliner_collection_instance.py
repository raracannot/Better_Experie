# 集合实例转换工具

import bpy
import mathutils
import numpy as np


class BetterExperie_CollectionInstanceProps(bpy.types.PropertyGroup):
    use_precise_bbox: bpy.props.BoolProperty(
        name="精确边界框计算",
        description="基于修改器后的真实网格计算边界框（较慢但极其准确）",
        default=False
    )
    use_min_bbox: bpy.props.BoolProperty(
        name="使用最小边界框",
        description="打包时计算最小包围盒（OBB），自动旋转实例以匹配最佳边界",
        default=False
    )
    origin_type: bpy.props.EnumProperty(
        name="设置原点",
        description="打包实例或修改原点时的对齐方式",
        items=[
            ('TOP_CENTER', "顶部", "包围盒顶部中心"),
            ('BOTTOM_CENTER', "底部", "包围盒底部中心"),
            ('CENTER', "中心", "整体中心"),
            ('WORLD_ORIGIN', "世界原点", "世界坐标(0,0,0)"),
            ('XYZ_MIN', "XYZ最小", "XYZ的最小值"),
        ],
        default='CENTER'
    )


def _get_group_obb_orientation(objects):
    points = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        if obj.type != 'MESH':
            continue
        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        matrix = obj.matrix_world
        points.extend([(matrix @ v.co).to_tuple() for v in mesh.vertices])
        eval_obj.to_mesh_clear()

    if not points:
        return mathutils.Matrix.Identity(4)

    points_np = np.array(points)
    centroid = np.mean(points_np, axis=0)
    centered = points_np - centroid
    cov = (centered.T @ centered) / len(points_np)

    U, s, Vh = np.linalg.svd(cov)
    Z = U[:, 0]
    X = U[:, 1]
    Y = np.cross(Z, X)
    Y = Y / np.linalg.norm(Y)
    X = np.cross(Y, Z)
    X = X / np.linalg.norm(X)

    rot_np = np.array([X, Y, Z]).T
    if np.linalg.det(rot_np) < 0:
        Y = -Y
        rot_np = np.array([X, Y, Z]).T

    return mathutils.Matrix(rot_np.tolist()).to_4x4()


def _get_object_world_corners(obj, context=None):
    corners = []
    if obj.type == 'EMPTY' and 'bbox_size' in obj and 'bbox_center' in obj:
        size = mathutils.Vector(obj['bbox_size'])
        center = mathutils.Vector(obj['bbox_center'])
        half_size = size / 2.0
        for x in (-1, 1):
            for y in (-1, 1):
                for z in (-1, 1):
                    local_corner = center + mathutils.Vector((x * half_size.x, y * half_size.y, z * half_size.z))
                    corners.append(obj.matrix_world @ local_corner)
        return corners

    if obj.type == 'EMPTY' and obj.instance_type == 'COLLECTION' and obj.instance_collection:
        for child in obj.instance_collection.all_objects:
            if child.type != 'EMPTY':
                child_world_mat = obj.matrix_world @ child.matrix_world
                child_corners = _get_object_world_corners(child, context)
                inv_child_mat = child.matrix_world.inverted()
                for c in child_corners:
                    corners.append(child_world_mat @ (inv_child_mat @ c))
        return corners

    if context and context.scene.better_experie_collection_instance.use_precise_bbox and obj.type == 'MESH':
        depsgraph = context.evaluated_depsgraph_get()
        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        if mesh.vertices:
            corners.extend([obj.matrix_world @ v.co for v in mesh.vertices])
        eval_obj.to_mesh_clear()
        return corners

    if hasattr(obj, 'bound_box') and obj.type != 'EMPTY':
        for corner in obj.bound_box:
            corners.append(obj.matrix_world @ mathutils.Vector(corner))
    return corners


def _calculate_objects_bbox(objects, context=None):
    min_vec = mathutils.Vector((float('inf'), float('inf'), float('inf')))
    max_vec = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))
    has_valid = False
    for obj in objects:
        corners = _get_object_world_corners(obj, context)
        for world_corner in corners:
            for i in range(3):
                if world_corner[i] < min_vec[i]:
                    min_vec[i] = world_corner[i]
                if world_corner[i] > max_vec[i]:
                    max_vec[i] = world_corner[i]
            has_valid = True
    return (min_vec, max_vec) if has_valid else None


def _convert_collection_to_instance(collection, origin_type, context):
    props = context.scene.better_experie_collection_instance
    use_min_bbox = props.use_min_bbox
    R = mathutils.Matrix.Identity(4)
    R_inv = mathutils.Matrix.Identity(4)

    all_objs_set = set(collection.all_objects)
    root_objs = [obj for obj in collection.all_objects if obj.parent not in all_objs_set]

    if use_min_bbox:
        R = _get_group_obb_orientation(collection.all_objects)
        R_inv = R.inverted()
        for obj in root_objs:
            obj.matrix_world = R_inv @ obj.matrix_world

    bbox = _calculate_objects_bbox(collection.all_objects, context)
    if bbox:
        min_vec, max_vec = bbox
        if origin_type == 'CENTER':
            target_origin = (min_vec + max_vec) / 2.0
        elif origin_type == 'TOP_CENTER':
            target_origin = mathutils.Vector(((min_vec.x + max_vec.x) / 2.0, (min_vec.y + max_vec.y) / 2.0, max_vec.z))
        elif origin_type == 'BOTTOM_CENTER':
            target_origin = mathutils.Vector(((min_vec.x + max_vec.x) / 2.0, (min_vec.y + max_vec.y) / 2.0, min_vec.z))
        elif origin_type == 'XYZ_MIN':
            target_origin = mathutils.Vector((min_vec.x, min_vec.y, min_vec.z))
        elif origin_type == 'WORLD_ORIGIN':
            target_origin = R_inv @ mathutils.Vector((0.0, 0.0, 0.0))
        else:
            loc = context.active_object.matrix_world.translation if context.active_object else None
            target_origin = R_inv @ loc if loc else mathutils.Vector((0.0, 0.0, 0.0))
    else:
        target_origin = mathutils.Vector((0.0, 0.0, 0.0))

    for obj in root_objs:
        obj.matrix_world = mathutils.Matrix.Translation(-target_origin) @ obj.matrix_world

    empty = bpy.data.objects.new(collection.name, None)
    empty.instance_type = 'COLLECTION'
    empty.instance_collection = collection
    empty.empty_display_size = 0.01
    empty.matrix_world = R @ mathutils.Matrix.Translation(target_origin)

    if bbox:
        local_min = min_vec - target_origin
        local_max = max_vec - target_origin
        empty['bbox_size'] = local_max - local_min
        empty['bbox_center'] = (local_max + local_min) / 2.0

    parent_collections = [col for col in bpy.data.collections if collection.name in col.children.keys()]
    in_scene = collection.name in context.scene.collection.children.keys()
    if parent_collections:
        parent_collections[0].objects.link(empty)
    else:
        context.scene.collection.objects.link(empty)

    for p_col in parent_collections:
        p_col.children.unlink(collection)
    if in_scene:
        context.scene.collection.children.unlink(collection)

    bpy.ops.object.select_all(action='DESELECT')
    empty.select_set(True)
    context.view_layer.objects.active = empty
    return empty


def _unwrap_obj_collection(collection, context):
    parent_collection = None
    for col in bpy.data.collections:
        if collection.name in col.children.keys():
            parent_collection = col
            break
    if parent_collection is None:
        parent_collection = context.scene.collection

    for obj in list(collection.objects):
        collection.objects.unlink(obj)
        target_col = parent_collection
        if 'orig_col_name' in obj:
            orig_name = obj['orig_col_name']
            if orig_name in bpy.data.collections:
                target_col = bpy.data.collections[orig_name]
            del obj['orig_col_name']
        if obj.name not in target_col.objects:
            target_col.objects.link(obj)
    bpy.data.collections.remove(collection)


def _duplicate_collection_hierarchy(src_col, matrix, parent_col, obj_map, processed_cols=None):
    if processed_cols is None:
        processed_cols = set()
    if src_col in processed_cols:
        return
    processed_cols.add(src_col)
    new_col = bpy.data.collections.new(src_col.name)
    if parent_col:
        parent_col.children.link(new_col)
    col_obj_map = {}
    for root_obj in [obj for obj in src_col.objects if not obj.parent]:
        _duplicate_hierarchy(root_obj, matrix, new_col, col_obj_map)
    for child_col in src_col.children:
        _duplicate_collection_hierarchy(child_col, matrix, new_col, obj_map, processed_cols)
    obj_map.update(col_obj_map)
    return new_col


def _duplicate_hierarchy(src_obj, matrix, col, obj_map):
    new_obj = src_obj.copy()
    if src_obj.data and not src_obj.instance_type == 'COLLECTION':
        new_obj.data = src_obj.data.copy()
    if not src_obj.parent:
        new_obj.matrix_world = matrix @ src_obj.matrix_local
    else:
        new_obj.matrix_local = src_obj.matrix_local
    obj_map[src_obj] = new_obj
    col.objects.link(new_obj)
    for child in src_obj.children:
        if child in obj_map:
            continue
        _duplicate_hierarchy(child, matrix, col, obj_map).parent = new_obj
    return new_obj


class BetterExperie_OT_CollectionToInstance(bpy.types.Operator):
    bl_idname = "better_experie.collection_to_instance"
    bl_label = "打包为实例"
    bl_description = "将选中的对象或活动集合打包为一个集合实例"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects) or (
            context.collection and context.collection != context.scene.collection
        )

    def execute(self, context):
        props = context.scene.better_experie_collection_instance
        selected = context.selected_objects
        selected_set = set(selected)
        origin_type = props.origin_type
        target_collection = None
        if not selected:
            if context.collection and context.collection != context.scene.collection:
                target_collection = context.collection
            else:
                return {'CANCELLED'}
        else:
            matching_cols = [
                col for col in bpy.data.collections
                if col != context.scene.collection and set(col.all_objects) == selected_set
            ]
            if matching_cols:
                target_collection = matching_cols[0]
            else:
                new_name = "obj_collection"
                target_collection = bpy.data.collections.new(new_name)
                context.scene.collection.children.link(target_collection)
                target_collection['is_obj'] = True
                roots = [obj for obj in selected if obj.parent not in selected_set]
                for obj in roots:
                    for col in list(obj.users_collection):
                        col.objects.unlink(obj)
                    target_collection.objects.link(obj)
        _convert_collection_to_instance(target_collection, origin_type, context)
        return {'FINISHED'}


class BetterExperie_OT_AdjustInstancePivot(bpy.types.Operator):
    bl_idname = "better_experie.adjust_instance_pivot"
    bl_label = "修改实例原点"
    bl_description = "批量修改选中实例的原点位置，保持视觉位置不变"
    bl_options = {'REGISTER', 'UNDO'}

    origin_type: bpy.props.EnumProperty(
        name="设置原点",
        description="打包实例或修改原点时的对齐方式",
        items=[
            ('TOP_CENTER', "顶部", "包围盒顶部中心"),
            ('BOTTOM_CENTER', "底部", "包围盒底部中心"),
            ('CENTER', "中心", "整体中心"),
            ('WORLD_ORIGIN', "世界原点", "世界坐标(0,0,0)"),
            ('XYZ_MIN', "XYZ最小", "XYZ的最小值"),
        ],
        default='CENTER'
    )
    
    # @classmethod
    # def poll(cls, context):
        # return any(
            # obj.type == 'EMPTY' and obj.instance_type == 'COLLECTION' and obj.instance_collection
            # for obj in context.selected_objects
        # )

    def execute(self, context):
        
        context.scene.better_experie_collection_instance.origin_type = self.origin_type
        
        instances = [
            obj for obj in context.selected_objects
            if obj.type == 'EMPTY' and obj.instance_type == 'COLLECTION' and obj.instance_collection
        ]
        if not instances:
            self.report({'WARNING'}, "请选中至少一个集合实例")
            return {'CANCELLED'}

        for empty in instances:
            collection = empty.instance_collection
            if 'bbox_size' not in empty or 'bbox_center' not in empty:
                continue
            size = mathutils.Vector(empty['bbox_size'])
            center = mathutils.Vector(empty['bbox_center'])
            min_vec, max_vec = center - size / 2.0, center + size / 2.0

            if self.origin_type == 'CENTER':
                local_target = center
            elif self.origin_type == 'TOP_CENTER':
                local_target = mathutils.Vector((center.x, center.y, max_vec.z))
            elif self.origin_type == 'BOTTOM_CENTER':
                local_target = mathutils.Vector((center.x, center.y, min_vec.z))
            elif self.origin_type == 'XYZ_MIN':
                local_target = mathutils.Vector((min_vec.x, min_vec.y, min_vec.z))
            elif self.origin_type == 'WORLD_ORIGIN':
                local_target = empty.matrix_world.inverted() @ mathutils.Vector((0.0, 0.0, 0.0))
            else:
                loc = context.active_object.matrix_world.translation if context.active_object else None
                local_target = empty.matrix_world.inverted() @ loc if loc else mathutils.Vector((0.0, 0.0, 0.0))

            new_matrix = empty.matrix_world @ mathutils.Matrix.Translation(local_target)
            empty.matrix_world = new_matrix
            all_objs = set(collection.all_objects)
            for obj in all_objs:
                if obj.parent not in all_objs:
                    obj.matrix_world = mathutils.Matrix.Translation(-local_target) @ obj.matrix_world
            empty['bbox_center'] = center - local_target

        self.report({'INFO'}, f"已修改 {len(instances)} 个实例的原点")
        # context.scene.better_experie_collection_instance.origin_type = self.origin_type
        return {'FINISHED'}


class BetterExperie_OT_InstanceToCollection(bpy.types.Operator):
    bl_idname = "better_experie.instance_to_collection"
    bl_label = "实例解包为集合"
    bl_description = "将选中的集合实例解包还原为集合层级结构"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(
            obj.type == 'EMPTY' and obj.instance_type == 'COLLECTION'
            for obj in context.selected_objects
        )

    def execute(self, context):
        instances = [
            obj for obj in context.selected_objects
            if obj.type == 'EMPTY' and obj.instance_type == 'COLLECTION'
        ]
        if not instances:
            self.report({'WARNING'}, "请选中至少一个集合实例")
            return {'CANCELLED'}

        for empty in instances:
            original_col = empty.instance_collection
            inst_matrix = empty.matrix_world.copy()
            parents = empty.users_collection
            instance_count = sum(
                1 for obj in bpy.data.objects if obj.instance_collection == original_col
            )
            if instance_count > 1:
                target_col = _duplicate_collection_hierarchy(original_col, inst_matrix, None, {})
            else:
                target_col = original_col
                all_objs = set(original_col.all_objects)
                for obj in all_objs:
                    if obj.parent not in all_objs:
                        obj.matrix_world = inst_matrix @ obj.matrix_world
            for p_col in parents:
                if empty.name in p_col.objects:
                    p_col.objects.unlink(empty)
                if target_col.name not in p_col.children:
                    p_col.children.link(target_col)
            if not parents and target_col.name not in context.scene.collection.children:
                context.scene.collection.children.link(target_col)
            bpy.data.objects.remove(empty)
            if target_col.get('is_obj', False):
                _unwrap_obj_collection(target_col, context)

        self.report({'INFO'}, f"已解包 {len(instances)} 个集合实例")
        return {'FINISHED'}


class BETTER_EXPERIE_MT_collection_instance_settings(bpy.types.Menu):
    bl_label = "修改实例原点"
    bl_idname = "BETTER_EXPERIE_MT_collection_instance_settings"

    _origin_labels = [
        ('CENTER', "实例原点>中心点"),
        ('TOP_CENTER', "实例原点>中心顶部"),
        ('BOTTOM_CENTER', "实例原点>中心底部"),
        ('WORLD_ORIGIN', "实例原点>世界原点"),
        ('XYZ_MIN', "实例原点>XYZ最小"),
    ]

    def draw(self, context):
        layout = self.layout
        props = context.scene.better_experie_collection_instance
        current = props.origin_type

        layout.prop(props, "use_precise_bbox", icon='MESH_DATA')
        layout.prop(props, "use_min_bbox", icon='MESH_CUBE')

        layout.separator()
        for origin_id, label in self._origin_labels:
            text = f"【{label}】" if origin_id == current else label
            layout.operator("better_experie.adjust_instance_pivot", text=text, icon='PIVOT_CURSOR').origin_type = origin_id



classes = (
    BetterExperie_CollectionInstanceProps,
    BetterExperie_OT_CollectionToInstance,
    BetterExperie_OT_AdjustInstancePivot,
    BetterExperie_OT_InstanceToCollection,
    BETTER_EXPERIE_MT_collection_instance_settings,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_experie_collection_instance = bpy.props.PointerProperty(
        type=BetterExperie_CollectionInstanceProps)


def unregister():
    del bpy.types.Scene.better_experie_collection_instance
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
