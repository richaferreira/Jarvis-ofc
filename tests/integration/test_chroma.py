"""Real local database persistence across processes, without model downloads."""

import subprocess
import sys


def test_chroma_persists_and_filters_between_processes(tmp_path):
    setup = '''
import sys
from pathlib import Path
from app.memory.vector_store import VectorStore
store = VectorStore(Path(sys.argv[1]))
assert store is VectorStore(Path(sys.argv[1]))
collection = store.collection("test_preferences")
collection.upsert(ids=["1", "2"], documents=["Português", "English"],
                  embeddings=[[1.0, 0.0], [1.0, 0.0]], metadatas=[{"owner": "a"}, {"owner": "b"}])
'''
    read = '''
import sys
from pathlib import Path
from app.memory.vector_store import VectorStore
collection = VectorStore(Path(sys.argv[1])).collection("test_preferences")
result = collection.query(query_embeddings=[[1.0, 0.0]], n_results=1,
                          where={"owner": "a"}, include=["documents"])
assert result["documents"] == [["Português"]], result
'''
    for script in (setup, read):
        subprocess.run([sys.executable, "-c", script, str(tmp_path / "chroma")], check=True, timeout=90)
