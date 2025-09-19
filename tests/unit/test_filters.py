"""
Unit tests for PR filtering functionality.

Tests various PR filter implementations.
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from gh_pr.core.filters import (
    PRFilter, StateFilter, AuthorFilter, LabelFilter,
    DateFilter, ReviewFilter, CombinedFilter
)


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
        pr_with_bug.labels = [Mock(name='bug'), Mock(name='urgent')]

        pr_without_bug = Mock()
        pr_without_bug.labels = [Mock(name='enhancement')]

        self.assertTrue(filter_label.matches(pr_with_bug))
        self.assertFalse(filter_label.matches(pr_without_bug))

    def test_multiple_labels_filter_any(self):
        """Test filtering by any of multiple labels."""
        filter_labels = LabelFilter(['bug', 'urgent'], require_all=False)

        pr_with_bug = Mock()
        pr_with_bug.labels = [Mock(name='bug')]

        pr_with_urgent = Mock()
        pr_with_urgent.labels = [Mock(name='urgent')]

        pr_with_both = Mock()
        pr_with_both.labels = [Mock(name='bug'), Mock(name='urgent')]

        pr_with_neither = Mock()
        pr_with_neither.labels = [Mock(name='enhancement')]

        self.assertTrue(filter_labels.matches(pr_with_bug))
        self.assertTrue(filter_labels.matches(pr_with_urgent))
        self.assertTrue(filter_labels.matches(pr_with_both))
        self.assertFalse(filter_labels.matches(pr_with_neither))

    def test_multiple_labels_filter_all(self):
        """Test filtering by all of multiple labels."""
        filter_labels = LabelFilter(['bug', 'urgent'], require_all=True)

        pr_with_bug = Mock()
        pr_with_bug.labels = [Mock(name='bug')]

        pr_with_urgent = Mock()
        pr_with_urgent.labels = [Mock(name='urgent')]

        pr_with_both = Mock()
        pr_with_both.labels = [Mock(name='bug'), Mock(name='urgent')]

        self.assertFalse(filter_labels.matches(pr_with_bug))
        self.assertFalse(filter_labels.matches(pr_with_urgent))
        self.assertTrue(filter_labels.matches(pr_with_both))

    def test_exclude_labels_filter(self):
        """Test excluding PRs with certain labels."""
        filter_exclude = LabelFilter('wip', exclude=True)

        pr_with_wip = Mock()
        pr_with_wip.labels = [Mock(name='wip'), Mock(name='bug')]

        pr_without_wip = Mock()
        pr_without_wip.labels = [Mock(name='bug')]

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
        pr_match.labels = [Mock(name='bug')]

        pr_no_match_state = Mock()
        pr_no_match_state.state = 'closed'
        pr_no_match_state.labels = [Mock(name='bug')]

        pr_no_match_label = Mock()
        pr_no_match_label.state = 'open'
        pr_no_match_label.labels = [Mock(name='enhancement')]

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
        pr_urgent.labels = [Mock(name='urgent')]

        pr_both = Mock()
        pr_both.user.login = 'alice'
        pr_both.labels = [Mock(name='urgent')]

        pr_neither = Mock()
        pr_neither.user.login = 'bob'
        pr_neither.labels = [Mock(name='bug')]

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
        pr_open_bug.labels = [Mock(name='bug')]

        pr_closed_resolved = Mock()
        pr_closed_resolved.state = 'closed'
        pr_closed_resolved.labels = [Mock(name='resolved')]

        pr_open_resolved = Mock()
        pr_open_resolved.state = 'open'
        pr_open_resolved.labels = [Mock(name='resolved')]

        self.assertTrue(combined.matches(pr_open_bug))
        self.assertTrue(combined.matches(pr_closed_resolved))
        self.assertFalse(combined.matches(pr_open_resolved))


if __name__ == '__main__':
    unittest.main()