from enum import Enum
from pathlib import Path
from .basedata import FilePath


class ClientSetting(Enum):
    """
    有关client的设置
    clanbattle_semaphore：会战查询最大并发量
    jjc_semaphore：会战查询最大并发量
    """

    clanbattle_max = 66
    jjc_max = 33


class TimeAxisLimit(Enum):
    """
    分刀限制
    max_calculate：最大计算量
    max_result：最大获取结果数
    max_query：一个boss显示几个作业
    single_limit：一个阶段中一个boss显示几个作业
    """

    max_calculate = 114514
    max_result = 3
    max_query = 8
    single_limit = 3


class JJCSetting(Enum):
    """
    竞技场设置
    buff_path：缓存储存路径
    query_local：作业网查询方法
    """

    buff_path = Path(__file__).parent.parent / "priconne" / "arena" / "buffer"
    query_local = True


class WebSetting(Enum):
    """
    网页端！！！
    """

    api_host = "127.0.0.1"
    api_port = "12139"
    cookie_secure = False
    # 本地实际配置请放在 settings_local.py，或使用动态模板。
    # 示例动态模板："{request_proto}://{host}/kanna_connection"
    trusted_hosts = (
        "xxxx",
    )
    web_public_url = "http://xxxx:12138/kanna_connection"


try:
    from .settings_local import WebSettingLocal
except ImportError:
    WebSettingLocal = None


def get_web_setting(name):
    if WebSettingLocal is not None:
        local_value = getattr(WebSettingLocal, name, None)
        if local_value is not None:
            return local_value
    return getattr(WebSetting, name).value


def _normalize_host(host):
    value = str(host or "").strip().lower()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0]
    if value.startswith("[") and "]" in value:
        return value[1:value.index("]")]
    if value.count(":") == 1:
        value = value.rsplit(":", 1)[0]
    return value.rstrip(".")


def get_request_scheme(request=None):
    if request is not None:
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if forwarded_proto:
            proto = forwarded_proto.split(",", 1)[0].strip().lower()
            if proto in ("http", "https"):
                return proto
        if request.url.scheme in ("http", "https"):
            return request.url.scheme
    return "https" if get_web_setting("cookie_secure") else "http"


def get_request_host(request=None):
    trusted_hosts = tuple(get_web_setting("trusted_hosts"))
    fallback = _normalize_host(trusted_hosts[0]) if trusted_hosts else "127.0.0.1"
    if request is None:
        return fallback

    host = _normalize_host(request.headers.get("host"))
    trusted = {
        _normalize_host(trusted_host)
        for trusted_host in get_web_setting("trusted_hosts")
    }
    return host if host in trusted else fallback


def resolve_web_public_url(request=None):
    template = str(get_web_setting("web_public_url")).rstrip("/")
    values = {
        "request_proto": get_request_scheme(request),
        "host": get_request_host(request),
    }
    try:
        return template.format(**values).rstrip("/")
    except (KeyError, ValueError):
        proto = get_request_scheme(request)
        return f"{proto}://{get_request_host(request)}/kanna_connection"


class BossData(Enum):
    """
    会战boss数据，主要为网页端服务
    """

    use_online = True
    info_path = FilePath.data.value / "boss_info.json"
