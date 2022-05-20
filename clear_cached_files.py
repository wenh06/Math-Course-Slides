"""
"""

import os
import re
from pathlib import Path


def main():
    project_dir = Path(__file__).parent.resolve()
    cached_file_extensions = [
        "\\.aux",
        "\\.auxlock",
        "\\.glo",
        "\\.idx",
        "\\.log",
        "\\.toc",
        "\\.ist",
        "\\.acn",
        "\\.acr",
        "\\.alg",
        "\\.bbl",
        "\\.blg",
        "\\.dvi",
        "\\.glg",
        "\\.gls",
        "\\.ilg",
        "\\.ind",
        "\\.lof",
        "\\.lot",
        "\\.maf",
        "\\.mtc",
        "\\.out",
        "\\.bak",
        "\\.ps",
        "\\.run\\.xml",
        "blx\\.bib",
        "\\.synctex\\.gz",
        "\\.fdb_latexmk",
        "\\.fls",
        "\\.tmppart",
    ]
    cached_file_pattern = f"^.+(?:{'|'.join(cached_file_extensions)})$"

    for file in project_dir.iterdir():
        if re.match(cached_file_pattern, file.name):
            os.remove(file)
            print(f"{file} removed")


if __name__ == "__main__":
    main()
