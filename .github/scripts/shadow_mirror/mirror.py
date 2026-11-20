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
    title = re.sub(r'https?://\S+|www\.\S+|#\d+', '', title)
    title = re.sub(re.escape(SOURCE), '', title, flags=re.I)
    title = re.sub(r'`?((?:npm:)?(?:@[\w.-]+/[\w.-]+(?:@[\w.^~*+-]+)?|[\w.-]+@[\w.^~*+-]+))`?', r'`\1`', title)
    title = re.sub(r'(?<![\w/])@[\w.-]+(?![\w./-])', '', title)
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


def file_matches(file, patterns):
    return any(path_matches(file[key], patterns) for key in ('filename', 'previous_filename') if file.get(key))


def dependency_file(filename):
    name = filename.rsplit('/', 1)[-1]
    return name in {
        'package.json', 'pnpm-lock.yaml', 'pnpm-workspace.yaml', 'package-lock.json',
        'npm-shrinkwrap.json', 'yarn.lock', 'bun.lock', 'bun.lockb', 'pyproject.toml',
        'uv.lock', 'poetry.lock', 'Pipfile', 'Pipfile.lock', 'go.mod', 'go.sum',
        'Cargo.toml', 'Cargo.lock', '.node-version', '.nvmrc',
    } or bool(re.fullmatch(r'(?:requirements|constraints)[^/]*\.txt', name))


def recorder_installs(filename, patterns, workspace):
    if path_matches(filename, patterns):
        return True
    if not filename.endswith('/package.json') or 'package.json' not in patterns:
        return False
    directory = filename.rsplit('/', 1)[0]
    included = [p for p in workspace if not p.startswith('!')]
    excluded = [p[1:] for p in workspace if p.startswith('!')]
    return path_matches(directory, included) and not path_matches(directory, excluded)


