import ast
import asyncio
import importlib
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "_kanna_public_url_test"
package = ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package
setting = importlib.import_module(f"{PACKAGE}.setting")


class PublicURLTest(unittest.TestCase):
    def setUp(self):
        self.local = SimpleNamespace(
            trusted_hosts=("https://nas.example.ts.net", "192.168.1.6:8080"),
            web_public_url="{request_proto}://{host}/kanna_connection",
            cookie_secure=False,
        )
        config = patch.object(setting, "WebSettingLocal", self.local)
        config.start()
        self.addCleanup(config.stop)

    def test_lan_and_tailscale_use_their_own_origins(self):
        lan = SimpleNamespace(headers={"host": "192.168.1.6:8080"},
                              url=SimpleNamespace(scheme="http"))
        tailscale = SimpleNamespace(headers={"host": "NAS.EXAMPLE.TS.NET", "x-forwarded-proto": "https"},
                                    url=SimpleNamespace(scheme="http"))
        self.assertEqual(setting.resolve_web_public_url(lan), "http://192.168.1.6:8080/kanna_connection")
        self.assertEqual(setting.resolve_web_public_url(tailscale), "https://nas.example.ts.net/kanna_connection")

    def test_untrusted_request_host_uses_configured_authority(self):
        request = SimpleNamespace(headers={"host": "foreign.example:1234"}, url=SimpleNamespace(scheme="https"))
        self.assertEqual(setting.resolve_web_public_url(request), "https://nas.example.ts.net/kanna_connection")
        request.headers["host"] = "192.168.1.6:1234"
        self.assertEqual(setting.resolve_web_public_url(request), "https://192.168.1.6:8080/kanna_connection")

    def test_no_request_keeps_first_host_protocol_and_port(self):
        self.local.trusted_hosts = ("https://[fd00::5]:8443", "192.168.1.6")
        self.assertEqual(setting.resolve_web_public_url(), "https://[fd00::5]:8443/kanna_connection")
        self.local.trusted_hosts = ("192.168.1.6:8080", "https://nas.example.ts.net")
        self.assertEqual(setting.resolve_web_public_url(), "http://192.168.1.6:8080/kanna_connection")

    def test_fixed_url_remains_authoritative(self):
        self.local.web_public_url = "https://fixed.example/pcr/"
        self.assertEqual(setting.resolve_web_public_url(), "https://fixed.example/pcr")

    def test_qq_handler_sends_only_the_single_ticket_url(self):
        # Load just the command body to avoid starting Hoshino or the HTTP server.
        source = ast.parse((ROOT / "webui" / "__init__.py").read_text(encoding="utf-8"))
        handler = next(node for node in source.body
                       if isinstance(node, ast.AsyncFunctionDef) and node.name == "apply_login")
        handler.decorator_list = []
        scope = {
            "NoticeSession": object,
            "pcr_sqla": SimpleNamespace(web_query_user=AsyncMock(return_value=True)),
            "create_login_ticket": lambda _qq: "stub-ticket",
            "resolve_web_public_url": setting.resolve_web_public_url,
        }
        exec(compile(ast.Module(body=[handler], type_ignores=[]), "qq_command", "exec"), scope)
        session = SimpleNamespace(ctx=SimpleNamespace(user_id=123), send=AsyncMock())
        asyncio.run(scope["apply_login"](session))
        session.send.assert_awaited_once_with(
            "https://nas.example.ts.net/kanna_connection/login?ticket=stub-ticket",
            ensure_private=True,
        )


if __name__ == "__main__":
    unittest.main()
