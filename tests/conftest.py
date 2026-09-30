"""
Pytest fixtures for ModerationGuard tests.
Self-contained mocks - no genlayer-test package or live node needed.
"""

import pytest
import sys
import re
from unittest.mock import MagicMock
from types import ModuleType


@pytest.fixture(scope="session", autouse=True)
def setup_genlayer_mock():
    """Inject mocked genlayer modules before any test runs."""

    genlayer_pkg = ModuleType("genlayer")
    genlayer_pkg.__path__ = []
    sys.modules["genlayer"] = genlayer_pkg

    fake_gl = ModuleType("genlayer.gl")
    fake_gl.message = MagicMock()
    fake_gl.message.sender_address = "0x1234567890abcdef"
    fake_gl.block = MagicMock()
    fake_gl.block.timestamp = 1690000000
    fake_gl.emit = MagicMock()
    genlayer_pkg.Contract = object
    genlayer_pkg.gl = fake_gl

    # eq_principle - just calls the wrapped function directly in tests,
    # standing in for real validator consensus.
    class EqPrinciple:
        @staticmethod
        def json_eq(fn, *args, **kwargs):
            return fn(*args, **kwargs) if callable(fn) else fn

        @staticmethod
        def strict_eq(fn, *args, **kwargs):
            return fn(*args, **kwargs) if callable(fn) else fn

    fake_gl.eq_principle = EqPrinciple()

    # nondet
    fake_nondet = MagicMock()
    fake_web = MagicMock()
    fake_web.render = MagicMock(return_value="Mock page content")
    fake_web.get = MagicMock(return_value=MagicMock(body=b"Mock page content"))
    fake_nondet.web = fake_web
    fake_nondet.exec_prompt = MagicMock(
        return_value='{"verdict":"TRUE","confidence":0.9,"reasoning":"Mock","key_evidence":"Mock"}'
    )
    fake_gl.nondet = fake_nondet

    fake_gl.Contract = object

    fake_public = MagicMock()
    fake_public.write = lambda fn: fn
    fake_public.view = lambda fn: fn
    fake_gl.public = fake_public

    fake_gl.vm = MagicMock()
    fake_gl.vm.UserError = ValueError

    sys.modules["genlayer.gl"] = fake_gl
    genlayer_pkg.gl = fake_gl
    sys.modules["genlayer.std"] = ModuleType("genlayer.std")
    sys.modules["genlayer.std._wasi"] = fake_gl

    yield

    for name in ["genlayer.std._wasi", "genlayer.std", "genlayer.gl", "genlayer"]:
        if name in sys.modules:
            del sys.modules[name]


@pytest.fixture
def direct_vm(setup_genlayer_mock):
    import genlayer.gl as gl

    class VMController:
        def __init__(self):
            self._web_mocks = []
            self._llm_mocks = []

            gl.nondet.web.render = self._web_render
            gl.nondet.exec_prompt = self._exec_prompt

        def _web_render(self, url, mode="text"):
            for pat, resp in self._web_mocks:
                if pat.search(url):
                    if resp.get("status", 200) >= 400:
                        raise Exception(f"HTTP {resp.get('status', 500)}")
                    return resp.get("body", "")
            return f"Mock content for {url}"

        def _exec_prompt(self, prompt):
            for pat, resp in self._llm_mocks:
                if pat.search(prompt):
                    return resp
            return '{"verdict":"TRUE","confidence":0.9,"reasoning":"Default mock","key_evidence":"Mock"}'

        def prank(self, address):
            class PrankContext:
                def __enter__(ctx):
                    ctx.saved = gl.message.sender_address
                    gl.message.sender_address = str(address)
                    return ctx
                def __exit__(ctx, *args):
                    gl.message.sender_address = ctx.saved
                    return False
            return PrankContext()

        def expect_revert(self, message_substring=""):
            class RevertContext:
                def __enter__(ctx):
                    return ctx
                def __exit__(ctx, exc_type, exc_val, exc_tb):
                    if exc_type is None:
                        raise AssertionError(f"Expected revert with \"{message_substring}\" but no exception was raised")
                    msg = str(exc_val)
                    if message_substring and message_substring not in msg:
                        raise AssertionError(f"Expected revert with \"{message_substring}\", got: {msg}")
                    return True
            return RevertContext()

        def mock_web(self, pattern, response):
            """response: dict with 'body' (str) and optional 'status' (int, >=400 raises)."""
            self._web_mocks.append((re.compile(pattern), response))

        def mock_llm(self, pattern, response):
            """response: raw string the mocked LLM should return for prompts matching pattern."""
            self._llm_mocks.append((re.compile(pattern), response))

    return VMController()


@pytest.fixture
def direct_owner():
    return "0x1234567890abcdef"


@pytest.fixture
def direct_alice():
    return "0xalicealicealicealicealicealicealice"


@pytest.fixture
def direct_deploy(setup_genlayer_mock):
    import importlib.util
    import os

    def _deploy(contract_path, *args, **kwargs):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        full_path = os.path.join(project_root, contract_path)

        module_name = os.path.splitext(os.path.basename(contract_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, full_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        contract_class = getattr(module, module_name)
        return contract_class(*args, **kwargs)

    return _deploy
