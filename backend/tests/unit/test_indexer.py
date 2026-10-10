from forgeflow.repository.indexer import analyze_repository, tokenize
from tests.conftest import SAMPLE_REPO


def test_tokenize_splits_identifiers():
    assert {"task", "store", "taskstore", "update", "completed"} <= set(tokenize("TaskStore.update(completed)"))


def test_analyzes_sample_repository():
    analysis, index = analyze_repository(SAMPLE_REPO)
    assert analysis.languages["Python"] >= 6
    assert {"FastAPI", "Pydantic", "pytest"} <= set(analysis.frameworks)
    assert "tests/test_tasks.py" in analysis.test_files and "tests" in analysis.test_dirs
    assert "taskboard/main.py" in analysis.entrypoints
    assert analysis.verification_profile == [["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]]
    assert "taskboard/store.py" in analysis.import_graph["taskboard/main.py"]
    assert any("conftest" in c for c in analysis.conventions)
    hits = index.search("update completed task store", k=3)
    assert hits[0].path == "taskboard/store.py"
