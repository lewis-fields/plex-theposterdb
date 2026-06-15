import unittest
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET
from pathlib import Path
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
        request_bytes.assert_called_once_with("http://plex/edit", method="PUT", timeout=server.PLEX_APPLY_TIMEOUT)

    def test_requires_plex_library_details(self):
        with self.assertRaisesRegex(server.AppError, "library details"):
            server.remove_overlay_label({"ratingKey": "42", "type": "movie"})


class UnlockPosterFieldTests(unittest.TestCase):
    def test_unlocks_selected_plex_item_poster_field(self):
        item = {"ratingKey": "42", "sectionKey": "7", "type": "movie"}

        with patch.object(server, "plex_url", return_value="http://plex/edit") as plex_url:
            with patch.object(server, "request_bytes") as request_bytes:
                server.unlock_poster_field(item)

        plex_url.assert_called_once_with(
            "/library/sections/7/all",
            {
                "type": "1",
                "id": "42",
                "thumb.locked": "0",
            },
        )
        request_bytes.assert_called_once_with("http://plex/edit", method="PUT", timeout=server.PLEX_APPLY_TIMEOUT)

    def test_requires_plex_library_details(self):
        with self.assertRaisesRegex(server.AppError, "library details"):
            server.unlock_poster_field({"ratingKey": "42", "type": "movie"})


class ApplyPosterTests(unittest.TestCase):
    def test_local_apply_removes_overlay_before_refreshing_plex(self):
        calls = []
        config = server.Config(remove_overlay_label_on_apply=True)
        item = {"ratingKey": "42", "sectionKey": "7", "type": "movie", "file": r"D:\Movie\Movie.mkv"}

        with patch.object(server.Config, "load", return_value=config):
            with patch.object(server, "fetch_image", return_value=(b"poster", "image/jpeg")):
                with patch.object(server, "save_local_poster", side_effect=lambda *args: calls.append("save") or {"mode": "local"}):
                    with patch.object(server, "remove_overlay_label", side_effect=lambda *args: calls.append("remove")):
                        with patch.object(server, "unlock_poster_field", side_effect=lambda *args: calls.append("unlock")):
                            with patch.object(server, "refresh_item", side_effect=lambda *args: calls.append("refresh")):
                                result = server.apply_poster("https://image", item, "local")

        self.assertTrue(result["overlayLabelRemoved"])
        self.assertEqual(calls, ["save", "remove", "unlock", "refresh"])

    def test_local_apply_unlocks_poster_before_refreshing_even_without_overlay_removal(self):
        calls = []
        config = server.Config(remove_overlay_label_on_apply=False)
        item = {"ratingKey": "42", "sectionKey": "7", "type": "movie", "file": r"D:\Movie\Movie.mkv"}

        with patch.object(server.Config, "load", return_value=config):
            with patch.object(server, "fetch_image", return_value=(b"poster", "image/jpeg")):
                with patch.object(server, "save_local_poster", side_effect=lambda *args: calls.append("save") or {"mode": "local"}):
                    with patch.object(server, "unlock_poster_field", side_effect=lambda *args: calls.append("unlock")):
                        with patch.object(server, "refresh_item", side_effect=lambda *args: calls.append("refresh")):
                            result = server.apply_poster("https://image", item, "local")

        self.assertFalse(result["overlayLabelRemoved"])
        self.assertEqual(calls, ["save", "unlock", "refresh"])

    def test_local_apply_returns_saved_poster_when_plex_refresh_fails(self):
        config = server.Config(remove_overlay_label_on_apply=False)
        item = {"ratingKey": "42", "sectionKey": "7", "type": "movie", "file": r"D:\Movie\Movie.mkv"}

        with patch.object(server.Config, "load", return_value=config):
            with patch.object(server, "fetch_image", return_value=(b"poster", "image/jpeg")):
                with patch.object(server, "save_local_poster", return_value={"mode": "local", "path": r"D:\Movie\poster.jpg"}):
                    with patch.object(server, "unlock_poster_field"):
                        with patch.object(server, "refresh_item", side_effect=server.AppError("Request timed out after 8 seconds.", 504)):
                            result = server.apply_poster("https://image", item, "local")

        self.assertEqual(result["mode"], "local")
        self.assertEqual(result["path"], r"D:\Movie\poster.jpg")
        self.assertEqual(result["plexUpdateError"], "Plex refresh failed: Request timed out after 8 seconds.")

    def test_plex_apply_removes_overlay_after_uploading_poster(self):
        calls = []
        config = server.Config(remove_overlay_label_on_apply=True)
        item = {"ratingKey": "42", "sectionKey": "7", "type": "movie"}

        with patch.object(server.Config, "load", return_value=config):
            with patch.object(server, "fetch_image", return_value=(b"poster", "image/jpeg")):
                with patch.object(server, "upload_plex_poster", side_effect=lambda *args: calls.append("upload") or {"mode": "plex"}):
                    with patch.object(server, "remove_overlay_label", side_effect=lambda *args: calls.append("remove")):
                        result = server.apply_poster("https://image", item, "plex")

        self.assertTrue(result["overlayLabelRemoved"])
        self.assertEqual(calls, ["upload", "remove"])


