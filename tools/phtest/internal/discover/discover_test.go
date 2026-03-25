package discover

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func repoRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "products")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Skip("could not find repo root")
		}
		dir = parent
	}
}

func TestDiscover_findsAllCategories(t *testing.T) {
	root := repoRoot(t)
	suites, err := Discover(root)
	if err != nil {
		t.Fatal(err)
	}

	cats := make(map[Category]int)
	for _, s := range suites {
		cats[s.Category]++
	}

	for _, cat := range []Category{CategoryBackend, CategoryFrontend, CategoryFrontendCore, CategoryRust, CategoryGo, CategoryE2E} {
		if cats[cat] == 0 {
			t.Errorf("expected suites for category %q", cat)
		}
	}
}

func TestDiscover_backendFindsProducts(t *testing.T) {
	root := repoRoot(t)
	ig := newIgnoreMatcher(root)
	suites, err := discoverBackend(root, ig)
	if err != nil {
		t.Fatal(err)
	}

	var productSuites, coreSuites int
	for _, s := range suites {
		if s.Category == CategoryBackend {
			productSuites++
		} else {
			coreSuites++
		}
	}
	if productSuites == 0 {
		t.Error("expected backend product suites")
	}
	if coreSuites == 0 {
		t.Error("expected backend core suites (posthog/ or ee/)")
	}
}

func TestDiscover_backendUsePytest(t *testing.T) {
	root := repoRoot(t)
	ig := newIgnoreMatcher(root)
	suites, err := discoverBackend(root, ig)
	if err != nil {
		t.Fatal(err)
	}
	for _, s := range suites {
		if !strings.HasPrefix(s.Cmd, "pytest ") {
			t.Errorf("suite %q: expected pytest command, got %q", s.Name, s.Cmd)
		}
	}
}

func TestDiscover_frontendFindsProductsAndCore(t *testing.T) {
	root := repoRoot(t)
	ig := newIgnoreMatcher(root)
	suites, err := discoverFrontend(root, ig)
	if err != nil {
		t.Fatal(err)
	}

	var productSuites, coreSuites int
	for _, s := range suites {
		switch s.Category {
		case CategoryFrontend:
			productSuites++
		case CategoryFrontendCore:
			coreSuites++
		}
	}
	if productSuites == 0 {
		t.Error("expected frontend product suites")
	}
	if coreSuites == 0 {
		t.Error("expected frontend core suites (frontend/src/)")
	}
}

func TestDiscover_rustFindsPackages(t *testing.T) {
	root := repoRoot(t)
	suites, err := discoverRust(root)
	if err != nil {
		t.Fatal(err)
	}
	if len(suites) < 10 {
		t.Errorf("expected at least 10 rust crates, got %d", len(suites))
	}

	found := false
	for _, s := range suites {
		if s.Name == "feature-flags" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected to find feature-flags crate")
	}

	// common/ crates should be in a subcategory
	var commonCount int
	for _, s := range suites {
		if strings.HasPrefix(string(s.Category), "Rust / ") {
			commonCount++
		}
	}
	if commonCount == 0 {
		t.Error("expected rust subcategories for nested crates (e.g. common/)")
	}
}

func TestDiscover_e2eFindsSpecFiles(t *testing.T) {
	root := repoRoot(t)
	ig := newIgnoreMatcher(root)
	suites, err := discoverE2E(root, ig)
	if err != nil {
		t.Fatal(err)
	}
	if len(suites) < 5 {
		t.Errorf("expected at least 5 E2E spec files, got %d", len(suites))
	}

	// Should have subcategories for nested directories
	var subCatCount int
	for _, s := range suites {
		if strings.HasPrefix(string(s.Category), "E2E / ") {
			subCatCount++
		}
	}
	if subCatCount == 0 {
		t.Error("expected E2E subcategories for nested spec directories")
	}
}

func TestDiscover_goFindsModules(t *testing.T) {
	root := repoRoot(t)
	ig := newIgnoreMatcher(root)
	suites, err := discoverGo(root, ig)
	if err != nil {
		t.Fatal(err)
	}
	if len(suites) < 2 {
		t.Errorf("expected at least 2 Go modules with tests, got %d", len(suites))
	}

	names := make(map[string]bool)
	for _, s := range suites {
		names[s.Name] = true
		if s.Category != CategoryGo {
			t.Errorf("suite %q: expected category %q, got %q", s.Name, CategoryGo, s.Category)
		}
		if s.Cmd != "go test ./..." {
			t.Errorf("suite %q: expected 'go test ./...', got %q", s.Name, s.Cmd)
		}
	}
	for _, expected := range []string{"livestream", "phrocs"} {
		if !names[expected] {
			t.Errorf("expected to find Go module %q", expected)
		}
	}
}

func TestParseCargoMembers(t *testing.T) {
	content := `[workspace]
resolver = "2"

members = [
    "capture",
    "common/hogvm",
    "feature-flags",
]`
	members := parseCargoMembers(content)
	if len(members) != 3 {
		t.Fatalf("expected 3 members, got %d: %v", len(members), members)
	}
	if members[0] != "capture" || members[1] != "common/hogvm" || members[2] != "feature-flags" {
		t.Errorf("unexpected members: %v", members)
	}
}

func TestParseCargoMembers_inline(t *testing.T) {
	content := `members = ["a", "b", "c"]`
	members := parseCargoMembers(content)
	if len(members) != 3 {
		t.Fatalf("expected 3 members, got %d: %v", len(members), members)
	}
}
