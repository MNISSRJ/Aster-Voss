"""Helpers for vendor-neutral multimodal message parts."""
from __future__ import annotations


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


def image_url_part(url: str) -> dict:
    return {"type": "image_url", "image_url": {"url": url}}


def multimodal_content(text: str, image_urls: list[str] | None = None) -> list[dict]:
    parts = [text_part(text)]
    for url in image_urls or []:
        if url.strip():
            parts.append(image_url_part(url.strip()))
    return parts
