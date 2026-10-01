"""CI step (spike): unpack a built bundle under a non-ASCII path with a space, then run smoke.py with its Python.

    ci_smoke.py <archive> <parent dir> [<folder name, default 한글 폴더>]
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

archive, dest = Path(sys.argv[1]), Path(sys.argv[2]) / (sys.argv[3] if len(sys.argv) > 3 else "한글 폴더")
shutil.rmtree(dest, ignore_errors=True)
dest.mkdir(parents=True)
if archive.suffix == ".zip":
    with zipfile.ZipFile(archive) as z:
        z.extractall(dest)
else:
    with tarfile.open(archive) as t:
        t.extractall(dest, filter="tar")
(bundle,) = list(dest.iterdir())
python = bundle / ("python/python.exe" if sys.platform == "win32" else "python/bin/python3")
smoke = Path(__file__).with_name("smoke.py")
sys.exit(subprocess.run([str(python), str(smoke), str(bundle)]).returncode)
