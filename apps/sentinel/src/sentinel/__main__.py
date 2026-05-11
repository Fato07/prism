"""Entry point for ``python -m sentinel``."""

import uvicorn


def main() -> None:
    """Start the sentinel FastAPI service."""
    uvicorn.run("sentinel.main:app", host="0.0.0.0", port=3202)


if __name__ == "__main__":
    main()
