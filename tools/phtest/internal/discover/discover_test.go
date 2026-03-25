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
	for _, cat := range []Category{CategoryBackend, CategoryFrontend, CategoryRust, CategoryGo, CategoryPlaywright} {
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
	suites, err := Discover(root)
	if err != nil {
		t.Fatal(err)
	}

	var backend []Suite
	for _, s := range suites {
		if s.Category == CategoryBackend {
			backend = append(backend, s)
		}
	}
	if len(backend) < 10 {
		t.Errorf("expected at least 10 backend test files, got %d", len(backend))
	}
	for _, s := range backend {
		if !strings.HasSuffix(s.RelPath, ".py") {
			t.Errorf("expected .py RelPath, got %q", s.RelPath)
		}
		if !strings.HasPrefix(s.Cmd, "pytest ") {
			t.Errorf("expected pytest command, got %q", s.Cmd)
		}
	}
}

func TestDiscover_frontendFindsTestFiles(t *testing.T) {
	root := repoRoot(t)
	suites, err := Discover(root)
	if err != nil {
		t.Fatal(err)
	}

	var frontend []Suite
	for _, s := range suites {
		if s.Category == CategoryFrontend {
			frontend = append(frontend, s)
		}
	}
	if len(frontend) < 10 {
		t.Errorf("expected at least 10 frontend test files, got %d", len(frontend))
	}
	for _, s := range frontend {
		if !isTSTestFile(filepath.Base(s.RelPath)) {
			t.Errorf("expected .test.ts(x) RelPath, got %q", s.RelPath)
		}
	}
}

func TestDiscover_rustFindsPackages(t *testing.T) {
	root := repoRoot(t)
	suites, err := Discover(root)
	if err != nil {
		t.Fatal(err)
	}

	var rust []Suite
	for _, s := range suites {
		if s.Category == CategoryRust {
			rust = append(rust, s)
		}
	}
	if len(rust) < 10 {
		t.Errorf("expected at least 10 rust crates, got %d", len(rust))
	}

	found := false
	for _, s := range rust {
		if s.Name == "feature-flags" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected to find feature-flags crate")
	}
}

func TestDiscover_playwrightFindsSpecFiles(t *testing.T) {
	root := repoRoot(t)
	suites, err := Discover(root)
	if err != nil {
		t.Fatal(err)
	}

	var e2e []Suite
	for _, s := range suites {
		if s.Category == CategoryPlaywright {
			e2e = append(e2e, s)
		}
	}
	if len(e2e) < 5 {
		t.Errorf("expected at least 5 E2E spec files, got %d", len(e2e))
	}
	for _, s := range e2e {
		if !strings.HasSuffix(s.RelPath, ".spec.ts") {
			t.Errorf("expected .spec.ts RelPath, got %q", s.RelPath)
		}
	}
}

func TestDiscover_goFindsPackages(t *testing.T) {
	root := repoRoot(t)
	suites, err := Discover(root)
	if err != nil {
		t.Fatal(err)
	}

	var goSuites []Suite
	for _, s := range suites {
		if s.Category == CategoryGo {
			goSuites = append(goSuites, s)
		}
	}
	if len(goSuites) < 5 {
		t.Errorf("expected at least 5 Go test packages, got %d", len(goSuites))
	}

	var hasLivestream, hasPhrocs bool
	for _, s := range goSuites {
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
	for _, s := range goSuites {
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
