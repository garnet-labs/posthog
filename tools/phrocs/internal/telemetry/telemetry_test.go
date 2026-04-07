package telemetry

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"
)

// writeConfig creates a hogli_telemetry.json under a temp HOME dir and
// points the HOME env var at it so loadConfig() picks it up.
func writeConfig(t *testing.T, cfg configFile) {
	t.Helper()
	tmp := t.TempDir()
	t.Setenv("HOME", tmp)
	dir := filepath.Join(tmp, ".config", "posthog")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	data, err := json.Marshal(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "hogli_telemetry.json"), data, 0o644); err != nil {
		t.Fatal(err)
	}
}

func boolPtr(b bool) *bool { return &b }

// enabledConfig returns a configFile with telemetry fully enabled.
func enabledConfig() configFile {
	return configFile{
		Enabled:             boolPtr(true),
		AnonymousID:         "test-anon-id",
		FirstRunNoticeShown: true,
	}
}

// clearPending drains accumulated stats so tests don't leak between each other.
func clearPending(t *testing.T) {
	t.Helper()
	mu.Lock()
	pending = nil
	mu.Unlock()
}

func TestLoadConfig_missingFile(t *testing.T) {
	t.Setenv("HOME", t.TempDir())
	cfg := loadConfig()
	if cfg.AnonymousID != "" {
		t.Errorf("expected empty anonymous_id, got %q", cfg.AnonymousID)
	}
	if cfg.Enabled != nil {
		t.Errorf("expected nil Enabled, got %v", *cfg.Enabled)
	}
}

func TestLoadConfig_validFile(t *testing.T) {
	writeConfig(t, configFile{
		Enabled:             boolPtr(true),
		AnonymousID:         "abc-123",
		FirstRunNoticeShown: true,
	})

	cfg := loadConfig()
	if cfg.AnonymousID != "abc-123" {
		t.Errorf("AnonymousID: got %q, want %q", cfg.AnonymousID, "abc-123")
	}
	if cfg.Enabled == nil || !*cfg.Enabled {
		t.Error("Enabled: expected true")
	}
	if !cfg.FirstRunNoticeShown {
		t.Error("FirstRunNoticeShown: expected true")
	}
}

func TestIsEnabled_defaultsTrue(t *testing.T) {
	t.Setenv("CI", "")
	t.Setenv("POSTHOG_TELEMETRY_OPT_OUT", "")
	t.Setenv("DO_NOT_TRACK", "")
	writeConfig(t, configFile{FirstRunNoticeShown: true})

	if !isEnabled() {
		t.Error("expected enabled by default when first run notice shown")
	}
}

func TestIsEnabled_CIDisables(t *testing.T) {
	t.Setenv("CI", "true")
	writeConfig(t, enabledConfig())

	if isEnabled() {
		t.Error("expected disabled when CI is set")
	}
}

func TestIsEnabled_optOutEnvDisables(t *testing.T) {
	t.Setenv("CI", "")
	t.Setenv("POSTHOG_TELEMETRY_OPT_OUT", "1")
	writeConfig(t, enabledConfig())

	if isEnabled() {
		t.Error("expected disabled when POSTHOG_TELEMETRY_OPT_OUT=1")
	}
}

func TestIsEnabled_doNotTrackDisables(t *testing.T) {
	t.Setenv("CI", "")
	t.Setenv("POSTHOG_TELEMETRY_OPT_OUT", "")
	t.Setenv("DO_NOT_TRACK", "1")
	writeConfig(t, enabledConfig())

	if isEnabled() {
		t.Error("expected disabled when DO_NOT_TRACK=1")
	}
}

func TestIsEnabled_configDisables(t *testing.T) {
	t.Setenv("CI", "")
	t.Setenv("POSTHOG_TELEMETRY_OPT_OUT", "")
	t.Setenv("DO_NOT_TRACK", "")
	writeConfig(t, configFile{
		Enabled:             boolPtr(false),
		AnonymousID:         "id",
		FirstRunNoticeShown: true,
	})

	if isEnabled() {
		t.Error("expected disabled when config enabled=false")
	}
}

func TestIsEnabled_noFirstRunNotice(t *testing.T) {
	t.Setenv("CI", "")
	t.Setenv("POSTHOG_TELEMETRY_OPT_OUT", "")
	t.Setenv("DO_NOT_TRACK", "")
	writeConfig(t, configFile{
		Enabled:             boolPtr(true),
		AnonymousID:         "id",
		FirstRunNoticeShown: false,
	})

	if isEnabled() {
		t.Error("expected disabled when first_run_notice_shown is false")
	}
}

