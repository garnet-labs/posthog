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

	for _, cat := range []Category{CategoryBackend, CategoryFrontend, CategoryRust, CategoryGo, CategoryE2E} {
		if cats[cat] == 0 {
			t.Errorf("expected suites for category %q", cat)
		}
	}
}

func TestDiscover_sortedByRelPath(t *testing.T) {
	root := repoRoot(t)
	suites, err := Discover(root)
	if err != nil {
		t.Fatal(err)
	}
	for i := 1; i < len(suites); i++ {
		if suites[i].RelPath < suites[i-1].RelPath {
			t.Errorf("suites not sorted: %q before %q", suites[i-1].RelPath, suites[i].RelPath)
			break
		}
	}
}

func TestDiscover_backendFindsTestFiles(t *testing.T) {
	root := repoRoot(t)
	ig := newIgnoreMatcher(root)
	suites, err := discoverBackend(root, ig)
	if err != nil {
		t.Fatal(err)
	}
	if len(suites) < 10 {
		t.Errorf("expected at least 10 backend test files, got %d", len(suites))
	}

	// All should be individual .py files
	for _, s := range suites {
		if !strings.HasSuffix(s.RelPath, ".py") {
			t.Errorf("expected .py RelPath, got %q", s.RelPath)
		}
		if !strings.HasPrefix(s.Cmd, "pytest ") {
			t.Errorf("expected pytest command, got %q", s.Cmd)
		}
	}

	// Should find files under products/, posthog/, and ee/
	var hasProducts, hasPosthog, hasEE bool
	for _, s := range suites {
		switch {
		case strings.HasPrefix(s.RelPath, "products/"):
			hasProducts = true
		case strings.HasPrefix(s.RelPath, "posthog/"):
			hasPosthog = true
		case strings.HasPrefix(s.RelPath, "ee/"):
			hasEE = true
		}
	}
	if !hasProducts {
		t.Error("expected test files under products/")
	}
	if !hasPosthog {
		t.Error("expected test files under posthog/")
	}
	if !hasEE {
		t.Error("expected test files under ee/")
	}
}

func TestDiscover_frontendFindsTestFiles(t *testing.T) {
	root := repoRoot(t)
	ig := newIgnoreMatcher(root)
	suites, err := discoverFrontend(root, ig)
	if err != nil {
		t.Fatal(err)
	}
	if len(suites) < 10 {
		t.Errorf("expected at least 10 frontend test files, got %d", len(suites))
	}

	for _, s := range suites {
		if !isTSTestFile(filepath.Base(s.RelPath)) {
			t.Errorf("expected .test.ts(x) RelPath, got %q", s.RelPath)
		}
	}

	// Should find files under both products/ and frontend/src/
	var hasProducts, hasFrontendSrc bool
	for _, s := range suites {
		switch {
		case strings.HasPrefix(s.RelPath, "products/"):
			hasProducts = true
		case strings.HasPrefix(s.RelPath, "frontend/src/"):
			hasFrontendSrc = true
		}
	}
	if !hasProducts {
		t.Error("expected test files under products/")
	}
	if !hasFrontendSrc {
		t.Error("expected test files under frontend/src/")
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
	for _, s := range suites {
		if !strings.HasSuffix(s.RelPath, ".spec.ts") {
			t.Errorf("expected .spec.ts RelPath, got %q", s.RelPath)
		}
	}
}

func TestDiscover_goFindsPackages(t *testing.T) {
	root := repoRoot(t)
	ig := newIgnoreMatcher(root)
	suites, err := discoverGo(root, ig)
	if err != nil {
		t.Fatal(err)
	}
	if len(suites) < 5 {
		t.Errorf("expected at least 5 Go test packages, got %d", len(suites))
	}

	// Should find packages within livestream and phrocs modules
	var hasLivestream, hasPhrocs bool
	for _, s := range suites {
		switch {
		case strings.HasPrefix(s.RelPath, "livestream"):
			hasLivestream = true
		case strings.HasPrefix(s.RelPath, "tools/phrocs"):
			hasPhrocs = true
		}
	}
	if !hasLivestream {
		t.Error("expected Go packages under livestream/")
	}
	if !hasPhrocs {
		t.Error("expected Go packages under tools/phrocs/")
	}

	// Commands should target specific packages, not ./...
	for _, s := range suites {
		if strings.Contains(s.Cmd, "./...") {
			t.Errorf("expected per-package command, got %q", s.Cmd)
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
