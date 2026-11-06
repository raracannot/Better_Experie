# 选择类工具共用的「参考方向」
#
# 循环边 / 并排边环 / 循环面 的 A/B 在几何上各不相同（边端点 / 跨面横向 / 条带前后），
# 所以这里只提供两件事：
#   1. 把一个「可解释的规则名」换算成物体局部空间的方向向量；
#   2. 用 dot 给候选方向排序（谁的贴合度高谁就是 A 端）。
# 各工具自己负责算出「第一步方向」，再交给 rank_by_reference() 排序。

from mathutils import Vector

# 三个模块共用同一份枚举，避免以后各改各的、默认值漂移
DIR_RULE_ITEMS = (
    ('SCREEN_LEFT', "屏幕左", "A 端 = 朝屏幕左边延伸的那一端（转视角会变）"),
    ('SCREEN_UP', "屏幕上", "A 端 = 朝屏幕上方延伸的那一端（转视角会变）"),
    ('WORLD_X', "世界 +X", "A 端 = 朝世界 +X 的那一端（稳定、可复现）"),
    ('WORLD_Y', "世界 +Y", "A 端 = 朝世界 +Y 的那一端（稳定、可复现）"),
    ('WORLD_Z', "世界 +Z", "A 端 = 朝世界 +Z 的那一端（稳定、可复现）"),
    ('STORAGE', "存储顺序", "旧行为：A = bmesh 存储顺序里的第一个"),
)

DIR_RULE_DEFAULT = 'SCREEN_LEFT'

_DIR_RULE_LABELS = {
    'SCREEN_LEFT': '屏幕左',
    'SCREEN_UP': '屏幕上',
    'WORLD_X': '世界+X',
    'WORLD_Y': '世界+Y',
    'WORLD_Z': '世界+Z',
    'STORAGE': '存储顺序',
}

_WORLD_AXES = {
    'WORLD_X': (1.0, 0.0, 0.0),
    'WORLD_Y': (0.0, 1.0, 0.0),
    'WORLD_Z': (0.0, 0.0, 1.0),
}


def rule_label(rule):
    """状态栏用的短名"""
    return _DIR_RULE_LABELS.get(rule, '屏幕左')


def _view_region_3d(context):
    """尽量拿到 3D 视图的 region_3d；顶栏/无视图上下文时返回 None"""
    rv3d = getattr(context, "region_data", None)
    if rv3d is not None:
        return rv3d
    space = getattr(context, "space_data", None)
    return getattr(space, "region_3d", None) if space is not None else None


def reference_vector(context, obj, rule):
    """按规则返回「物体局部空间」里的参考方向；None 表示沿用 bmesh 存储顺序。

    换到局部空间再比较，是为了在有缩放/镜像的物体上也不会判反。
    """
    if rule == 'STORAGE':
        return None

    if rule in _WORLD_AXES:
        world = Vector(_WORLD_AXES[rule])
    else:
        # 屏幕系：视图空间 -X = 屏幕左，+Y = 屏幕上
        is_up = (rule == 'SCREEN_UP')
        view_dir = Vector((0.0, 1.0, 0.0)) if is_up else Vector((-1.0, 0.0, 0.0))
        rv3d = _view_region_3d(context)
        if rv3d is None:
            # 没有视图上下文时退回世界轴（屏幕左≈-X，屏幕上≈+Z）
            world = Vector((0.0, 0.0, 1.0)) if is_up else Vector((-1.0, 0.0, 0.0))
        else:
            # view_matrix 是 世界→视图，逆变换把「视图空间方向」搬回世界
            world = rv3d.view_matrix.to_3x3().inverted() @ view_dir

    if world.length < 1e-9:
        return None

    local = obj.matrix_world.inverted().to_3x3() @ world
    return local if local.length > 1e-9 else None


def score(vec_local, ref_local):
    """候选方向与参考方向的贴合度；任一不可用时返回 0（保持原有顺序）"""
    if ref_local is None or vec_local is None:
        return 0.0
    if vec_local.length < 1e-9:
        return 0.0
    return vec_local.normalized().dot(ref_local)


def rank_by_reference(items, direction_of, ref_local):
    """按贴合度降序返回 items（稳定排序）；ref 为 None 时原样返回。

    direction_of(item) 返回该项的「第一步方向」（局部空间向量），拿不到时返回 None。
    """
    items = list(items)
    if ref_local is None or len(items) < 2:
        return items
    items.sort(key=lambda item: score(direction_of(item), ref_local), reverse=True)
    return items
