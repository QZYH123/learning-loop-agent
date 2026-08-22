"""PyInstaller entry. Imports the package so relative imports keep working."""
from backend.app.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
