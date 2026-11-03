# 强制更新：从 GitHub Release 下载最新安装包，整体覆盖当前插件目录

import hashlib
import json
import os
import re
import shutil
import socket
import ssl
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile

import bpy

from ... import bl_info as _BL_INFO

REPO = "raracannot/Better_Experie"
PROJECT_URL = f"https://github.com/{REPO}"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"

# 本地版本以插件根的 bl_info 为准（与【检查更新】看到的插件版本是同一个来源）
LOCAL_VERSION = tuple(_BL_INFO.get("version") or (0, 0, 0))

# 暂存 / 备份目录固定放在 addons 根目录下：同盘 rename 是原子的，且以 "." 开头
# 不会被 Blender 当成插件扫描（addon_utils 只扫描含 __init__.py 的普通目录）。
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ADDONS_ROOT = os.path.dirname(ADDON_DIR)
STAGING_DIR = os.path.join(ADDONS_ROOT, ".better_experie_staging")
BACKUP_DIR = os.path.join(ADDONS_ROOT, ".better_experie_backup")

# ---------------------------------------------------------------------------
# 内置下载参数（不做偏好设置，需要代理或换镜像时直接改这里）
# ---------------------------------------------------------------------------
PROXY = ""                              # 例："http://127.0.0.1:7890"，留空则直连
MIRRORS = (                             # 直连过慢或失败时的兜底前缀，内容仍走官方 sha256 校验
    "https://ghfast.top/",
    "https://gh-proxy.com/",
)
TIMEOUT = 30                            # 单次网络读写超时（秒）

# 线路选择：只在**本机**找代理（手动常量 / 系统代理 / 环境变量 / 常见端口），
# 绝不使用公网代理——把流量交给来路不明的代理是隐私事故。
PROXY_PROBE_TIMEOUT = 0.3               # 本地端口连通性探测（并行，总耗时≈这个值）
PROXY_CHECK_TIMEOUT = 6                 # 通过代理验证"真的能取到数据"
PROXY_SAMPLE_BYTES = 256 * 1024         # 判定"最优"时的吞吐抽样大小
PROXY_SAMPLE_TIMEOUT = 20
PROXY_CACHE_SECONDS = 300               # 延迟探测结果缓存（吞吐每次都实测）
PROXY_PROBE_PORTS = (
    7890, 7891, 7897, 1080, 1081, 10808, 10809, 8889, 2080, 8080, 8118, 3128, 57379,
)
DIRECT_TIMEOUT = 8                      # 先试直连；失败才去找代理
DOWNLOAD_BUDGET = 150                   # 所有线路都毫无进展时的总预算（秒）

CHUNK_SIZE = 64 * 1024
MAX_ATTEMPTS_PER_SOURCE = 2

# 直连速度探测：下载开始 6 秒后若低于 60 KB/s 且有备用源，立刻换源（已下载部分保留续传）
SLOW_PROBE_SECONDS = 6.0
SLOW_PROBE_BYTES_PER_SEC = 60 * 1024
SLOW_PROBE_MIN_BYTES = 512 * 1024


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _parse_version(text):
    """从任意版本字符串里提取前三段数字，缺位补 0。"""
    nums = re.findall(r"\d+", str(text or ""))
    if not nums:
        return (0, 0, 0)
    nums = [int(n) for n in nums[:3]]
    nums += [0] * (3 - len(nums))
    return tuple(nums)


def _fmt_version(version):
    """把版本元组格式化成 1.2.0 这样的字符串。"""
    return ".".join(str(int(n)) for n in version)


def _human_size(size):
    """把字节数格式化成可读大小。"""
    size = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} GB"


def _rmtree(path):
    """安静地删除目录，删不掉再抛错。"""
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
        if os.path.isdir(path):
            raise RuntimeError(f"无法删除目录：{path}")


def _has_git_dir():
    """判断当前插件目录是不是 git 工作副本（用于开发副本保护提示）。"""
    return os.path.isdir(os.path.join(ADDON_DIR, ".git"))


