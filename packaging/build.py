"""Build a native SQLTUI folder bundle for the current operating system."""

from __future__ import annotations

import platform
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
WORK = ROOT / "build" / "pyinstaller"


def create_icons() -> tuple[Path, Path]:
    try:
        from PIL import Image, ImageDraw
    except ImportError as error:
        raise SystemExit("Install build dependencies with: python -m pip install -e '.[build]'") from error

    DIST.mkdir(exist_ok=True)
    png_path = DIST / "sqltui.png"
    ico_path = DIST / "sqltui.ico"

    image = Image.new("RGBA", (256, 256), (20, 26, 28, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 24, 232, 232), radius=38, fill=(32, 43, 45, 255))
    draw.rounded_rectangle((61, 58, 195, 190), radius=17, fill=(38, 102, 93, 255))
    draw.ellipse((61, 48, 195, 92), fill=(91, 169, 155, 255))
    draw.rectangle((61, 69, 195, 167), fill=(38, 102, 93, 255))
    draw.arc((61, 139, 195, 205), start=0, end=180, fill=(145, 203, 191, 255), width=10)
    draw.line((87, 118, 112, 137, 151, 105), fill=(244, 238, 216, 255), width=13, joint="curve")
    image.save(png_path)
    image.save(ico_path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return png_path, ico_path


def main() -> None:
    try:
        from PyInstaller.__main__ import run as pyinstaller_run
    except ImportError as error:
        raise SystemExit("Install build dependencies with: python -m pip install -e '.[build]'") from error

    icon_png, icon_ico = create_icons()
    icon = icon_ico if platform.system() == "Windows" else icon_png
    data_separator = ";" if platform.system() == "Windows" else ":"
    css = ROOT / "src" / "sqltui" / "app.tcss"
    entry_point = ROOT / "packaging" / "entry.py"

    arguments = [
        str(entry_point),
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--name=SQLTUI",
        f"--distpath={DIST}",
        f"--workpath={WORK}",
        f"--specpath={ROOT / 'packaging'}",
        f"--paths={ROOT / 'src'}",
        f"--icon={icon}",
        f"--add-data={css}{data_separator}sqltui",
        "--collect-all=mysql.connector",
        "--collect-all=textual",
    ]
    pyinstaller_run(arguments)

    output = DIST / "SQLTUI"
    shutil.copy2(icon_png, output / "sqltui.png")
    shutil.copy2(icon_ico, output / "sqltui.ico")
    print(f"Built {output}")
    if platform.system() == "Linux":
        print("Install the CachyOS app-menu launcher with: bash packaging/linux/install.sh")
    elif platform.system() == "Windows":
        print("Build the Windows installer with Inno Setup 6 and packaging/windows/sqltui.iss")
    else:
        print("This bundle is for the current OS only; build separately on each target platform.")


if __name__ == "__main__":
    main()
