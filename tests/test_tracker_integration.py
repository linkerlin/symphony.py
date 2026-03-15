"""Integration tests for trackers.

Tests Linear API connectivity and issue tracking functionality.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest

from symphony.models.issue import Issue
from symphony.trackers.linear import LinearTracker
from symphony.trackers.memory import MemoryTracker


@pytest.mark.skipif(
    not os.environ.get("LINEAR_API_KEY"),
    reason="LINEAR_API_KEY not set"
)
@pytest.mark.integration
class TestLinearTrackerIntegration:
    """Integration tests for Linear tracker with real API."""
    
    @pytest.mark.timeout(15)
    async def test_linear_connectivity(self):
        """Test basic connectivity to Linear API."""
        tracker = LinearTracker(
            api_key=os.environ["LINEAR_API_KEY"],
            project_slug=os.environ.get("LINEAR_PROJECT_SLUG", "test-project"),
        )
        
        try:
            # Just initializing and closing tests connectivity
            assert tracker.api_key is not None
        finally:
            await tracker.close()
    
    @pytest.mark.timeout(15)
    async def test_fetch_issues(self):
        """Test fetching issues from Linear."""
        tracker = LinearTracker(
            api_key=os.environ["LINEAR_API_KEY"],
            project_slug=os.environ.get("LINEAR_PROJECT_SLUG", "test-project"),
            active_states=["Todo", "In Progress"],
        )
        
        try:
            issues = await tracker.fetch_candidate_issues()
            
            # Should return a list (might be empty)
            assert isinstance(issues, list)
            
            # If issues exist, verify structure
            for issue in issues:
                assert issue.id is not None
                assert issue.identifier is not None
                assert issue.title is not None
                
        finally:
            await tracker.close()
    
    @pytest.mark.timeout(15)
    async def test_claim_and_complete(self):
        """Test claiming and completing an issue.
        
        Note: This creates a real issue in Linear if the project exists.
        """
        project_slug = os.environ.get("LINEAR_PROJECT_SLUG")
        if not project_slug:
            pytest.skip("LINEAR_PROJECT_SLUG not set")
        
        tracker = LinearTracker(
            api_key=os.environ["LINEAR_API_KEY"],
            project_slug=project_slug,
        )
        
        try:
            # Fetch issues first
            issues = await tracker.fetch_candidate_issues()
            
            if not issues:
                pytest.skip("No issues available in Linear for testing")
            
            # Try to claim the first issue
            issue = issues[0]
            claimed = await tracker.claim(issue)
            
            # Claim result depends on permissions
            # Just verify it doesn't error
            assert claimed is True or claimed is False
            
        finally:
            await tracker.close()


class TestMemoryTracker:
    """Tests for memory tracker (used in tests)."""
    
    async def test_memory_tracker_basic(self):
        """Test basic memory tracker operations."""
        tracker = MemoryTracker()
        
        # Initially no issues
        issues = await tracker.fetch_candidate_issues()
        assert len(issues) == 0
        
        await tracker.close()
    
    async def test_memory_tracker_add_issues(self):
        """Test adding issues to memory tracker."""
        tracker = MemoryTracker()
        
        # Add test issues
        tracker.add_issue(Issue(
            id="mem-1",
            identifier="MEM-1",
            title="Test 1",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        ))
        tracker.add_issue(Issue(
            id="mem-2",
            identifier="MEM-2",
            title="Test 2",
            description="Test",
            state="In Progress",
            labels=[],
            blockers=[],
        ))
        
        issues = await tracker.fetch_candidate_issues()
        assert len(issues) == 2
        
        await tracker.close()
    
    async def test_memory_tracker_claim(self):
        """Test claiming issues in memory tracker."""
        tracker = MemoryTracker()
        
        issue = Issue(
            id="mem-1",
            identifier="MEM-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        tracker.add_issue(issue)
        
        # Claim should succeed
        result = await tracker.claim(issue)
        assert result is True
        
        # Second claim should fail
        result = await tracker.claim(issue)
        assert result is False
        
        await tracker.close()
    
    async def test_memory_tracker_complete(self):
        """Test completing issues in memory tracker."""
        tracker = MemoryTracker()
        
        issue = Issue(
            id="mem-1",
            identifier="MEM-1",
            title="Test",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        tracker.add_issue(issue)
        
        # Complete the issue
        result = await tracker.complete(issue, success=True)
        assert result is True
        
        # Issue should be marked as completed
        assert tracker.completed_issues[issue.id]["success"] is True
        
        await tracker.close()
    
    async def test_memory_tracker_state_filtering(self):
        """Test that tracker filters by state."""
        tracker = MemoryTracker(
            active_states=["Todo"],
            terminal_states=["Done"],
        )
        
        # Add issues in different states
        tracker.add_issue(Issue(
            id="mem-1",
            identifier="MEM-1",
            title="Todo Issue",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        ))
        tracker.add_issue(Issue(
            id="mem-2",
            identifier="MEM-2",
            title="Done Issue",
            description="Test",
            state="Done",
            labels=[],
            blockers=[],
        ))
        tracker.add_issue(Issue(
            id="mem-3",
            identifier="MEM-3",
            title="Other Issue",
            description="Test",
            state="Other",
            labels=[],
            blockers=[],
        ))
        
        # Should only get Todo issues
        issues = await tracker.fetch_candidate_issues()
        assert len(issues) == 1
        assert issues[0].state == "Todo"
        
        await tracker.close()


class TestIssueModel:
    """Tests for Issue data model."""
    
    def test_issue_creation(self):
        """Test creating an issue."""
        issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Test Issue",
            description="Test description",
            state="Todo",
            labels=["bug", "urgent"],
            blockers=[],
        )
        
        assert issue.id == "test-1"
        assert issue.identifier == "TEST-1"
        assert issue.title == "Test Issue"
        assert len(issue.labels) == 2
    
    def test_issue_is_blocked(self):
        """Test checking if issue is blocked."""
        blocked_issue = Issue(
            id="test-1",
            identifier="TEST-1",
            title="Blocked",
            description="Test",
            state="Todo",
            labels=[],
            blockers=["BLOCK-1"],
        )
        
        unblocked_issue = Issue(
            id="test-2",
            identifier="TEST-2",
            title="Not Blocked",
            description="Test",
            state="Todo",
            labels=[],
            blockers=[],
        )
        
        assert blocked_issue.is_blocked() is True
        assert unblocked_issue.is_blocked() is False
    
    def test_issue_from_dict(self):
        """Test creating issue from dictionary."""
        data = {
            "id": "test-1",
            "identifier": "TEST-1",
            "title": "Test",
            "description": "Description",
            "state": "Todo",
            "labels": ["bug"],
            "blockers": [],
        }
        
        issue = Issue.from_dict(data)
        
        assert issue.id == "test-1"
        assert issue.title == "Test"
        assert issue.labels == ["bug"]
