import unittest
import xml.etree.ElementTree as ET
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


if __name__ == "__main__":
    unittest.main()
