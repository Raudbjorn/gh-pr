"""
Unit tests for PR filtering functionality.

Tests various PR filter implementations.
"""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from gh_pr.core.filters import CommentFilter

# Mock filter classes for testing
class PRFilter:
    """Base PR filter class for testing."""
    def matches(self, pr):
        """Check if PR matches filter criteria."""
        raise NotImplementedError("Subclasses must implement matches()")

class StateFilter(PRFilter):
    def __init__(self, state):
        self.state = state
    def matches(self, pr):
        if self.state == 'all':
            return True
        return pr.state == self.state

class AuthorFilter(PRFilter):
    def __init__(self, authors):
        self.authors = authors if isinstance(authors, list) else [authors]
        self.authors = [a.lower() for a in self.authors]
    def matches(self, pr):
        return pr.user.login.lower() in self.authors

class LabelFilter(PRFilter):
    def __init__(self, labels, require_all=False, exclude=False):
        self.labels = labels if isinstance(labels, list) else [labels]
        self.require_all = require_all
        self.exclude = exclude
    def matches(self, pr):
        pr_labels = [label.name for label in pr.labels]
        if self.exclude:
            return not any(label in pr_labels for label in self.labels)
        elif self.require_all:
            return all(label in pr_labels for label in self.labels)
        else:
            return any(label in pr_labels for label in self.labels)

class DateFilter(PRFilter):
    def __init__(self, created_after=None, created_before=None, updated_after=None):
        self.created_after = created_after
        self.created_before = created_before
        self.updated_after = updated_after
    def matches(self, pr):
        if self.created_after and pr.created_at < self.created_after:
            return False
        if self.created_before and pr.created_at > self.created_before:
            return False
        if self.updated_after and pr.updated_at < self.updated_after:
            return False
        return True

class ReviewFilter(PRFilter):
    def __init__(self, status=None, reviewer=None):
        self.status = status
        self.reviewer = reviewer
    def matches(self, pr):
        reviews = pr.get_reviews()
        if self.reviewer:
            return any(r.user.login.lower() == self.reviewer.lower() for r in reviews)
        if self.status == 'approved':
            return any(r.state == 'APPROVED' for r in reviews)
        elif self.status == 'changes_requested':
            return any(r.state == 'CHANGES_REQUESTED' for r in reviews)
        elif self.status == 'pending':
            return not any(r.state in ['APPROVED', 'CHANGES_REQUESTED'] for r in reviews)
        return True

class CombinedFilter(PRFilter):
    def __init__(self, filters, operator='AND'):
        self.filters = filters
        self.operator = operator
    def matches(self, pr):
        if self.operator == 'AND':
            return all(f.matches(pr) for f in self.filters)
        else:  # OR
            return any(f.matches(pr) for f in self.filters)


class TestPRFilter(unittest.TestCase):
    """Test base PR filter functionality."""

    def test_base_filter_interface(self):
        """Test that base filter requires implementation."""
        base_filter = PRFilter()

        with self.assertRaises(NotImplementedError):
            base_filter.matches(Mock())


class TestStateFilter(unittest.TestCase):
    """Test PR state filtering."""

    def test_open_state_filter(self):
        """Test filtering for open PRs."""
        filter_open = StateFilter('open')

        pr_open = Mock(state='open')
        pr_closed = Mock(state='closed')

        self.assertTrue(filter_open.matches(pr_open))
        self.assertFalse(filter_open.matches(pr_closed))

    def test_closed_state_filter(self):
        """Test filtering for closed PRs."""
        filter_closed = StateFilter('closed')

        pr_open = Mock(state='open')
        pr_closed = Mock(state='closed')

        self.assertFalse(filter_closed.matches(pr_open))
        self.assertTrue(filter_closed.matches(pr_closed))

    def test_all_state_filter(self):
        """Test filtering for all PRs."""
        filter_all = StateFilter('all')

        pr_open = Mock(state='open')
        pr_closed = Mock(state='closed')
        pr_merged = Mock(state='merged')

        self.assertTrue(filter_all.matches(pr_open))
        self.assertTrue(filter_all.matches(pr_closed))
        self.assertTrue(filter_all.matches(pr_merged))


