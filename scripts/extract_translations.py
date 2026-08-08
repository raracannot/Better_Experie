# extract_translations.py
# 将插件源码中的所有中文字符串提取为 CSV，方便补翻和校对。
# 用法: python extract_translations.py [addon_root_dir] [output.csv]

import re, os, sys, csv

ADDON_ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ADDON_ROOT, "translations.csv")

# ── 加载现有翻译 ──
existing = {}
en_us_path = os.path.join(ADDON_ROOT, "translation", "en_US.py")
if os.path.isfile(en_us_path):
    ns = {}
    with open(en_us_path, encoding="utf-8") as f:
        exec(f.read(), ns)
    existing = ns.get("data", {})

# ── 扫描源码 ──
ZH_RE = re.compile(r'[\u4e00-\u9fff]')
CONTEXT_LABELS = {
    "button_text":     'Operator 按钮文本',
    "tool_label":      'Tool 标签',
    "property_name":   '属性名',
    "property_desc":   '属性描述',
    "enum_item":       '枚举项名',
    "enum_desc":       '枚举描述',
    "draw_label":      'Panel 标签',
    "status_text":     '状态栏文本',
    "hud_text":        'GPU HUD 文本',
    "undo_message":    '撤销消息',
    "report":          '报告消息',
    "error_prefix":    '错误前缀',
    "prefs_label":     '偏好设置标签',
    "prefs_desc":      '偏好设置描述',
    "other":           '其他',
}

found = {}  # chinese_text -> {context, filepath, line}

def add_entry(text, context, filepath, line):
    text = text.strip()
    if not ZH_RE.search(text):
        return
    key = text
    if key not in found:
        found[key] = {"context": context, "files": [], "lines": []}
    found[key]["files"].append(os.path.relpath(filepath, ADDON_ROOT))
    found[key]["lines"].append(str(line))


def scan_file(filepath):
    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()

    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not ZH_RE.search(line):
            continue
        if line.startswith("#") and not any(kw in line for kw in ["text=", "name=", "label", "description=", "message"]):
            continue

        # ── pattern 1: text="中文" ──
        for m in re.finditer(r'\btext\s*=\s*["\']([^"\']*[\u4e00-\u9fff][^"\']*)["\']', raw):
            ctx = "button_text"
            if "row.prop" in raw or "layout.prop" in raw or "col.prop" in raw or "box.prop" in raw:
                ctx = "property_name"
            elif "layout.label" in raw or "box.label" in raw or "row.label" in raw or "col.label" in raw or "header.label" in raw:
                ctx = "draw_label"
            add_entry(m.group(1), ctx, filepath, lineno)

        # ── pattern 2: name="中文" (properties) ──
        for m in re.finditer(r'\bname\s*=\s*["\']([^"\']*[\u4e00-\u9fff][^"\']*)["\']', raw):
            if m.group(1) not in found or found[m.group(1)]["context"] == "other":
                add_entry(m.group(1), "property_name", filepath, lineno)

        # ── pattern 3: description="中文" ──
        for m in re.finditer(r'\bdescription\s*=\s*["\']([^"\']*[\u4e00-\u9fff][^"\']*)["\']', raw):
            ctx = "property_desc"
            if "prefs" in raw.lower() or "preferences" in raw.lower():
                ctx = "prefs_desc"
            add_entry(m.group(1), ctx, filepath, lineno)

        # ── pattern 4: label = '中文' (tool label) ──
        for m in re.finditer(r'''\blabel\s*=\s*["']([^"']*[\u4e00-\u9fff][^"']*)["']''', raw):
            if m.group(1) in found:
                continue
            if "class " in raw:
                ctx = "tool_label"
            elif "bl_label" in raw:
                ctx = "button_text"
            else:
                ctx = "other"
            add_entry(m.group(1), ctx, filepath, lineno)

        # ── pattern 5: bl_label = "中文" ──
        for m in re.finditer(r'''bl_label\s*=\s*["']([^"']*[\u4e00-\u9fff][^"']*)["']''', raw):
            add_entry(m.group(1), "button_text", filepath, lineno)

        # ── pattern 6: message="中文" (undo_push) ──
        for m in re.finditer(r'''\bmessage\s*=\s*["']([^"']*[\u4e00-\u9fff][^"']*)["']''', raw):
            add_entry(m.group(1), "undo_message", filepath, lineno)

        # ── pattern 7: status_text_set("中文") ──
        for m in re.finditer(r'''status_text_set\s*\(\s*["']([^"']*[\u4e00-\u9fff][^"']*)["']''', raw):
            add_entry(m.group(1), "status_text", filepath, lineno)

        # ── pattern 8: self.report({'WARNING'}, "中文") ──
        for m in re.finditer(r'''report\s*\(\s*\{.*?\}\s*,\s*["']([^"']*[\u4e00-\u9fff][^"']*)["']''', raw):
            add_entry(m.group(1), "report", filepath, lineno)

        # ── pattern 9: state.current_tool = 'warp:中文' ──
        for m in re.finditer(r'''current_tool\s*=\s*["'](warp:[^"']*[\u4e00-\u9fff][^"']*)["']''', raw):
            add_entry(m.group(1), "other", filepath, lineno)

        # ── pattern 10: pget_tmpl("中文模板") ──
        for m in re.finditer(r'''pget_tmpl\s*\(\s*["']([^"']*[\u4e00-\u9fff][^"']*)["']''', raw):
            add_entry(m.group(1), "hud_text", filepath, lineno)

        # ── pattern 11: print(f"[中文] ...") error prefix ──
        for m in re.finditer(r'''print\s*\(\s*(?:f)?["']\[([^\[\]]*[\u4e00-\u9fff][^\[\]]*)\][^"']*["']''', raw):
            add_entry(f"[{m.group(1)}]", "error_prefix", filepath, lineno)

        # ── pattern 12: operator("id", text="中文") in context ──
        for m in re.finditer(r'''\.operator\s*\(\s*["'][^"']*["']\s*,\s*text\s*=\s*["']([^"']*[\u4e00-\u9fff][^"']*)["']''', raw):
            add_entry(m.group(1), "button_text", filepath, lineno)


# ── 遍历文件 ──
for dn, _, files in os.walk(ADDON_ROOT):
    for fn in files:
        if not fn.endswith('.py'):
            continue
        if '__pycache__' in dn or '.git' in dn or '.opencode' in dn or '\\note' in dn or '\\history_bak' in dn or '\\utils\\bak' in dn:
            continue
        if fn.endswith('.py') and fn not in ['en_US.py', 'zh_HANS.py']:
            scan_file(os.path.join(dn, fn))
        # also scan translation files for their keys
        if fn in ('en_US.py',):
            fp = os.path.join(dn, fn)
            # already loaded at top
            continue

# ── 输出 CSV ──
with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8-sig') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["context", "context_label", "chinese", "english", "source_file:line"])
    for chinese in sorted(found.keys()):
        info = found[chinese]
        ctx = info["context"]
        ctx_label = CONTEXT_LABELS.get(ctx, ctx)
        eng = existing.get(chinese, "")
        src = "; ".join(f"{f}:{l}" for f, l in zip(info["files"], info["lines"]))
        writer.writerow([ctx, ctx_label, chinese, eng, src])

print(f"Extracted {len(found)} unique Chinese strings -> {OUTPUT_CSV}")
print(f"Existing translations: {len(existing)}")
print(f"Untranslated: {sum(1 for k in found if k not in existing)}")
