"""Build script for Vercel: copy static assets to public/ for CDN serving."""
import shutil
from pathlib import Path

def main():
    static = Path("static")
    public_static = Path("public/static")
    if static.exists():
        public_static.parent.mkdir(parents=True, exist_ok=True)
        if public_static.exists():
            shutil.rmtree(public_static)
        shutil.copytree(static, public_static)
        print(f"Copied {static} -> {public_static}")
    else:
        print("No static/ directory found")

if __name__ == "__main__":
    main()
