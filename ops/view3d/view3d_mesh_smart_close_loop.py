# 智能闭合循环线

import bpy
import bmesh
import heapq

def find_shortest_path(bm, start_v, valid_targets):
    """使用 Dijkstra 算法寻找从 start_v 到 valid_targets 中任意一个顶点的最短路径"""
    queue = [(0.0, start_v.index)]
    distances = {start_v.index: 0.0}
    came_from = {start_v.index: (None, None)}
    
    while queue:
        current_dist, current_idx = heapq.heappop(queue)
        
        # 如果到达了目标端点之一，回溯路径
        if current_idx in valid_targets:
            path = []
            curr = current_idx
            while curr != start_v.index:
                prev, edge = came_from[curr]
                path.append(edge)
                curr = prev
            return path, current_dist, current_idx
            
        if current_dist > distances.get(current_idx, float('inf')):
            continue
            
        current_v = bm.verts[current_idx]
        for edge in current_v.link_edges:
            # 绝对不能经过已经被选中的边
            if edge.select:
                continue
                
            neighbor_v = edge.other_vert(current_v)
            neighbor_idx = neighbor_v.index
            new_dist = current_dist + edge.calc_length()
            
            if new_dist < distances.get(neighbor_idx, float('inf')):
                distances[neighbor_idx] = new_dist
                came_from[neighbor_idx] = (current_idx, edge)
                heapq.heappush(queue, (new_dist, neighbor_idx))
                
    return None, float('inf'), None


class BetterExperie_OT_MeshSmartCloseLoop(bpy.types.Operator):
    bl_idname = "better_experie.mesh_smart_close_loop"
    bl_label = "智能闭合循环线 (多线段)"
    bl_description = "自动配对最近的端点并寻找最短路径闭合（避开已选边）"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.mode == 'EDIT_MESH'

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        # 1. 寻找所有端点
        # 端点的定义：在选中的顶点中，只连接了 1 条【选中边】的顶点
        endpoints = [v for v in bm.verts if v.select and sum(1 for e in v.link_edges if e.select) == 1]

        if not endpoints:
            self.report({'WARNING'}, "没有找到开放的端点！请确保选中了线段。")
            return {'CANCELLED'}
            
        if len(endpoints) % 2 != 0:
            self.report({'WARNING'}, f"发现奇数个端点 ({len(endpoints)}个)，拓扑可能存在分叉！")
            # 即使是奇数个，我们也尝试尽可能多地配对闭合

        total_edges_selected = 0
        pairs_connected = 0

        # 2. 贪心算法：每次寻找全局最短的一对端点进行连接
        while len(endpoints) >= 2:
            best_dist = float('inf')
            best_path = []
            best_pair = (None, None)
            
            # 遍历当前所有端点，寻找距离最近的一对
            for start_v in endpoints:
                valid_targets = set(v.index for v in endpoints if v != start_v)
                path, dist, end_idx = find_shortest_path(bm, start_v, valid_targets)
                
                if path and dist < best_dist:
                    best_dist = dist
                    best_path = path
                    best_pair = (start_v, bm.verts[end_idx])
                    
            # 如果找到了最短路径
            if best_path:
                for edge in best_path:
                    edge.select = True
                total_edges_selected += len(best_path)
                pairs_connected += 1
                
                # 将这对端点从待处理列表中移除
                endpoints.remove(best_pair[0])
                endpoints.remove(best_pair[1])
            else:
                # 找不到任何通路（可能在不同的网格岛屿上）
                break

        if pairs_connected > 0:
            bmesh.update_edit_mesh(obj.data)
            self.report({'INFO'}, f"成功闭合 {pairs_connected} 对端点！新增选中了 {total_edges_selected} 条边。")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "无法找到任何连接端点的路径！（可能属于不同的网格岛屿）")
            return {'CANCELLED'}




classes = (
    BetterExperie_OT_MeshSmartCloseLoop,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


