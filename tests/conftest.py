import os
import tempfile

os.environ["MEMORY_DATA_DIR"] = tempfile.mkdtemp(prefix="memory-test-")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["MEMORY_EXTRA_LOCAL_HOSTS"] = "testserver"   # FastAPI's TestClient host counts as local
os.environ.pop("MEMORY_PLANNER_SYNC_TOKEN", None)          # each test sets its own
