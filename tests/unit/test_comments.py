"""
Unit tests for comment management.

Tests PR comment operations and filtering.
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from gh_pr.core.comments import CommentProcessor as CommentManager


class TestCommentManager(unittest.TestCase):
    """Test comment management functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_pr = Mock()
        self.mock_pr.number = 123
        self.mock_pr.base.repo.full_name = 'owner/repo'

        self.manager = CommentManager(self.mock_pr)

    def test_get_all_comments(self):
        """Test retrieving all comments from a PR."""
        # Create mock comments
        comment1 = Mock()
        comment1.id = 1
        comment1.user.login = 'user1'
        comment1.body = 'First comment'
        comment1.created_at = datetime.now() - timedelta(days=2)
        comment1.updated_at = datetime.now() - timedelta(days=2)

        comment2 = Mock()
        comment2.id = 2
        comment2.user.login = 'user2'
        comment2.body = 'Second comment'
        comment2.created_at = datetime.now() - timedelta(days=1)
        comment2.updated_at = datetime.now()

        self.mock_pr.get_issue_comments.return_value = [comment1, comment2]

        comments = self.manager.get_all_comments()

        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0].body, 'First comment')
        self.assertEqual(comments[1].user.login, 'user2')
        self.mock_pr.get_issue_comments.assert_called_once()

    def test_get_review_comments(self):
        """Test retrieving review comments from a PR."""
        # Mock review comment
        review_comment = Mock()
        review_comment.id = 10
        review_comment.user.login = 'reviewer'
        review_comment.body = 'Code review comment'
        review_comment.path = 'src/main.py'
        review_comment.line = 42
        review_comment.commit_id = 'abc123'

        self.mock_pr.get_review_comments.return_value = [review_comment]

        comments = self.manager.get_review_comments()

        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0].body, 'Code review comment')
        self.assertEqual(comments[0].path, 'src/main.py')
        self.assertEqual(comments[0].line, 42)

    def test_add_comment(self):
        """Test adding a comment to a PR."""
        mock_comment = Mock()
        mock_comment.id = 100
        mock_comment.body = 'New comment'

        self.mock_pr.create_issue_comment.return_value = mock_comment

        result = self.manager.add_comment('New comment')

        self.assertEqual(result.body, 'New comment')
        self.mock_pr.create_issue_comment.assert_called_once_with('New comment')

    def test_add_review_comment(self):
        """Test adding a review comment to specific code."""
        mock_review_comment = Mock()
        mock_review_comment.id = 200
        mock_review_comment.body = 'Review feedback'

        self.mock_pr.create_review_comment.return_value = mock_review_comment

        result = self.manager.add_review_comment(
            body='Review feedback',
            commit='abc123',
            file='src/main.py',
            line=42
        )

        self.assertEqual(result.body, 'Review feedback')
        self.mock_pr.create_review_comment.assert_called_once()

    def test_edit_comment(self):
        """Test editing an existing comment."""
        mock_comment = Mock()
        mock_comment.id = 1
        mock_comment.body = 'Original text'
        mock_comment.edit = Mock()

        # Mock getting the comment
        self.mock_pr.base.repo.get_issue_comment.return_value = mock_comment

        self.manager.edit_comment(1, 'Updated text')

        mock_comment.edit.assert_called_once_with('Updated text')

    def test_delete_comment(self):
        """Test deleting a comment."""
        mock_comment = Mock()
        mock_comment.id = 1
        mock_comment.delete = Mock()

        self.mock_pr.base.repo.get_issue_comment.return_value = mock_comment

        self.manager.delete_comment(1)

        mock_comment.delete.assert_called_once()

    def test_filter_comments_by_author(self):
        """Test filtering comments by author."""
        # Create comments from different authors
        comments = []
        for i, author in enumerate(['alice', 'bob', 'alice', 'charlie']):
            comment = Mock()
            comment.id = i
            comment.user.login = author
            comment.body = f'Comment from {author}'
            comments.append(comment)

        self.mock_pr.get_issue_comments.return_value = comments

        # Filter by author
        alice_comments = self.manager.filter_comments_by_author('alice')

        self.assertEqual(len(alice_comments), 2)
        self.assertTrue(all(c.user.login == 'alice' for c in alice_comments))

    def test_filter_comments_by_date(self):
        """Test filtering comments by date range."""
        now = datetime.now()
        comments = []

        # Create comments with different dates
        for i in range(5):
            comment = Mock()
            comment.id = i
            comment.created_at = now - timedelta(days=i)
            comment.body = f'Comment {i}'
            comments.append(comment)

        self.mock_pr.get_issue_comments.return_value = comments

        # Filter last 3 days
        since = now - timedelta(days=3)
        recent_comments = self.manager.filter_comments_by_date(since=since)

        self.assertEqual(len(recent_comments), 4)  # Today + 3 days back

    def test_get_comment_thread(self):
        """Test retrieving comment threads."""
        # Create comments that reference each other
        comments = []
        for i in range(4):
            comment = Mock()
            comment.id = i
            comment.in_reply_to_id = i - 1 if i > 0 else None
            comment.body = f'Comment {i}'
            comments.append(comment)

        self.mock_pr.get_issue_comments.return_value = comments

        # Get thread starting from comment 0
        thread = self.manager.get_comment_thread(0)

        self.assertEqual(len(thread), 4)
        self.assertEqual(thread[0].id, 0)
        self.assertEqual(thread[-1].id, 3)

    def test_resolve_comment(self):
        """Test marking a comment as resolved."""
        mock_comment = Mock()
        mock_comment.id = 1
        mock_comment.body = 'Issue found'

        self.mock_pr.base.repo.get_issue_comment.return_value = mock_comment

        # Add resolved marker
        self.manager.resolve_comment(1)

        # Should edit with resolved marker
        mock_comment.edit.assert_called_once()
        edited_body = mock_comment.edit.call_args[0][0]
        self.assertIn('✓ Resolved', edited_body)
        self.assertIn('Issue found', edited_body)

    def test_get_unresolved_comments(self):
        """Test getting unresolved review comments."""
        resolved = Mock()
        resolved.id = 1
        resolved.body = '✓ Resolved: Fixed'
        resolved.resolved = True

        unresolved = Mock()
        unresolved.id = 2
        unresolved.body = 'Please fix this'
        unresolved.resolved = False

        self.mock_pr.get_review_comments.return_value = [resolved, unresolved]

        unresolved_comments = self.manager.get_unresolved_comments()

        self.assertEqual(len(unresolved_comments), 1)
        self.assertEqual(unresolved_comments[0].id, 2)

    def test_get_comment_reactions(self):
        """Test getting reactions on a comment."""
        mock_comment = Mock()
        mock_comment.get_reactions.return_value = [
            Mock(content='+1', user=Mock(login='user1')),
            Mock(content='-1', user=Mock(login='user2')),
            Mock(content='+1', user=Mock(login='user3'))
        ]

        self.mock_pr.base.repo.get_issue_comment.return_value = mock_comment

        reactions = self.manager.get_comment_reactions(1)

        self.assertEqual(reactions['+1'], 2)
        self.assertEqual(reactions['-1'], 1)

    def test_add_reaction(self):
        """Test adding a reaction to a comment."""
        mock_comment = Mock()
        mock_comment.create_reaction = Mock(return_value=Mock(content='heart'))

        self.mock_pr.base.repo.get_issue_comment.return_value = mock_comment

        self.manager.add_reaction(1, 'heart')

        mock_comment.create_reaction.assert_called_once_with('heart')

    def test_get_comment_stats(self):
        """Test getting comment statistics."""
        comments = []
        authors = ['alice', 'bob', 'alice', 'charlie', 'alice']

        for i, author in enumerate(authors):
            comment = Mock()
            comment.user.login = author
            comment.created_at = datetime.now() - timedelta(hours=i)
            comment.body = f'Comment {i}' * (i + 1)  # Varying lengths
            comments.append(comment)

        self.mock_pr.get_issue_comments.return_value = comments

        stats = self.manager.get_comment_stats()

        self.assertEqual(stats['total_comments'], 5)
        self.assertEqual(stats['unique_authors'], 3)
        self.assertEqual(stats['most_active_author'], ('alice', 3))
        self.assertIsNotNone(stats['first_comment_date'])
        self.assertIsNotNone(stats['last_comment_date'])
        self.assertGreater(stats['avg_comment_length'], 0)


if __name__ == '__main__':
    unittest.main()