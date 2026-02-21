from __future__ import annotations

import re
from typing import Any, Iterable

_MD_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _content_text_and_images(content: Any) -> tuple[str, list[str]]:
    if isinstance(content, str):
        images = _MD_IMAGE.findall(content)
        return content, [u.strip() for u in images if u.strip()]

    if isinstance(content, list):
        text_chunks: list[str] = []
        images: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("type", "")).strip().lower()
            if part_type in {"text", "input_text"}:
                text = part.get("text", "")
                if isinstance(text, str) and text.strip():
                    text_chunks.append(text.strip())
            elif part_type in {"image_url", "input_image"}:
                image_obj = part.get("image_url")
                if isinstance(image_obj, dict):
                    url = image_obj.get("url", "")
                    if isinstance(url, str) and url.strip():
                        images.append(url.strip())
                elif isinstance(image_obj, str) and image_obj.strip():
                    images.append(image_obj.strip())
        return "\n".join(text_chunks).strip(), images

    if isinstance(content, dict):
        # Some clients may send custom shape with inline text and image_url.
        text = content.get("text", "")
        text_s = text.strip() if isinstance(text, str) else ""
        images: list[str] = []
        image_obj = content.get("image_url")
        if isinstance(image_obj, dict):
            url = image_obj.get("url", "")
            if isinstance(url, str) and url.strip():
                images.append(url.strip())
        elif isinstance(image_obj, str) and image_obj.strip():
            images.append(image_obj.strip())
        if not images and text_s:
            images = [u.strip() for u in _MD_IMAGE.findall(text_s) if u.strip()]
        return text_s, images

    return "", []


def extract_latest_user_input(messages: Iterable[Any]) -> tuple[str, list[str]]:
    msg_list = list(messages)
    for msg in reversed(msg_list):
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", None)
        if role is None and isinstance(msg, dict):
            role = msg.get("role")
            content = msg.get("content")
        if role == "user":
            return _content_text_and_images(content)

    # Do not fall back to non-user messages (system/tool text can poison parsing).
    return "", []
