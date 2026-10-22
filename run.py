"""
Entry point. Loads .env before anything else imports app.config, since
Config reads os.environ at import time.
"""

from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402 - must come after load_dotenv()
from app.models import *  # noqa: F401,E402 - ensures models are registered with SQLAlchemy

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
