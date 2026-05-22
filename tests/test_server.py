import unittest
from unittest.mock import patch

import server


class RemoveOverlayLabelTests(unittest.TestCase):
    def test_removes_overlay_label_from_selected_plex_item(self):
        item = {"ratingKey": "42", "sectionKey": "7", "type": "show"}

        with patch.object(server, "plex_url", return_value="http://plex/edit") as plex_url:
            with patch.object(server, "request_bytes") as request_bytes:
                server.remove_overlay_label(item)

        plex_url.assert_called_once_with(
            "/library/sections/7/all",
            {
                "type": "2",
                "id": "42",
                "label.locked": "1",
                "label[].tag.tag-": "Overlay",
            },
        )
        request_bytes.assert_called_once_with("http://plex/edit", method="PUT")

    def test_requires_plex_library_details(self):
        with self.assertRaisesRegex(server.AppError, "library details"):
            server.remove_overlay_label({"ratingKey": "42", "type": "movie"})


if __name__ == "__main__":
    unittest.main()
