"""Entry point.

Run either way:
    python run.py                          # reads PDF_TOOLS_HOST/PORT/DEBUG
    flask --app run:app run --debug        # spec's documented command
"""
import os

from app import create_app

app = create_app(os.environ.get("PDF_TOOLS_CONFIG", "development"))

if __name__ == "__main__":
    app.run(
        host=os.environ.get("PDF_TOOLS_HOST", "127.0.0.1"),
        port=int(os.environ.get("PDF_TOOLS_PORT", "5000")),
        debug=os.environ.get("PDF_TOOLS_DEBUG", "1") == "1",
    )
