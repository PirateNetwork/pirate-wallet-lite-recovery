"""PyInstaller entry point; keep normal package-relative imports intact."""

from pirate_wallet_lite_recovery.cli import entrypoint


if __name__ == "__main__":
    entrypoint()