class _Cancelled(Exception):
    """用户取消了下载。"""


class _DownloadError(Exception):
    """下载失败。"""


class _ChecksumError(_DownloadError):
    """sha256 校验失败：包内容不对，换源重试没有意义，直接终止。"""


class _SlowSource(Exception):
    """当前源太慢，换下一个源（已下载的 .part 保留，可续传）。"""


# ---------------------------------------------------------------------------
# 网络层
# ---------------------------------------------------------------------------

def _ssl_context():
    """优先用 certifi 的证书链，Blender 自带的 Python 不一定带系统根证书。"""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _open(url, headers=None, timeout=30, proxy=""):
    """带上 UA / 证书链 / 可选代理的 urlopen。"""
    hdrs = {"User-Agent": f"Better_Experie-ForceUpdate/{_fmt_version(LOCAL_VERSION)} (+{PROJECT_URL})"}
    if headers:
        hdrs.update(headers)

    if proxy:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        opener = urllib.request.build_opener(handler, urllib.request.HTTPSHandler(context=_ssl_context()))
    else:
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl_context()))

    request = urllib.request.Request(url, headers=hdrs)
    return opener.open(request, timeout=timeout)


# ---------------------------------------------------------------------------
# 线路选择：直连 / 本机代理 / 镜像
# ---------------------------------------------------------------------------

_ROUTE = {"proxy": "", "label": "直连", "detail": ""}
_ROUTE_CACHE = {"time": 0.0, "proxies": [], "tried": 0, "note": ""}


def _is_local_host(host):
    """只接受本机 / 私有网段，避免把流量交给来路不明的代理。"""
    host = (host or "").strip().lower()
    if not host:
        return False
    if host in ("localhost", "::1"):
        return True
    if host.startswith(("127.", "10.", "192.168.")):
        return True
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
        except (IndexError, ValueError):
            return False
        return 16 <= second <= 31
    return False


