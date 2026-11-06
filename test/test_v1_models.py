from __future__ import annotations

import json
import unittest
from unittest import mock

import requests

from services.protocol import openai_v1_models


AUTH_KEY = "chatgpt2api"
BASE_URL = "http://localhost:8000"


class ModelListTests(unittest.TestCase):
    def test_list_models_only_returns_image_models_backed_by_account_types(self):
        with (
            mock.patch.object(
                openai_v1_models.model_catalog_service,
                "list_models",
                return_value={"object": "list", "data": []},
            ),
            mock.patch.object(
                openai_v1_models.account_service,
                "list_accounts",
                return_value=[
                    {"access_token": "token-free", "type": "free"},
                    {"access_token": "token-web-team", "type": "Team", "source_type": "web"},
                    {"access_token": "token-codex-team", "type": "Team", "source_type": "codex"},
                ],
            ),
        ):
            result = openai_v1_models.list_models()

        ids = {item["id"] for item in result["data"]}
        self.assertIn("gpt-image-2", ids)
        self.assertIn("gpt-image-2.5", ids)
        self.assertIn("gpt-image-2.6", ids)
        self.assertIn("codex-gpt-image-2", ids)
        self.assertIn("team-codex-gpt-image-2", ids)
        self.assertNotIn("plus-codex-gpt-image-2", ids)
        self.assertNotIn("pro-codex-gpt-image-2", ids)

    def test_list_models_does_not_return_codex_models_for_web_plus_accounts(self):
        with (
            mock.patch.object(
                openai_v1_models.model_catalog_service,
                "list_models",
                return_value={"object": "list", "data": []},
            ),
            mock.patch.object(
                openai_v1_models.account_service,
                "list_accounts",
                return_value=[
                    {"access_token": "token-web-plus", "type": "Plus", "source_type": "web"},
                ],
            ),
        ):
            result = openai_v1_models.list_models()

        ids = {item["id"] for item in result["data"]}
        self.assertIn("gpt-image-2", ids)
        self.assertNotIn("codex-gpt-image-2", ids)
        self.assertNotIn("plus-codex-gpt-image-2", ids)

    def test_list_models_hides_web_image_models_without_usable_web_accounts(self):
        with (
            mock.patch.object(
                openai_v1_models.model_catalog_service,
                "list_models",
                return_value={"object": "list", "data": []},
            ),
            mock.patch.object(
                openai_v1_models.account_service,
                "list_accounts",
                return_value=[
                    {"access_token": "token-codex-plus", "type": "Plus", "source_type": "codex"},
                    {"access_token": "token-web-disabled", "type": "Team", "source_type": "web", "status": "禁用"},
                ],
            ),
        ):
            result = openai_v1_models.list_models()

        ids = {item["id"] for item in result["data"]}
        # 没有可用的官网账号就不暴露官网图片模型（禁用账号不算）
        self.assertNotIn("gpt-image-2", ids)
        self.assertNotIn("gpt-image-2.5", ids)
        self.assertNotIn("gpt-image-2.6", ids)
        # codex 账号仍然提供 codex 图片模型
        self.assertIn("codex-gpt-image-2", ids)
        self.assertIn("plus-codex-gpt-image-2", ids)

    def test_list_models_hides_internal_and_work_mode_upstream_entries(self):
        upstream = {
            "object": "list",
            "data": [
                {"id": "gpt-6", "object": "model", "owned_by": "chatgpt"},
                {
                    "id": "chatgpt_alpha_model_external_access_reserved_gate_12",
                    "object": "model",
                    "owned_by": "chatgpt",
                    "tags": ["hidden", "history_off_approved"],
                },
                {
                    "id": "gpt-5.6-luna-wm",
                    "object": "model",
                    "owned_by": "chatgpt",
                    "is_work_mode_model": True,
                },
            ],
        }
        with (
            mock.patch.object(
                openai_v1_models.model_catalog_service,
                "list_models",
                return_value=upstream,
            ),
            mock.patch.object(
                openai_v1_models.account_service,
                "list_accounts",
                return_value=[],
            ),
        ):
            result = openai_v1_models.list_models()

        ids = [item["id"] for item in result["data"]]
        self.assertIn("gpt-6", ids)
        self.assertNotIn("chatgpt_alpha_model_external_access_reserved_gate_12", ids)
        self.assertNotIn("gpt-5.6-luna-wm", ids)
        # 过滤只作用于本次返回值，不能改动上游缓存的那份列表
        self.assertEqual(len(upstream["data"]), 3)

    def test_list_models_function(self):
        """测试直接调用服务层获取模型列表。"""
        result = openai_v1_models.list_models()
        print("function result:")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    def test_list_models_http(self):
        """测试通过 HTTP 接口获取模型列表。"""
        response = requests.get(
            f"{BASE_URL}/v1/models",
            headers={"Authorization": f"Bearer {AUTH_KEY}"},
            timeout=30,
        )
        print("http status:")
        print(response.status_code)
        print("http result:")
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
