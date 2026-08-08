
import bpy
import importlib

MODULE_NAMES = [
    "sequencer_align_strips",
    "sequencer_stack_strips",
    "sequencer_stack_simple",
    "sequencer_swap_strips",
    "sequencer_compact_channels",
]

ops_module_list = [importlib.import_module(f".{name}", __package__) for name in MODULE_NAMES]

def register():
    for ops in ops_module_list:
        if hasattr(ops, "register"):
            ops.register()

def unregister():
    for ops in reversed(ops_module_list):
        if hasattr(ops, "unregister"):
            ops.unregister()

def update():
    unregister()
    for ops in ops_module_list:
        importlib.reload(ops)
    register()
