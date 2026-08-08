# 纹理节点工具

import bpy
from ...utils.node_tree import get_image_from_selected_node

def get_selected_texture_nodes(context):
    results = get_image_from_selected_node(context)
    return list({item[0] for item in results})


classes = ()

def register():
    pass

def unregister():
    pass