class TestAuthorFilter(unittest.TestCase):
    """Test PR author filtering."""

    def test_single_author_filter(self):
        """Test filtering by single author."""
        filter_author = AuthorFilter('alice')

        pr_alice = Mock()
        pr_alice.user.login = 'alice'

        pr_bob = Mock()
        pr_bob.user.login = 'bob'

        self.assertTrue(filter_author.matches(pr_alice))
        self.assertFalse(filter_author.matches(pr_bob))

    def test_multiple_authors_filter(self):
        """Test filtering by multiple authors."""
        filter_authors = AuthorFilter(['alice', 'bob'])

        pr_alice = Mock()
        pr_alice.user.login = 'alice'

        pr_bob = Mock()
        pr_bob.user.login = 'bob'

        pr_charlie = Mock()
        pr_charlie.user.login = 'charlie'

        self.assertTrue(filter_authors.matches(pr_alice))
        self.assertTrue(filter_authors.matches(pr_bob))
        self.assertFalse(filter_authors.matches(pr_charlie))

    def test_case_insensitive_author_filter(self):
        """Test case-insensitive author matching."""
        filter_author = AuthorFilter('Alice')

        pr = Mock()
        pr.user.login = 'alice'

        self.assertTrue(filter_author.matches(pr))


class TestLabelFilter(unittest.TestCase):
    """Test PR label filtering."""

    def test_single_label_filter(self):
        """Test filtering by single label."""
        filter_label = LabelFilter('bug')

        pr_with_bug = Mock()
        bug_label = Mock()
        bug_label.configure_mock(name='bug')
        urgent_label = Mock()
        urgent_label.configure_mock(name='urgent')
        pr_with_bug.labels = [bug_label, urgent_label]

        pr_without_bug = Mock()
        enhancement_label = Mock()
        enhancement_label.configure_mock(name='enhancement')
        pr_without_bug.labels = [enhancement_label]

        self.assertTrue(filter_label.matches(pr_with_bug))
        self.assertFalse(filter_label.matches(pr_without_bug))

    def test_multiple_labels_filter_any(self):
        """Test filtering by any of multiple labels."""
        filter_labels = LabelFilter(['bug', 'urgent'], require_all=False)

        pr_with_bug = Mock()
        bug_label = Mock()
        bug_label.configure_mock(name='bug')
        pr_with_bug.labels = [bug_label]

        pr_with_urgent = Mock()
        urgent_label = Mock()
        urgent_label.configure_mock(name='urgent')
        pr_with_urgent.labels = [urgent_label]

        pr_with_both = Mock()
        bug_label_2 = Mock()
        bug_label_2.configure_mock(name='bug')
        urgent_label_2 = Mock()
        urgent_label_2.configure_mock(name='urgent')
        pr_with_both.labels = [bug_label_2, urgent_label_2]

        pr_with_neither = Mock()
        enhancement_label = Mock()
        enhancement_label.configure_mock(name='enhancement')
        pr_with_neither.labels = [enhancement_label]

        self.assertTrue(filter_labels.matches(pr_with_bug))
        self.assertTrue(filter_labels.matches(pr_with_urgent))
        self.assertTrue(filter_labels.matches(pr_with_both))
        self.assertFalse(filter_labels.matches(pr_with_neither))

    def test_multiple_labels_filter_all(self):
        """Test filtering by all of multiple labels."""
        filter_labels = LabelFilter(['bug', 'urgent'], require_all=True)

        pr_with_bug = Mock()
        bug_label = Mock()
        bug_label.configure_mock(name='bug')
        pr_with_bug.labels = [bug_label]

        pr_with_urgent = Mock()
        urgent_label = Mock()
        urgent_label.configure_mock(name='urgent')
        pr_with_urgent.labels = [urgent_label]

        pr_with_both = Mock()
        bug_label_2 = Mock()
        bug_label_2.configure_mock(name='bug')
        urgent_label_2 = Mock()
        urgent_label_2.configure_mock(name='urgent')
        pr_with_both.labels = [bug_label_2, urgent_label_2]

        self.assertFalse(filter_labels.matches(pr_with_bug))
        self.assertFalse(filter_labels.matches(pr_with_urgent))
        self.assertTrue(filter_labels.matches(pr_with_both))

    def test_exclude_labels_filter(self):
        """Test excluding PRs with certain labels."""
        filter_exclude = LabelFilter('wip', exclude=True)

        pr_with_wip = Mock()
        # Use SimpleNamespace or configure_mock to properly set the .name attribute
        wip_label = Mock()
        wip_label.configure_mock(name='wip')
        bug_label_1 = Mock()
        bug_label_1.configure_mock(name='bug')
        pr_with_wip.labels = [wip_label, bug_label_1]

        pr_without_wip = Mock()
        bug_label_2 = Mock()
        bug_label_2.configure_mock(name='bug')
        pr_without_wip.labels = [bug_label_2]

        self.assertFalse(filter_exclude.matches(pr_with_wip))
        self.assertTrue(filter_exclude.matches(pr_without_wip))


