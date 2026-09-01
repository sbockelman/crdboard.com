import os

from crdboard.table_server import app, socketio


if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=7000,
        debug=os.getenv("FLASK_DEBUG") == "1",
        allow_unsafe_werkzeug=True,
    )