class RefreshItemTests(unittest.TestCase):
    def test_forces_metadata_refresh_with_put(self):
        with patch.object(server, "plex_url", return_value="http://plex/refresh") as plex_url:
            with patch.object(server, "request_bytes") as request_bytes:
                server.refresh_item("42")

        plex_url.assert_called_once_with("/library/metadata/42/refresh", {"force": "1"})
        request_bytes.assert_called_once_with("http://plex/refresh", method="PUT", timeout=server.PLEX_APPLY_TIMEOUT)


class PathMappingTests(unittest.TestCase):
    def test_maps_multiple_absolute_library_roots(self):
        config = server.Config(
            path_mappings=[
                {"plex": r"D:\Plex\Movies", "local": r"W:\Movies"},
                {"plex": r"E:\Plex\TV Shows", "local": r"W:\TV Shows"},
            ]
        )

        with patch.object(server.Config, "load", return_value=config):
            mapped_movie = server.map_plex_path(r"D:\Plex\Movies\Alien\Alien.mkv")
            mapped_show = server.map_plex_path(r"E:\Plex\TV Shows\Severance")

        self.assertEqual(mapped_movie, r"W:\Movies\Alien\Alien.mkv")
        self.assertEqual(mapped_show, r"W:\TV Shows\Severance")

    def test_prefers_the_most_specific_mapping_root(self):
        config = server.Config(
            path_mappings=[
                {"plex": r"E:\Plex", "local": r"W:\Plex"},
                {"plex": r"E:\Plex\TV Shows", "local": r"X:\Shows"},
            ]
        )

        with patch.object(server.Config, "load", return_value=config):
            mapped_show = server.map_plex_path(r"E:\Plex\TV Shows\Severance")

        self.assertEqual(mapped_show, r"X:\Shows\Severance")

    def test_does_not_map_a_similarly_named_sibling_root(self):
        config = server.Config(path_mappings=[{"plex": r"E:\Plex\TV", "local": r"X:\Shows"}])

        with patch.object(server.Config, "load", return_value=config):
            untouched_path = server.map_plex_path(r"E:\Plex\TV Shows\Severance")

        self.assertEqual(untouched_path, r"E:\Plex\TV Shows\Severance")


class SeasonItemsTests(unittest.TestCase):
    def test_returns_show_folder_exposed_by_show_metadata(self):
        roots = {
            "/library/metadata/42": ET.fromstring(
                r"""
                <MediaContainer>
                    <Directory title="All Her Fault" librarySectionID="1">
                        <Location path="H:\TV Shows\All Her Fault (2025)" />
                    </Directory>
                </MediaContainer>
                """
            ),
            "/library/metadata/42/children": ET.fromstring(
                """
                <MediaContainer>
                    <Directory type="season" ratingKey="43" title="Season 1" index="1" />
                </MediaContainer>
                """
            ),
            "/library/metadata/43/children": ET.fromstring(
                r"""
                <MediaContainer>
                    <Video>
                        <Media>
                            <Part file="H:\TV Shows\All Her Fault (2025)\Season 1\Episode 1.mkv" />
                        </Media>
                    </Video>
                </MediaContainer>
                """
            ),
        }

        with patch.object(server, "plex_xml", side_effect=lambda path: roots[path]):
            payload = server.season_items("42")

        self.assertEqual(payload["showFolder"], r"H:\TV Shows\All Her Fault (2025)")
        self.assertEqual(payload["seasons"][0]["folder"], r"H:\TV Shows\All Her Fault (2025)\Season 1")


