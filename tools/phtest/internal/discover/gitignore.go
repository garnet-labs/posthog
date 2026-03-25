package discover

import (
	"io/fs"
	"os"
	"path/filepath"
	"strings"

	ignore "github.com/sabhiram/go-gitignore"
)

// ignoreMatcher checks paths against .gitignore files collected from the repo.
// It scopes each .gitignore to its directory so patterns only apply to descendants.
type ignoreMatcher struct {
	repoRoot string
	matchers []scopedMatcher
	loaded   map[string]bool
}

type scopedMatcher struct {
	dir string
	gi  *ignore.GitIgnore
}

func newIgnoreMatcher(repoRoot string) *ignoreMatcher {
	m := &ignoreMatcher{
		repoRoot: repoRoot,
		loaded:   make(map[string]bool),
	}
	m.loadDir(repoRoot)
	return m
}

// loadDir loads the .gitignore in dir, if present and not already loaded.
func (m *ignoreMatcher) loadDir(dir string) {
	if m.loaded[dir] {
		return
	}
	m.loaded[dir] = true
	gi, err := ignore.CompileIgnoreFile(filepath.Join(dir, ".gitignore"))
	if err != nil {
		return
	}
	m.matchers = append(m.matchers, scopedMatcher{dir: dir, gi: gi})
}

// loadChain loads .gitignore files from repoRoot down to dir.
func (m *ignoreMatcher) loadChain(dir string) {
	var chain []string
	cur := dir
	for {
		chain = append(chain, cur)
		if cur == m.repoRoot {
			break
		}
		parent := filepath.Dir(cur)
		if parent == cur {
			break
		}
		cur = parent
	}
	// Load from root down
	for i := len(chain) - 1; i >= 0; i-- {
		m.loadDir(chain[i])
	}
}

// isIgnored returns true if absPath is matched by any loaded .gitignore
// whose directory is an ancestor of absPath.
func (m *ignoreMatcher) isIgnored(absPath string) bool {
	if filepath.Base(absPath) == ".git" {
		return true
	}
	for _, sm := range m.matchers {
		rel, err := filepath.Rel(sm.dir, absPath)
		if err != nil || strings.HasPrefix(rel, "..") {
			continue
		}
		if sm.gi.MatchesPath(rel) {
			return true
		}
	}
	return false
}

// Walk walks root respecting .gitignore files. It loads .gitignore files
// from repoRoot down to root before starting, and picks up nested ones
// during the walk. Ignored directories are skipped automatically.
func (m *ignoreMatcher) Walk(root string, fn fs.WalkDirFunc) error {
	m.loadChain(root)
	return filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return fn(path, d, err)
		}
		if d.IsDir() {
			if path != root && m.isIgnored(path) {
				return filepath.SkipDir
			}
			m.loadDir(path)
		}
		return fn(path, d, err)
	})
}
