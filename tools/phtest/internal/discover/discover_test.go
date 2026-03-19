package discover

import (
	"os"
	"path/filepath"
	"testing"
)

func repoRoot(t *testing.T) string {
	t.Helper()
	// Walk up from this test file to find the repo root
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

	if cats[CategoryBackend] == 0 {
		t.Error("expected backend suites")
	}
	if cats[CategoryRust] == 0 {
		t.Error("expected rust suites")
	}
	if cats[CategoryE2E] == 0 {
		t.Error("expected E2E suite")
	}
}

func TestDiscover_backendSkipsNoTests(t *testing.T) {
	root := repoRoot(t)
	suites, err := discoverBackend(root)
	if err != nil {
		t.Fatal(err)
	}
	for _, s := range suites {
		if s.Name == "product_analytics" || s.Name == "managed_migrations" {
			t.Errorf("should not include %q (has echo stub)", s.Name)
		}
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
	// Check a known crate exists
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
