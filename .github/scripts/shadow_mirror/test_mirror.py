import unittest
import base64
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from mirror import FORK, SOURCE, WORKFLOW, BaselineUnavailable, Mirror, dependency_file, path_matches, recorder_installs, scrub_title, version_transitions, workflow_paths


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

    def test_package_tokens_are_preserved_and_idempotent(self):
        text = 'Update @scope/name npm:@scope/name@1.2.3 package@2.0 ' + chr(64) + 'reviewer'
        expected = 'Update `@scope/name` `npm:@scope/name@1.2.3` `package@2.0`'
        self.assertEqual(scrub_title(text), expected)
        self.assertEqual(scrub_title(expected), expected)


class MirrorDiscoveryTest(unittest.TestCase):
    def make_pr(self):
        return {'number': 1, 'body': '<!-- garnet-shadow-mirror upstream=1 upstream_head=' + 'a' * 40 + ' upstream_base=' + 'b' * 40 + ' -->',
                'head': {'repo': {'full_name': FORK}, 'ref': 'shadow/pr/1-r2'},
                'base': {'repo': {'full_name': FORK}, 'ref': 'shadow/base/1-r2'}}

    def discover(self, prs):
        api = Mock()
        workflow = b'on:\n    pull_request:\n        paths:\n            - package.json\n    push:\n        branches: [master]\n'
        api.call.return_value = {'content': base64.b64encode(workflow).decode()}
        api.pages.return_value = prs
        return Mirror(api)

    def test_valid_same_repository_pair_is_discovered(self):
        pr = self.make_pr()
        self.assertEqual(self.discover([pr]).mirrors, {1: pr})
        self.assertEqual(self.discover([]).mirrors, {})

    def test_spoofed_marker_is_ignored(self):
        for side, key, value in [('head', 'repo', {'full_name': 'other/repository'}),
                                  ('base', 'repo', {'full_name': 'other/repository'}),
                                  ('head', 'repo', None), ('base', 'repo', None),
                                  ('head', 'ref', 'shadow/pr/2-r2'), ('base', 'ref', 'shadow/base/2-r2'),
                                  ('head', 'ref', 'shadow/pr/1-r2-extra'), ('base', 'ref', 'master'),
                                  ('base', 'ref', 'shadow/base/1-r3')]:
            with self.subTest(side=side, key=key, value=value):
                pr = deepcopy(self.make_pr())
                pr[side][key] = value
                self.assertEqual(self.discover([pr]).mirrors, {})


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
            if path.startswith('git/matching-refs/'):
                return []
            if path.startswith('compare/'):
                return {'merge_base_commit': {'sha': 'source-merge-base'}}
            if path.startswith('contents/pnpm-workspace.yaml'):
                return {'content': base64.b64encode(b'packages:\n  - services/mcp\n  - nodejs\n').decode()}
            if repo == SOURCE:
                return {'state': 'open', 'draft': False, 'author_association': 'MEMBER', 'user': {'type': 'User'}, 'base': {'ref': 'master', 'sha': 'source-base'},
                        'head': {'sha': 'source-head'}, 'title': 'Bump pnpm'}
            if path.startswith('git/ref/heads/shadow/base/'):
                return {'object': {'sha': 'baseline'}}
            if path.startswith('git/ref/heads/shadow/pr/'):
                return {'object': {'sha': 'head'}}
            if path == 'git/commits/head':
                return {'tree': {'sha': 'head-tree'}, 'message': 'Bump pnpm', 'parents': [{'sha': 'baseline'}]}
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
            self.assertIn('upstream_base=source-merge-base', body)
        mirror.commit.assert_not_called()
        mirror.ref.assert_not_called()
        mirror.api.write.assert_not_called()

    def test_failed_dispatch_allocates_fresh_pair(self):
        mirror = self.make_mirror()
        mirror.baseline_started.side_effect = [BaselineUnavailable('HTTP 403: dispatch denied'), None]
        mirror.commit.side_effect = ['fresh-baseline', 'fresh-head']
        with TemporaryDirectory() as directory, patch('mirror.Path', return_value=Path(directory)):
            result = mirror.sync(1)
        self.assertEqual(result['base_ref'], 'shadow/base/1-r2')
        self.assertEqual(result['head_ref'], 'shadow/pr/1-r2')
        self.assertEqual(mirror.baseline_started.call_args_list[1].args, ('shadow/base/1-r2', 'fresh-baseline'))
        self.assertEqual(mirror.commit.call_args_list[1].args, ('head-tree', ['fresh-baseline'], 'Bump pnpm'))
        self.assertEqual(mirror.ref.call_args_list[0].args, ('shadow/base/1-r2', 'fresh-baseline'))

    def test_existing_revision_is_reused_without_old_refs_or_pr(self):
        mirror = self.make_mirror()
        original_call = mirror.api.call.side_effect
        def call(repo, path):
            if path.startswith('git/matching-refs/'):
                return [{'ref': 'refs/heads/shadow/base/1-r2'}, {'ref': 'refs/heads/shadow/base/10-r9'}]
            return original_call(repo, path)
        mirror.api.call.side_effect = call
        self.assertEqual(mirror.branches(1, None), ('shadow/base/1-r2', 'shadow/pr/1-r2'))

    def test_denied_dispatch_reports_baseline_unavailable(self):
        mirror = self.make_mirror()
        mirror.api.call.return_value = {'workflow_runs': []}
        mirror.api.call.side_effect = None
        mirror.api.write.side_effect = RuntimeError('HTTP 403: dispatch denied')
        with patch('mirror.time.sleep'), self.assertRaisesRegex(BaselineUnavailable, 'HTTP 403'):
            Mirror.baseline_started(mirror, 'shadow/base/1', 'baseline')

    def test_failed_fresh_baseline_does_not_push_head_or_recurse(self):
        mirror = self.make_mirror()
        mirror.baseline_started.side_effect = BaselineUnavailable('No baseline recording')
        mirror.commit.return_value = 'fresh-baseline'
        with self.assertRaises(BaselineUnavailable):
            mirror.sync(1)
        mirror.commit.assert_called_once_with('head-tree', [], 'chore: shadow baseline')
        mirror.ref.assert_called_once_with('shadow/base/1-r2', 'fresh-baseline')

    def test_only_trusted_authors_and_bots_are_selected(self):
        for association, user_type, expected in [('NONE', 'User', 'untrusted_author'), ('CONTRIBUTOR', 'User', 'untrusted_author'),
                                                  ('OWNER', 'User', 'dry-run'), ('MEMBER', 'User', 'dry-run'),
                                                  ('COLLABORATOR', 'User', 'dry-run'), ('NONE', 'Bot', 'dry-run')]:
            with self.subTest(association=association, user_type=user_type):
                mirror = self.make_mirror()
                mirror.dry_run = True
                original_call = mirror.api.call.side_effect
                def call(repo, path):
                    result = original_call(repo, path)
                    if path == 'pulls/1':
                        result.update(author_association=association, user={'type': user_type})
                    return result
                mirror.api.call.side_effect = call
                self.assertEqual(mirror.sync(1)['status'], expected)
                mirror.api.write.assert_not_called()
                mirror.commit.assert_not_called()

    def test_new_baseline_uses_merge_base_not_current_master(self):
        mirror = self.make_mirror()
        original_call = mirror.api.call.side_effect
        def call(repo, path):
            if path.startswith('git/ref/'):
                raise RuntimeError('HTTP 404: missing ref')
            return original_call(repo, path)
        mirror.api.call.side_effect = call
        mirror.commit.side_effect = ['new-baseline', 'new-head']
        with TemporaryDirectory() as directory, patch('mirror.Path', return_value=Path(directory)):
            mirror.sync(1)
        self.assertEqual(mirror.tree.call_args_list[0].args, ('source-merge-base',))
        mirror.api.call.assert_any_call(SOURCE, 'compare/source-base...source-head')
        self.assertEqual(mirror.commit.call_args_list[0].args, ('head-tree', [], 'chore: shadow baseline'))
        self.assertEqual(mirror.commit.call_args_list[1].args, ('head-tree', ['new-baseline'], 'Bump pnpm'))

    def test_existing_pr_no_open_exports_marker_without_updating_pr(self):
        mirror = self.make_mirror()
        mirror.mirrors[1] = {'state': 'open', 'base': {'sha': 'baseline', 'ref': 'shadow/base/1'}, 'head': {'ref': 'shadow/pr/1'}}
        with TemporaryDirectory() as directory, patch('mirror.Path', return_value=Path(directory)):
            result = mirror.sync(1)
            self.assertIn('upstream_base=source-merge-base', Path(result['body_file']).read_text())
        mirror.api.write.assert_not_called()

    def test_changed_merge_base_allocates_fresh_baseline_revision(self):
        mirror = self.make_mirror()
        mirror.mirrors[1] = {'state': 'open', 'base': {'sha': 'old-baseline', 'ref': 'shadow/base/1'},
                             'head': {'ref': 'shadow/pr/1'},
                             'body': '<!-- garnet-shadow-mirror upstream=1 upstream_head=' + 'a' * 40 + ' upstream_base=' + 'b' * 40 + ' -->'}
        original_call = mirror.api.call.side_effect
        def call(repo, path):
            if path.endswith('-r2'):
                raise RuntimeError('HTTP 404: missing ref')
            return original_call(repo, path)
        mirror.api.call.side_effect = call
        mirror.commit.side_effect = ['fresh-baseline', 'fresh-head']
        with TemporaryDirectory() as directory, patch('mirror.Path', return_value=Path(directory)):
            result = mirror.sync(1)
        self.assertEqual(result['base_ref'], 'shadow/base/1-r2')
        self.assertEqual(result['head_ref'], 'shadow/pr/1-r2')
        self.assertEqual(mirror.tree.call_args_list[0].args, ('source-merge-base',))
        mirror.baseline_started.assert_called_once_with('shadow/base/1-r2', 'fresh-baseline')
        self.assertEqual(mirror.commit.call_args_list[1].args, ('head-tree', ['fresh-baseline'], 'Bump pnpm'))
        mirror.ref.assert_any_call('shadow/base/1-r2', 'fresh-baseline')

    def test_closed_mirror_uses_next_revision_and_reuses_prepared_refs(self):
        mirror = self.make_mirror()
        closed = {'state': 'closed', 'base': {'ref': 'shadow/base/1'}, 'head': {'ref': 'shadow/pr/1'}}
        mirror.mirrors[1] = closed
        with TemporaryDirectory() as directory, patch('mirror.Path', return_value=Path(directory)):
            result = mirror.sync(1)
            repeated = mirror.sync(1)
        self.assertEqual(result['base_ref'], 'shadow/base/1-r2')
        self.assertEqual(result['head_ref'], 'shadow/pr/1-r2')
        self.assertEqual(result, repeated)
        mirror.commit.assert_not_called()
        mirror.ref.assert_not_called()
        closed['head']['ref'] = 'shadow/pr/1-r2'
        self.assertEqual(mirror.branches(1, closed), ('shadow/base/1-r3', 'shadow/pr/1-r3'))

    def test_base_force_update_is_always_rejected(self):
        mirror = self.make_mirror()
        for state in ('open', 'closed'):
            mirror.mirrors[1] = {'state': state}
            with self.assertRaises(ValueError):
                Mirror.ref(mirror, 'shadow/base/1', 'new-base', force=True)
        mirror.api.write.assert_not_called()

    def test_reopened_upstream_creates_new_pair_after_closed_revision(self):
        mirror = self.make_mirror()
        mirror.mirrors[1] = {'state': 'closed', 'base': {'ref': 'shadow/base/1-r2'}, 'head': {'ref': 'shadow/pr/1-r2'}}
        original_call = mirror.api.call.side_effect
        def call(repo, path):
            if path.endswith('-r3'):
                raise RuntimeError('HTTP 404: missing ref')
            return original_call(repo, path)
        mirror.api.call.side_effect = call
        mirror.commit.side_effect = ['reopened-base', 'reopened-head']
        with TemporaryDirectory() as directory, patch('mirror.Path', return_value=Path(directory)):
            result = mirror.sync(1)
        self.assertEqual(result['base_ref'], 'shadow/base/1-r3')
        self.assertEqual(result['head_ref'], 'shadow/pr/1-r3')
        mirror.ref.assert_any_call('shadow/base/1-r3', 'reopened-base')
        mirror.ref.assert_any_call('shadow/pr/1-r3', 'reopened-head')
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

    def test_no_dependency_changes_closes_open_mirror_without_comment(self):
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run):
                mirror = self.make_mirror()
                mirror.dry_run = dry_run
                mirror.mirrors[1] = {'state': 'open', 'number': 2,
                                     'base': {'sha': 'baseline', 'ref': 'shadow/base/1'}, 'head': {'ref': 'shadow/pr/1'}}
                mirror.api.pages.return_value = [{'filename': 'README.md'}]
                result = mirror.sync(1)
                self.assertEqual(result['status'], 'dry-run' if dry_run else 'closed_no_deps')
                if dry_run:
                    mirror.api.write.assert_not_called()
                else:
                    mirror.api.write.assert_called_once_with('pulls/2', {'state': 'closed'}, 'PATCH')
                mirror.commit.assert_not_called()

    def test_renames_check_old_and_new_paths(self):
        for filename, previous, expected in [('moved.json', 'package.json', 'dry-run'),
                                              ('package.json', 'moved.json', 'dry-run'),
                                              ('other.json', 'old.json', 'skipped'),
                                              ('other.json', WORKFLOW, 'skipped')]:
            with self.subTest(filename=filename, previous=previous):
                mirror = self.make_mirror()
                mirror.dry_run = True
                mirror.api.pages.return_value = [{'filename': filename, 'previous_filename': previous}]
                self.assertEqual(mirror.sync(1)['status'], expected)

    def test_bad_message_is_replaced_with_same_tree_and_parent(self):
        mirror = self.make_mirror()
        original_call = mirror.api.call.side_effect
        def call(repo, path):
            result = original_call(repo, path)
            if path == 'pulls/1':
                result['title'] = 'Bump @scope/name'
            return result
        mirror.api.call.side_effect = call
        with TemporaryDirectory() as directory, patch('mirror.Path', return_value=Path(directory)):
            mirror.sync(1)
        mirror.commit.assert_called_once_with('head-tree', ['baseline'], 'Bump `@scope/name`')
        mirror.ref.assert_called_once_with('shadow/pr/1', 'new-head', force=True)

    def test_force_update_is_blocked_by_any_open_pr(self):
        mirror = self.make_mirror()
        mirror.api.pages.return_value = [{'number': 2}]
        with self.assertRaisesRegex(RuntimeError, 'open mirror pull request'):
            Mirror.ref(mirror, 'shadow/pr/1', 'new-head', force=True)
        mirror.api.write.assert_not_called()

    def test_force_update_allowed_without_open_pr(self):
        mirror = self.make_mirror()
        mirror.api.pages.return_value = []
        Mirror.ref(mirror, 'shadow/pr/1', 'new-head', force=True)
        mirror.api.write.assert_called_once_with('git/refs/heads/shadow/pr/1', {'sha': 'new-head', 'force': True}, 'PATCH')

    def test_all_dependency_files_and_install_membership_are_exported(self):
        mirror = self.make_mirror()
        mirror.api.pages.return_value.extend([
            {'filename': 'services/mcp/package.json', 'patch': '- "@scope/name": "npm:@scope/pkg@1"\n+ "@scope/name": "npm:@scope/pkg@2"'},
            {'filename': 'nodejs/package.json', 'patch': '- "lib": "1"\n+ "lib": "2"'},
            {'filename': 'other/go.mod', 'patch': '-example.com/lib v1.0.0\n+example.com/lib v2.0.0'},
            {'filename': 'README.md', 'patch': ''},
        ])
        with TemporaryDirectory() as directory, patch('mirror.Path', return_value=Path(directory)):
            result = mirror.sync(1)
            body = Path(result['body_file']).read_text()
        self.assertIn('`services/mcp/package.json` (recorder installs)', body)
        self.assertIn('`nodejs/package.json` (recorder installs)', body)
        self.assertIn('`other/go.mod` (not installed by recorder)', body)
        self.assertIn('`@scope/name` `npm:@scope/pkg@1` → `npm:@scope/pkg@2`', body)
        self.assertNotIn('README.md', body)

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
    def test_dependency_file_types(self):
        for path in ['a/package.json', 'pnpm-lock.yaml', 'a/requirements-dev.txt', 'a/go.mod', 'go.sum', 'Cargo.toml', 'Cargo.lock', '.node-version', '.nvmrc', 'uv.lock']:
            self.assertTrue(dependency_file(path), path)
        self.assertFalse(dependency_file('README.md'))
        self.assertFalse(dependency_file(''))

    def test_workspace_membership_excludes_independent_projects(self):
        patterns = ['package.json']
        workspace = ['products/*', '!products/mobile', 'services/mcp']
        self.assertTrue(recorder_installs('services/mcp/package.json', patterns, workspace))
        self.assertFalse(recorder_installs('products/mobile/package.json', patterns, workspace))
        self.assertFalse(recorder_installs('other/go.sum', patterns, workspace))

    def test_pnpm_lock(self):
        patch = "-  '@scope/pkg@1.0.0':\n+  '@scope/pkg@2.0.0':\n-  lib@1.0.0:\n+  lib@2.0.0:\n-      '@scope/pkg': 1.0.0\n+      '@scope/pkg': 2.0.0"
        self.assertEqual(version_transitions('pnpm-lock.yaml', patch), [('@scope/pkg', '1.0.0', '2.0.0'), ('lib', '1.0.0', '2.0.0')])

    def test_go_rust_python_locks_and_node(self):
        self.assertEqual(version_transitions('go.mod', '-example.com/lib v1.0.0\n+example.com/lib v2.0.0'), [('example.com/lib', 'v1.0.0', 'v2.0.0')])
        for filename in ['Cargo.lock', 'uv.lock']:
            self.assertEqual(version_transitions(filename, ' [[package]]\n name = "lib"\n-version = "1"\n+version = "2"'), [('lib', '1', '2')])
        self.assertEqual(version_transitions('.nvmrc', '-20\n+22'), [('Node.js', '20', '22')])

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
