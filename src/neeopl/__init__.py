from .app import create_app


def main() -> None:
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8000)