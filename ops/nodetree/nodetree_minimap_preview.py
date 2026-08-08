# 节点编辑器小地图预览

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from ...utils import get_pref

draw_handle = None
MINIMAP_DATA = {}


def _get_node_bounds(node):
    scale = bpy.context.preferences.system.ui_scale
    di_x = node.dimensions.x
    di_y = node.dimensions.y

    w_cloud_magic_value = 9
    rara_magic_value = 5

    if hasattr(node, "location_absolute"):
        node_x = node.location_absolute.x
        node_y = node.location_absolute.y
    else:
        node_x = node.location.x
        node_y = node.location.y
        node_p = node.parent
        while node_p:
            node_x += node_p.location.x
            node_y += node_p.location.y
            node_p = node_p.parent

    if node.type == "REROUTE":
        x_min = (node_x - rara_magic_value) * scale
        x_max = (node_x + rara_magic_value) * scale
        y_min = (node_y - rara_magic_value) * scale
        y_max = (node_y + rara_magic_value) * scale
        return x_min, x_max, y_min, y_max

    x_min = node_x * scale
    x_max = x_min + di_x

    if node.hide and node.type not in {"REROUTE", "FRAME"}:
        y_min = node_y * scale - w_cloud_magic_value * scale - di_y / 2
        y_max = node_y * scale - w_cloud_magic_value * scale + di_y / 2
    else:
        y_min = node_y * scale - di_y
        y_max = node_y * scale

    return x_min, x_max, y_min, y_max


def _get_active_node_tree(context):
    try:
        active_node_tree = context.space_data.node_tree
        if hasattr(context.space_data, "path") and len(context.space_data.path) > 0:
            active_node_tree = context.space_data.path[-1].node_tree
        return active_node_tree
    except Exception:
        return None


def _draw_minimap():
    context = bpy.context
    space = context.space_data
    region = context.region

    if space.type != 'NODE_EDITOR':
        return

    prefs = get_pref()
    if prefs is None or not getattr(prefs, "show_node_minimap", True):
        return

    tree = _get_active_node_tree(context)
    if not tree or not tree.nodes:
        return

    minimap_width = 200
    minimap_height = 150
    padding = 20
    margin_x = 20
    margin_y = 20

    map_rect_min_x = margin_x
    map_rect_max_x = margin_x + minimap_width
    map_rect_min_y = margin_y
    map_rect_max_y = margin_y + minimap_height

    min_nx = float('inf')
    max_nx = float('-inf')
    min_ny = float('inf')
    max_ny = float('-inf')

    node_bounds_cache = {}

    for node in tree.nodes:
        x_min, x_max, y_min, y_max = _get_node_bounds(node)
        node_bounds_cache[node.name] = (x_min, x_max, y_min, y_max)

        min_nx = min(min_nx, x_min)
        max_nx = max(max_nx, x_max)
        min_ny = min(min_ny, y_min)
        max_ny = max(max_ny, y_max)

    if max_nx == min_nx:
        max_nx = min_nx + 1
    if max_ny == min_ny:
        max_ny = min_ny + 1

    tree_width = max_nx - min_nx
    tree_height = max_ny - min_ny
    scale_x = (minimap_width - padding * 2) / tree_width
    scale_y = (minimap_height - padding * 2) / tree_height
    scale = min(scale_x, scale_y)

    offset_x = map_rect_min_x + padding + ((minimap_width - padding * 2) - tree_width * scale) / 2
    offset_y = map_rect_min_y + padding + ((minimap_height - padding * 2) - tree_height * scale) / 2

    def map_coords(x, y):
        mx = offset_x + (x - min_nx) * scale
        my = offset_y + (y - min_ny) * scale
        return (mx, my)

    node_centers = {}
    for node in tree.nodes:
        x_min, x_max, y_min, y_max = node_bounds_cache[node.name]
        cx = (x_min + x_max) / 2
        cy = (y_min + y_max) / 2
        node_centers[node.name] = map_coords(cx, cy)

    global MINIMAP_DATA
    MINIMAP_DATA[region.as_pointer()] = {
        "rect": (map_rect_min_x, map_rect_min_y, map_rect_max_x, map_rect_max_y),
        "node_centers": node_centers
    }

    gpu.state.blend_set('ALPHA')

    shader_rect = gpu.shader.from_builtin('UNIFORM_COLOR')
    bg_verts = [
        (map_rect_min_x, map_rect_min_y), (map_rect_max_x, map_rect_min_y),
        (map_rect_min_x, map_rect_max_y), (map_rect_max_x, map_rect_max_y)
    ]
    bg_indices = [(0, 1, 2), (2, 1, 3)]
    batch_bg = batch_for_shader(shader_rect, 'TRIS', {"pos": bg_verts}, indices=bg_indices)
    shader_rect.bind()
    shader_rect.uniform_float("color", (0.1, 0.1, 0.1, 0.7))
    batch_bg.draw(shader_rect)

    if tree.links:
        line_verts = []
        for link in tree.links:
            if not link.is_valid:
                continue

            from_n = link.from_node
            to_n = link.to_node

            f_xmin, f_xmax, f_ymin, f_ymax = node_bounds_cache[from_n.name]
            t_xmin, t_xmax, t_ymin, t_ymax = node_bounds_cache[to_n.name]

            fx = f_xmax
            fy = (f_ymin + f_ymax) * 0.5
            tx = t_xmin
            ty = (t_ymin + t_ymax) * 0.5

            line_verts.append(map_coords(fx, fy))
            line_verts.append(map_coords(tx, ty))

        if line_verts:
            shader_line = gpu.shader.from_builtin('UNIFORM_COLOR')
            batch_lines = batch_for_shader(shader_line, 'LINES', {"pos": line_verts})
            shader_line.bind()
            shader_line.uniform_float("color", (0.6, 0.6, 0.6, 0.8))
            gpu.state.line_width_set(1.5)
            batch_lines.draw(shader_line)

    node_verts = []
    node_colors = []
    node_indices = []
    idx = 0

    active_node = tree.nodes.active

    for node in tree.nodes:
        if node == active_node:
            color = (1.0, 1.0, 1.0, 1.0)
        elif node.select:
            color = (1.0, 0.6, 0.1, 1.0)
        else:
            color = (0.3, 0.6, 0.9, 0.9)

        x_min, x_max, y_min, y_max = node_bounds_cache[node.name]

        v1 = map_coords(x_min, y_min)
        v2 = map_coords(x_max, y_min)
        v3 = map_coords(x_min, y_max)
        v4 = map_coords(x_max, y_max)

        node_verts.extend([v1, v2, v3, v4])
        node_colors.extend([color, color, color, color])
        node_indices.extend([(idx, idx + 1, idx + 2), (idx + 2, idx + 1, idx + 3)])
        idx += 4

    if node_verts:
        shader_nodes = gpu.shader.from_builtin('SMOOTH_COLOR')
        batch_nodes = batch_for_shader(shader_nodes, 'TRIS', {"pos": node_verts, "color": node_colors},
                                       indices=node_indices)
        shader_nodes.bind()
        batch_nodes.draw(shader_nodes)

    if region and region.type == 'WINDOW':
        v_min_x, v_min_y = region.view2d.region_to_view(0, 0)
        v_max_x, v_max_y = region.view2d.region_to_view(region.width, region.height)

        mx1, my1 = map_coords(v_min_x, v_min_y)
        mx2, my2 = map_coords(v_max_x, v_max_y)

        mx1 = max(map_rect_min_x, min(mx1, map_rect_max_x))
        mx2 = max(map_rect_min_x, min(mx2, map_rect_max_x))
        my1 = max(map_rect_min_y, min(my1, map_rect_max_y))
        my2 = max(map_rect_min_y, min(my2, map_rect_max_y))

        vp_p1 = (mx1, my1)
        vp_p2 = (mx2, my1)
        vp_p3 = (mx2, my2)
        vp_p4 = (mx1, my2)

        vp_verts = [vp_p1, vp_p2, vp_p3, vp_p4]
        vp_indices = [(0, 1), (1, 2), (2, 3), (3, 0)]

        shader_vp = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch_vp = batch_for_shader(shader_vp, 'LINES', {"pos": vp_verts}, indices=vp_indices)
        shader_vp.bind()
        shader_vp.uniform_float("color", (1.0, 1.0, 1.0, 0.9))
        gpu.state.line_width_set(2.0)
        batch_vp.draw(shader_vp)

    gpu.state.blend_set('NONE')


