package parse

import (
	"testing"
	"time"

	"github.com/posthog/posthog/phtest/internal/discover"
)

func TestParsePytest_passed(t *testing.T) {
	lines := []string{
		"collecting ...",
		"test_foo.py::test_one PASSED",
		"test_foo.py::test_two PASSED",
		"========================= 2 passed in 1.23s =========================",
	}
	r := Parse(discover.CategoryBackend, lines)
	if r == nil {
		t.Fatal("expected result")
	}
	if r.Passed != 2 {
		t.Errorf("Passed: got %d, want 2", r.Passed)
	}
	if r.Failed != 0 {
		t.Errorf("Failed: got %d, want 0", r.Failed)
	}
	if !r.IsPass() {
		t.Error("expected IsPass() == true")
	}
}

func TestParsePytest_mixed(t *testing.T) {
	lines := []string{
		"================= 3 passed, 2 failed, 1 skipped in 4.50s ==================",
	}
	r := Parse(discover.CategoryBackend, lines)
	if r == nil {
		t.Fatal("expected result")
	}
	if r.Passed != 3 || r.Failed != 2 || r.Skipped != 1 {
		t.Errorf("got passed=%d failed=%d skipped=%d", r.Passed, r.Failed, r.Skipped)
	}
	if r.IsPass() {
		t.Error("expected IsPass() == false")
	}
}

func TestParsePytest_errors(t *testing.T) {
	lines := []string{
		"========================= 2 failed, 1 error in 2.30s ====================",
	}
	r := Parse(discover.CategoryBackend, lines)
	if r == nil {
		t.Fatal("expected result")
	}
	if r.Failed != 2 || r.Errors != 1 {
		t.Errorf("got failed=%d errors=%d", r.Failed, r.Errors)
	}
}

func TestParsePytest_bareFormat(t *testing.T) {
	lines := []string{
		"FAILED ee/api/test/test_billing.py::TestBillingAPI::test_something",
		"!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!",
		"1 failed, 416 passed in 63.97s (0:01:03)",
	}
	r := Parse(discover.CategoryBackend, lines)
	if r == nil {
		t.Fatal("expected result")
	}
	if r.Passed != 416 || r.Failed != 1 {
		t.Errorf("got passed=%d failed=%d, want 416/1", r.Passed, r.Failed)
	}
}

func TestParsePytest_noSummary(t *testing.T) {
	lines := []string{"some random output", "no summary here"}
	r := Parse(discover.CategoryBackend, lines)
	if r != nil {
		t.Error("expected nil for no summary")
	}
}

func TestParseJest_passed(t *testing.T) {
	lines := []string{
		"Test Suites: 3 passed, 3 total",
		"Tests:       40 passed, 40 total",
		"Snapshots:   0 total",
		"Time:        4.123 s",
	}
	r := Parse(discover.CategoryFrontend, lines)
	if r == nil {
		t.Fatal("expected result")
	}
	if r.Passed != 40 {
		t.Errorf("Passed: got %d, want 40", r.Passed)
	}
	if r.Duration != time.Duration(4.123*float64(time.Second)) {
		t.Errorf("Duration: got %v", r.Duration)
	}
}

func TestParseJest_mixed(t *testing.T) {
	lines := []string{
		"Tests:       2 failed, 1 skipped, 38 passed, 41 total",
		"Time:        5.0 s",
	}
	r := Parse(discover.CategoryFrontend, lines)
	if r == nil {
		t.Fatal("expected result")
	}
	if r.Passed != 38 || r.Failed != 2 || r.Skipped != 1 {
		t.Errorf("got passed=%d failed=%d skipped=%d", r.Passed, r.Failed, r.Skipped)
	}
}

func TestParseGoTest_passed(t *testing.T) {
	lines := []string{
		"=== RUN   TestFoo",
		"--- PASS: TestFoo (0.00s)",
		"=== RUN   TestBar",
		"--- PASS: TestBar (0.01s)",
		"PASS",
		"ok  	github.com/posthog/posthog/livestream/auth	0.123s",
	}
	r := Parse(discover.CategoryGo, lines)
	if r == nil {
		t.Fatal("expected result")
	}
	if r.Passed != 2 {
		t.Errorf("Passed: got %d, want 2", r.Passed)
	}
	if r.Failed != 0 {
		t.Errorf("Failed: got %d, want 0", r.Failed)
	}
	if !r.IsPass() {
		t.Error("expected IsPass() == true")
	}
}

