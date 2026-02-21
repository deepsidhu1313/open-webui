
import sys
from unittest.mock import MagicMock

# List of modules to mock because they are missing or expensive
MOCK_MODULES = [
    "chromadb",
    "chromadb.config",
    "langchain",
    "langchain_community",
    "langchain_community.document_loaders",
    "langchain_community.vectorstores",
    "langchain_community.embeddings",
    "langchain.text_splitter",
    "sentence_transformers",
    "pydub",
    "tiktoken",
    "faster_whisper",
    "authlib",
    "authlib.integrations.starlette_client",
    "starsessions",
    "starsessions.stores.redis",
    "bcrypt",
    "argon2",
    "passlib",
    "passlib.context",
    "apscheduler",
    "apscheduler.schedulers",
    "apscheduler.schedulers.background",
    "jwt",
    "jose",
    "socketio",
    "python_socketio",
    "engineio",
    "yfinance",
    "duckduckgo_search",
    "googleapiclient.discovery",
    "google.oauth2.credentials",
    "google_auth_oauthlib.flow",
    "extract_msg",
    "mesh_client",
    "peewee",
    "peewee_migrate",
    "psutil",
    "rapidfuzz",
    "sqlalchemy",
    "sqlalchemy.orm",
    "sqlalchemy.ext.declarative",
    "alembic",
    "alembic.config",
    "pandas",
    "numpy", 
    "docker",
    "typer",
    "markdown",
    "bs4",
    "watchdog",
    "watchdog.observers",
    "watchdog.events",
    "validators",
    "aiocache",
    "aiofiles",
    "async_timeout",
    "fake_useragent",
    "starlette_compress",
    "bcrypt",
    "passlib.hash",
    "aiohttp", 
    "requests",
    "itsdangerous",
]

class MockModule(MagicMock):
    @classmethod
    def __getattr__(cls, name):
        return MagicMock()

for mod in MOCK_MODULES:
    sys.modules[mod] = MockModule()

# Also mock some open_webui internal heavy imports if needed, but let's try just external first.
