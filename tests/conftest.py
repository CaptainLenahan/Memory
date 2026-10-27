import os
import tempfile

os.environ["MEMORY_DATA_DIR"] = tempfile.mkdtemp(prefix="memory-test-")
os.environ["ANTHROPIC_API_KEY"] = ""