func TestParseGoTest_mixed(t *testing.T) {
	lines := []string{
		"--- PASS: TestFoo (0.00s)",
		"--- FAIL: TestBar (0.01s)",
		"--- SKIP: TestBaz (0.00s)",
		"FAIL",
		"FAIL	github.com/posthog/posthog/livestream/events	0.456s",
	}
	r := Parse(discover.CategoryGo, lines)
	if r == nil {
		t.Fatal("expected result")
	}
	if r.Passed != 1 || r.Failed != 1 || r.Skipped != 1 {
		t.Errorf("got passed=%d failed=%d skipped=%d", r.Passed, r.Failed, r.Skipped)
	}
	if r.IsPass() {
		t.Error("expected IsPass() == false")
	}
}

func TestParseGoTest_multiplePackages(t *testing.T) {
	lines := []string{
		"--- PASS: TestA (0.00s)",
		"ok  	github.com/posthog/posthog/livestream/auth	0.100s",
		"--- PASS: TestB (0.00s)",
		"--- PASS: TestC (0.00s)",
		"--- FAIL: TestD (0.01s)",
		"FAIL	github.com/posthog/posthog/livestream/events	0.200s",
	}
	r := Parse(discover.CategoryGo, lines)
	if r == nil {
		t.Fatal("expected result")
	}
	if r.Passed != 3 || r.Failed != 1 {
		t.Errorf("got passed=%d failed=%d", r.Passed, r.Failed)
	}
	// Duration should aggregate both package times
	expectedDuration := time.Duration(0.3 * float64(time.Second))
	if r.Duration != expectedDuration {
		t.Errorf("Duration: got %v, want %v", r.Duration, expectedDuration)
	}
}

func TestParseGoTest_noOutput(t *testing.T) {
	lines := []string{"some random output", "no test results"}
	r := Parse(discover.CategoryGo, lines)
	if r != nil {
		t.Error("expected nil for no test output")
	}
}

func TestParseCargo_single(t *testing.T) {
	lines := []string{
		"running 15 tests",
		"test result: ok. 13 passed; 0 failed; 2 ignored; 0 measured; 0 filtered out; finished in 1.23s",
	}
	r := Parse(discover.CategoryRust, lines)
	if r == nil {
		t.Fatal("expected result")
	}
	if r.Passed != 13 || r.Failed != 0 || r.Skipped != 2 {
		t.Errorf("got passed=%d failed=%d skipped=%d", r.Passed, r.Failed, r.Skipped)
	}
}

func TestParseCargo_multiple(t *testing.T) {
	lines := []string{
		"test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.50s",
		"test result: ok. 10 passed; 1 failed; 1 ignored; 0 measured; 0 filtered out; finished in 2.00s",
	}
	r := Parse(discover.CategoryRust, lines)
	if r == nil {
		t.Fatal("expected result")
	}
	if r.Passed != 15 || r.Failed != 1 || r.Skipped != 1 {
		t.Errorf("got passed=%d failed=%d skipped=%d", r.Passed, r.Failed, r.Skipped)
	}
}

func TestParsePlaywright_passed(t *testing.T) {
	lines := []string{
		"  42 passed (1.5m)",
	}
	r := Parse(discover.CategoryE2E, lines)
	if r == nil {
		t.Fatal("expected result")
	}
	if r.Passed != 42 {
		t.Errorf("Passed: got %d, want 42", r.Passed)
	}
}

func TestParsePlaywright_mixed(t *testing.T) {
	lines := []string{
		"  40 passed (2m)",
		"  2 failed",
		"  3 skipped",
	}
	r := Parse(discover.CategoryE2E, lines)
	if r == nil {
		t.Fatal("expected result")
	}
	if r.Passed != 40 || r.Failed != 2 || r.Skipped != 3 {
		t.Errorf("got passed=%d failed=%d skipped=%d", r.Passed, r.Failed, r.Skipped)
	}
}