func TestFlush_sendsCorrectPayload(t *testing.T) {
	clearPending(t)

	var received atomic.Value

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		received.Store(body)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	t.Setenv("CI", "")
	t.Setenv("POSTHOG_TELEMETRY_OPT_OUT", "")
	t.Setenv("DO_NOT_TRACK", "")
	t.Setenv("POSTHOG_TELEMETRY_HOST", srv.URL)
	writeConfig(t, enabledConfig())

	exitCode := 0
	TrackProcessCompleted(ProcessStats{
		Name:       "web",
		Status:     "done",
		ExitCode:   &exitCode,
		DurationS:  42.5,
		PeakMemMB:  512.3,
		PeakCPUPct: 95.2,
		CPUTimeS:   30.1,
	})

	Flush(2 * time.Second)

	raw, ok := received.Load().([]byte)
	if !ok || raw == nil {
		t.Fatal("server did not receive a request")
	}

	var payload struct {
		APIKey string `json:"api_key"`
		Batch  []struct {
			Event      string         `json:"event"`
			DistinctID string         `json:"distinct_id"`
			Timestamp  string         `json:"timestamp"`
			Properties map[string]any `json:"properties"`
		} `json:"batch"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}

	if payload.APIKey != apiKey {
		t.Errorf("api_key: got %q, want %q", payload.APIKey, apiKey)
	}
	if len(payload.Batch) != 1 {
		t.Fatalf("batch length: got %d, want 1", len(payload.Batch))
	}

	ev := payload.Batch[0]
	if ev.Event != "phrocs_process_completed" {
		t.Errorf("event: got %q, want %q", ev.Event, "phrocs_process_completed")
	}
	if ev.DistinctID != "test-anon-id" {
		t.Errorf("distinct_id: got %q, want %q", ev.DistinctID, "test-anon-id")
	}
	if ev.Timestamp == "" {
		t.Error("timestamp: expected non-empty")
	}

	props := ev.Properties
	if props["process_name"] != "web" {
		t.Errorf("process_name: got %v, want %q", props["process_name"], "web")
	}
	if props["status"] != "done" {
		t.Errorf("status: got %v, want %q", props["status"], "done")
	}
	if props["duration_s"] != 42.5 {
		t.Errorf("duration_s: got %v, want 42.5", props["duration_s"])
	}
	if props["peak_mem_rss_mb"] != 512.3 {
		t.Errorf("peak_mem_rss_mb: got %v, want 512.3", props["peak_mem_rss_mb"])
	}
	if props["peak_cpu_percent"] != 95.2 {
		t.Errorf("peak_cpu_percent: got %v, want 95.2", props["peak_cpu_percent"])
	}
	if props["cpu_time_s"] != 30.1 {
		t.Errorf("cpu_time_s: got %v, want 30.1", props["cpu_time_s"])
	}
	// JSON numbers decode as float64
	if props["exit_code"] != float64(0) {
		t.Errorf("exit_code: got %v, want 0", props["exit_code"])
	}

	groups, ok := props["$groups"].(map[string]any)
	if !ok || groups["project"] != "hogli" {
		t.Errorf("$groups: got %v, want {project: hogli}", props["$groups"])
	}
}

func TestFlush_batchesMultipleEvents(t *testing.T) {
	clearPending(t)

	var received atomic.Value

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		received.Store(body)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	t.Setenv("CI", "")
	t.Setenv("POSTHOG_TELEMETRY_OPT_OUT", "")
	t.Setenv("DO_NOT_TRACK", "")
	t.Setenv("POSTHOG_TELEMETRY_HOST", srv.URL)
	writeConfig(t, enabledConfig())

	TrackProcessCompleted(ProcessStats{Name: "web", Status: "done", DurationS: 10})
	TrackProcessCompleted(ProcessStats{Name: "worker", Status: "crashed", DurationS: 5})
	TrackProcessCompleted(ProcessStats{Name: "plugin-server", Status: "done", DurationS: 20})

	Flush(2 * time.Second)

	raw, ok := received.Load().([]byte)
	if !ok || raw == nil {
		t.Fatal("server did not receive a request")
	}

	var payload struct {
		Batch []struct {
			Properties map[string]any `json:"properties"`
		} `json:"batch"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}

	if len(payload.Batch) != 3 {
		t.Fatalf("batch length: got %d, want 3", len(payload.Batch))
	}

	names := []string{"web", "worker", "plugin-server"}
	for i, ev := range payload.Batch {
		if ev.Properties["process_name"] != names[i] {
			t.Errorf("batch[%d] process_name: got %v, want %q", i, ev.Properties["process_name"], names[i])
		}
	}
}

