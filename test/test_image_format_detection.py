from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import image_service
from services.image_storage_service import ImageStorageService, image_storage_service
from utils.helper import detect_image_extension, image_mime_type_for_path

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF_BYTES = b"GIF89a" + b"\x00" * 16
WEBP_BYTES = b"RIFF\x24\x00\x00\x00WEBP" + b"\x00" * 16
SVG_BYTES = b'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg"></svg>'


class ImageFormatDetectionTests(unittest.TestCase):
    def test_detects_common_image_formats_from_bytes(self) -> None:
        self.assertEqual(detect_image_extension(PNG_BYTES), ".png")
        self.assertEqual(detect_image_extension(JPEG_BYTES), ".jpg")
        self.assertEqual(detect_image_extension(GIF_BYTES), ".gif")
        self.assertEqual(detect_image_extension(WEBP_BYTES), ".webp")
        self.assertEqual(detect_image_extension(SVG_BYTES), ".svg")

    def test_detects_svg_with_leading_whitespace_and_bom(self) -> None:
        self.assertEqual(detect_image_extension(b"\xef\xbb\xbf\n  <svg></svg>"), ".svg")
        self.assertEqual(detect_image_extension(b"<!-- comment --><svg></svg>"), ".svg")

    def test_returns_none_for_unknown_payload(self) -> None:
        self.assertIsNone(detect_image_extension(b""))
        self.assertIsNone(detect_image_extension(b"not an image payload"))

    def test_relative_path_keeps_original_extension(self) -> None:
        service = ImageStorageService()
        self.assertTrue(service.make_relative_path(PNG_BYTES).endswith(".png"))
        self.assertTrue(service.make_relative_path(GIF_BYTES).endswith(".gif"))
        self.assertTrue(service.make_relative_path(SVG_BYTES).endswith(".svg"))
        # 识别不出来时退回 png，保持旧行为
        self.assertTrue(service.make_relative_path(b"not an image payload").endswith(".png"))

    def test_mime_type_follows_extension(self) -> None:
        self.assertEqual(image_mime_type_for_path("2026/01/01/a.svg"), "image/svg+xml")
        self.assertEqual(image_mime_type_for_path("a.gif"), "image/gif")
        self.assertEqual(image_mime_type_for_path("a.webp"), "image/webp")
        self.assertEqual(image_mime_type_for_path("a.unknown"), "image/png")

    def test_gif_is_served_as_gif(self) -> None:
        with (
            mock.patch.object(image_service.image_storage_service, "has_local", return_value=False),
            mock.patch.object(image_service.image_storage_service, "get_bytes", return_value=GIF_BYTES),
        ):
            response = image_service.get_image_response("2026/01/01/a.gif")

        self.assertEqual(response.media_type, "image/gif")
        self.assertNotIn("content-security-policy", response.headers)

    def test_svg_is_served_locked_down(self) -> None:
        with (
            mock.patch.object(image_service.image_storage_service, "has_local", return_value=False),
            mock.patch.object(image_service.image_storage_service, "get_bytes", return_value=SVG_BYTES),
        ):
            response = image_service.get_image_response("2026/01/01/a.svg")

        self.assertEqual(response.media_type, "image/svg+xml")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("default-src 'none'", response.headers["content-security-policy"])

    def test_svg_thumbnail_falls_back_to_original(self) -> None:
        with mock.patch.object(image_service, "get_image_response", return_value="original") as fallback:
            result = image_service.get_thumbnail_response("2026/01/01/a.svg")

        self.assertEqual(result, "original")
        fallback.assert_called_once_with("2026/01/01/a.svg")

    def test_save_keeps_original_bytes_and_extension(self) -> None:
        for payload, suffix in (
            (PNG_BYTES, ".png"),
            (GIF_BYTES, ".gif"),
            (SVG_BYTES, ".svg"),
        ):
            with tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                with (
                    mock.patch("services.image_storage_service._local_image_path", lambda rel, _root=root: _root / rel),
                    mock.patch.object(image_storage_service, "_load_clean_index", lambda: {}),
                    mock.patch.object(image_storage_service, "_save_index", lambda items: None),
                    mock.patch.object(
                        image_storage_service,
                        "settings",
                        lambda: {"enabled": True, "mode": "local"},
                    ),
                    mock.patch("services.image_storage_service.config.cleanup_old_images"),
                ):
                    stored = image_storage_service.save(payload)

                self.assertTrue(stored.rel.endswith(suffix), stored.rel)
                # 原始字节必须一字不改地落盘，GIF 动画 / SVG 矢量才不会被打断
                self.assertEqual((root / stored.rel).read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
