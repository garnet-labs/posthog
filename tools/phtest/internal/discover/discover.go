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
	CategoryE2E      Category = "E2E"
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
	var suites []Suite

	backend, err := discoverBackend(repoRoot, ig)
	if err != nil {
		return nil, err
	}
	suites = append(suites, backend...)

	frontend, err := discoverFrontend(repoRoot, ig)
	if err != nil {
		return nil, err
	}
	suites = append(suites, frontend...)

	rust, err := discoverRust(repoRoot)
	if err != nil {
		return nil, err
	}
	suites = append(suites, rust...)

	goSuites, err := discoverGo(repoRoot, ig)
	if err != nil {
		return nil, err
	}
	suites = append(suites, goSuites...)

	e2e, err := discoverE2E(repoRoot, ig)
	if err != nil {
		return nil, err
	}
	suites = append(suites, e2e...)

	// Sort by RelPath so the tree follows filesystem order
	sort.Slice(suites, func(i, j int) bool {
		return suites[i].RelPath < suites[j].RelPath
	})

	return suites, nil
}

// discoverBackend finds individual Python test files (test_*.py)
// under products/*/, posthog/, and ee/.
func discoverBackend(repoRoot string, ig *ignoreMatcher) ([]Suite, error) {
	var suites []Suite

	for _, searchRoot := range []string{"products", "posthog", "ee"} {
		dir := filepath.Join(repoRoot, searchRoot)
		if _, err := os.Stat(dir); err != nil {
			continue
		}
		_ = ig.Walk(dir, func(path string, d os.DirEntry, err error) error {
			if err != nil {
				return nil
			}
			if d.IsDir() {
				// Skip frontend subdirs — no Python tests there
				if d.Name() == "frontend" {
					return filepath.SkipDir
				}
				return nil
			}
			if !isPythonTestFile(d.Name()) {
				return nil
			}
			rel, _ := filepath.Rel(repoRoot, path)
			suites = append(suites, Suite{
				Name:     d.Name(),
				Category: CategoryBackend,
				RelPath:  rel,
				Dir:      repoRoot,
				Cmd:      "pytest " + rel,
			})
			return nil
		})
	}

	return suites, nil
}

func isPythonTestFile(name string) bool {
	return strings.HasSuffix(name, ".py") &&
		(strings.HasPrefix(name, "test_") || strings.HasSuffix(name, "_test.py"))
}

// discoverFrontend finds individual *.test.ts(x) files under products/*/frontend/
// and frontend/src/.
func discoverFrontend(repoRoot string, ig *ignoreMatcher) ([]Suite, error) {
	var suites []Suite

	for _, searchRoot := range []string{
		filepath.Join("products"),
		filepath.Join("frontend", "src"),
	} {
		dir := filepath.Join(repoRoot, searchRoot)
		if _, err := os.Stat(dir); err != nil {
			continue
		}
		_ = ig.Walk(dir, func(path string, d os.DirEntry, err error) error {
			if err != nil {
				return nil
			}
			if d.IsDir() {
				return nil
			}
			if !isTSTestFile(d.Name()) {
				return nil
			}
			rel, _ := filepath.Rel(repoRoot, path)
			suites = append(suites, Suite{
				Name:     d.Name(),
				Category: CategoryFrontend,
				RelPath:  rel,
				Dir:      repoRoot,
				Cmd:      "pnpm --filter=@posthog/frontend jest " + rel,
			})
			return nil
		})
	}

	return suites, nil
}

// discoverRust parses rust/Cargo.toml for workspace members,
// grouped by their directory structure.
func discoverRust(repoRoot string) ([]Suite, error) {
	cargoPath := filepath.Join(repoRoot, "rust", "Cargo.toml")
	data, err := os.ReadFile(cargoPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}

	members := parseCargoMembers(string(data))
	rustDir := filepath.Join(repoRoot, "rust")

	var suites []Suite
	for _, member := range members {
		name := resolveRustPackageName(rustDir, member)

		cat := CategoryRust
		if dir := filepath.Dir(member); dir != "." {
			cat = Category("Rust / " + strings.ReplaceAll(dir, string(filepath.Separator), " / "))
		}

		suites = append(suites, Suite{
			Name:     name,
			Category: cat,
			RelPath:  filepath.Join("rust", member),
			Dir:      rustDir,
			Cmd:      "cargo test -p " + name,
		})
	}

	sort.Slice(suites, func(i, j int) bool {
		if suites[i].Category != suites[j].Category {
			return suites[i].Category < suites[j].Category
		}
		return suites[i].Name < suites[j].Name
	})
	return suites, nil
}

