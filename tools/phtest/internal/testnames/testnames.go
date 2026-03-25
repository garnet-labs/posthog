package testnames

import (
	"os"
	"regexp"
	"strings"
)

type TestEntry struct {
	Name  string
	Depth int // 0 = top-level (class/describe), 1 = test case
}

// Extract reads a test file and returns the test entries found in it.
// It picks the parser based on file extension.
func Extract(filePath string) []TestEntry {
	data, err := os.ReadFile(filePath)
	if err != nil {
		return nil
	}
	lines := strings.Split(string(data), "\n")

	switch {
	case strings.HasSuffix(filePath, ".py"):
		return extractPython(lines)
	case strings.HasSuffix(filePath, ".test.ts"), strings.HasSuffix(filePath, ".test.tsx"):
		return extractJest(lines)
	case strings.HasSuffix(filePath, ".spec.ts"):
		return extractPlaywright(lines)
	case strings.HasSuffix(filePath, "_test.go"):
		return extractGo(lines)
	case strings.HasSuffix(filePath, ".rs"):
		return extractRust(lines)
	default:
		return nil
	}
}

// ── Python ──────────────────────────────────────────────────────────────────────

var (
	pyClassRe  = regexp.MustCompile(`^class\s+(Test\w+)`)
	pyMethodRe = regexp.MustCompile(`^\s+def\s+(test_\w+)`)
)

func extractPython(lines []string) []TestEntry {
	var entries []TestEntry
	for _, line := range lines {
		if m := pyClassRe.FindStringSubmatch(line); m != nil {
			entries = append(entries, TestEntry{Name: m[1], Depth: 0})
		} else if m := pyMethodRe.FindStringSubmatch(line); m != nil {
			entries = append(entries, TestEntry{Name: m[1], Depth: 1})
		}
	}
	return entries
}

// ── Jest (TypeScript) ───────────────────────────────────────────────────────────

var (
	jestDescribeRe = regexp.MustCompile("^\\s*describe\\s*\\(\\s*['\"`]([^'\"`]+)['\"`]")
	jestTestRe     = regexp.MustCompile("^\\s*(?:it|test)\\s*\\(\\s*['\"`]([^'\"`]+)['\"`]")
)

func extractJest(lines []string) []TestEntry {
	var entries []TestEntry
	for _, line := range lines {
		if m := jestDescribeRe.FindStringSubmatch(line); m != nil {
			entries = append(entries, TestEntry{Name: m[1], Depth: 0})
		} else if m := jestTestRe.FindStringSubmatch(line); m != nil {
			entries = append(entries, TestEntry{Name: m[1], Depth: 1})
		}
	}
	return entries
}

// ── Playwright ──────────────────────────────────────────────────────────────────

var (
	pwDescribeRe = regexp.MustCompile("^\\s*test\\.describe\\s*\\(\\s*['\"`]([^'\"`]+)['\"`]")
	pwTestRe     = regexp.MustCompile("^\\s*test\\s*\\(\\s*['\"`]([^'\"`]+)['\"`]")
)

func extractPlaywright(lines []string) []TestEntry {
	var entries []TestEntry
	for _, line := range lines {
		if m := pwDescribeRe.FindStringSubmatch(line); m != nil {
			entries = append(entries, TestEntry{Name: m[1], Depth: 0})
		} else if m := pwTestRe.FindStringSubmatch(line); m != nil {
			entries = append(entries, TestEntry{Name: m[1], Depth: 1})
		}
	}
	return entries
}

// ── Go ──────────────────────────────────────────────────────────────────────────

var (
	goFuncRe = regexp.MustCompile(`^func\s+(Test\w+)\s*\(`)
	goRunRe  = regexp.MustCompile(`t\.Run\s*\(\s*["']([^"']+)["']`)
)

func extractGo(lines []string) []TestEntry {
	var entries []TestEntry
	for _, line := range lines {
		if m := goFuncRe.FindStringSubmatch(line); m != nil {
			entries = append(entries, TestEntry{Name: m[1], Depth: 0})
		} else if m := goRunRe.FindStringSubmatch(line); m != nil {
			entries = append(entries, TestEntry{Name: m[1], Depth: 1})
		}
	}
	return entries
}

// ── Rust ────────────────────────────────────────────────────────────────────────

var (
	rustTestAttrRe = regexp.MustCompile(`#\[(?:tokio::)?test`)
	rustFnRe       = regexp.MustCompile(`(?:async\s+)?fn\s+(\w+)\s*\(`)
)

func extractRust(lines []string) []TestEntry {
	var entries []TestEntry
	sawAttr := false
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if rustTestAttrRe.MatchString(trimmed) {
			sawAttr = true
			continue
		}
		if sawAttr {
			if m := rustFnRe.FindStringSubmatch(trimmed); m != nil {
				entries = append(entries, TestEntry{Name: m[1], Depth: 0})
			}
			sawAttr = false
		}
	}
	return entries
}
