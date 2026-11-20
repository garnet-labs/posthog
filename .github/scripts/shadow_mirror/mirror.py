#!/usr/bin/env python3
"""Replay dependency changes using isolated, recorded baselines."""
import argparse
import base64
import datetime
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

FORK = 'garnet-labs/posthog'
SOURCE = '/'.join(('PostHog', 'posthog'))
WORKFLOW = '.github/workflows/garnet-ci.yml'
MARKER = re.compile(r'<!-- garnet-shadow-mirror upstream=(\d+) upstream_head=([a-f0-9]+) upstream_base=([a-f0-9]+) -->')


def scrub_title(title):
    title = re.sub(r'https?://\S+|www\.\S+|#\d+|@[\w-]+', '', title)
    title = re.sub(re.escape(SOURCE), '', title, flags=re.I)
    return ' '.join(title.split()).strip() or 'Dependency update'


def path_matches(path, patterns):
    if path == WORKFLOW:
        return False
    def regex(pattern):
        parts = []
        i = 0
        while i < len(pattern):
            if pattern[i:i + 3] == '**/':
                parts.append('(?:.*/)?')
                i += 3
            elif pattern[i:i + 2] == '**':
                parts.append('.*')
                i += 2
            else:
                parts.append('[^/]*' if pattern[i] == '*' else '[^/]' if pattern[i] == '?' else re.escape(pattern[i]))
                i += 1
        return ''.join(parts)
    return any(re.fullmatch(regex(p), path) for p in patterns)


def workflow_paths(content):
    match = re.search(r'(?m)^([ ]*)pull_request:\s*\n(.*?)(?=^\1\S|\Z)', content, re.S)
    if not match:
        raise ValueError('Missing pull_request path configuration')
    paths = re.search(r'(?m)^\s+paths:\s*\n((?:\s+-[^\n]+\n)+)', match[2])
    if not paths:
        raise ValueError('Missing pull_request paths list')
    return [line.strip()[1:].strip().strip("'\"") for line in paths[1].splitlines()]


def version_transitions(filename, patch):
    """Read paired dependency declarations from a unified manifest diff."""
    if not (filename.endswith(('package.json', 'pyproject.toml', 'requirements.txt', 'constraints.txt'))):
        return []
    sides = {'-': {}, '+': {}}
    for line in (patch or '').splitlines():
        if not line or line[0] not in sides or line.startswith(('---', '+++')):
            continue
        value = line[1:].strip().rstrip(',')
        pair = re.match(r'"([^"\s]+)"\s*:\s*"([^"]+)"', value)
        if not pair:
            pair = re.match(r'["\']?([A-Za-z0-9_.-]+(?:\[[^\]]+\])?)\s*(?:=\s*["\']|(?=[<>=!~]))([^"\';]+)', value)
        if pair:
            sides[line[0]][pair[1]] = pair[2].strip()
    return [(name, sides['-'][name], new) for name, new in sorted(sides['+'].items())
            if name in sides['-'] and sides['-'][name] != new]


