from __future__ import annotations

from typing import Any

from services.account_service import account_service
from services.model_service import model_catalog_service
from utils.helper import CODEX_IMAGE_MODEL, WEB_IMAGE_MODELS


def _is_hidden_upstream_model(item: object) -> bool:
    """判断上游模型目录里的条目是否不该对外暴露。

    上游会把内部/实验条目一起塞进 `/backend-api/models`：
    - `tags` 里带 `hidden`（例如 chatgpt_alpha_model_external_access_reserved_gate_12/13）
    - `is_work_mode_model` 为真（工作模式专用副本，例如 gpt-5.6-luna-wm，与 gpt-5-6 重复）
    这些模型普通请求用不了，暴露出去只会让客户端选到必失败的项。
    这里只影响 /v1/models 的展示，不影响按模型名的实际路由。
    """
    if not isinstance(item, dict):
        return False
    tags = item.get("tags")
    if isinstance(tags, list) and "hidden" in {str(tag).strip().lower() for tag in tags}:
        return True
    return bool(item.get("is_work_mode_model"))


def list_models() -> dict[str, Any]:
    result = model_catalog_service.list_models()
    data = result.get("data")
    if not isinstance(data, list):
        return result
    visible = [
        item
        for item in data
        if isinstance(item, dict) and not _is_hidden_upstream_model(item)
    ]
    seen = {str(item.get("id") or "").strip() for item in visible}
    dynamic_models: set[str] = set()
    accounts = account_service.list_accounts()
    # 只有处于可用状态的官网（web）账号才代表"官网生图链路可用"。
    # 原来的实现没有任何过滤：账号池里只剩 codex 账号、或账号全被禁用时，
    # 依然会暴露官网图片模型，等于对外承诺了一个用不了的能力。
    web_image_accounts = [
        account
        for account in accounts
        if isinstance(account, dict)
           and account_service._normalize_source_type(account.get("source_type")) == "web"
           and account.get("status") not in {"禁用", "异常"}
    ]
    codex_types = {
        normalized
        for account in accounts
        if isinstance(account, dict)
           and account_service._normalize_source_type(account.get("source_type")) == "codex"
           and account.get("status") not in {"禁用", "异常"}
           and (normalized := account_service._normalize_account_type(account.get("type")))
    }

    if web_image_accounts:
        dynamic_models.update(WEB_IMAGE_MODELS)
    if codex_types & {"Plus", "Team", "Pro"}:
        dynamic_models.add(CODEX_IMAGE_MODEL)
    if "Plus" in codex_types:
        dynamic_models.add(f"plus-{CODEX_IMAGE_MODEL}")
    if "Team" in codex_types:
        dynamic_models.add(f"team-{CODEX_IMAGE_MODEL}")
    if "Pro" in codex_types:
        dynamic_models.add(f"pro-{CODEX_IMAGE_MODEL}")

    for model in sorted(dynamic_models):
        if model not in seen:
            visible.append({
                "id": model,
                "object": "model",
                "created": 0,
                "owned_by": "chatgpt2api",
                "permission": [],
                "root": model,
                "parent": None,
            })
    return {**result, "data": visible}