class BetterExperie_OT_MinimapInteract(bpy.types.Operator):
    bl_idname = "better_experie.minimap_interact"
    bl_label = "小地图点击跳转"
    bl_description = "点击小地图中的节点，快速跳转到对应节点"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data.type == 'NODE_EDITOR'

    def invoke(self, context, event):
        region = context.region
        if not region or region.type != 'WINDOW':
            return {'PASS_THROUGH'}

        data = MINIMAP_DATA.get(region.as_pointer())
        if not data:
            return {'PASS_THROUGH'}

        rect = data["rect"]
        mx, my = event.mouse_region_x, event.mouse_region_y

        in_minimap = (rect[0] <= mx <= rect[2] and rect[1] <= my <= rect[3])

        if in_minimap and event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            node_centers = data.get("node_centers", {})
            if not node_centers:
                return {'CANCELLED'}

            closest_node_name = None
            min_dist_sq = float('inf')

            for name, (cx, cy) in node_centers.items():
                dist_sq = (mx - cx) ** 2 + (my - cy) ** 2
                if dist_sq < min_dist_sq:
                    min_dist_sq = dist_sq
                    closest_node_name = name

            if closest_node_name:
                tree = _get_active_node_tree(context)
                if tree and closest_node_name in tree.nodes:
                    for n in tree.nodes:
                        n.select = False

                    target_node = tree.nodes[closest_node_name]
                    target_node.select = True
                    tree.nodes.active = target_node

                    with context.temp_override(region=region, space_data=context.space_data):
                        bpy.ops.node.view_selected()

            return {'FINISHED'}

        return {'PASS_THROUGH'}


def _draw_minimap_toggle(self, context):
    if context.space_data.type != 'NODE_EDITOR':
        return
    from ...utils import get_pref
    prefs = get_pref()
    if prefs is None:
        return
    self.layout.separator()
    self.layout.prop(prefs, "show_node_minimap", text="节点预览图")


classes = (
    BetterExperie_OT_MinimapInteract,
)


def register():
    global draw_handle
    for cls in classes:
        bpy.utils.register_class(cls)
    draw_handle = bpy.types.SpaceNodeEditor.draw_handler_add(
        _draw_minimap, (), 'WINDOW', 'POST_PIXEL'
    )

    bpy.types.NODE_PT_overlay.append(_draw_minimap_toggle)

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='Node Editor', space_type='NODE_EDITOR')
        km.keymap_items.new("better_experie.minimap_interact", 'LEFTMOUSE', 'PRESS')


def unregister():
    global draw_handle

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.get('Node Editor')
        if km:
            for kmi in km.keymap_items:
                if kmi.idname == "better_experie.minimap_interact":
                    km.keymap_items.remove(kmi)
                    break

    bpy.types.NODE_PT_overlay.remove(_draw_minimap_toggle)
    if draw_handle:
        bpy.types.SpaceNodeEditor.draw_handler_remove(draw_handle, 'WINDOW')
        draw_handle = None
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
