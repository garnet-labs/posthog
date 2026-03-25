package discover

import (
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type Category string

const (
	CategoryBackend  Category = "Backend"
	CategoryFrontend Category = "Frontend"
	CategoryRust     Category = "Rust"
	CategoryGo       Category = "Go"
	CategoryPlaywright Category = "Playwright"
)

type Suite struct {
	Name     string
	Category Category
	RelPath  string // path relative to repo root (used for tree layout)
	Dir      string // working directory for the command
	Cmd      string // shell command to run
}

// Discover finds all test suites in the repo rooted at repoRoot.
func Discover(repoRoot string) ([]Suite, error) {
	ig := newIgnoreMatcher(repoRoot)

	suites := discoverFileTests(repoRoot, ig)

	rust, err := discoverRust(repoRoot)
	if err != nil {
		return nil, err
	}
	suites = append(suites, rust...)

	goSuites := discoverGo(repoRoot, ig)
	suites = append(suites, goSuites...)

	sort.Slice(suites, func(i, j int) bool {
		return suites[i].RelPath < suites[j].RelPath
	})
	return suites, nil
}

// discoverFileTests finds test files in a single walk over the repo:
// Python (test_*.py), TypeScript (*.test.ts(x)), and Playwright (*.spec.ts).
func discoverFileTests(repoRoot string, ig *ignoreMatcher) []Suite {
	playwrightDir := filepath.Join(repoRoot, "playwright")
	var suites []Suite

	_ = ig.Walk(repoRoot, func(path string, d os.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return nil
		}
		name := d.Name()
		rel, _ := filepath.Rel(repoRoot, path)

		switch {
		case isPythonTestFile(name):
			suites = append(suites, Suite{
				Name:     name,
				Category: CategoryBackend,
				RelPath:  rel,
				Dir:      repoRoot,
				Cmd:      "pytest " + rel,
			})
		case isTSTestFile(name):
			suites = append(suites, Suite{
				Name:     name,
				Category: CategoryFrontend,
				RelPath:  rel,
				Dir:      repoRoot,
				Cmd:      "pnpm --filter=@posthog/frontend jest " + rel,
			})
		case strings.HasSuffix(name, ".spec.ts"):
			e2eRel, relErr := filepath.Rel(playwrightDir, path)
			if relErr != nil {
				return nil
			}
			suites = append(suites, Suite{
				Name:     strings.TrimSuffix(name, ".spec.ts"),
				Category: CategoryPlaywright,
				RelPath:  rel,
				Dir:      playwrightDir,
				Cmd:      "npx playwright test " + filepath.ToSlash(e2eRel),
			})
		}
		return nil
	})

	return suites
}

// discoverRust parses rust/Cargo.toml for workspace members.
func discoverRust(repoRoot string) ([]Suite, error) {
	cargoPath := filepath.Join(repoRoot, "rust", "Cargo.toml")
	data, err := os.ReadFile(cargoPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}

	rustDir := filepath.Join(repoRoot, "rust")
	var suites []Suite
	for _, member := range parseCargoMembers(string(data)) {
		name := resolveRustPackageName(rustDir, member)
		suites = append(suites, Suite{
			Name:     name,
			Category: CategoryRust,
			RelPath:  filepath.Join("rust", member),
			Dir:      rustDir,
			Cmd:      "cargo test -p " + name,
		})
	}
	return suites, nil
}

// discoverGo finds Go test packages within Go modules,
// excluding the phtest module itself.
func discoverGo(repoRoot string, ig *ignoreMatcher) []Suite {
	// Phase 1: find module roots (go.mod locations)
	type goModule struct{ dir, rel string }
	var modules []goModule

	_ = ig.Walk(repoRoot, func(path string, d os.DirEntry, err error) error {
		if err != nil || d.IsDir() || d.Name() != "go.mod" {
			return nil
		}
		dir := filepath.Dir(path)
		rel, _ := filepath.Rel(repoRoot, dir)
		if rel == filepath.Join("tools", "phtest") {
			return nil
		}
		modules = append(modules, goModule{dir, rel})
		return nil
	})

	// Phase 2: find packages with _test.go files within each module
	var suites []Suite
	for _, mod := range modules {
		_ = ig.Walk(mod.dir, func(path string, d os.DirEntry, err error) error {
			if err != nil || !d.IsDir() || !dirHasGoTests(path) {
				return nil
			}
			rel, _ := filepath.Rel(repoRoot, path)
			pkgRel, _ := filepath.Rel(mod.dir, path)
			pkg := "./" + filepath.ToSlash(pkgRel)
			if pkgRel == "." {
				pkg = "."
			}
			suites = append(suites, Suite{
				Name:     filepath.Base(path),
				Category: CategoryGo,
				RelPath:  rel,
				Dir:      mod.dir,
				Cmd:      "go test " + pkg,
			})
			return nil
		})
	}
	return suites
}

// ── file matchers ───────────────────────────────────────────────────────────────

func isPythonTestFile(name string) bool {
	return strings.HasSuffix(name, ".py") &&
		(strings.HasPrefix(name, "test_") || strings.HasSuffix(name, "_test.py"))
}

func isTSTestFile(name string) bool {
	return strings.HasSuffix(name, ".test.ts") || strings.HasSuffix(name, ".test.tsx")
}

// dirHasGoTests returns true if the directory directly contains _test.go files.
func dirHasGoTests(dir string) bool {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return false
	}
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), "_test.go") {
			return true
		}
	}
	return false
}

// ── cargo helpers ───────────────────────────────────────────────────────────────

// parseCargoMembers extracts workspace member paths from Cargo.toml content.
func parseCargoMembers(content string) []string {
	var members []string
	inMembers := false
	for _, line := range strings.Split(content, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "members") && strings.Contains(trimmed, "[") {
			inMembers = true
			if strings.Contains(trimmed, "]") {
				return parseMembersInline(trimmed)
			}
			continue
		}
		if inMembers {
			if strings.Contains(trimmed, "]") {
				break
			}
			trimmed = strings.Trim(trimmed, `", `)
			if trimmed != "" && !strings.HasPrefix(trimmed, "#") {
				members = append(members, trimmed)
			}
		}
	}
	return members
}

func parseMembersInline(line string) []string {
	start := strings.Index(line, "[")
	end := strings.Index(line, "]")
	if start < 0 || end < 0 || end <= start {
		return nil
	}
	inner := line[start+1 : end]
	var members []string
	for _, part := range strings.Split(inner, ",") {
		m := strings.Trim(strings.TrimSpace(part), `"`)
		if m != "" {
			members = append(members, m)
		}
	}
	return members
}

// resolveRustPackageName reads the member's Cargo.toml to get the package name.
// Falls back to the last path segment if the file can't be read.
func resolveRustPackageName(rustDir, member string) string {
	fallback := filepath.Base(member)
	data, err := os.ReadFile(filepath.Join(rustDir, member, "Cargo.toml"))
	if err != nil {
		return fallback
	}
	for _, line := range strings.Split(string(data), "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "name") && strings.Contains(trimmed, "=") {
			parts := strings.SplitN(trimmed, "=", 2)
			if len(parts) == 2 {
				name := strings.Trim(strings.TrimSpace(parts[1]), `"`)
				if name != "" {
					return name
				}
			}
		}
	}
	return fallback
}