def _normalize_proxy(text):
    """把 127.0.0.1:7890 / http://host:port 统一成 http://host:port；非本机返回空。"""
    text = (text or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if not parts.hostname or not parts.port or not _is_local_host(parts.hostname):
        return ""
    return f"http://{parts.hostname}:{parts.port}"


def _system_proxy():
    """读 Windows 系统代理；PAC 模式不解析，只返回一条提示。"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
    except (ImportError, OSError):
        return "", ""
    try:
        try:
            enable = winreg.QueryValueEx(key, "ProxyEnable")[0]
            server = str(winreg.QueryValueEx(key, "ProxyServer")[0])
        except OSError:
            return "", ""
        try:
            auto = str(winreg.QueryValueEx(key, "AutoConfigURL")[0])
        except OSError:
            auto = ""
    finally:
        try:
            winreg.CloseKey(key)
        except Exception:
            pass

    if auto:
        return "", "检测到 PAC 自动配置，暂不解析，可手动填写代理地址"
    if not enable or not server:
        return "", ""
    for chunk in server.split(";"):          # 形如 http=127.0.0.1:7890;https=127.0.0.1:7890
        if "=" in chunk:
            kind, _, value = chunk.partition("=")
            if kind.strip().lower() in ("https", "http"):
                return _normalize_proxy(value), ""
        else:
            return _normalize_proxy(chunk), ""
    return "", ""


def _env_proxies():
    """环境变量里的代理（很多工具会设 HTTPS_PROXY）。"""
    found = []
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
                 "ALL_PROXY", "all_proxy"):
        value = os.environ.get(name, "")
        if not value:
            continue
        proxy = _normalize_proxy(value)
        if proxy and proxy not in found:
            found.append(proxy)
    return found


def _port_proxies(timeout=PROXY_PROBE_TIMEOUT):
    """并行探测常见的本机代理端口（串行会因为超时拖慢好几秒）。"""
    alive = []
    lock = threading.Lock()

    def worker(port):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout):
                pass
        except OSError:
            return
        with lock:
            alive.append(port)

    threads = [threading.Thread(target=worker, args=(port,), daemon=True)
               for port in PROXY_PROBE_PORTS]
    for thread in threads:
        thread.start()
    deadline = time.time() + timeout + 0.2
    for thread in threads:
        thread.join(max(0.0, deadline - time.time()))
    return [f"http://127.0.0.1:{port}" for port in sorted(alive)]


def _collect_proxies():
    """候选线路：手动常量 > 系统代理 > 环境变量 > 本机常见端口。"""
    ordered = []
    notes = []

    manual = _normalize_proxy(PROXY)
    if manual:
        ordered.append(manual)

    system, note = _system_proxy()
    if note:
        notes.append(note)
    if system:
        ordered.append(system)

    ordered.extend(_env_proxies())
    ordered.extend(_port_proxies())

    unique = []
    for proxy in ordered:
        if proxy and proxy not in unique:
            unique.append(proxy)
    return unique, "；".join(notes)


def _proxy_ping(proxy):
    """通过代理真的取一次 GitHub API：既能验证可用，也能量出延迟。"""
    started = time.time()
    try:
        with _open(API_LATEST, {"Accept": "application/vnd.github+json"},
                   PROXY_CHECK_TIMEOUT, proxy) as response:
            if not response.read(2048):
                return False, 0.0, "空响应"
        return True, time.time() - started, ""
    except Exception as exc:
        return False, 0.0, str(exc)


def _is_rate_limited(text):
    """GitHub API 触发限流（403/429）时，别误报成"没有可用代理"。"""
    text = str(text or "").lower()
    return "403" in text or "429" in text or "rate limit" in text


def _proxy_speed(proxy, url, cancel):
    """抽样下载一小段，返回 KB/s；失败返回 0。"""
    started = time.time()
    got = 0
    headers = {"Accept": "application/octet-stream",
               "Accept-Encoding": "identity",
               "Range": f"bytes=0-{PROXY_SAMPLE_BYTES - 1}"}
    try:
        with _open(url, headers, PROXY_SAMPLE_TIMEOUT, proxy) as response:
            while got < PROXY_SAMPLE_BYTES:
                if cancel.is_set():
                    return 0.0
                block = response.read(CHUNK_SIZE)
                if not block:
                    break
                got += len(block)
    except Exception:
        return 0.0
    if not got:
        return 0.0
    return got / max(time.time() - started, 0.001) / 1024.0


def _find_proxies(asset_url="", cancel=None):
    """返回 (按"最优"排序的代理列表, 候选数, 附注)。

    没有安装包地址时只量延迟（快、几乎不耗流量）；拿到地址后对前两名做
    256KB 吞吐抽样，真正选出"最优"。延迟结果缓存 PROXY_CACHE_SECONDS 秒。
    """
    now = time.time()
    if not asset_url and _ROUTE_CACHE["proxies"] and now - _ROUTE_CACHE["time"] < PROXY_CACHE_SECONDS:
        return _ROUTE_CACHE["proxies"], _ROUTE_CACHE["tried"], _ROUTE_CACHE["note"]

    candidates, note = _collect_proxies()
    ranked = []
    errors = []
    for proxy in candidates:
        if cancel is not None and cancel.is_set():
            raise _Cancelled()
        ok, latency, error = _proxy_ping(proxy)
        if ok:
            ranked.append({"proxy": proxy, "latency": latency, "speed": 0.0})
        else:
            errors.append(error)
    ranked.sort(key=lambda item: item["latency"])
    if not ranked and errors:
        limit_hit = next((e for e in errors if _is_rate_limited(e)), "")
        note = "；".join([p for p in (note, limit_hit) if p])

    if asset_url and ranked[:2]:
        for item in ranked[:2]:
            item["speed"] = _proxy_speed(item["proxy"], asset_url, cancel or threading.Event())
        # 实测到速度的排前面（按速度降序），没测到的按延迟
        ranked.sort(key=lambda item: (item["speed"] <= 0, -item["speed"], item["latency"]))

    if not asset_url:
        _ROUTE_CACHE.update(time=now, proxies=ranked, tried=len(candidates), note=note)
    return ranked, len(candidates), note


def _build_attempts(proxies, mirrors):
    """(代理, 镜像前缀, 是否做慢速探测) 的尝试顺序。"""
    attempts = []
    mirror_list = [m for m in mirrors if m]
    for proxy in proxies:
        attempts.append((proxy, "", True))
        attempts.extend((proxy, mirror, False) for mirror in mirror_list)
    if "" not in proxies:
        attempts.append(("", "", False))     # 最后给直连留一次机会
    return attempts


def _route_label():
    """当前线路的可读文本。"""
    if not _ROUTE["proxy"]:
        return "直连"
    label = _ROUTE["label"] or _ROUTE["proxy"]
    return f"{label}（{_ROUTE['detail']}）" if _ROUTE["detail"] else label


def _sha256_of(path):
    """计算文件 sha256。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fetch_release(proxy="", timeout=30):
    """读取 GitHub 最新发布信息，返回版本、下载地址、大小与 sha256。"""
    with _open(API_LATEST, {"Accept": "application/vnd.github+json"}, timeout, proxy) as response:
        payload = json.loads(response.read().decode("utf-8"))

    assets = payload.get("assets") or []
    asset = next((a for a in assets if str(a.get("name", "")).lower().endswith(".zip")), None)
    if asset is None:
        raise RuntimeError("最新发布里没有 .zip 资产")

    digest = str(asset.get("digest") or "")
    sha = digest.split(":", 1)[1].strip().lower() if digest.lower().startswith("sha256:") else ""

    return {
        "tag": str(payload.get("tag_name") or ""),
        "version": _parse_version(payload.get("tag_name")),
        "url": asset["browser_download_url"],
        "name": asset.get("name") or "better_experie.zip",
        "size": int(asset.get("size") or 0),
        "sha256": sha,
        "published": payload.get("published_at") or "",
        "notes": (payload.get("body") or "").strip(),
    }


def _download_once(url, part_path, total_hint, on_progress, cancel, proxy, timeout, probe=False):
    """单次下载，支持 HTTP Range 续传。返回实际字节数。"""
    existing = os.path.getsize(part_path) if os.path.isfile(part_path) else 0
    headers = {"Accept": "application/octet-stream", "Accept-Encoding": "identity"}
    if existing:
        headers["Range"] = f"bytes={existing}-"

    response = _open(url, headers, timeout, proxy)
    try:
        status = getattr(response, "status", 200)
        if existing and status != 206:
            # 服务端不支持断点续传，从头来
            existing = 0
            response.close()
            response = _open(url, {"Accept": "application/octet-stream",
                                   "Accept-Encoding": "identity"}, timeout, proxy)

        total = 0
        content_range = response.headers.get("Content-Range") or ""
        if "/" in content_range:
            try:
                total = int(content_range.rsplit("/", 1)[1])
            except ValueError:
                total = 0
        if not total:
            length = response.headers.get("Content-Length") or ""
            if length.isdigit():
                total = existing + int(length)
        if not total:
            total = total_hint or 0

        done = existing
        started = time.time()
        on_progress(done, total, True)
        with open(part_path, "ab" if existing else "wb") as handle:
            while True:
                if cancel.is_set():
                    raise _Cancelled()
                block = response.read(CHUNK_SIZE)
                if not block:
                    break
                handle.write(block)
                done += len(block)
                on_progress(done, total, False)

                # 速度探测：太慢就放弃当前源，换下一个（.part 保留续传）
                if probe and total > SLOW_PROBE_MIN_BYTES and done < total:
                    elapsed = time.time() - started
                    if elapsed >= SLOW_PROBE_SECONDS:
                        rate = (done - existing) / max(elapsed, 0.001)
                        if rate < SLOW_PROBE_BYTES_PER_SEC:
                            raise _SlowSource(f"直连只有 {rate / 1024:.0f} KB/s，改用镜像")

                if total and done >= total:
                    break
        return done
    finally:
        try:
            response.close()
        except Exception:
            pass


def _download(url, dest_path, total_hint, sha256, on_progress, cancel, attempts, timeout):
    """带续传、重试、慢速换源、代理/镜像回退、sha256 校验的下载。"""
    part_path = dest_path + ".part"

    errors = []
    stalled_since = time.time()
    last_size = os.path.getsize(part_path) if os.path.isfile(part_path) else 0

    for proxy, prefix, probe in attempts:
        for attempt in range(MAX_ATTEMPTS_PER_SOURCE):
            if cancel.is_set():
                raise _Cancelled()

            target = (prefix + url) if prefix else url
            try:
                got = _download_once(target, part_path, total_hint, on_progress,
                                     cancel, proxy, timeout, probe)
                if total_hint and got < total_hint:
                    raise _DownloadError(f"数据不完整（{_human_size(got)} / {_human_size(total_hint)}）")
                if sha256:
                    actual = _sha256_of(part_path)
                    if actual != sha256:
                        os.remove(part_path)
                        raise _ChecksumError(
                            f"sha256 校验失败（期望 {sha256[:12]}…，实际 {actual[:12]}…）")
                os.replace(part_path, dest_path)
                return
            except _Cancelled:
                raise
            except _ChecksumError:
                raise  # 内容不对，不换源重试
            except _SlowSource as exc:
                errors.append(str(exc))
                break  # 立刻换源，不重试当前源
            except Exception as exc:
                errors.append(f"{prefix or '直连'}: {exc}")
                time.sleep(1.2 * (attempt + 1))

            # 只要多下到一点，就重置"毫无进展"的计时
            size = os.path.getsize(part_path) if os.path.isfile(part_path) else 0
            if size > last_size:
                last_size = size
                stalled_since = time.time()

        if time.time() - stalled_since > DOWNLOAD_BUDGET:
            errors.append(f"已等待 {int(DOWNLOAD_BUDGET)} 秒仍无进展，停止尝试")
            break

    raise _DownloadError("；".join(errors[-3:]) or "下载失败")


# ---------------------------------------------------------------------------
# 安装（覆盖自身）
# ---------------------------------------------------------------------------

def _locate_package_root(root):
    """zip 可能平铺，也可能带一层外壳目录；返回真正的插件根目录。"""
    if os.path.isfile(os.path.join(root, "__init__.py")):
        return root
    entries = [name for name in os.listdir(root) if not name.startswith("__MACOSX")]
    dirs = [name for name in entries if os.path.isdir(os.path.join(root, name))]
    if len(dirs) == 1 and os.path.isfile(os.path.join(root, dirs[0], "__init__.py")):
        return os.path.join(root, dirs[0])
    raise RuntimeError("压缩包里没有找到插件入口 __init__.py")


def _validate_package(root):
    """校验 manifest 里的插件 id，避免把别的插件包铺进来。"""
    manifest = os.path.join(root, "blender_manifest.toml")
    if not os.path.isfile(manifest):
        return
    try:
        with open(manifest, "r", encoding="utf-8") as handle:
            text = handle.read()
    except Exception:
        return
    match = re.search(r'^\s*id\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match and match.group(1).strip() != "better_experie":
        raise RuntimeError(f"这不是 Better_Experie 的安装包（id={match.group(1)}）")


def _install_from_zip(zip_path, addon_dir):
    """解压 -> 校验 -> 备份旧目录 -> 原子替换。失败时回滚。"""
    _rmtree(STAGING_DIR)
    os.makedirs(STAGING_DIR, exist_ok=True)

    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(STAGING_DIR)

    package_root = _locate_package_root(STAGING_DIR)
    _validate_package(package_root)

    _rmtree(BACKUP_DIR)
    os.rename(addon_dir, BACKUP_DIR)
    try:
        shutil.move(package_root, addon_dir)
        if not os.path.isfile(os.path.join(addon_dir, "__init__.py")):
            raise RuntimeError("替换后找不到 __init__.py")
    except Exception:
        _rmtree(addon_dir)
        os.rename(BACKUP_DIR, addon_dir)
        raise
    finally:
        _rmtree(STAGING_DIR)


# ---------------------------------------------------------------------------
# 任务状态（线程 <-> UI 的唯一通道）
# ---------------------------------------------------------------------------

_LOCK = threading.RLock()
_CANCEL = threading.Event()
_ACTIVE = {"running": False}
_STATE = {
    "phase": "idle",        # idle / checking / ready / downloading / installing / done / error
    "message": "",
    "detail": "",
    "progress": 0.0,
    "remote": None,
    "notified": True,
}


def _snapshot():
    """线程安全地取一份状态副本。"""
    with _LOCK:
        return dict(_STATE)


def _update(**kwargs):
    """线程安全地更新状态。"""
    with _LOCK:
        _STATE.update(kwargs)


def _is_newer(remote_version, local_version):
    """线上版本是否比本地新。"""
    size = max(len(remote_version), len(local_version))
    lhs = tuple(remote_version) + (0,) * (size - len(remote_version))
    rhs = tuple(local_version) + (0,) * (size - len(local_version))
    return lhs > rhs


def _run_job(job):
    """把耗时任务丢到后台线程，避免卡住界面。"""
    def runner():
        try:
            job()
        except _Cancelled:
            _update(phase="idle", message="已取消", detail="", progress=0.0)
        except Exception as exc:
            _update(phase="error", message=f"{exc}", detail="", progress=0.0, notified=False)
        finally:
            _ACTIVE["running"] = False

    _ACTIVE["running"] = True
    threading.Thread(target=runner, daemon=True).start()


def _job_check():
    """查询线上最新发布：先直连，失败再自动找本机代理。"""
    _update(phase="checking", message="正在检查线上版本…", detail="直连…", progress=0.0)
    _ROUTE.update(proxy="", label="直连", detail="")

    release = None
    direct_error = ""
    try:
        release = _fetch_release(proxy="", timeout=DIRECT_TIMEOUT)
    except Exception as exc:
        direct_error = str(exc)
        _update(detail="直连失败，正在寻找本机代理…")

    if release is None:
        proxies, tried, note = _find_proxies(cancel=_CANCEL)
        if not proxies:
            if _is_rate_limited(direct_error) or _is_rate_limited(note):
                raise RuntimeError("GitHub API 触发限流（403/429），请过一会儿再试")
            detail = f"直连失败，且没有发现可用的本机代理（候选 {tried} 个）"
            if note:
                detail = f"{detail}；{note}"
            raise RuntimeError(detail)
        last_error = None
        for item in proxies:
            if _CANCEL.is_set():
                raise _Cancelled()
            _update(detail=f"尝试 {item['proxy'].split('://', 1)[-1]}…")
            try:
                release = _fetch_release(proxy=item["proxy"], timeout=PROXY_CHECK_TIMEOUT + 6)
                _ROUTE.update(
                    proxy=item["proxy"],
                    label=item["proxy"].split("://", 1)[-1],
                    detail=f"{int(item['latency'] * 1000)}ms",
                )
                break
            except Exception as exc:
                last_error = exc
        if release is None:
            raise RuntimeError(f"直连与 {len(proxies)} 个本机代理都没能连上 GitHub（{last_error}）")

    if _is_newer(release["version"], LOCAL_VERSION):
        message = f"发现新版本 {release['tag']}"
    else:
        message = f"线上版本 {release['tag']}，将强制重装"

    _update(
        phase="ready",
        remote=release,
        message=f"{message} · 线路 {_route_label()}",
        detail=f"{release['name']} · {_human_size(release['size'])}",
        progress=0.0,
    )


def _job_install():
    """下载并覆盖安装。"""
    with _LOCK:
        release = _STATE["remote"]
    if not release:
        raise RuntimeError("还没有获取到线上的版本信息")

    temp_dir = tempfile.mkdtemp(prefix="better_experie_")
    zip_path = os.path.join(temp_dir, release["name"])

    started = time.time()
    last = {"time": 0.0}

    def on_progress(done, total, reset):
        now = time.time()
        if not reset and now - last["time"] < 0.12 and done != total:
            return
        last["time"] = now
        ratio = (done / total) if total else 0.0
        speed = done / max(now - started, 0.001)
        _update(
            progress=min(ratio, 1.0),
            detail=f"{_human_size(done)} / {_human_size(total)} · {_human_size(speed)}/s",
        )

    try:
        _update(phase="downloading", message=f"正在下载 {release['tag']}…", detail="", progress=0.0)

        # 有了安装包地址，才对前两名代理做真实吞吐抽样，选出真正最快的那条
        proxies = [""]
        if _ROUTE["proxy"]:
            ranked, _tried, _note = _find_proxies(asset_url=release["url"], cancel=_CANCEL)
            proxies = [item["proxy"] for item in ranked[:2]] or [_ROUTE["proxy"]]
            if _ROUTE["proxy"] in proxies:
                proxies.remove(_ROUTE["proxy"])
                proxies.insert(0, _ROUTE["proxy"])
        _download(release["url"], zip_path, release["size"], release["sha256"],
                  on_progress, _CANCEL, _build_attempts(proxies, MIRRORS), TIMEOUT)

        _update(phase="installing", message="正在安装…", detail="", progress=1.0)
        _install_from_zip(zip_path, ADDON_DIR)

        _update(
            phase="done",
            message=f"已更新到 {release['tag']}，请重启 Blender",
            detail=f"旧版本备份：{BACKUP_DIR}",
            progress=1.0,
            notified=False,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# UI 回调
# ---------------------------------------------------------------------------

def _progress_begin():
    try:
        bpy.context.window_manager.progress_begin(0, 100)
    except Exception:
        pass


def _progress_update(state):
    try:
        bpy.context.window_manager.progress_update(int(state.get("progress", 0.0) * 100))
    except Exception:
        pass


def _progress_end():
    try:
        bpy.context.window_manager.progress_end()
    except Exception:
        pass


def _redraw():
    """重绘视口与偏好设置区域，让进度和按钮文案实时刷新。"""
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type in {'VIEW_3D', 'PREFERENCES'}:
                    area.tag_redraw()
    except Exception:
        pass


def _notify(title, text, icon='INFO'):
    """任务结束后弹一次提示。"""
    try:
        window_manager = bpy.context.window_manager

        def draw(menu, _context):
            column = menu.layout.column(align=True)
            for line in text.splitlines()[:6]:
                column.label(text=line)

        window_manager.popup_menu(draw, title=title, icon=icon)
    except Exception:
        pass


def _timer():
    """轮询后台任务状态，驱动进度条与提示。"""
    state = _snapshot()
    if _ACTIVE["running"]:
        _progress_update(state)
        _redraw()
        return 0.25

    _progress_end()
    _redraw()
    if not state.get("notified", True):
        _update(notified=True)
        if state["phase"] == "done":
            _notify("Better_Experie 更新完成", state["message"], 'CHECKMARK')
        elif state["phase"] == "error":
            _notify("Better_Experie 更新失败", state["message"], 'ERROR')
    return None


def _start(job):
    """启动一个后台任务；已有任务在跑时返回 False。"""
    if _ACTIVE["running"]:
        return False
    _CANCEL.clear()
    if not bpy.app.timers.is_registered(_timer):
        bpy.app.timers.register(_timer, first_interval=0.1, persistent=False)
    _progress_begin()
    _run_job(job)
    return True


def get_ui_state():
    """给偏好设置面板用的按钮文案 / 图标 / 状态行。"""
    state = _snapshot()
    phase = state["phase"]

    if phase == "checking":
        status = f'{state["message"]} {state.get("detail", "")}'.strip()
        return {"label": "检查中…", "icon": "TIME", "status": status}
    if phase == "downloading":
        percent = int(state.get("progress", 0.0) * 100)
        status = f'{state["message"]}  {percent}%  {state["detail"]}'
        return {"label": "取消下载", "icon": "CANCEL", "status": status}
    if phase == "installing":
        return {"label": "安装中…", "icon": "TIME", "status": state["message"]}
    if phase == "done":
        return {"label": "强制更新", "icon": "CHECKMARK", "status": f'{state["message"]}（{state["detail"]}）'}
    if phase == "error":
        return {"label": "强制更新", "icon": "ERROR", "status": f'失败：{state["message"]}'}
    if state.get("remote"):
        return {"label": "强制更新", "icon": "IMPORT", "status": state["message"]}
    # 空闲但留有最近一次结果（例如「已取消」）
    return {"label": "强制更新", "icon": "IMPORT", "status": state.get("message", "")}


# ---------------------------------------------------------------------------
# 操作符（按状态决定行为：检查 / 确认安装 / 取消）
# ---------------------------------------------------------------------------

class BetterExperie_OT_ForceUpdate(bpy.types.Operator):
    bl_idname = "better_experie.force_update"
    bl_label = "强制更新"
    bl_description = "从 GitHub 发布页下载最新安装包并完整覆盖当前插件；有新版本时先确认，安装完成需重启 Blender"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        state = _snapshot()

        # 下载中：同一个按钮就是「取消」
        if state["phase"] == "downloading":
            _CANCEL.set()
            return {'CANCELLED'}

        if _ACTIVE["running"]:
            self.report({'WARNING'}, "正在处理，请稍候")
            return {'CANCELLED'}

        if state["phase"] == "done":
            self.report({'INFO'}, "已更新，请重启 Blender")
            return {'CANCELLED'}

        if state["remote"]:
            return context.window_manager.invoke_props_dialog(self, width=520)

        if not _start(_job_check):
            self.report({'WARNING'}, "已有任务在进行")
            return {'CANCELLED'}
        return {'FINISHED'}

    def draw(self, context):
        release = _snapshot()["remote"] or {}
        layout = self.layout
        column = layout.column(align=True)
        column.label(text=f"当前版本：{_fmt_version(LOCAL_VERSION)}")
        column.label(text=f"线上版本：{release.get('tag') or '未知'}")
        if not _is_newer(release.get("version") or (0, 0, 0), LOCAL_VERSION):
            column.label(text="版本不高于当前，将强制重装同一版本。")
        column.label(text=f"线路：{_route_label()}")
        column.separator()
        column.label(text=f"将下载 {release.get('name') or '安装包'}"
                          f"（{_human_size(release.get('size'))}）")
        column.label(text="并完整覆盖：")
        column.label(text=ADDON_DIR)
        if _has_git_dir():
            column.separator()
            row = column.row()
            row.alert = True
            row.label(text="检测到 .git：当前是开发副本，", icon='ERROR')
            row = column.row()
            row.alert = True
            row.label(text="git 历史与 note/、scripts/ 会一起移入备份目录。", icon='BLANK1')
        column.separator()
        column.label(text="安装完成后必须重启 Blender 才会生效。", icon='ERROR')

    def execute(self, context):
        if not _snapshot()["remote"]:
            self.report({'ERROR'}, "还没有获取到线上版本")
            return {'CANCELLED'}
        if not _start(_job_install):
            self.report({'WARNING'}, "已有任务在进行")
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (
    BetterExperie_OT_ForceUpdate,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    _CANCEL.set()
    try:
        if bpy.app.timers.is_registered(_timer):
            bpy.app.timers.unregister(_timer)
    except Exception:
        pass
    _progress_end()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
