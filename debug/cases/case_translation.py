# -*- coding: utf-8 -*-
"""翻译表一致性：中文覆盖表必须落在英文表里，关键文案不能漏。"""

# 这些键必须存在（按钮文案）
CRITICAL = (
    "强制更新",
    "优化加速",
    "一键文件输出",
    "智能模板表达式",
)


def run(context):
    results = []

    en = context["find_module"]("translation.en_US")
    zh = context["find_module"]("translation.zh_HANS")
    if en is None or zh is None:
        return [{"name": "翻译模块", "ok": False, "detail": "en_US / zh_HANS 未加载"}]

    en_data = getattr(en, "data", None)
    zh_data = getattr(zh, "data", None)
    if not isinstance(en_data, dict) or not isinstance(zh_data, dict):
        return [{"name": "翻译模块", "ok": False, "detail": "缺少 data 字典"}]

    results.append({"name": "英文词条 >= 200", "ok": len(en_data) >= 200,
                    "detail": f"{len(en_data)} from {getattr(en, '__name__', '?')} / zh={len(zh_data)} from {getattr(zh, '__name__', '?')}"})
    results.append({"name": "中文词条 >= 1000", "ok": len(zh_data) >= 1000,
                    "detail": str(len(zh_data))})

    only_en = sorted(set(en_data) - set(zh_data))
    only_zh = sorted(set(zh_data) - set(en_data))
    # 英文表是母表：中文里出现的键都必须有英文，允许极少数转义差异
    results.append({"name": "中文键都在英文表内（容差 6）", "ok": len(only_zh) <= 6,
                    "detail": f"仅中文 {len(only_zh)}: {only_zh[:4]}"})
    results.append({"name": "英文未翻译项 <= 60", "ok": len(only_en) <= 60,
                    "detail": f"仅英文 {len(only_en)}: {only_en[:4]}"})

    empty_values = [key for key, value in en_data.items() if not str(value).strip()]
    results.append({"name": "英文值非空", "ok": not empty_values, "detail": str(empty_values[:5])})

    missing = [key for key in CRITICAL if key not in en_data]
    results.append({"name": "关键文案已翻译", "ok": not missing, "detail": str(missing)})

    # 英文值里不该残留大段中文（漏翻）
    leftover = [key for key, value in en_data.items()
                if isinstance(value, str) and any('\u4e00' <= ch <= '\u9fff' for ch in value)]
    results.append({"name": "英文表无残留中文（<=3 条容忍）", "ok": len(leftover) <= 3,
                    "detail": f"{len(leftover)} 条: {leftover[:5]}"})

    return results
