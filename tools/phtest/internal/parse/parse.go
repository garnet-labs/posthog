package parse

import (
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/posthog/posthog/phtest/internal/discover"
)

type TestResult struct {
	Passed   int           `json:"passed"`
	Failed   int           `json:"failed"`
	Skipped  int           `json:"skipped"`
	Errors   int           `json:"errors"`
	Duration time.Duration `json:"duration_ms"`
}

func (r *TestResult) IsPass() bool {
	return r.Failed == 0 && r.Errors == 0
}

// Parse extracts test results from the output lines based on the test category.
func Parse(category discover.Category, lines []string) *TestResult {
	// Only scan the last 30 lines for summary
	tail := lines
	if len(tail) > 30 {
		tail = tail[len(tail)-30:]
	}

	switch category {
	case discover.CategoryBackend:
		return parsePytest(tail)
	case discover.CategoryFrontend:
		return parseJest(tail)
	case discover.CategoryRust:
		return parseCargo(tail)
	case discover.CategoryGo:
		return parseGoTest(tail)
	case discover.CategoryE2E:
		return parsePlaywright(tail)
	default:
		return nil
	}
}

// ── pytest ──────────────────────────────────────────────────────────────────────
// ===== 5 passed, 2 failed in 3.21s =====

var (
	pytestCountRe = regexp.MustCompile(`(\d+)\s+(passed|failed|skipped|errors?|warnings?|deselected)`)
	pytestTimeRe  = regexp.MustCompile(`in\s+([\d.]+)s`)
)

func parsePytest(lines []string) *TestResult {
	// Scan from the bottom for any line containing pytest result counts
	for i := len(lines) - 1; i >= 0; i-- {
		line := lines[i]
		counts := pytestCountRe.FindAllStringSubmatch(line, -1)
		if len(counts) == 0 {
			continue
		}
		// Must contain at least one of passed/failed/error to be a summary line
		isSummary := false
		for _, cm := range counts {
			if cm[2] == "passed" || cm[2] == "failed" || strings.HasPrefix(cm[2], "error") {
				isSummary = true
				break
			}
		}
		if !isSummary {
			continue
		}
		r := &TestResult{}
		for _, cm := range counts {
			n, _ := strconv.Atoi(cm[1])
			switch {
			case cm[2] == "passed":
				r.Passed = n
			case cm[2] == "failed":
				r.Failed = n
			case cm[2] == "skipped":
				r.Skipped = n
			case strings.HasPrefix(cm[2], "error"):
				r.Errors = n
			}
		}
		if tm := pytestTimeRe.FindStringSubmatch(line); tm != nil {
			if secs, err := strconv.ParseFloat(tm[1], 64); err == nil {
				r.Duration = time.Duration(secs * float64(time.Second))
			}
		}
		return r
	}
	return nil
}

// ── jest ────────────────────────────────────────────────────────────────────────
// Tests:       2 failed, 1 skipped, 40 passed, 43 total
// Time:        4.123 s

var (
	jestTestsRe = regexp.MustCompile(`Tests:\s+(.+)`)
	jestCountRe = regexp.MustCompile(`(\d+)\s+(failed|skipped|passed|todo)`)
	jestTimeRe  = regexp.MustCompile(`Time:\s+([\d.]+)\s*s`)
)

func parseJest(lines []string) *TestResult {
	r := &TestResult{}
	found := false
	for i := len(lines) - 1; i >= 0; i-- {
		if tm := jestTimeRe.FindStringSubmatch(lines[i]); tm != nil {
			if secs, err := strconv.ParseFloat(tm[1], 64); err == nil {
				r.Duration = time.Duration(secs * float64(time.Second))
			}
		}
		if m := jestTestsRe.FindStringSubmatch(lines[i]); m != nil {
			for _, cm := range jestCountRe.FindAllStringSubmatch(m[1], -1) {
				n, _ := strconv.Atoi(cm[1])
				switch cm[2] {
				case "passed":
					r.Passed = n
				case "failed":
					r.Failed = n
				case "skipped", "todo":
					r.Skipped += n
				}
			}
			found = true
		}
	}
	if !found {
		return nil
	}
	return r
}

