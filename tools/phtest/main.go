// phtest is a TUI dashboard for running PostHog's test suites across
// backend (pytest), frontend (jest), Rust (cargo test), Go, and Playwright.
//
// Usage:
//
//	phtest [--debug] [--root <repo-root>]
//
// Flags:
//
//	--root   Path to the PostHog repo root. Auto-detected if omitted.
//	--debug  Write a debug log to /tmp/phtest-debug.log.
package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"

	tea "charm.land/bubbletea/v2"
	"github.com/posthog/posthog/phtest/internal/discover"
	"github.com/posthog/posthog/phtest/internal/runner"
	"github.com/posthog/posthog/phtest/internal/tui"
)

func main() {
	var repoRoot string
	var logger *log.Logger

	for i := 1; i < len(os.Args); i++ {
		switch os.Args[i] {
		case "--root":
			if i+1 < len(os.Args) {
				repoRoot = os.Args[i+1]
				i++
			}
		case "--debug":
			f, err := os.OpenFile("/tmp/phtest-debug.log", os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
			if err != nil {
				fmt.Fprintf(os.Stderr, "phtest: open debug log: %v\n", err)
				os.Exit(1)
			}
			logger = log.New(f, "", log.LstdFlags|log.Lmicroseconds)
			logger.Println("debug logging started")
		}
	}

	if repoRoot == "" {
		var err error
		repoRoot, err = findRepoRoot()
		if err != nil {
			fmt.Fprintf(os.Stderr, "phtest: %v\n", err)
			os.Exit(1)
		}
	}

	suites, err := discover.Discover(repoRoot)
	if err != nil {
		fmt.Fprintf(os.Stderr, "phtest: discover: %v\n", err)
		os.Exit(1)
	}
	if len(suites) == 0 {
		fmt.Fprintln(os.Stderr, "phtest: no test suites found")
		os.Exit(1)
	}

	mgr := runner.NewManager(suites)
	m := tui.New(mgr, logger)
	p := tea.NewProgram(m)
	mgr.SetSend(p.Send)

	if _, err := p.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "phtest: %v\n", err)
		os.Exit(1)
	}
}

// findRepoRoot walks up from the CWD looking for a directory containing "products/".
func findRepoRoot() (string, error) {
	dir, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "products")); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", fmt.Errorf("could not find repo root (no products/ directory found)")
		}
		dir = parent
	}
}