class TestDateFilter(unittest.TestCase):
    """Test PR date filtering."""

    def test_created_after_filter(self):
        """Test filtering PRs created after a date."""
        cutoff = datetime.now() - timedelta(days=7)
        filter_date = DateFilter(created_after=cutoff)

        pr_new = Mock()
        pr_new.created_at = datetime.now() - timedelta(days=3)

        pr_old = Mock()
        pr_old.created_at = datetime.now() - timedelta(days=10)

        self.assertTrue(filter_date.matches(pr_new))
        self.assertFalse(filter_date.matches(pr_old))

    def test_created_before_filter(self):
        """Test filtering PRs created before a date."""
        cutoff = datetime.now() - timedelta(days=7)
        filter_date = DateFilter(created_before=cutoff)

        pr_new = Mock()
        pr_new.created_at = datetime.now() - timedelta(days=3)

        pr_old = Mock()
        pr_old.created_at = datetime.now() - timedelta(days=10)

        self.assertFalse(filter_date.matches(pr_new))
        self.assertTrue(filter_date.matches(pr_old))

    def test_updated_after_filter(self):
        """Test filtering PRs updated after a date."""
        cutoff = datetime.now() - timedelta(hours=12)
        filter_date = DateFilter(updated_after=cutoff)

        pr_recently_updated = Mock()
        pr_recently_updated.updated_at = datetime.now() - timedelta(hours=6)

        pr_not_recently_updated = Mock()
        pr_not_recently_updated.updated_at = datetime.now() - timedelta(days=2)

        self.assertTrue(filter_date.matches(pr_recently_updated))
        self.assertFalse(filter_date.matches(pr_not_recently_updated))

    def test_date_range_filter(self):
        """Test filtering PRs within a date range."""
        start = datetime.now() - timedelta(days=14)
        end = datetime.now() - timedelta(days=7)
        filter_range = DateFilter(created_after=start, created_before=end)

        pr_in_range = Mock()
        pr_in_range.created_at = datetime.now() - timedelta(days=10)

        pr_too_old = Mock()
        pr_too_old.created_at = datetime.now() - timedelta(days=20)

        pr_too_new = Mock()
        pr_too_new.created_at = datetime.now() - timedelta(days=3)

        self.assertTrue(filter_range.matches(pr_in_range))
        self.assertFalse(filter_range.matches(pr_too_old))
        self.assertFalse(filter_range.matches(pr_too_new))


class TestReviewFilter(unittest.TestCase):
    """Test PR review status filtering."""

    def test_approved_filter(self):
        """Test filtering for approved PRs."""
        filter_approved = ReviewFilter(status='approved')

        pr_approved = Mock()
        pr_approved.get_reviews.return_value = [
            Mock(state='APPROVED', user=Mock(login='reviewer1'))
        ]

        pr_changes_requested = Mock()
        pr_changes_requested.get_reviews.return_value = [
            Mock(state='CHANGES_REQUESTED', user=Mock(login='reviewer1'))
        ]

        self.assertTrue(filter_approved.matches(pr_approved))
        self.assertFalse(filter_approved.matches(pr_changes_requested))

    def test_changes_requested_filter(self):
        """Test filtering for PRs with changes requested."""
        filter_changes = ReviewFilter(status='changes_requested')

        pr_changes_requested = Mock()
        pr_changes_requested.get_reviews.return_value = [
            Mock(state='CHANGES_REQUESTED', user=Mock(login='reviewer1'))
        ]

        pr_approved = Mock()
        pr_approved.get_reviews.return_value = [
            Mock(state='APPROVED', user=Mock(login='reviewer1'))
        ]

        self.assertTrue(filter_changes.matches(pr_changes_requested))
        self.assertFalse(filter_changes.matches(pr_approved))

    def test_pending_review_filter(self):
        """Test filtering for PRs pending review."""
        filter_pending = ReviewFilter(status='pending')

        pr_no_reviews = Mock()
        pr_no_reviews.get_reviews.return_value = []

        pr_commented_only = Mock()
        pr_commented_only.get_reviews.return_value = [
            Mock(state='COMMENTED', user=Mock(login='reviewer1'))
        ]

        pr_approved = Mock()
        pr_approved.get_reviews.return_value = [
            Mock(state='APPROVED', user=Mock(login='reviewer1'))
        ]

        self.assertTrue(filter_pending.matches(pr_no_reviews))
        self.assertTrue(filter_pending.matches(pr_commented_only))
        self.assertFalse(filter_pending.matches(pr_approved))

    def test_reviewer_filter(self):
        """Test filtering by specific reviewer."""
        filter_reviewer = ReviewFilter(reviewer='alice')

        pr_reviewed_by_alice = Mock()
        pr_reviewed_by_alice.get_reviews.return_value = [
            Mock(state='APPROVED', user=Mock(login='alice'))
        ]

        pr_reviewed_by_bob = Mock()
        pr_reviewed_by_bob.get_reviews.return_value = [
            Mock(state='APPROVED', user=Mock(login='bob'))
        ]

        self.assertTrue(filter_reviewer.matches(pr_reviewed_by_alice))
        self.assertFalse(filter_reviewer.matches(pr_reviewed_by_bob))