func TestFlush_nilExitCodeOmitted(t *testing.T) {
	clearPending(t)

	var received atomic.Value

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		received.Store(body)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	t.Setenv("CI", "")
	t.Setenv("POSTHOG_TELEMETRY_OPT_OUT", "")
	t.Setenv("DO_NOT_TRACK", "")
	t.Setenv("POSTHOG_TELEMETRY_HOST", srv.URL)
	writeConfig(t, enabledConfig())

	TrackProcessCompleted(ProcessStats{
		Name:   "worker",
		Status: "crashed",
	})
	Flush(2 * time.Second)

	raw, ok := received.Load().([]byte)
	if !ok || raw == nil {
		t.Fatal("server did not receive a request")
	}

	var payload struct {
		Batch []struct {
			Properties map[string]any `json:"properties"`
		} `json:"batch"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}

	if _, exists := payload.Batch[0].Properties["exit_code"]; exists {
		t.Error("exit_code should not be present when ExitCode is nil")
	}
}

func TestFlush_disabledNoRequest(t *testing.T) {
	clearPending(t)

	var called atomic.Int32

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called.Add(1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	t.Setenv("CI", "")
	t.Setenv("POSTHOG_TELEMETRY_OPT_OUT", "1")
	t.Setenv("POSTHOG_TELEMETRY_HOST", srv.URL)
	writeConfig(t, enabledConfig())

	TrackProcessCompleted(ProcessStats{Name: "web", Status: "done"})
	Flush(500 * time.Millisecond)

	if called.Load() != 0 {
		t.Error("expected no HTTP request when telemetry is disabled")
	}
}

func TestFlush_noAnonymousID(t *testing.T) {
	clearPending(t)

	var called atomic.Int32

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called.Add(1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	t.Setenv("CI", "")
	t.Setenv("POSTHOG_TELEMETRY_OPT_OUT", "")
	t.Setenv("DO_NOT_TRACK", "")
	t.Setenv("POSTHOG_TELEMETRY_HOST", srv.URL)
	writeConfig(t, configFile{
		Enabled:             boolPtr(true),
		FirstRunNoticeShown: true,
		// AnonymousID intentionally empty
	})

	TrackProcessCompleted(ProcessStats{Name: "web", Status: "done"})
	Flush(500 * time.Millisecond)

	if called.Load() != 0 {
		t.Error("expected no HTTP request when anonymous_id is empty")
	}
}

func TestFlush_respectsTimeout(t *testing.T) {
	clearPending(t)

	unblock := make(chan struct{})

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-unblock
	}))

	t.Setenv("CI", "")
	t.Setenv("POSTHOG_TELEMETRY_OPT_OUT", "")
	t.Setenv("DO_NOT_TRACK", "")
	t.Setenv("POSTHOG_TELEMETRY_HOST", srv.URL)
	writeConfig(t, enabledConfig())

	TrackProcessCompleted(ProcessStats{Name: "web", Status: "done"})

	start := time.Now()
	Flush(200 * time.Millisecond)
	elapsed := time.Since(start)

	// Unblock the handler so srv.Close() can complete
	close(unblock)
	srv.Close()

	if elapsed > 1*time.Second {
		t.Errorf("Flush took %v, expected it to respect the 200ms timeout", elapsed)
	}
}

func TestFlush_noPendingNoRequest(t *testing.T) {
	clearPending(t)

	var called atomic.Int32

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called.Add(1)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	t.Setenv("CI", "")
	t.Setenv("POSTHOG_TELEMETRY_OPT_OUT", "")
	t.Setenv("DO_NOT_TRACK", "")
	t.Setenv("POSTHOG_TELEMETRY_HOST", srv.URL)
	writeConfig(t, enabledConfig())

	Flush(500 * time.Millisecond)

	if called.Load() != 0 {
		t.Error("expected no HTTP request when no events are pending")
	}
}

func TestHost_defaultAndOverride(t *testing.T) {
	t.Setenv("POSTHOG_TELEMETRY_HOST", "")
	if got := host(); got != defaultHost {
		t.Errorf("default host: got %q, want %q", got, defaultHost)
	}

	t.Setenv("POSTHOG_TELEMETRY_HOST", "https://custom.example.com")
	if got := host(); got != "https://custom.example.com" {
		t.Errorf("override host: got %q, want %q", got, "https://custom.example.com")
	}
}