// ── cargo test ──────────────────────────────────────────────────────────────────
// test result: ok. 15 passed; 0 failed; 2 ignored; 0 measured; 0 filtered out; finished in 1.23s

var cargoResultRe = regexp.MustCompile(
	`test result:.*?(\d+) passed.*?(\d+) failed.*?(\d+) ignored.*?finished in ([\d.]+)s`,
)

func parseCargo(lines []string) *TestResult {
	// cargo test may print multiple "test result:" lines (one per crate). Aggregate them.
	r := &TestResult{}
	found := false
	for _, line := range lines {
		m := cargoResultRe.FindStringSubmatch(line)
		if m == nil {
			continue
		}
		found = true
		if n, err := strconv.Atoi(m[1]); err == nil {
			r.Passed += n
		}
		if n, err := strconv.Atoi(m[2]); err == nil {
			r.Failed += n
		}
		if n, err := strconv.Atoi(m[3]); err == nil {
			r.Skipped += n
		}
		if secs, err := strconv.ParseFloat(m[4], 64); err == nil {
			r.Duration += time.Duration(secs * float64(time.Second))
		}
	}
	if !found {
		return nil
	}
	return r
}

// ── playwright ──────────────────────────────────────────────────────────────────
//   42 passed (1.5m)
//   2 failed
//   3 skipped

var (
	playwrightCountRe = regexp.MustCompile(`(\d+)\s+(passed|failed|skipped)`)
	playwrightTimeRe  = regexp.MustCompile(`\(([\d.]+)([ms]+)\)`)
)

// ── go test ─────────────────────────────────────────────────────────────────────
// --- PASS: TestFoo (0.00s)
// --- FAIL: TestBar (0.01s)
// --- SKIP: TestBaz (0.00s)
// ok      github.com/pkg   0.123s
// FAIL    github.com/pkg   0.456s

var (
	goTestResultRe = regexp.MustCompile(`^---\s+(PASS|FAIL|SKIP):\s+\S+\s+\(([\d.]+)s\)`)
	goPkgOkRe      = regexp.MustCompile(`^ok\s+\S+\s+([\d.]+)s`)
	goPkgFailRe    = regexp.MustCompile(`^FAIL\s+\S+\s+([\d.]+)s`)
)

func parseGoTest(lines []string) *TestResult {
	r := &TestResult{}
	found := false
	for _, line := range lines {
		if m := goTestResultRe.FindStringSubmatch(line); m != nil {
			found = true
			switch m[1] {
			case "PASS":
				r.Passed++
			case "FAIL":
				r.Failed++
			case "SKIP":
				r.Skipped++
			}
		}
		// Accumulate duration from package summary lines
		if m := goPkgOkRe.FindStringSubmatch(line); m != nil {
			found = true
			if secs, err := strconv.ParseFloat(m[1], 64); err == nil {
				r.Duration += time.Duration(secs * float64(time.Second))
			}
		}
		if m := goPkgFailRe.FindStringSubmatch(line); m != nil {
			found = true
			if secs, err := strconv.ParseFloat(m[1], 64); err == nil {
				r.Duration += time.Duration(secs * float64(time.Second))
			}
		}
	}
	if !found {
		return nil
	}
	return r
}

func parsePlaywright(lines []string) *TestResult {
	r := &TestResult{}
	found := false
	for _, line := range lines {
		for _, cm := range playwrightCountRe.FindAllStringSubmatch(line, -1) {
			n, _ := strconv.Atoi(cm[1])
			switch cm[2] {
			case "passed":
				r.Passed = n
			case "failed":
				r.Failed = n
			case "skipped":
				r.Skipped = n
			}
			found = true
		}
		if tm := playwrightTimeRe.FindStringSubmatch(line); tm != nil {
			val, _ := strconv.ParseFloat(tm[1], 64)
			switch tm[2] {
			case "s":
				r.Duration = time.Duration(val * float64(time.Second))
			case "m":
				r.Duration = time.Duration(val * float64(time.Minute))
			case "ms":
				r.Duration = time.Duration(val * float64(time.Millisecond))
			}
		}
	}
	if !found {
		return nil
	}
	return r
}
