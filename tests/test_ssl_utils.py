# Copyright contributors to the IBM ODM MCP Server project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import tempfile

import pytest

# Add the root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from decision_mcp_server.utils.ssl_utils import merge_ssl_cert_paths


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_pem(content: str) -> str:
    """Write *content* to a temporary file and return its path."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
        f.write(content)
        return f.name


CERT_A = "-----BEGIN CERTIFICATE-----\nMIIAcertA==\n-----END CERTIFICATE-----\n"
CERT_B = "-----BEGIN CERTIFICATE-----\nMIIAcertB==\n-----END CERTIFICATE-----\n"
CERT_C = "-----BEGIN CERTIFICATE-----\nMIIAcertC==\n-----END CERTIFICATE-----\n"


# ---------------------------------------------------------------------------
# Single-path pass-through
# ---------------------------------------------------------------------------

class TestMergeSslCertPathsSinglePath:
    """A single path is returned unchanged — no temp file is created."""

    def test_single_path_returned_as_is(self, tmp_path):
        cert_file = tmp_path / "ca.pem"
        cert_file.write_text(CERT_A)
        path = str(cert_file)

        result = merge_ssl_cert_paths(path)

        assert result == path

    def test_single_path_with_surrounding_whitespace(self, tmp_path):
        """Whitespace around a single entry is stripped; the resolved path is returned."""
        cert_file = tmp_path / "ca.pem"
        cert_file.write_text(CERT_A)
        path = str(cert_file)

        result = merge_ssl_cert_paths(f"  {path}  ")

        assert result == path


# ---------------------------------------------------------------------------
# Multi-path concatenation — comma separator
# ---------------------------------------------------------------------------

class TestMergeSslCertPathsComma:

    def test_two_paths_comma_separated(self, tmp_path):
        f_a = tmp_path / "a.pem"
        f_b = tmp_path / "b.pem"
        f_a.write_text(CERT_A)
        f_b.write_text(CERT_B)

        result = merge_ssl_cert_paths(f"{f_a},{f_b}")

        assert result != str(f_a)
        assert os.path.isfile(result)
        content = open(result).read()
        assert CERT_A in content
        assert CERT_B in content
        os.unlink(result)

    def test_three_paths_comma_separated(self, tmp_path):
        f_a = tmp_path / "a.pem"
        f_b = tmp_path / "b.pem"
        f_c = tmp_path / "c.pem"
        f_a.write_text(CERT_A)
        f_b.write_text(CERT_B)
        f_c.write_text(CERT_C)

        result = merge_ssl_cert_paths(f"{f_a},{f_b},{f_c}")

        content = open(result).read()
        assert CERT_A in content
        assert CERT_B in content
        assert CERT_C in content
        os.unlink(result)

    def test_comma_with_spaces_around_paths(self, tmp_path):
        f_a = tmp_path / "a.pem"
        f_b = tmp_path / "b.pem"
        f_a.write_text(CERT_A)
        f_b.write_text(CERT_B)

        result = merge_ssl_cert_paths(f" {f_a} , {f_b} ")

        content = open(result).read()
        assert CERT_A in content
        assert CERT_B in content
        os.unlink(result)


# ---------------------------------------------------------------------------
# Multi-path concatenation — semicolon separator
# ---------------------------------------------------------------------------

class TestMergeSslCertPathsSemicolon:

    def test_two_paths_semicolon_separated(self, tmp_path):
        f_a = tmp_path / "a.pem"
        f_b = tmp_path / "b.pem"
        f_a.write_text(CERT_A)
        f_b.write_text(CERT_B)

        result = merge_ssl_cert_paths(f"{f_a};{f_b}")

        content = open(result).read()
        assert CERT_A in content
        assert CERT_B in content
        os.unlink(result)

    def test_semicolon_with_spaces(self, tmp_path):
        f_a = tmp_path / "a.pem"
        f_b = tmp_path / "b.pem"
        f_a.write_text(CERT_A)
        f_b.write_text(CERT_B)

        result = merge_ssl_cert_paths(f" {f_a} ; {f_b} ")

        content = open(result).read()
        assert CERT_A in content
        assert CERT_B in content
        os.unlink(result)


# ---------------------------------------------------------------------------
# Merged file properties
# ---------------------------------------------------------------------------

class TestMergedFileProperties:

    def test_merged_file_has_pem_suffix(self, tmp_path):
        f_a = tmp_path / "a.pem"
        f_b = tmp_path / "b.pem"
        f_a.write_text(CERT_A)
        f_b.write_text(CERT_B)

        result = merge_ssl_cert_paths(f"{f_a},{f_b}")
        assert result.endswith('.pem')
        os.unlink(result)

    def test_cert_blocks_separated_by_newline(self, tmp_path):
        """No certificate block should bleed into the next without a newline."""
        f_a = tmp_path / "a.pem"
        f_b = tmp_path / "b.pem"
        # Deliberately omit trailing newline in CERT_A content
        f_a.write_text(CERT_A.rstrip('\n'))
        f_b.write_text(CERT_B)

        result = merge_ssl_cert_paths(f"{f_a},{f_b}")
        content = open(result).read()
        # END CERTIFICATE of cert A must not directly touch BEGIN CERTIFICATE of cert B
        assert "-----END CERTIFICATE-----\n-----BEGIN CERTIFICATE-----" in content
        os.unlink(result)

    def test_missing_file_raises(self, tmp_path):
        """A non-existent path in the list causes the application to stop."""
        f_a = tmp_path / "a.pem"
        f_a.write_text(CERT_A)
        missing = "/nonexistent/path/ca.pem"

        with pytest.raises(FileNotFoundError):
            merge_ssl_cert_paths(f"{f_a},{missing}")


# ---------------------------------------------------------------------------
# Directory expansion
# ---------------------------------------------------------------------------

class TestMergeSslCertPathsDirectory:

    def test_single_directory_with_one_pem_returned_as_is(self, tmp_path):
        """A single directory containing one .pem is returned without merging."""
        (tmp_path / "ca.pem").write_text(CERT_A)

        result = merge_ssl_cert_paths(str(tmp_path))

        assert result == str(tmp_path / "ca.pem")

    def test_single_directory_expands_and_merges_pem_files(self, tmp_path):
        """A single directory containing multiple .pem files is merged."""
        (tmp_path / "a.pem").write_text(CERT_A)
        (tmp_path / "b.pem").write_text(CERT_B)

        result = merge_ssl_cert_paths(str(tmp_path))

        content = open(result).read()
        assert CERT_A in content
        assert CERT_B in content
        os.unlink(result)

    def test_directory_ignores_non_cert_files(self, tmp_path):
        """Only .pem and .crt files inside a directory are included."""
        (tmp_path / "ca.pem").write_text(CERT_A)
        (tmp_path / "readme.txt").write_text("ignore me")

        result = merge_ssl_cert_paths(str(tmp_path))

        assert result == str(tmp_path / "ca.pem")

    def test_directory_mixed_with_file(self, tmp_path):
        """A directory entry and a file entry are concatenated together."""
        subdir = tmp_path / "certs"
        subdir.mkdir()
        (subdir / "a.pem").write_text(CERT_A)
        (subdir / "b.pem").write_text(CERT_B)
        extra = tmp_path / "extra.pem"
        extra.write_text(CERT_C)

        result = merge_ssl_cert_paths(f"{subdir},{extra}")

        content = open(result).read()
        assert CERT_A in content
        assert CERT_B in content
        assert CERT_C in content
        os.unlink(result)

    def test_directory_includes_cert_files(self, tmp_path):
        """Both .pem and .crt files in a directory are included."""
        (tmp_path / "a.pem").write_text(CERT_A)
        (tmp_path / "b.crt").write_text(CERT_B)

        result = merge_ssl_cert_paths(str(tmp_path))

        content = open(result).read()
        assert CERT_A in content
        assert CERT_B in content
        os.unlink(result)

    def test_subdirectory_with_pem_suffix_is_excluded(self, tmp_path):
        """A subdirectory whose name ends with .pem or .crt must not be included."""
        (tmp_path / "ca.pem").write_text(CERT_A)
        subdir = tmp_path / "bundle.pem"
        subdir.mkdir()
        (subdir / "ignored.pem").write_text(CERT_B)

        result = merge_ssl_cert_paths(str(tmp_path))

        # Only the file ca.pem should be picked up — bundle.pem is a directory.
        assert result == str(tmp_path / "ca.pem")

    def test_missing_directory_raises(self, tmp_path):
        """A non-existent path raises FileNotFoundError regardless of type."""
        with pytest.raises(FileNotFoundError):
            merge_ssl_cert_paths("/nonexistent/directory")