class PosterParsingTests(unittest.TestCase):
    def test_search_targets_include_year_from_title(self):
        html = """
        <a href="/posters/123">Star Wars: Episode IV - A New Hope (1977)</a>
        <a href="/posters/456">Star Wars Collection (N/A)</a>
        """

        targets = server.parse_search_targets(html, "movie")

        self.assertEqual(targets[0]["year"], "1977")
        self.assertEqual(targets[1]["year"], "")

    def test_card_preview_uses_full_asset_for_apply_url(self):
        html = """
        <div class="hovereffect rounded-poster">
            <picture>
                <source type="image/jpeg" srcset="//images.theposterdb.com/previews/poster.jpg" />
            </picture>
            <button data-poster-id='231507'></button>
            <p class="p-0 mb-1 text-break">Severance (2022)</p>
            <p class="uploaded-by">by <a>Sevi</a></p>
        </div></div></div>
        """

        posters = server.parse_posters(html)

        self.assertEqual(posters[0]["imageUrl"], "https://theposterdb.com/api/assets/231507/view")
        self.assertEqual(posters[0]["previewUrl"], "https://images.theposterdb.com/previews/poster.jpg")


class LocalPosterFilenameTests(unittest.TestCase):
    def test_uses_plex_season_number_for_numbered_season_poster(self):
        self.assertEqual(server.local_poster_filename({"type": "season", "index": "1"}, ".png"), "season01.png")

    def test_uses_specials_name_for_specials_season_poster(self):
        self.assertEqual(
            server.local_poster_filename({"type": "season", "index": "0", "title": "Specials"}, ".jpg"),
            "season-specials-poster.jpg",
        )

    def test_keeps_standard_poster_name_for_non_season_items(self):
        self.assertEqual(server.local_poster_filename({"type": "show"}, ".jpg"), "poster.jpg")


class SaveLocalPosterTests(unittest.TestCase):
    def test_rejects_an_unavailable_mapped_media_folder(self):
        with TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "missing-library-folder"

            with patch.object(server, "media_folder", return_value=folder):
                with self.assertRaisesRegex(server.AppError, "Mapped media folder is not available"):
                    server.save_local_poster(
                        "https://theposterdb.com/api/assets/1/view",
                        {"type": "movie"},
                        b"poster",
                        "image/jpeg",
                    )

            self.assertFalse(folder.exists())

    def test_replaces_stale_movie_poster_extensions(self):
        with TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "poster.jpg").write_bytes(b"old-jpg")
            (folder / "poster.webp").write_bytes(b"old-webp")

            with patch.object(server, "media_folder", return_value=folder):
                result = server.save_local_poster(
                    "https://theposterdb.com/api/assets/1/view",
                    {"type": "movie"},
                    b"new-png",
                    "image/png",
                )

            self.assertEqual(Path(result["path"]).name, "poster.png")
            self.assertEqual((folder / "poster.png").read_bytes(), b"new-png")
            self.assertFalse((folder / "poster.jpg").exists())
            self.assertFalse((folder / "poster.webp").exists())

    def test_replaces_stale_numbered_season_poster_extensions(self):
        with TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "season01.jpg").write_bytes(b"old-season")
            (folder / "poster.jpg").write_bytes(b"unrelated")

            with patch.object(server, "media_folder", return_value=folder):
                result = server.save_local_poster(
                    "https://theposterdb.com/api/assets/1/view",
                    {"type": "season", "index": "1"},
                    b"new-season",
                    "image/png",
                )

            self.assertEqual(Path(result["path"]).name, "season01.png")
            self.assertEqual((folder / "season01.png").read_bytes(), b"new-season")
            self.assertFalse((folder / "season01.jpg").exists())
            self.assertTrue((folder / "poster.jpg").exists())


if __name__ == "__main__":
    unittest.main()
