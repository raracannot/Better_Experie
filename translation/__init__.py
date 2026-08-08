
# Blender 多语言支持模块

import re
import ast
import bpy

TRANSLATION_DOMAIN = "better_experie"

_lang_modules = {}
for _mod_name in ('zh_HANS', 'en_US'):
    try:
        _mod = __import__(f'{__package__}.{_mod_name}', fromlist=['data'])
        _lang_modules[_mod_name] = _mod.data
    except ImportError:
        pass

langs = {
    "zh_CN": _lang_modules.get('zh_HANS', {}),
    "zh_HANS": _lang_modules.get('zh_HANS', {}),
    "en_GB": _lang_modules.get('en_US', {}),
    "en_US": _lang_modules.get('en_US', {}),
}


def get_language_list() -> list:
    try:
        bpy.context.preferences.view.language = ""
    except TypeError as e:
        matches = re.findall(r"\(([^()]*)\)", e.args[-1])
        return ast.literal_eval(f"({matches[-1]})")


def _build_translations(data: dict, lang: str) -> dict:
    convert = {}
    for src, src_trans in data.items():
        for ctx in ("*", "Operator", TRANSLATION_DOMAIN):
            convert.setdefault(lang, {})[(ctx, src)] = src_trans
    return convert


def register():
    global _registered
    all_languages = get_language_list()
    combined = {}
    for lang_code, data in langs.items():
        if lang_code in all_languages and data:
            trans = _build_translations(data, lang_code)
            for lang, entries in trans.items():
                combined.setdefault(lang, {}).update(entries)
    if combined:
        try:
            bpy.app.translations.register(TRANSLATION_DOMAIN, combined)
            _registered = True
        except ValueError:
            pass


def unregister():
    global _registered
    if _registered:
        try:
            bpy.app.translations.unregister(TRANSLATION_DOMAIN)
        except ValueError:
            pass
        _registered = False


_registered = False