class API:
    def __init__(self):
        self.token = os.environ.get('SHADOW_MIRROR_TOKEN') or os.environ.get('GH_TOKEN')
        if not self.token:
            raise ValueError('Set SHADOW_MIRROR_TOKEN or GH_TOKEN')

    def call(self, repo, path, method='GET', data=None):
        if method != 'GET' and repo != FORK:
            raise ValueError('Writes are restricted to the mirror repository')
        request = urllib.request.Request(
            f'https://api.github.com/repos/{repo}/{path}',
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': f'Bearer {self.token}', 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'{method} {path}: HTTP {error.code}: {error.read().decode()}') from error

    def pages(self, repo, path):
        result = []
        for page in range(1, 1000):
            items = self.call(repo, f'{path}{"&" if "?" in path else "?"}per_page=100&page={page}')
            result.extend(items)
            if len(items) < 100:
                return result
        raise RuntimeError('Pagination limit reached')

    def write(self, path, data, method='POST'):
        return self.call(FORK, path, method, data)


class Mirror:
    def __init__(self, api, dry_run=False, no_open_pr=False):
        self.api, self.dry_run, self.no_open_pr = api, dry_run, no_open_pr
        content = api.call(FORK, f'contents/{WORKFLOW}?ref=master')
        workflow = base64.b64decode(content['content']).decode()
        self.patterns = workflow_paths(workflow)
        self.workflow, count = re.subn(r'(?m)^(\s+branches:)\s*\[master\]', r"\1 [master, 'shadow/base/**']", workflow, count=1)
        if count != 1:
            raise ValueError('Unexpected push.branches configuration')
        self.mirrors = {}
        for pr in api.pages(FORK, 'pulls?state=all'):
            marker = MARKER.search(pr.get('body') or '')
            if marker:
                self.mirrors[int(marker[1])] = pr

    def tree(self, sha):
        api = self.api
        root = api.call(FORK, f'git/commits/{sha}')['tree']['sha']
        entries = api.call(FORK, f'git/trees/{root}')['tree']
        github = next((e['sha'] for e in entries if e['path'] == '.github'), None)
        workflows = api.write('git/trees', {'tree': [{'path': 'garnet-ci.yml', 'mode': '100644', 'type': 'blob', 'content': self.workflow}]})['sha']
        replacement = {'path': 'workflows', 'mode': '040000', 'type': 'tree', 'sha': workflows}
        data = {'tree': [replacement]}
        if github:
            data['base_tree'] = github
        github = api.write('git/trees', data)['sha']
        return api.write('git/trees', {'base_tree': root, 'tree': [{'path': '.github', 'mode': '040000', 'type': 'tree', 'sha': github}]})['sha']

    def commit(self, tree, parents, message):
        return self.api.write('git/commits', {'tree': tree, 'parents': parents, 'message': message})['sha']

    def ref(self, name, sha):
        try:
            self.api.call(FORK, f'git/ref/heads/{name}')
        except RuntimeError as error:
            if 'HTTP 404:' not in str(error):
                raise
            self.api.write('git/refs', {'ref': f'refs/heads/{name}', 'sha': sha})
        else:
            self.api.write(f'git/refs/heads/{name}', {'sha': sha, 'force': False}, 'PATCH')

    def baseline_started(self, branch, sha):
        query = urllib.parse.urlencode({'branch': branch, 'head_sha': sha, 'per_page': 10})
        def started():
            return bool(self.api.call(FORK, f'actions/workflows/garnet-ci.yml/runs?{query}')['workflow_runs'])
        for _ in range(12):
            if started():
                return
            time.sleep(5)
        self.api.write('actions/workflows/garnet-ci.yml/dispatches', {'ref': branch})
        for _ in range(24):
            if started():
                return
            time.sleep(5)
        raise RuntimeError('Baseline workflow did not start; head was not pushed')

    def sync(self, number):
        api = self.api
        pr = api.call(SOURCE, f'pulls/{number}')
        existing = self.mirrors.get(number)
        if pr['state'] != 'open':
            if existing and existing['state'] == 'open' and not self.dry_run:
                api.write(f'pulls/{existing["number"]}', {'state': 'closed'}, 'PATCH')
            return {'status': 'closed' if existing else 'skipped'}
        if pr['draft'] or pr['base']['ref'] != 'master':
            return {'status': 'skipped'}
        if existing and not self.no_open_pr and MARKER.search(existing['body'])[2] == pr['head']['sha']:
            return {'status': 'unchanged', 'url': existing['html_url']}
        files = api.pages(SOURCE, f'pulls/{number}/files')
        matched = [f for f in files if path_matches(f['filename'], self.patterns)]
        if not matched:
            return {'status': 'skipped'}
        if self.dry_run:
            return {'status': 'dry-run', 'files': [f['filename'] for f in matched]}
        base_branch, head_branch = f'shadow/base/{number}', f'shadow/pr/{number}'
        if existing:
            baseline = existing['base']['sha']
            parent = api.call(FORK, f'git/ref/heads/{head_branch}')['object']['sha']
        else:
            try:
                baseline = api.call(FORK, f'git/ref/heads/{base_branch}')['object']['sha']
            except RuntimeError as error:
                if 'HTTP 404:' not in str(error):
                    raise
                baseline = self.commit(self.tree(pr['base']['sha']), [], 'shadow: baseline')
                self.ref(base_branch, baseline)
            parent = baseline
            try:
                parent = api.call(FORK, f'git/ref/heads/{head_branch}')['object']['sha']
            except RuntimeError as error:
                if 'HTTP 404:' not in str(error):
                    raise
        self.baseline_started(base_branch, baseline)
        title = scrub_title(pr['title'])
        tree = self.tree(pr['head']['sha'])
        if parent != baseline and api.call(FORK, f'git/commits/{parent}')['tree']['sha'] == tree:
            head = parent
        else:
            head = self.commit(tree, [parent], title)
            self.ref(head_branch, head)
        lines = ['Dependency files changed:', '']
        for file in matched:
            lines.append(f'- `{scrub_title(file["filename"])}`')
            for name, old, new in version_transitions(file['filename'], file.get('patch')):
                lines.append(f'  - {scrub_title(name)} {scrub_title(old)} → {scrub_title(new)}')
        lines.extend(['', f'Mirror base `{baseline}` → head `{head}`', '',
                      f'<!-- garnet-shadow-mirror upstream={number} upstream_head={pr["head"]["sha"]} upstream_base={pr["base"]["sha"]} -->'])
        data = {'title': title, 'body': '\n'.join(lines)}
        if self.no_open_pr:
            directory = Path('/tmp/shadow_mirror')
            directory.mkdir(parents=True, exist_ok=True)
            title_path = directory / f'{number}.title'
            body_path = directory / f'{number}.body.md'
            title_path.write_text(title + '\n', encoding='utf-8')
            body_path.write_text(data['body'] + '\n', encoding='utf-8')
            if not existing:
                return {'status': 'ready', 'base': baseline, 'head': head,
                        'title_file': str(title_path), 'body_file': str(body_path)}
        if existing:
            result = api.write(f'pulls/{existing["number"]}', data, 'PATCH')
        else:
            result = api.write('pulls', dict(data, head=head_branch, base=base_branch))
        return {'status': 'updated' if existing else 'created', 'url': result['html_url'], 'base': baseline, 'head': head}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sync = sub.add_parser('sync')
    sync.add_argument('--pr', type=int, action='append')
    sync.add_argument('--since-hours', type=float, default=72)
    sync.add_argument('--dry-run', action='store_true')
    sync.add_argument('--no-open-pr', action='store_true')
    args = parser.parse_args()
    api = API()
    mirror = Mirror(api, args.dry_run, args.no_open_pr)
    numbers = args.pr
    if not numbers:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=args.since_hours)
        numbers = [pr['number'] for pr in api.pages(SOURCE, 'pulls?state=open&base=master&sort=created&direction=desc')
                   if datetime.datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) >= cutoff]
        numbers = list(dict.fromkeys(numbers + [n for n, pr in mirror.mirrors.items() if pr['state'] == 'open']))
    failed = False
    for number in numbers:
        try:
            result = mirror.sync(number)
        except Exception as error:
            result = {'status': 'error', 'error': str(error)}
            failed = True
        print(json.dumps(dict(pr=number, **result)), flush=True)
        if result['status'] == 'error':
            break
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
