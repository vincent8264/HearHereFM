"""Managed local daemon with a graceful shutdown callback."""

import uvicorn

from app.main import app


def main() -> None:
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=8000, access_log=False)
    )

    def shutdown() -> None:
        server.should_exit = True

    app.state.request_shutdown = shutdown
    server.run()


if __name__ == "__main__":
    main()
