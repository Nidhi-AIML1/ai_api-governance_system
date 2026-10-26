"""
Dashboard ke rang ek command se badalne wali script.

Chalane ke liye (frontend folder ke andar):
    python recolor.py pink        -> gulabi theme
    python recolor.py mint        -> mint / teal (hara-neela) theme
    python recolor.py original    -> pehle wale rang wapas

Ye script src/index.css, src/components.jsx aur src/App.jsx ke sirf rang badalti hai.
Pehli baar chalane par asli files ka backup src/_backup_original folder mein ban jata hai,
isliye kabhi bhi "original" se wapas aa sakti ho.
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
BACKUP = os.path.join(SRC, "_backup_original")
FILES = ["index.css", "components.jsx", "App.jsx"]

# (purana rang) -> (naya rang). Sab ek saath badalte hain, isliye ek rang do baar nahi badalta.
THEMES = {
    "pink": {
        # mukhya rang
        "#4f46e5": "#be185d", "#6366f1": "#f43f8b", "#818cf8": "#f9a8d4", "#8b5cf6": "#d946ef",
        "#7c3aed": "#c026d3", "#db2777": "#9333ea", "#ec4899": "#f472b6", "#a5b4fc": "#f9a8d4",
        # halke (tint) rang
        "#eef2ff": "#fdf2f8", "#f5f3ff": "#fff0f7", "#faf5ff": "#fdf4ff", "#c7d2fe": "#fbcfe8",
        "#e0e7ff": "#fce7f3", "#3730a3": "#9d174d", "#4c1d95": "#86198f",
        # background aur sidebar
        "#f1f5f9": "#fff5fa", "#fafbff": "#fffafc", "#eef0fb": "#fbe7f1",
        "#1e1b4b": "#3b0a2e", "#312e81": "#6b1747",
        # rgba (shadow / glow) ke rang
        "79, 70, 229": "190, 24, 93", "99, 102, 241": "244, 63, 139", "124, 58, 237": "192, 38, 211",
        "168, 85, 247": "217, 70, 239", "236, 72, 153": "244, 114, 182",
    },
    "mint": {
        "#4f46e5": "#0f766e", "#6366f1": "#14b8a6", "#818cf8": "#5eead4", "#8b5cf6": "#06b6d4",
        "#7c3aed": "#0891b2", "#db2777": "#059669", "#ec4899": "#34d399", "#a5b4fc": "#5eead4",
        "#eef2ff": "#f0fdfa", "#f5f3ff": "#ecfeff", "#faf5ff": "#f0fdf4", "#c7d2fe": "#99f6e4",
        "#e0e7ff": "#ccfbf1", "#3730a3": "#115e59", "#4c1d95": "#155e75",
        "#f1f5f9": "#f0fdfa", "#fafbff": "#f7fefd", "#eef0fb": "#d9f2ee",
        "#1e1b4b": "#042f2e", "#312e81": "#115e59",
        "79, 70, 229": "15, 118, 110", "99, 102, 241": "20, 184, 166", "124, 58, 237": "8, 145, 178",
        "168, 85, 247": "6, 182, 212", "236, 72, 153": "52, 211, 153",
    },
}


def make_backup() -> None:
    if os.path.isdir(BACKUP):
        return
    os.makedirs(BACKUP)
    for name in FILES:
        shutil.copyfile(os.path.join(SRC, name), os.path.join(BACKUP, name))
    print("Backup of the original files saved in src/_backup_original")


def apply(theme: str) -> None:
    mapping = THEMES.get(theme)
    pattern = None
    if mapping:
        pattern = re.compile("|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)), re.IGNORECASE)
    for name in FILES:
        with open(os.path.join(BACKUP, name), encoding="utf-8") as f:
            text = f.read()
        count = 0
        if pattern:
            text, count = pattern.subn(lambda m: mapping[m.group(0).lower()], text)
        with open(os.path.join(SRC, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print(f"  {name}: {count} colors changed")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in list(THEMES) + ["original"]:
        sys.exit("Use:  python recolor.py pink   |   python recolor.py mint   |   python recolor.py original")
    if not os.path.isdir(SRC):
        sys.exit("Run this file from the frontend folder (the one that contains the src folder).")
    make_backup()
    theme = sys.argv[1]
    print(f"Applying theme: {theme}")
    apply(theme)
    print("Done. The browser updates by itself (or press Ctrl + F5).")


if __name__ == "__main__":
    main()