import os
import unittest
from unittest.mock import patch

import docker_entrypoint


class NumericIdTests(unittest.TestCase):
    def test_uses_default_when_variable_is_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(docker_entrypoint.numeric_id("PUID", 10001), 10001)

    def test_reads_numeric_environment_value(self):
        with patch.dict(os.environ, {"PUID": "99"}):
            self.assertEqual(docker_entrypoint.numeric_id("PUID", 10001), 99)

    def test_rejects_non_numeric_environment_value(self):
        with patch.dict(os.environ, {"PUID": "nobody"}):
            with self.assertRaisesRegex(SystemExit, "PUID must be a numeric ID"):
                docker_entrypoint.numeric_id("PUID", 10001)


if __name__ == "__main__":
    unittest.main()
