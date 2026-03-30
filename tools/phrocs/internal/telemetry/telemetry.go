// Package telemetry sends anonymous process-level analytics to PostHog.
//
// It shares the same config file and opt-out conventions as the hogli
// Python telemetry (~/.config/posthog/hogli_telemetry.json), so a user
// who opts out of hogli telemetry automatically opts out of phrocs too.
package telemetry

import (
	"bytes"
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// Same write-only project token used by hogli.
const apiKey = "phc_JYFXrbqdzueOYb0wFUTnCglFKZuC4xRXBW790ewdcvn"
const defaultHost = "https://us.i.posthog.com"

var (
	httpClient = &http.Client{Timeout: 5 * time.Second}
	inflight   sync.WaitGroup
)

// configFile mirrors the relevant fields from hogli_telemetry.json.
type configFile struct {
	Enabled             *bool  `json:"enabled,omitempty"`
	AnonymousID         string `json:"anonymous_id,omitempty"`
	FirstRunNoticeShown bool   `json:"first_run_notice_shown,omitempty"`
}

func loadConfig() configFile {
	home, err := os.UserHomeDir()
	if err != nil {
		return configFile{}
	}
	data, err := os.ReadFile(filepath.Join(home, ".config", "posthog", "hogli_telemetry.json"))
	if err != nil {
		return configFile{}
	}
	var cfg configFile
	_ = json.Unmarshal(data, &cfg)
	return cfg
}

func isEnabled() bool {
	if os.Getenv("CI") != "" {
		return false
	}
	if os.Getenv("POSTHOG_TELEMETRY_OPT_OUT") == "1" {
		return false
	}
	if os.Getenv("DO_NOT_TRACK") == "1" {
		return false
	}
	cfg := loadConfig()
	if !cfg.FirstRunNoticeShown {
		return false
	}
	if cfg.Enabled != nil {
		return *cfg.Enabled
	}
	return true
}

func host() string {
	if h := os.Getenv("POSTHOG_TELEMETRY_HOST"); h != "" {
		return h
	}
	return defaultHost
}

// ProcessStats are the metrics captured at process exit.
type ProcessStats struct {
	Name       string
	Status     string
	ExitCode   *int
	DurationS  float64
	PeakMemMB  float64
	PeakCPUPct float64
	CPUTimeS   float64
}

// TrackProcessCompleted queues a fire-and-forget POST with the process's
// peak resource usage. Safe to call from any goroutine.
func TrackProcessCompleted(stats ProcessStats) {
	if !isEnabled() {
		return
	}
	cfg := loadConfig()
	if cfg.AnonymousID == "" {
		return
	}

	props := map[string]any{
		"$process_person_profile": false,
		"$groups":                 map[string]string{"project": "hogli"},
		"process_name":            stats.Name,
		"status":                  stats.Status,
		"duration_s":              stats.DurationS,
		"peak_mem_rss_mb":         stats.PeakMemMB,
		"peak_cpu_percent":        stats.PeakCPUPct,
		"cpu_time_s":              stats.CPUTimeS,
	}
	if stats.ExitCode != nil {
		props["exit_code"] = *stats.ExitCode
	}

	event := map[string]any{
		"event":       "phrocs_process_completed",
		"distinct_id": cfg.AnonymousID,
		"properties":  props,
		"timestamp":   time.Now().UTC().Format(time.RFC3339Nano),
	}

	body := map[string]any{
		"api_key": apiKey,
		"batch":   []any{event},
	}

	data, err := json.Marshal(body)
	if err != nil {
		return
	}

	inflight.Add(1)
	go func() {
		defer inflight.Done()
		url := host() + "/batch/"
		resp, err := httpClient.Post(url, "application/json", bytes.NewReader(data))
		if err == nil {
			_ = resp.Body.Close()
		}
	}()
}

// Flush blocks until all in-flight telemetry POSTs complete or timeout
// elapses. Call before phrocs exits.
func Flush(timeout time.Duration) {
	done := make(chan struct{})
	go func() {
		inflight.Wait()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(timeout):
	}
}