// discoverE2E finds individual *.spec.ts files under playwright/e2e/,
// grouped by their directory structure.
func discoverE2E(repoRoot string, ig *ignoreMatcher) ([]Suite, error) {
	e2eDir := filepath.Join(repoRoot, "playwright", "e2e")
	if _, err := os.Stat(e2eDir); err != nil {
		return nil, nil
	}

	type specFile struct {
		relPath string // relative to e2eDir
		name    string // filename without .spec.ts
		dir     string // directory relative to e2eDir, "." for root
	}
	var specs []specFile

	err := ig.Walk(e2eDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			return nil
		}
		if !strings.HasSuffix(d.Name(), ".spec.ts") {
			return nil
		}
		rel, _ := filepath.Rel(e2eDir, path)
		specs = append(specs, specFile{
			relPath: rel,
			name:    strings.TrimSuffix(d.Name(), ".spec.ts"),
			dir:     filepath.Dir(rel),
		})
		return nil
	})
	if err != nil {
		return nil, err
	}

	// Detect name collisions to disambiguate
	nameCount := make(map[string]int)
	for _, s := range specs {
		nameCount[s.name]++
	}

	playwrightDir := filepath.Join(repoRoot, "playwright")
	var suites []Suite
	for _, s := range specs {
		cat := CategoryE2E
		if s.dir != "." {
			cat = Category("E2E / " + strings.ReplaceAll(s.dir, string(filepath.Separator), " / "))
		}

		name := s.name
		if nameCount[name] > 1 {
			name = s.dir + "/" + name
		}

		suites = append(suites, Suite{
			Name:     name,
			Category: cat,
			RelPath:  filepath.Join("playwright", "e2e", s.relPath),
			Dir:      playwrightDir,
			Cmd:      "npx playwright test e2e/" + s.relPath,
		})
	}

	sort.Slice(suites, func(i, j int) bool {
		if suites[i].Category != suites[j].Category {
			return suites[i].Category < suites[j].Category
		}
		return suites[i].Name < suites[j].Name
	})

	return suites, nil
}

// discoverGo finds Go test packages within Go modules,
// excluding the phtest module itself. One suite per package with _test.go files.
func discoverGo(repoRoot string, ig *ignoreMatcher) ([]Suite, error) {
	var suites []Suite

	// First find all go.mod files to identify module roots
	var modules []struct {
		dir    string // absolute path
		rel    string // relative to repoRoot
	}
	_ = ig.Walk(repoRoot, func(path string, d os.DirEntry, err error) error {
		if err != nil || d.IsDir() || d.Name() != "go.mod" {
			return nil
		}
		dir := filepath.Dir(path)
		rel, _ := filepath.Rel(repoRoot, dir)
		if rel == filepath.Join("tools", "phtest") {
			return nil
		}
		modules = append(modules, struct {
			dir string
			rel string
		}{dir, rel})
		return nil
	})

	// For each module, find packages with test files
	for _, mod := range modules {
		_ = ig.Walk(mod.dir, func(path string, d os.DirEntry, err error) error {
			if err != nil || !d.IsDir() {
				return nil
			}
			if !dirHasGoTests(path) {
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

	return suites, nil
}

// dirHasGoTests returns true if the directory directly contains _test.go files (non-recursive).
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

func isTSTestFile(name string) bool {
	return strings.HasSuffix(name, ".test.ts") || strings.HasSuffix(name, ".test.tsx")
}

// parseCargoMembers extracts workspace member paths from Cargo.toml content.
// Uses simple line parsing to avoid a TOML dependency.
func parseCargoMembers(content string) []string {
	var members []string
	inMembers := false
	for _, line := range strings.Split(content, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "members") && strings.Contains(trimmed, "[") {
			inMembers = true
			// Handle inline: members = ["a", "b"]
			if strings.Contains(trimmed, "]") {
				return parseMembersInline(trimmed)
			}
			continue
		}
		if inMembers {
			if strings.Contains(trimmed, "]") {
				break
			}
			// Each line is like: "common/hogvm",
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
	// Simple line scan for name = "..."
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