def version_transitions(filename, patch):
    """Read paired dependency declarations from a unified manifest diff."""
    if not dependency_file(filename):
        return []
    sides = {'-': {}, '+': {}}
    package = None
    pnpm = filename.endswith('pnpm-lock.yaml')
    package_lock = filename.endswith(('Cargo.lock', 'uv.lock', 'poetry.lock'))
    for line in (patch or '').splitlines():
        if line.startswith('@@'):
            package = None
        if not line or line[0] not in (' ', '-', '+') or line.startswith(('---', '+++')):
            continue
        value = line[1:].strip().rstrip(',')
        if package_lock:
            if value.startswith('[['):
                package = None
            match = re.match(r'name\s*=\s*"([^"]+)"', value)
            if match:
                package = match[1]
        if line[0] not in sides:
            continue
        pair = None
        if filename.endswith(('.node-version', '.nvmrc')):
            pair = ('Node.js', value)
        elif package_lock and package:
            match = re.match(r'version\s*=\s*"([^"]+)"', value)
            if match:
                pair = (package, match[1])
        elif pnpm:
            match = re.match(r"['\"]?((?:@[\w.-]+/)?[\w.-]+)@([\w.+-]+)(?:\(|['\"]?:)", value)
            if not match:
                match = re.match(r"['\"]?((?:@[\w.-]+/)?[\w.-]+)['\"]?:\s*['\"]?([~^]?\d[\w.+-]*)", value)
                if match and match[1] in ('version', 'specifier'):
                    match = None
            if match:
                pair = (match[1], match[2])
        elif filename.endswith(('go.mod', 'go.sum')):
            match = re.match(r'(\S+)\s+(v\S+?)(?:/go.mod)?(?:\s|$)', value)
            if match:
                pair = (match[1], match[2])
        if not pair and not pnpm and not package_lock:
            pair = re.match(r'"([^"\s]+)"\s*:\s*"([^"]+)"', value)
        if not pair and not pnpm and not package_lock:
            pair = re.match(r'["\']?([A-Za-z0-9_.-]+(?:\[[^\]]+\])?)\s*(?:=\s*["\']|(?=[<>=!~]))([^"\';]+)', value)
        if pair:
            name, version = (pair[1], pair[2]) if isinstance(pair, re.Match) else pair
            sides[line[0]].setdefault(name, set()).add(version.strip())
    transitions = []
    for name in sorted(sides['-'].keys() | sides['+'].keys()):
        old, new = sides['-'].get(name, set()), sides['+'].get(name, set())
        removed, added = old - new, new - old
        if removed or added:
            transitions.append((name, ', '.join(sorted(removed)) or '∅', ', '.join(sorted(added)) or '∅'))
    return transitions


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
        self.history = {}
        for pr in api.pages(FORK, 'pulls?state=all'):
            marker = MARKER.search(pr.get('body') or '')
            if marker:
                number = int(marker[1])
                self.history.setdefault(number, []).append(pr)
                if number not in self.mirrors or pr['number'] > self.mirrors[number]['number']:
                    self.mirrors[number] = pr

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

    def merge_base(self, pr):
        comparison = self.api.call(SOURCE, f'compare/{pr["base"]["sha"]}...{pr["head"]["sha"]}')
        return comparison['merge_base_commit']['sha']

    def branches(self, number, existing, new_revision=False):
        if existing and existing['state'] == 'open' and not new_revision:
            return existing['base']['ref'], existing['head']['ref']
        history = getattr(self, 'history', {}).get(number, [existing] if existing else [])
        revision = 1
        for pr in history:
            match = re.fullmatch(rf'shadow/pr/{number}(?:-r(\d+))?', pr['head']['ref'])
            if match:
                revision = max(revision, int(match[1] or 1) + 1)
        suffix = f'-r{revision}' if revision > 1 else ''
        return f'shadow/base/{number}{suffix}', f'shadow/pr/{number}{suffix}'

    def ref(self, name, sha, force=False):
        if force:
            if not name.startswith('shadow/pr/'):
                raise ValueError('Only unreviewed mirror heads can be replaced')
            query = urllib.parse.urlencode({'state': 'open', 'head': f'{FORK.split("/")[0]}:{name}'})
            if self.api.pages(FORK, f'pulls?{query}'):
                raise RuntimeError('Cannot replace a branch with an open mirror pull request')
        try:
            self.api.call(FORK, f'git/ref/heads/{name}')
        except RuntimeError as error:
            if 'HTTP 404:' not in str(error):
                raise
            self.api.write('git/refs', {'ref': f'refs/heads/{name}', 'sha': sha})
        else:
            self.api.write(f'git/refs/heads/{name}', {'sha': sha, 'force': force}, 'PATCH')

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
        if pr.get('author_association') not in {'OWNER', 'MEMBER', 'COLLABORATOR'} and pr.get('user', {}).get('type') != 'Bot':
            return {'status': 'untrusted_author'}
        upstream_base = self.merge_base(pr)
        marker = MARKER.search(existing.get('body') or '') if existing else None
        rebased = bool(marker and marker[3] != upstream_base)
        base_branch, head_branch = self.branches(number, existing, new_revision=rebased)
        if existing and (existing['state'] != 'open' or rebased):
            existing = None
        if existing and not self.no_open_pr and MARKER.search(existing['body']).groups()[1:] == (pr['head']['sha'], upstream_base):
            return {'status': 'unchanged', 'url': existing['html_url']}
        files = api.pages(SOURCE, f'pulls/{number}/files')
        matched = [f for f in files if file_matches(f, self.patterns)]
        if not matched:
            return {'status': 'skipped'}
        if self.dry_run:
            return {'status': 'dry-run', 'files': [f['filename'] for f in matched]}
        workspace = []
        if any(f['filename'].endswith('/package.json') and not path_matches(f['filename'], self.patterns) for f in files):
            content = api.call(SOURCE, f'contents/pnpm-workspace.yaml?ref={pr["head"]["sha"]}')
            document = base64.b64decode(content['content']).decode()
            section = re.search(r'(?m)^packages:\s*\n(.*?)(?=^\S|\Z)', document, re.S)
            if not section:
                raise ValueError('Missing workspace packages list')
            workspace = [m.strip().strip("'\"") for m in re.findall(r'(?m)^\s+-\s+([^\n]+)', section[1])]
        if existing:
            baseline = existing['base']['sha']
            parent = api.call(FORK, f'git/ref/heads/{head_branch}')['object']['sha']
        else:
            try:
                baseline = api.call(FORK, f'git/ref/heads/{base_branch}')['object']['sha']
            except RuntimeError as error:
                if 'HTTP 404:' not in str(error):
                    raise
                baseline = self.commit(self.tree(upstream_base), [], 'chore: shadow baseline')
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
        current = api.call(FORK, f'git/commits/{parent}') if parent != baseline else None
        if current and current['tree']['sha'] == tree:
            head = parent
            if current['message'] != title and [p['sha'] for p in current['parents']] == [baseline] and not (existing and existing['state'] == 'open'):
                head = self.commit(tree, [baseline], title)
                self.ref(head_branch, head, force=True)
        else:
            head = self.commit(tree, [parent], title)
            self.ref(head_branch, head)
        lines = ['Dependency files changed:', '']
        for file in files:
            if not dependency_file(file['filename']):
                continue
            recorded = 'recorder installs' if recorder_installs(file['filename'], self.patterns, workspace) else 'not installed by recorder'
            lines.append(f'- `{scrub_title(file["filename"])}` ({recorded})')
            for name, old, new in version_transitions(file['filename'], file.get('patch')):
                lines.append(f'  - {scrub_title(name)} {scrub_title(old)} → {scrub_title(new)}')
        lines.extend(['', f'Mirror base `{baseline}` → head `{head}`', '',
                      f'<!-- garnet-shadow-mirror upstream={number} upstream_head={pr["head"]["sha"]} upstream_base={upstream_base} -->'])
        data = {'title': title, 'body': '\n'.join(lines)}
        if self.no_open_pr:
            directory = Path('/tmp/shadow_mirror')
            directory.mkdir(parents=True, exist_ok=True)
            title_path = directory / f'{number}.title'
            body_path = directory / f'{number}.body.md'
            title_path.write_text(title + '\n', encoding='utf-8')
            body_path.write_text(data['body'] + '\n', encoding='utf-8')
            return {'status': 'ready', 'base': baseline, 'head': head,
                    'base_ref': base_branch, 'head_ref': head_branch,
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
