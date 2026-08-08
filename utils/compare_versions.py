
import bpy
import re

def parse_version_to_list(ver_str):
    # 万能版本解析：从任意混乱字符串中提取【连续数字段】作为版本号
    # 自动标准化为 5 位数字数组，不足补 0，超出截前 5
    if not ver_str or not isinstance(ver_str, str):
        return [0, 0, 0, 0, 0]
    # 提取所有【连续数字块】，忽略所有字母、中文、符号、分隔符
    number_parts = re.findall(r'(\d+)', ver_str.lower())
    parts = []
    for p in number_parts:
        try:
            parts.append(int(p))
        except:
            parts.append(0)

    # 标准化规则
    parts = parts[:5]   # 超过 5 段 → 只留前 5
    while len(parts) < 5:
        parts.append(0)  # 不足 5 段 → 向后补 0 到 5 位
    return parts

def is_version_older(ver_a, ver_b):
    # 判断 ver_a 是否 < ver_b
    # return True/False
    a_parts = parse_version_to_list(ver_a)
    b_parts = parse_version_to_list(ver_b)
    # 逐位比较
    for a, b in zip(a_parts, b_parts):
        if a < b:
            return True
        if a > b:
            return False
    return False  # 相等