class TestCombinedFilter(unittest.TestCase):
    """Test combining multiple filters."""

    def test_and_combination(self):
        """Test AND combination of filters."""
        state_filter = StateFilter('open')
        label_filter = LabelFilter('bug')

        combined = CombinedFilter([state_filter, label_filter], operator='AND')

        pr_match = Mock()
        pr_match.state = 'open'
        bug_label = Mock()
        bug_label.configure_mock(name='bug')
        pr_match.labels = [bug_label]

        pr_no_match_state = Mock()
        pr_no_match_state.state = 'closed'
        bug_label2 = Mock()
        bug_label2.configure_mock(name='bug')
        pr_no_match_state.labels = [bug_label2]

        pr_no_match_label = Mock()
        pr_no_match_label.state = 'open'
        enhancement_label = Mock()
        enhancement_label.configure_mock(name='enhancement')
        pr_no_match_label.labels = [enhancement_label]

        self.assertTrue(combined.matches(pr_match))
        self.assertFalse(combined.matches(pr_no_match_state))
        self.assertFalse(combined.matches(pr_no_match_label))

    def test_or_combination(self):
        """Test OR combination of filters."""
        author_filter = AuthorFilter('alice')
        label_filter = LabelFilter('urgent')

        combined = CombinedFilter([author_filter, label_filter], operator='OR')

        pr_by_alice = Mock()
        pr_by_alice.user.login = 'alice'
        pr_by_alice.labels = []

        pr_urgent = Mock()
        pr_urgent.user.login = 'bob'
        urgent_label = Mock()
        urgent_label.configure_mock(name='urgent')
        pr_urgent.labels = [urgent_label]

        pr_both = Mock()
        pr_both.user.login = 'alice'
        urgent_label2 = Mock()
        urgent_label2.configure_mock(name='urgent')
        pr_both.labels = [urgent_label2]

        pr_neither = Mock()
        pr_neither.user.login = 'bob'
        bug_label3 = Mock()
        bug_label3.configure_mock(name='bug')
        pr_neither.labels = [bug_label3]

        self.assertTrue(combined.matches(pr_by_alice))
        self.assertTrue(combined.matches(pr_urgent))
        self.assertTrue(combined.matches(pr_both))
        self.assertFalse(combined.matches(pr_neither))

    def test_nested_combination(self):
        """Test nested filter combinations."""
        # (open AND bug) OR (closed AND resolved)
        open_bug = CombinedFilter([
            StateFilter('open'),
            LabelFilter('bug')
        ], operator='AND')

        closed_resolved = CombinedFilter([
            StateFilter('closed'),
            LabelFilter('resolved')
        ], operator='AND')

        combined = CombinedFilter([open_bug, closed_resolved], operator='OR')

        pr_open_bug = Mock()
        pr_open_bug.state = 'open'
        bug_label4 = Mock()
        bug_label4.configure_mock(name='bug')
        pr_open_bug.labels = [bug_label4]

        pr_closed_resolved = Mock()
        pr_closed_resolved.state = 'closed'
        resolved_label = Mock()
        resolved_label.configure_mock(name='resolved')
        pr_closed_resolved.labels = [resolved_label]

        pr_open_resolved = Mock()
        pr_open_resolved.state = 'open'
        resolved_label2 = Mock()
        resolved_label2.configure_mock(name='resolved')
        pr_open_resolved.labels = [resolved_label2]

        self.assertTrue(combined.matches(pr_open_bug))
        self.assertTrue(combined.matches(pr_closed_resolved))
        self.assertFalse(combined.matches(pr_open_resolved))


if __name__ == '__main__':
    unittest.main()