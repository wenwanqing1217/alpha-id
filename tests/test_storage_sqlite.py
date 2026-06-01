"""Tests for core/storage_sqlite.py — SqliteStorage backend."""

import json
import os
import tempfile

import pytest

from core.storage_sqlite import SqliteStorage


@pytest.fixture
def db():
    """Create a SqliteStorage instance backed by a temp file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    storage = SqliteStorage(db_path)
    yield storage
    storage.close()
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def memory_db():
    """In-memory SQLite for coalesced operations."""
    return SqliteStorage("file::memory:?cache=shared")


class TestInit:
    def test_default_path(self, monkeypatch):
        monkeypatch.setenv("COZE_WORKSPACE_PATH", "test_ws")
        storage = SqliteStorage()
        assert "test_ws" in storage.db_path
        assert storage.db_path.endswith(".db")

    def test_custom_path(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            p = f.name
        storage = SqliteStorage(p)
        assert storage.db_path == p
        storage.close()
        os.unlink(p)


class TestLoadSave:
    def test_load_nonexistent(self, db):
        assert db.load("ghost") is None

    def test_save_and_load(self, db):
        data = {"key1": "value1", "num": 42}
        db.save("my_collection", data)
        loaded = db.load("my_collection")
        assert loaded == data

    def test_save_overwrite(self, db):
        db.save("col", {"v": 1})
        db.save("col", {"v": 2})
        assert db.load("col") == {"v": 2}


class TestGetPutDelete:
    def test_get_nonexistent(self, db):
        assert db.get("users", "nonexistent") is None

    def test_put_and_get(self, db):
        record = {"name": "Alice", "age": 30}
        db.put("users", "alice", record)
        loaded = db.get("users", "alice")
        assert loaded == record

    def test_put_overwrite(self, db):
        db.put("users", "alice", {"v": 1})
        db.put("users", "alice", {"v": 2})
        assert db.get("users", "alice") == {"v": 2}

    def test_delete(self, db):
        db.put("col", "id1", {"x": 1})
        db.delete("col", "id1")
        assert db.get("col", "id1") is None

    def test_delete_nonexistent(self, db):
        # should not raise
        db.delete("col", "ghost")


class TestListCount:
    def test_list_empty(self, db):
        assert db.list("empty_col") == []

    def test_list_all_items(self, db):
        db.save("fruits", {"apple": {"name": "apple"}, "banana": {"name": "banana"}})
        items = db.list("fruits")
        assert len(items) == 2

    def test_list_with_filter(self, db):
        db.save("people", {
            "p1": {"name": "Alice", "age": 30},
            "p2": {"name": "Bob", "age": 25},
            "p3": {"name": "Charlie", "age": 30},
        })
        items = db.list("people", {"age": 30})
        assert len(items) == 2
        assert all(i["age"] == 30 for i in items)

    def test_list_filter_no_match(self, db):
        db.save("col", {"a": {"v": 1}})
        assert db.list("col", {"v": 999}) == []

    def test_count(self, db):
        db.save("col", {"x": {}, "y": {}, "z": {}})
        assert db.count("col") == 3

    def test_count_with_filter(self, db):
        db.save("col", {"a": {"t": "x"}, "b": {"t": "y"}, "c": {"t": "x"}})
        assert db.count("col", {"t": "x"}) == 2


class TestUserOps:
    def test_get_user_nonexistent(self, db):
        assert db.get_user("noone") is None

    def test_upsert_and_get_user(self, db):
        data = {"name": "Alice", "score": 100}
        db.upsert_user("alpha_001", data)
        loaded = db.get_user("alpha_001")
        assert loaded == data

    def test_upsert_overwrite(self, db):
        db.upsert_user("u1", {"v": 1})
        db.upsert_user("u1", {"v": 2})
        assert db.get_user("u1") == {"v": 2}

    def test_list_users(self, db):
        db.upsert_user("a", {"n": "Alice"})
        db.upsert_user("b", {"n": "Bob"})
        users = db.list_users()
        assert "a" in users
        assert "b" in users
        assert users["a"]["n"] == "Alice"

    def test_list_users_empty(self, db):
        assert db.list_users() == {}


class TestFriendOps:
    def test_add_and_get_friends(self, db):
        db.add_friend("alpha_1", "friend_a")
        db.add_friend("alpha_1", "friend_b")
        friends = db.get_friends("alpha_1")
        assert "friend_a" in friends
        assert "friend_b" in friends

    def test_add_duplicate_friend(self, db):
        db.add_friend("alpha_1", "friend_a")
        db.add_friend("alpha_1", "friend_a")
        assert len(db.get_friends("alpha_1")) == 1

    def test_remove_friend(self, db):
        db.add_friend("alpha_1", "friend_a")
        db.remove_friend("alpha_1", "friend_a")
        assert db.get_friends("alpha_1") == []

    def test_remove_nonexistent_friend(self, db):
        db.remove_friend("alpha_1", "ghost")  # should not raise
        assert True

    def test_get_friends_empty(self, db):
        assert db.get_friends("no_one") == []

    def test_are_friends_yes(self, db):
        db.add_friend("a", "b")
        assert db.are_friends("a", "b") is True

    def test_are_friends_no(self, db):
        assert db.are_friends("a", "b") is False

    def test_are_friends_reverse_only(self, db):
        # Only one direction
        db.add_friend("a", "b")
        assert db.are_friends("b", "a") is False


class TestClose:
    def test_close_idempotent(self, db):
        db.close()
        db.close()  # second close should not raise
        assert True
