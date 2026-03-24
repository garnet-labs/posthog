package discover

import (
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type Category string

const (
	CategoryBackend      Category = "Backend / products"
	CategoryFrontend     Category = "Frontend / products"
	CategoryFrontendCore Category = "Frontend"
	CategoryRust         Category = "Rust"
	CategoryE2E          Category = "E2E"
)

type Suite struct {
	Name     string
	Category Category
	Dir      string // working directory for the command
	Cmd      string // shell command to run
}

// Discover finds all test suites in the repo rooted at repoRoot.
func Discover(repoRoot string) ([]Suite, error) {
	var suites []Suite

	backend, err := discoverBackend(repoRoot)
	if err != nil {
		return nil, err
	}
	suites = append(suites, backend...)

	frontend, err := discoverFrontend(repoRoot)
	if err != nil {
		return nil, err
	}
	suites = append(suites, frontend...)

	rust, err := discoverRust(repoRoot)
	if err != nil {
		return nil, err
	}
	suites = append(suites, rust...)

	e2e, err := discoverE2E(repoRoot)
	if err != nil {
		return nil, err
	}
	suites = append(suites, e2e...)

	return suites, nil
}

// discoverBackend finds Python test directories containing APIBaseTest usages.
// It scans products/*/, posthog/, and ee/ and groups by product or subdirectory.
func discoverBackend(repoRoot string) ([]Suite, error) {
	var suites []Suite

	// Products — one suite per product that has APIBaseTest tests
	productsDir := filepath.Join(repoRoot, "products")
	if entries, err := os.ReadDir(productsDir); err == nil {
		for _, e := range entries {
			if !e.IsDir() {
				continue
			}
			dir := filepath.Join(productsDir, e.Name())
			if !hasPythonTestFiles(dir) {
				continue
			}
			rel, _ := filepath.Rel(repoRoot, dir)
			suites = append(suites, Suite{
				Name:     e.Name(),
				Category: CategoryBackend,
				Dir:      repoRoot,
				Cmd:      "pytest " + rel + "/",
			})
		}
	}

	// Core dirs — one suite per top-level subdirectory of posthog/ and ee/
	for _, root := range []string{"posthog", "ee"} {
		rootDir := filepath.Join(repoRoot, root)
		entries, err := os.ReadDir(rootDir)
		if err != nil {
			continue
		}
		cat := Category("Backend / " + root)
		for _, e := range entries {
			if !e.IsDir() {
				continue
			}
			dir := filepath.Join(rootDir, e.Name())
			if !hasPythonTestFiles(dir) {
				continue
			}
			rel, _ := filepath.Rel(repoRoot, dir)
			suites = append(suites, Suite{
				Name:     e.Name(),
				Category: cat,
				Dir:      repoRoot,
				Cmd:      "pytest " + rel + "/",
			})
		}
	}

	sort.Slice(suites, func(i, j int) bool {
		if suites[i].Category != suites[j].Category {
			return suites[i].Category < suites[j].Category
		}
		return suites[i].Name < suites[j].Name
	})
	return suites, nil
}

// discoverFrontend finds products with *.test.ts(x) files under products/*/frontend/
// and top-level directories under frontend/src/ that contain test files.
func discoverFrontend(repoRoot string) ([]Suite, error) {
	var suites []Suite

	// Products
	productsDir := filepath.Join(repoRoot, "products")
	entries, err := os.ReadDir(productsDir)
	if err != nil {
		return nil, err
	}
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		frontendDir := filepath.Join(productsDir, e.Name(), "frontend")
		if !hasTSTestFiles(frontendDir) {
			continue
		}
		suites = append(suites, Suite{
			Name:     e.Name(),
			Category: CategoryFrontend,
			Dir:      repoRoot,
			Cmd:      "pnpm --filter=@posthog/frontend jest products/" + e.Name() + "/",
		})
	}

	// Top-level frontend/src/ directories
	srcDir := filepath.Join(repoRoot, "frontend", "src")
	srcEntries, err := os.ReadDir(srcDir)
	if err == nil {
		var hasRootTests bool
		for _, e := range srcEntries {
			if e.IsDir() {
				dir := filepath.Join(srcDir, e.Name())
				if !hasTSTestFiles(dir) {
					continue
				}
				suites = append(suites, Suite{
					Name:     e.Name(),
					Category: CategoryFrontendCore,
					Dir:      repoRoot,
					Cmd:      "pnpm --filter=@posthog/frontend jest frontend/src/" + e.Name() + "/",
				})
			} else if isTSTestFile(e.Name()) {
				hasRootTests = true
			}
		}
		if hasRootTests {
			suites = append(suites, Suite{
				Name:     "src",
				Category: CategoryFrontendCore,
				Dir:      repoRoot,
				Cmd:      "pnpm --filter=@posthog/frontend jest --testPathPattern='frontend/src/[^/]+\\.test\\.tsx?$'",
			})
		}
	}

	sort.Slice(suites, func(i, j int) bool {
		if suites[i].Category != suites[j].Category {
			return suites[i].Category < suites[j].Category
		}
		return suites[i].Name < suites[j].Name
	})
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
func discoverE2E(repoRoot string) ([]Suite, error) {
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

	err := filepath.WalkDir(e2eDir, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			if d.Name() == "node_modules" {
				return filepath.SkipDir
			}
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

// hasPythonTestFiles returns true if dir contains any .py files referencing APIBaseTest.
func hasPythonTestFiles(dir string) bool {
	if _, err := os.Stat(dir); err != nil {
		return false
	}
	found := false
	_ = filepath.WalkDir(dir, func(path string, d os.DirEntry, err error) error {
		if err != nil || found {
			return filepath.SkipDir
		}
		if d.IsDir() {
			name := d.Name()
			if name == "node_modules" || name == "__pycache__" || name == ".venv" || name == "frontend" {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(d.Name(), ".py") {
			return nil
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return nil
		}
		if strings.Contains(string(data), "APIBaseTest") {
			found = true
			return filepath.SkipDir
		}
		return nil
	})
	return found
}

func isTSTestFile(name string) bool {
	return strings.HasSuffix(name, ".test.ts") || strings.HasSuffix(name, ".test.tsx")
}

// hasTSTestFiles returns true if dir contains any *.test.ts or *.test.tsx files.
func hasTSTestFiles(dir string) bool {
	if _, err := os.Stat(dir); err != nil {
		return false
	}
	found := false
	_ = filepath.WalkDir(dir, func(path string, d os.DirEntry, err error) error {
		if err != nil || found {
			return filepath.SkipDir
		}
		if d.IsDir() {
			if d.Name() == "node_modules" || d.Name() == "__pycache__" {
				return filepath.SkipDir
			}
			return nil
		}
		if isTSTestFile(d.Name()) {
			found = true
			return filepath.SkipDir
		}
		return nil
	})
	return found
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
