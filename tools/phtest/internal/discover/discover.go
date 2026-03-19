package discover

import (
	"encoding/json"
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
	CategoryE2E      Category = "E2E"
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

// discoverBackend scans products/*/package.json for backend:test scripts.
func discoverBackend(repoRoot string) ([]Suite, error) {
	productsDir := filepath.Join(repoRoot, "products")
	entries, err := os.ReadDir(productsDir)
	if err != nil {
		return nil, err
	}

	var suites []Suite
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		pkgPath := filepath.Join(productsDir, e.Name(), "package.json")
		cmd, ok := readPackageScript(pkgPath, "backend:test")
		if !ok || strings.HasPrefix(cmd, "echo ") {
			continue
		}
		suites = append(suites, Suite{
			Name:     e.Name(),
			Category: CategoryBackend,
			Dir:      filepath.Join(productsDir, e.Name()),
			Cmd:      cmd,
		})
	}
	sort.Slice(suites, func(i, j int) bool { return suites[i].Name < suites[j].Name })
	return suites, nil
}

// discoverFrontend finds products with *.test.ts(x) files under frontend/.
func discoverFrontend(repoRoot string) ([]Suite, error) {
	productsDir := filepath.Join(repoRoot, "products")
	entries, err := os.ReadDir(productsDir)
	if err != nil {
		return nil, err
	}

	var suites []Suite
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		frontendDir := filepath.Join(productsDir, e.Name(), "frontend")
		if !hasTestFiles(frontendDir) {
			continue
		}
		suites = append(suites, Suite{
			Name:     e.Name(),
			Category: CategoryFrontend,
			Dir:      repoRoot,
			Cmd:      "pnpm --filter=@posthog/frontend jest products/" + e.Name() + "/",
		})
	}
	sort.Slice(suites, func(i, j int) bool { return suites[i].Name < suites[j].Name })
	return suites, nil
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

	members := parseCargoMembers(string(data))
	rustDir := filepath.Join(repoRoot, "rust")

	var suites []Suite
	for _, member := range members {
		// Resolve the package name from the member's Cargo.toml
		name := resolveRustPackageName(rustDir, member)
		suites = append(suites, Suite{
			Name:     name,
			Category: CategoryRust,
			Dir:      rustDir,
			Cmd:      "cargo test -p " + name,
		})
	}
	sort.Slice(suites, func(i, j int) bool { return suites[i].Name < suites[j].Name })
	return suites, nil
}

// discoverE2E adds a single playwright suite if the directory exists.
func discoverE2E(repoRoot string) ([]Suite, error) {
	playwrightDir := filepath.Join(repoRoot, "playwright")
	if _, err := os.Stat(filepath.Join(playwrightDir, "package.json")); err != nil {
		return nil, nil
	}
	return []Suite{{
		Name:     "playwright",
		Category: CategoryE2E,
		Dir:      repoRoot,
		Cmd:      "pnpm --filter=playwright test",
	}}, nil
}

// readPackageScript reads a package.json and returns the named script.
func readPackageScript(path, scriptName string) (string, bool) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", false
	}
	var pkg struct {
		Scripts map[string]string `json:"scripts"`
	}
	if err := json.Unmarshal(data, &pkg); err != nil {
		return "", false
	}
	cmd, ok := pkg.Scripts[scriptName]
	return cmd, ok
}

// hasTestFiles returns true if dir contains any *.test.ts or *.test.tsx files.
func hasTestFiles(dir string) bool {
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
		name := d.Name()
		if strings.HasSuffix(name, ".test.ts") || strings.HasSuffix(name, ".test.tsx") {
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
