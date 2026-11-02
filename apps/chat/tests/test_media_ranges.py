"""The development media server must honour HTTP Range (video playback)."""

import shutil
import tempfile
from pathlib import Path

from django.test import SimpleTestCase
from django.test.client import RequestFactory

from config.media_views import serve_media


class MediaRangeTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "chat").mkdir()
        (self.root / "chat" / "clip.mp4").write_bytes(bytes(range(256)) * 4)  # 1024 bytes
        self.factory = RequestFactory()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def get(self, **headers):
        request = self.factory.get("/media/chat/clip.mp4", **headers)
        return serve_media(request, "chat/clip.mp4", document_root=self.root)

    def test_full_file_advertises_ranges(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Accept-Ranges"], "bytes")
        response.close()

    def test_partial_content(self):
        response = self.get(HTTP_RANGE="bytes=1000-")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], "bytes 1000-1023/1024")
        self.assertEqual(len(b"".join(response.streaming_content)), 24)

    def test_suffix_and_unsatisfiable(self):
        response = self.get(HTTP_RANGE="bytes=-10")
        self.assertEqual(response["Content-Range"], "bytes 1014-1023/1024")
        self.assertEqual(self.get(HTTP_RANGE="bytes=5000-").status_code, 416)

    def test_path_traversal_is_rejected(self):
        from django.http import Http404

        request = self.factory.get("/media/../settings.py")
        with self.assertRaises(Http404):
            serve_media(request, "../settings.py", document_root=self.root)
