# csv_to_en_us.py
# 将翻译 CSV 转回 en_US.py 格式。
# 用法: python csv_to_en_us.py [input.csv] [output_en_US.py]

import csv, sys, os

INPUT_CSV = sys.argv[1] if len(sys.argv) > 1 else "translations.csv"
OUTPUT_PY = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "translation", "en_US.py"
)

# ── 分类模板：context -> section header ──
SECTION_ORDER = [
    ("button_text",      "# ====== Operator button texts ====="),
    ("tool_label",       "# ====== Tool labels (tool.label) ====="),
    ("property_name",    "# ====== Property names ====="),
    ("property_desc",    "# ====== Property descriptions ====="),
    ("prefs_desc",       "# ====== Property descriptions ====="),
    ("enum_item",        "# ====== Enum item names ====="),
    ("enum_desc",        "# ====== Enum item descriptions ====="),
    ("draw_label",       "# ====== draw_panel label texts ====="),
    ("status_text",      "# ====== status_text_set ====="),
    ("hud_text",         "# ====== GPU HUD texts ====="),
    ("undo_message",     "# ====== undo_push messages ====="),
    ("report",           "# ====== report messages ====="),
    ("error_prefix",     "# ====== Print error prefixes ====="),
    ("prefs_label",      "# ====== Preferences ====="),
    ("other",            "# ====== Other ====="),
]

section_groups = {}
for ctx, header in SECTION_ORDER:
    section_groups.setdefault((header,), [])

def escape_val(v):
    return v.replace("\\", "\\\\").replace('"', '\\"')

rows = []
with open(INPUT_CSV, encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for row in reader:
        chinese = row.get("chinese", "").strip()
        english = row.get("english", "").strip()
        ctx = row.get("context", "other").strip()
        if not chinese or not english:
            continue
        key = chinese.replace('"', '\\"')
        val = english.replace('"', '\\"')
        rows.append((ctx, key, val))

# 去重(同一中文可能在不同 context 出现)
seen = set()
unique = []
for ctx, key, val in rows:
    if (key, ctx) not in seen:
        seen.add((key, ctx))
        unique.append((ctx, key, val))

# 按 section 分组
grouped = {}
for ctx, header in SECTION_ORDER:
    grouped[ctx] = []

for ctx, key, val in unique:
    if ctx in grouped:
        grouped[ctx].append((key, val))
    else:
        grouped.setdefault("other", []).append((key, val))

lines = []
lines.append("data = {")

first_section = True
for ctx, header in SECTION_ORDER:
    entries = grouped.get(ctx, [])
    if not entries:
        continue
    if not first_section:
        lines.append("")
    lines.append(f"    {header}")
    for key, val in entries:
        lines.append(f'    "{key}": "{val}",')
    first_section = False

# 处理 other 分组
other_entries = grouped.get("other", [])
if other_entries:
    lines.append("")
    lines.append("    # ====== Other =====")
    for key, val in other_entries:
        lines.append(f'    "{key}": "{val}",')

lines.append("}")

with open(OUTPUT_PY, 'w', encoding='utf-8') as f:
    f.write("\n".join(lines) + "\n")

total = sum(len(v) for v in grouped.values())
print(f"Wrote {total} entries -> {OUTPUT_PY}")
