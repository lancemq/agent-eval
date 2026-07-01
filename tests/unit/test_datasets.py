"""Tests for the DatasetStore and row-level diff."""

import pytest

from agent_eval.datasets import DatasetRecord, DatasetStore
from agent_eval.datasets.store import diff_rows


@pytest.fixture()
def store(tmp_path):
    return DatasetStore(str(tmp_path))


def test_create_and_get(store):
    rows = [{"task_id": "t1", "input": "hello", "expected": "world"}]
    record = store.create("ds1", rows, description="d")
    assert record.name == "ds1"
    assert record.version == "1.0.0"
    assert record.row_count == 1

    got = store.get("ds1")
    assert got.rows == rows

    summaries = store.list_datasets()
    assert len(summaries) == 1
    assert summaries[0]["name"] == "ds1"
    assert summaries[0]["latest_version"] == "1.0.0"
    assert summaries[0]["row_count"] == 1


def test_create_duplicate_raises(store):
    store.create("ds1", [])
    with pytest.raises(ValueError):
        store.create("ds1", [])


def test_invalid_name(store):
    with pytest.raises(ValueError):
        store.create("bad name!", [])


def test_add_version(store):
    store.create("ds1", [{"task_id": "t1"}])
    v2 = store.add_version("ds1", [{"task_id": "t1"}, {"task_id": "t2"}])
    assert v2.version == "1.1.0"
    assert v2.row_count == 2
    versions = store.list_versions("ds1")
    assert len(versions) == 2
    assert versions[1]["version"] == "1.1.0"


def test_update_rows_patch_bump(store):
    store.create("ds1", [{"task_id": "t1", "input": "a"}])
    updated = store.update_rows("ds1", [{"task_id": "t1", "input": "b"}])
    assert updated.version == "1.0.1"
    assert updated.rows[0]["input"] == "b"
    # original version still retrievable
    assert store.get("ds1", "1.0.0").rows[0]["input"] == "a"


def test_delete_and_delete_version(store):
    store.create("ds1", [{"task_id": "t1"}])
    store.add_version("ds1", [{"task_id": "t1"}, {"task_id": "t2"}])
    assert store.delete_version("ds1", "1.1.0") is True
    assert store.get("ds1").version == "1.0.0"
    assert store.delete("ds1") is True
    assert store.list_datasets() == []


def test_diff_added_removed_modified(store):
    rows_a = [
        {"task_id": "t1", "input": "a", "expected": "x"},
        {"task_id": "t2", "input": "b", "expected": "y"},
        {"task_id": "t3", "input": "c", "expected": "z"},
    ]
    rows_b = [
        {"task_id": "t1", "input": "a", "expected": "x"},
        {"task_id": "t2", "input": "b", "expected": "CHANGED"},
        {"task_id": "t4", "input": "d", "expected": "w"},
    ]
    store.create("ds", rows_a)
    store.add_version("ds", rows_b)
    d = store.diff("ds", "1.0.0", "1.1.0")
    assert d["summary"]["added"] == 1
    assert d["summary"]["removed"] == 1
    assert d["summary"]["modified"] == 1
    assert d["summary"]["unchanged"] == 1
    assert d["added"][0]["task_id"] == "t4"
    assert d["removed"][0]["task_id"] == "t3"
    assert d["modified"][0]["task_id"] == "t2"
    assert d["modified"][0]["fields"]["expected"]["to"] == "CHANGED"


def test_diff_rows_function_directly():
    a = [{"task_id": "x", "v": 1}]
    b = [{"task_id": "x", "v": 2}]
    d = diff_rows(a, b)
    assert d["summary"]["modified"] == 1
    assert d["modified"][0]["fields"]["v"] == {"from": 1, "to": 2}


def test_dataset_record_roundtrip():
    r = DatasetRecord(name="d", version="1", rows=[{"task_id": "a"}], description="x")
    d = r.to_dict()
    r2 = DatasetRecord.from_dict(d)
    assert r2.name == "d"
    assert r2.rows == r.rows
