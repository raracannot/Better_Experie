# -*- coding: utf-8 -*-
"""强制更新：线路选择逻辑（纯逻辑，不联网）。"""


def run(context):
    fu = context["find_module"]("ops.other.other_force_update")
    if fu is None:
        return [{"name": "强制更新模块", "ok": False, "detail": "导入失败"}]

    results = []

    # 1) 只接受本机 / 私有地址
    cases = [
        ("http://127.0.0.1:7890", True),
        ("http://localhost:1080", True),
        ("http://192.168.1.5:8080", True),
        ("http://8.8.8.8:8080", False),
        ("https://example.com:443", False),
    ]
    bad = [text for text, expect in cases if bool(fu._normalize_proxy(text)) != expect]
    results.append({"name": "代理地址过滤（拒绝公网）", "ok": not bad, "detail": str(bad)})

    # 2) 尝试顺序：代理直连 → 代理+镜像 → 直连兜底
    attempts = fu._build_attempts(["http://127.0.0.1:7890"], ("https://m1/", "https://m2/"))
    expected = [
        ("http://127.0.0.1:7890", "", True),
        ("http://127.0.0.1:7890", "https://m1/", False),
        ("http://127.0.0.1:7890", "https://m2/", False),
        ("", "", False),
    ]
    results.append({"name": "线路尝试顺序", "ok": attempts == expected, "detail": str(attempts)})

    # 3) 限流识别
    results.append({
        "name": "403/429 限流识别",
        "ok": fu._is_rate_limited("HTTP Error 403: rate limit exceeded")
        and not fu._is_rate_limited("Connection refused"),
        "detail": "",
    })

    # 4) 没有任何代理时快速返回（把候选来源换成空，避免真的去探端口/读注册表）
    real_collect = fu._collect_proxies
    real_cache = dict(fu._ROUTE_CACHE)
    try:
        fu._collect_proxies = lambda: ([], "")
        fu._ROUTE_CACHE.update(time=0.0, proxies=[], tried=0, note="")
        import time as _time
        started = _time.time()
        proxies, tried, _note = fu._find_proxies()
        cost = _time.time() - started
    finally:
        fu._collect_proxies = real_collect
        fu._ROUTE_CACHE.update(real_cache)

    results.append({"name": "无代理时返回空", "ok": proxies == [], "detail": str(proxies)})
    results.append({"name": "无代理时不拖时间", "ok": cost < 2.0, "detail": f"{cost:.2f}s"})

    # 5) 版本 / 大小 / 线路文案这些纯函数
    results.append({"name": "版本解析 v1.2.3",
                    "ok": fu._parse_version("v1.2.3") == (1, 2, 3),
                    "detail": str(fu._parse_version("v1.2.3"))})
    results.append({"name": "版本解析空串",
                    "ok": fu._parse_version("") == (0, 0, 0),
                    "detail": str(fu._parse_version(""))})
    results.append({"name": "版本格式化",
                    "ok": fu._fmt_version((1, 2, 1)) == "1.2.1",
                    "detail": fu._fmt_version((1, 2, 1))})
    results.append({"name": "字节格式化",
                    "ok": fu._human_size(512).endswith("B")
                    and "KB" in fu._human_size(1536)
                    and "MB" in fu._human_size(5 * 1024 * 1024),
                    "detail": f"{fu._human_size(512)} / {fu._human_size(1536)}"})
    results.append({"name": "线路文案非空",
                    "ok": isinstance(fu._route_label(), str) and bool(fu._route_label()),
                    "detail": fu._route_label()})
    results.append({"name": "线路缓存 5 分钟",
                    "ok": fu.PROXY_CACHE_SECONDS == 300,
                    "detail": str(fu.PROXY_CACHE_SECONDS)})

    return results
