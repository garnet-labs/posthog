import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from mirror import SOURCE, WORKFLOW, Mirror, path_matches, scrub_title, version_transitions, workflow_paths


class PathsTest(unittest.TestCase):
    def test_recursive_and_direct(self):
        patterns = ['package.json', 'products/desktop/**/package.json']
        for path in ['package.json', 'products/desktop/package.json', 'products/desktop/a/b/package.json']:
            self.assertTrue(path_matches(path, patterns))
        self.assertFalse(path_matches('other/package.json', patterns))
        self.assertFalse(path_matches('a/b/package.json', ['a/*/other.json']))

    def test_empty_and_workflow(self):
        self.assertFalse(path_matches('package.json', []))
        self.assertFalse(path_matches(WORKFLOW, ['**']))

    def test_runtime_paths(self):
        self.assertEqual(workflow_paths('on:\n    pull_request:\n        paths:\n            - package.json\n            - "a/**"\n    push:\n        branches: [master]\n'), ['package.json', 'a/**'])
        with self.assertRaises(ValueError):
            workflow_paths('on: {}')
        with self.assertRaises(ValueError):
            workflow_paths('on:\n    pull_request:\n        types: [opened]\n')


class TitleTest(unittest.TestCase):
    def test_scrub(self):
        reference = '#' + '123'
        mention = chr(64) + 'someone'
        self.assertEqual(scrub_title(f'Bump pnpm {reference} {mention} https://example.com/a {SOURCE}'), 'Bump pnpm')

    def test_empty(self):
        self.assertEqual(scrub_title(''), 'Dependency update')
        self.assertEqual(scrub_title('#' + '123 ' + chr(64) + 'bot'), 'Dependency update')

    def test_normal(self):
        self.assertEqual(scrub_title('Bump pnpm from 9 to 10'), 'Bump pnpm from 9 to 10')


class DeferredPRTest(unittest.TestCase):
    def make_mirror(self, no_open_pr=True):
        mirror = Mirror.__new__(Mirror)
        mirror.api = Mock()
        mirror.dry_run = False
        mirror.no_open_pr = no_open_pr
        mirror.mirrors = {}
        mirror.patterns = ['package.json']
        mirror.tree = Mock(return_value='head-tree')
        mirror.commit = Mock(return_value='new-head')
        mirror.ref = Mock()
        mirror.baseline_started = Mock()
        def call(repo, path):
            if repo == SOURCE:
                return {'state': 'open', 'draft': False, 'base': {'ref': 'master', 'sha': 'source-base'},
                        'head': {'sha': 'source-head'}, 'title': 'Bump pnpm'}
            if path.startswith('git/ref/heads/shadow/base/'):
                return {'object': {'sha': 'baseline'}}
            if path.startswith('git/ref/heads/shadow/pr/'):
                return {'object': {'sha': 'head'}}
            if path == 'git/commits/head':
                return {'tree': {'sha': 'head-tree'}}
            raise AssertionError((repo, path))
        mirror.api.call.side_effect = call
        mirror.api.pages.return_value = [{'filename': 'package.json', 'patch': '- "pnpm": "9"\n+ "pnpm": "10"'}]
        return mirror

    def test_export_reuses_existing_commits(self):
        mirror = self.make_mirror()
        with TemporaryDirectory() as directory, patch('mirror.Path', return_value=Path(directory)):
            for _ in range(2):
                result = mirror.sync(1)
            self.assertEqual(result['status'], 'ready')
            self.assertEqual(result['head'], 'head')
            self.assertEqual(Path(result['title_file']).read_text(), 'Bump pnpm\n')
            body = Path(result['body_file']).read_text()
            self.assertIn('pnpm 9 → 10', body)
            self.assertIn('Mirror base `baseline` → head `head`', body)
        mirror.commit.assert_not_called()
        mirror.ref.assert_not_called()
        mirror.api.write.assert_not_called()

    def test_missing_pr_is_opened_without_new_commit(self):
        mirror = self.make_mirror(no_open_pr=False)
        mirror.api.write.return_value = {'html_url': 'https://example.com/mirror'}
        result = mirror.sync(1)
        self.assertEqual(result['status'], 'created')
        mirror.api.write.assert_called_once()
        self.assertEqual(mirror.api.write.call_args.args[0], 'pulls')
        self.assertEqual(mirror.api.write.call_args.args[1]['head'], 'shadow/pr/1')
        mirror.commit.assert_not_called()

    def test_changed_tree_appends_commit(self):
        mirror = self.make_mirror()
        mirror.tree.return_value = 'changed-tree'
        with TemporaryDirectory() as directory, patch('mirror.Path', return_value=Path(directory)):
            result = mirror.sync(1)
        self.assertEqual(result['head'], 'new-head')
        mirror.commit.assert_called_once_with('changed-tree', ['head'], 'Bump pnpm')
        mirror.ref.assert_called_once_with('shadow/pr/1', 'new-head')

    def test_dry_run_does_not_write_files_or_refs(self):
        mirror = self.make_mirror()
        mirror.dry_run = True
        with patch('mirror.Path') as path:
            self.assertEqual(mirror.sync(1)['status'], 'dry-run')
        path.assert_not_called()
        mirror.commit.assert_not_called()
        mirror.api.write.assert_not_called()

    def test_export_error_does_not_open_pr(self):
        mirror = self.make_mirror()
        with patch('mirror.Path') as path:
            path.return_value.mkdir.side_effect = OSError('Export unavailable')
            with self.assertRaisesRegex(OSError, 'Export unavailable'):
                mirror.sync(1)
        mirror.api.write.assert_not_called()


class VersionsTest(unittest.TestCase):
    def test_json(self):
        self.assertEqual(version_transitions('package.json', '@@\n- "pnpm": "9",\n+ "pnpm": "10",'), [('pnpm', '9', '10')])

    def test_python(self):
        self.assertEqual(version_transitions('pyproject.toml', '- "django>=4.0",\n+ "django>=5.0",'), [('django', '>=4.0', '>=5.0')])
        self.assertEqual(version_transitions('requirements.txt', '-django==4.0\n+django==5.0'), [('django', '==4.0', '==5.0')])
        self.assertEqual(version_transitions('pyproject.toml', '-django = "4.0"\n+django = "5.0"'), [('django', '4.0', '5.0')])

    def test_empty_unchanged_and_malformed(self):
        self.assertEqual(version_transitions('package.json', None), [])
        self.assertEqual(version_transitions('package.json', '-broken\n+also broken'), [])
        self.assertEqual(version_transitions('pnpm-lock.yaml', '-a==1\n+a==2'), [])
        self.assertEqual(version_transitions('requirements.txt', '-django==4\n+django==4'), [])


if __name__ == '__main__':
    unittest.main()
