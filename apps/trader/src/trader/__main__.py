"""Entry point for ``python -m trader``."""

import uvicorn


def main() -> None:
    """Start the trader FastAPI service."""
    uvicorn.run("trader.main:app", host="0.0.0.0", port=3201)


if __name__ == "__main__":
    main()
