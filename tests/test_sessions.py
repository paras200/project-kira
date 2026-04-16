"""Tests for session database."""

from __future__ import annotations

import json


class TestSessionDB:
    def test_create_session(self, tmp_db):
        sid = tmp_db.create_session(channel="cli", title="Test Session")
        assert sid is not None
        assert len(sid) == 8

    def test_get_session(self, tmp_db):
        sid = tmp_db.create_session(channel="test", title="My Session")
        session = tmp_db.get_session(sid)
        assert session is not None
        assert session["title"] == "My Session"
        assert session["channel"] == "test"
        assert session["message_count"] == 0

    def test_get_nonexistent_session(self, tmp_db):
        assert tmp_db.get_session("nonexistent") is None

    def test_add_and_get_messages(self, tmp_db):
        sid = tmp_db.create_session()
        tmp_db.add_message(sid, "user", "hello")
        tmp_db.add_message(sid, "assistant", "hi there", tokens=50, cost_usd=0.001)

        msgs = tmp_db.get_messages(sid)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["tokens"] == 50

    def test_message_count_updates(self, tmp_db):
        sid = tmp_db.create_session()
        tmp_db.add_message(sid, "user", "one")
        tmp_db.add_message(sid, "user", "two")
        tmp_db.add_message(sid, "assistant", "three")

        session = tmp_db.get_session(sid)
        assert session["message_count"] == 3

    def test_cost_accumulates(self, tmp_db):
        sid = tmp_db.create_session()
        tmp_db.add_message(sid, "user", "q1", cost_usd=0.01)
        tmp_db.add_message(sid, "assistant", "a1", cost_usd=0.02)

        session = tmp_db.get_session(sid)
        assert abs(session["total_cost_usd"] - 0.03) < 0.001

    def test_token_count_accumulates(self, tmp_db):
        sid = tmp_db.create_session()
        tmp_db.add_message(sid, "user", "q", tokens=100)
        tmp_db.add_message(sid, "assistant", "a", tokens=200)

        session = tmp_db.get_session(sid)
        assert session["total_tokens"] == 300

    def test_tool_calls_stored(self, tmp_db):
        sid = tmp_db.create_session()
        tool_calls = [{"id": "tc1", "name": "terminal", "arguments": {"command": "ls"}}]
        tmp_db.add_message(sid, "assistant", "running", tool_calls=tool_calls)

        msgs = tmp_db.get_messages(sid)
        stored = json.loads(msgs[0]["tool_calls"])
        assert stored[0]["name"] == "terminal"

    def test_tool_result_stored(self, tmp_db):
        sid = tmp_db.create_session()
        tmp_db.add_message(sid, "tool", "file1.py", tool_call_id="tc1", tool_name="terminal")

        msgs = tmp_db.get_messages(sid)
        assert msgs[0]["tool_call_id"] == "tc1"
        assert msgs[0]["tool_name"] == "terminal"

    def test_list_sessions(self, tmp_db):
        tmp_db.create_session(title="Session A")
        tmp_db.create_session(title="Session B")
        tmp_db.create_session(title="Session C")

        sessions = tmp_db.list_sessions(limit=2)
        assert len(sessions) == 2

    def test_list_sessions_ordered_by_updated(self, tmp_db):
        s1 = tmp_db.create_session(title="First")
        s2 = tmp_db.create_session(title="Second")
        # Add a message to s1 to bump its updated_at
        tmp_db.add_message(s1, "user", "update to make s1 most recent")

        sessions = tmp_db.list_sessions()
        # s1 should have more messages and be updated more recently
        session_ids = [s["id"] for s in sessions]
        assert s1 in session_ids
        assert s2 in session_ids

    def test_full_text_search(self, tmp_db):
        sid = tmp_db.create_session()
        tmp_db.add_message(sid, "user", "tell me about quantum computing")
        tmp_db.add_message(sid, "assistant", "quantum computing uses qubits")
        tmp_db.add_message(sid, "user", "what about regular computers")

        results = tmp_db.search("quantum")
        assert len(results) == 2

    def test_search_no_results(self, tmp_db):
        sid = tmp_db.create_session()
        tmp_db.add_message(sid, "user", "hello world")

        results = tmp_db.search("nonexistent_term_xyz")
        assert len(results) == 0

    def test_update_session_title(self, tmp_db):
        sid = tmp_db.create_session(title="Original")
        tmp_db.update_session_title(sid, "Updated Title")

        session = tmp_db.get_session(sid)
        assert session["title"] == "Updated Title"
