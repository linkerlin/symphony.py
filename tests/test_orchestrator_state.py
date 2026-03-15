"""Tests for orchestrator state management.

Tests state transitions, retry logic, and concurrent execution control.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from symphony.models.issue import Issue
from symphony.models.session import SessionState, SessionStatus
from symphony.orchestrator.state import (
    OrchestratorState,
    RetryEntry,
    RunningEntry,
)


class TestOrchestratorState:
    """Tests for orchestrator state management."""
    
    def test_state_initialization(self):
        """Test initial state is empty."""
        state = OrchestratorState(max_concurrent_agents=3)
        
        assert state.max_concurrent_agents == 3
        assert len(state.running) == 0
        assert len(state.claimed) == 0
        assert len(state.retry_attempts) == 0
        assert len(state.completed) == 0
        assert state.available_slots == 3
    
    def test_claim_issue(self):
        """Test claiming an issue."""
        state = OrchestratorState(max_concurrent_agents=3)
        
        issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        result = state.claim(issue)
        
        assert result is True
        assert issue.id in state.claimed
        assert state.claimed[issue.id].issue_id == issue.id
    
    def test_claim_duplicate_fails(self):
        """Test claiming same issue twice fails."""
        state = OrchestratorState(max_concurrent_agents=3)
        
        issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        state.claim(issue)
        result = state.claim(issue)
        
        assert result is False
    
    def test_start_running(self):
        """Test starting an issue."""
        state = OrchestratorState(max_concurrent_agents=3)
        
        issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        state.claim(issue)
        session = SessionState(issue_id=issue.id, issue_identifier="TEST-" + str(issue.id)[-4:])
        
        result = state.start(issue, session)
        
        assert result is True
        assert issue.id in state.running
        assert issue.id not in state.claimed
        assert state.available_slots == 2
    
    def test_start_exceeds_max_concurrent(self):
        """Test starting when at max concurrent fails."""
        state = OrchestratorState(max_concurrent_agents=1)
        
        issue1 = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        issue2 = Issue(
            id="test-2",
            identifier="TEST-2",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        state.claim(issue1)
        state.claim(issue2)
        
        session1 = SessionState(issue_id=issue1.id, issue_identifier="TEST-" + str(issue1.id)[-4:])
        session2 = SessionState(issue_id=issue2.id, issue_identifier="TEST-" + str(issue2.id)[-4:])
        
        state.start(issue1, session1)
        result = state.start(issue2, session2)
        
        assert result is False
        assert issue2.id in state.claimed  # Should stay claimed
    
    def test_complete_issue(self):
        """Test completing an issue."""
        state = OrchestratorState(max_concurrent_agents=3)
        
        issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        state.claim(issue)
        session = SessionState(issue_id=issue.id, issue_identifier="TEST-" + str(issue.id)[-4:])
        state.start(issue, session)
        
        result = state.complete(issue, success=True)
        
        assert result is True
        assert issue.id not in state.running
        assert issue.id in state.completed
        assert state.available_slots == 3
    
    def test_retry_queue(self):
        """Test retry queue functionality."""
        state = OrchestratorState(max_concurrent_agents=3)
        
        issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        # Schedule retry
        state.schedule_retry(issue, attempt=1, delay_seconds=0)
        
        assert issue.id in state.retry_attempts
        entry = state.retry_attempts[issue.id]
        assert entry.attempt == 1
        assert entry.due_in_seconds <= 0
    
    def test_retry_ready(self):
        """Test checking if retries are ready."""
        state = OrchestratorState(max_concurrent_agents=3)
        
        issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        # Schedule retry with no delay
        state.schedule_retry(issue, attempt=1, delay_seconds=0)
        
        # Should be ready immediately
        ready = state.get_ready_retries()
        
        assert len(ready) == 1
        assert ready[0].issue_id == issue.id
    
    def test_retry_not_ready_yet(self):
        """Test that future retries are not ready."""
        state = OrchestratorState(max_concurrent_agents=3)
        
        issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        # Schedule retry far in future
        state.schedule_retry(issue, attempt=1, delay_seconds=3600)
        
        ready = state.get_ready_retries()
        
        assert len(ready) == 0
    
    def test_release_claim(self):
        """Test releasing a claimed issue."""
        state = OrchestratorState(max_concurrent_agents=3)
        
        issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        state.claim(issue)
        assert issue.id in state.claimed
        
        state.release(issue)
        
        assert issue.id not in state.claimed
    
    def test_get_state_summary(self):
        """Test getting state summary."""
        state = OrchestratorState(max_concurrent_agents=3)
        
        issue1 = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        issue2 = Issue(
            id="test-2",
            identifier="TEST-2",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        state.claim(issue1)
        state.claim(issue2)
        
        summary = state.get_summary()
        
        assert summary["claimed"] == 2
        assert summary["running"] == 0
        assert summary["retrying"] == 0
        assert summary["completed"] == 0
        assert summary["available_slots"] == 3


class TestSessionState:
    """Tests for session state management."""
    
    def test_session_initialization(self):
        """Test initial session state."""
        session = SessionState(issue_id="test-1", issue_identifier="TEST-1")
        
        assert session.issue_id == "test-1"
        assert session.status == SessionStatus.PREPARING
        assert session.llm_usage.total_tokens == 0
    
    def test_session_status_transitions(self):
        """Test session status transitions."""
        session = SessionState(issue_id="test-1", issue_identifier="TEST-" + str("test-1")[-4:])
        
        # Default status is PREPARING
        assert session.status == SessionStatus.PREPARING
        
        # Status can be set directly
        session.status = SessionStatus.RUNNING
        assert session.status == SessionStatus.RUNNING
        
        session.status = SessionStatus.COMPLETED
        assert session.status == SessionStatus.COMPLETED
    
    def test_session_turn_tracking(self):
        """Test turn count tracking."""
        session = SessionState(issue_id="test-1", issue_identifier="TEST-" + str("test-1")[-4:])
        
        session.increment_turn()
        assert session.turn_count == 1
        
        session.increment_turn()
        assert session.turn_count == 2
    
    def test_session_token_tracking(self):
        """Test LLM token usage tracking."""
        session = SessionState(issue_id="test-1", issue_identifier="TEST-" + str("test-1")[-4:])
        
        session.add_usage({"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})
        
        assert session.llm_usage.prompt_tokens == 100
        assert session.llm_usage.completion_tokens == 50
        assert session.llm_usage.total_tokens == 150
    
    def test_session_runtime_tracking(self):
        """Test runtime tracking."""
        session = SessionState(issue_id="test-1", issue_identifier="TEST-" + str("test-1")[-4:])
        session.start()
        
        # Simulate some work
        import time
        time.sleep(0.01)
        
        runtime = session.get_runtime_seconds()
        assert runtime > 0
    
    def test_session_is_active(self):
        """Test checking if session is active."""
        session = SessionState(issue_id="test-1", issue_identifier="TEST-" + str("test-1")[-4:])
        
        # PREPARING is not considered active
        assert not session.is_active()
        
        # RUNNING is active
        session.status = SessionStatus.RUNNING
        assert session.is_active()
        
        # COMPLETED is not active
        session.status = SessionStatus.COMPLETED
        assert not session.is_active()


class TestRetryEntry:
    """Tests for retry entry."""
    
    def test_retry_entry_creation(self):
        """Test creating retry entry."""
        entry = RetryEntry(
            issue_id="test-1",
            identifier="TEST-1",
            attempt=2,
            scheduled_at=datetime.utcnow(),
            delay_seconds=60,
        )
        
        assert entry.issue_id == "test-1"
        assert entry.attempt == 2
        assert entry.due_in_seconds <= 60  # Should be near 60 or negative if past
    
    def test_retry_entry_is_due(self):
        """Test checking if retry is due."""
        entry = RetryEntry(
            issue_id="test-1",
            identifier="TEST-1",
            attempt=1,
            scheduled_at=datetime.utcnow() - timedelta(seconds=10),
            delay_seconds=5,
        )
        
        assert entry.is_due() is True
    
    def test_retry_entry_not_due(self):
        """Test checking if retry is not yet due."""
        entry = RetryEntry(
            issue_id="test-1",
            identifier="TEST-1",
            attempt=1,
            scheduled_at=datetime.utcnow(),
            delay_seconds=3600,
        )
        
        assert entry.is_due() is False
    
    def test_retry_entry_exponential_backoff(self):
        """Test exponential backoff calculation."""
        delays = [RetryEntry.calculate_backoff(attempt) for attempt in range(1, 6)]
        
        # Each delay should be larger than previous
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i-1]
        
        # First attempt should be small
        assert delays[0] < 20
        
        # Later attempts should be larger
        assert delays[4] > delays[0]


class TestRunningEntry:
    """Tests for running entry."""
    
    def test_running_entry_creation(self):
        """Test creating running entry."""
        issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        session = SessionState(issue_id=issue.id, issue_identifier="TEST-" + str(issue.id)[-4:])
        
        entry = RunningEntry(
            issue=issue,
            session_state=session,
            started_at=datetime.utcnow(),
        )
        
        assert entry.issue.id == "test-1"
        assert entry.session_state == session
        assert entry.retry_attempt is None
    
    def test_running_entry_with_attempt(self):
        """Test running entry with retry attempt."""
        issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        session = SessionState(issue_id=issue.id, issue_identifier="TEST-" + str(issue.id)[-4:])
        
        entry = RunningEntry(
            issue=issue,
            session_state=session,
            started_at=datetime.utcnow(),
            retry_attempt=2,
        )
        
        assert entry.retry_attempt == 2
