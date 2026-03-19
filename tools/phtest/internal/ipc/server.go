package ipc

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"syscall"

	"github.com/posthog/posthog/phtest/internal/runner"
)

func SocketPathFor(dir string) string {
	real, err := filepath.EvalSymlinks(dir)
	if err != nil {
		real = dir
	}
	abs, err := filepath.Abs(real)
	if err != nil {
		abs = real
	}
	sum := sha256.Sum256([]byte(abs))
	return "/tmp/phtest-" + hex.EncodeToString(sum[:4]) + ".sock"
}

type request struct {
	Cmd     string `json:"cmd"`
	Process string `json:"process,omitempty"`
	Lines   int    `json:"lines,omitempty"`
	Grep    string `json:"grep,omitempty"`
}

func Listen(path string) (net.Listener, error) {
	if fi, err := os.Lstat(path); err == nil {
		if fi.Mode()&os.ModeSocket == 0 {
			return nil, fmt.Errorf("ipc: existing path is not a socket: %s", path)
		}
		if stat, ok := fi.Sys().(*syscall.Stat_t); ok {
			if stat.Uid != uint32(os.Getuid()) {
				return nil, fmt.Errorf("ipc: existing socket not owned by current user: %s", path)
			}
		}
		if err := os.Remove(path); err != nil {
			return nil, err
		}
	}
	ln, err := net.Listen("unix", path)
	if err != nil {
		return nil, err
	}
	if err := os.Chmod(path, 0o600); err != nil {
		_ = ln.Close()
		return nil, err
	}
	return ln, nil
}

func Serve(ln net.Listener, mgr *runner.SuiteManager) error {
	for {
		conn, err := ln.Accept()
		if err != nil {
			return err
		}
		go handle(conn, mgr)
	}
}

func handle(conn net.Conn, mgr *runner.SuiteManager) {
	defer func() { _ = conn.Close() }()
	scanner := bufio.NewScanner(conn)
	for scanner.Scan() {
		var req request
		if err := json.Unmarshal(scanner.Bytes(), &req); err != nil {
			writeJSON(conn, map[string]any{"ok": false, "error": "invalid JSON"})
			continue
		}
		writeJSON(conn, dispatch(req, mgr))
	}
}

func dispatch(req request, mgr *runner.SuiteManager) any {
	switch req.Cmd {
	case "list":
		suites := mgr.Suites()
		type entry struct {
			Name     string `json:"name"`
			Category string `json:"category"`
		}
		items := make([]entry, 0, len(suites))
		for _, s := range suites {
			items = append(items, entry{Name: s.Suite.Name, Category: string(s.Suite.Category)})
		}
		return map[string]any{"ok": true, "suites": items}

	case "status":
		s, ok := mgr.Get(req.Process)
		if !ok {
			return map[string]any{"ok": false, "error": "suite not found: " + req.Process}
		}
		return okSnapshot{OK: true, Snapshot: s.Snapshot()}

	case "status_all":
		suites := mgr.Suites()
		result := make(map[string]any, len(suites))
		for _, s := range suites {
			result[s.Suite.Name] = s.Snapshot()
		}
		return map[string]any{"ok": true, "suites": result}

	case "logs":
		s, ok := mgr.Get(req.Process)
		if !ok {
			return map[string]any{"ok": false, "error": "suite not found: " + req.Process}
		}
		n := req.Lines
		if n <= 0 {
			n = 100
		}
		if n > 500 {
			n = 500
		}
		all := s.Lines()
		if req.Grep != "" {
			re, err := regexp.Compile(req.Grep)
			if err != nil {
				return map[string]any{"ok": false, "error": "invalid grep pattern: " + err.Error()}
			}
			var matched []string
			for _, l := range all {
				if re.MatchString(l) {
					matched = append(matched, l)
				}
			}
			tail := matched
			if len(tail) > n {
				tail = tail[len(tail)-n:]
			}
			return map[string]any{
				"ok":            true,
				"lines":         tail,
				"total_matched": len(matched),
				"buffered":      len(all),
			}
		}
		tail := all
		if len(tail) > n {
			tail = tail[len(tail)-n:]
		}
		return map[string]any{
			"ok":       true,
			"lines":    tail,
			"buffered": len(all),
		}

	case "results":
		if req.Process != "" {
			s, ok := mgr.Get(req.Process)
			if !ok {
				return map[string]any{"ok": false, "error": "suite not found: " + req.Process}
			}
			return okSnapshot{OK: true, Snapshot: s.Snapshot()}
		}
		suites := mgr.Suites()
		result := make(map[string]any, len(suites))
		for _, s := range suites {
			result[s.Suite.Name] = s.Snapshot()
		}
		return map[string]any{"ok": true, "results": result}

	default:
		return map[string]any{"ok": false, "error": "unknown command: " + req.Cmd}
	}
}

type okSnapshot struct {
	OK bool `json:"ok"`
	runner.Snapshot
}

func writeJSON(conn net.Conn, v any) {
	data, _ := json.Marshal(v)
	data = append(data, '\n')
	_, _ = conn.Write(data)
}
