import unittest

from mirror import SOURCE, WORKFLOW, path_matches, scrub_title, version_transitions, workflow_paths


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
