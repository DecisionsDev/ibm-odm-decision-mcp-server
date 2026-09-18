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
import re
import tempfile

def merge_ssl_cert_paths(ssl_cert_path: str) -> str:
    """Return a path to a single CA-bundle PEM file.

    If *ssl_cert_path* contains multiple paths separated by ``,`` or
    ``;``, the files are concatenated into a new temporary file and the
    path of that temporary file is returned.  When only a single path is
    given the original value is returned unchanged.

    Directory entries are expanded to all ``*.pem`` and ``*.crt`` files they
    contain (sorted alphabetically).  Non-existent paths raise a
    FileNotFoundError.

    Args:
        ssl_cert_path: One or more PEM/CRT file or directory paths, separated
            by ``,`` or ``;``.

    Returns:
        A file path suitable for use as a CA bundle.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Split on commas or semicolons, stripping whitespace around each entry.
    raw_paths = [p.strip() for p in re.split(r'[,;]+', ssl_cert_path) if p.strip()]

    # Expand directory entries to the sorted list of *.pem / *.crt files they contain.
    paths: list[str] = []
    for path in raw_paths:
        if os.path.isdir(path):
            cert_files = sorted(
                os.path.join(path, f)
                for f in os.listdir(path)
                if (f.endswith('.pem') or f.endswith('.crt')) and os.path.isfile(os.path.join(path, f))
            )
            paths.extend(cert_files)
        elif os.path.isfile(path):
            paths.append(path)
        else:
            err = FileNotFoundError(f"No such file or directory: '{path}'")
            logger.error("ssl-cert-path: path %s not found, stopping", path)
            raise err

    if len(paths) <= 1:
        # Single path — no temp file required - return as-is (with any leading or ending space characters removed)
        return paths[0] if paths else ssl_cert_path

    # Multiple paths: concatenate into a NamedTemporaryFile that persists until
    # the process exits (delete=False).
    try:
        tmp = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.pem',
            delete=False,
            prefix='odm_merged_ca_',
        )
    except OSError as e:
        logger.error(
            "ssl-cert-path: could not create temporary file (%s), stopping. Set TMPDIR env to mitigate",
            e,
        )
        raise e

    with tmp:
        merged = []
        for path in paths:
            try:
                with open(path, 'r') as f:
                    content = f.read()
            except FileNotFoundError as e:
                logger.error("ssl-cert-path: file %s not found, stopping", path)
                raise e
            # Ensure each certificate block ends with a newline before the next.
            if not content.endswith('\n'):
                content += '\n'
            try:
                tmp.write(content)
            except OSError as e:
                logger.error(
                    "ssl-cert-path: could not write to temporary file (%s), stopping. Set TMPDIR env to mitigate",
                    e,
                )
                raise e
            merged.append(path)
        logger.info(
            "ssl-cert-path: concatenated %s into %s",
            ", ".join(merged),
            tmp.name,
        )
        return tmp.name
