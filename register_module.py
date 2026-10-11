
import bpy
import importlib

from .import addon_prefs
from .import other
from .import ops
from .import utils
from .import menu
from . import translation


module_list = [addon_prefs, other, utils, ops, menu, translation] #严格按照顺序依次注册（utils 先于 ops，保证热重载时 ops 取到最新 util）

def register():
    for module in module_list:
       if hasattr(module, "register"): 
            module.register()

def unregister():
    for module in reversed(module_list):
        if hasattr(module, "unregister"): 
            module.unregister()

def update():
    
    for module in module_list: # 执行所有子模块的刷新
        if hasattr(module, "update"): 
            module.update()
    
    unregister()
    for module in module_list: # 重载所有子模块
        importlib.reload(module)
    register()