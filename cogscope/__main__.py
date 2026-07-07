"""Allow ``python -m cogscope`` and PyInstaller entry."""

from cogscope.cli.main import app

if __name__ == "__main__":
    app()
