package process

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"sync"
	"syscall"
	"time"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"
	"github.com/charmbracelet/x/vt"
	"github.com/creack/pty"
	gops "github.com/shirou/gopsutil/v4/process"

	"github.com/posthog/posthog/phrocs/internal/config"
)

const metricsSampleInterval = 5 * time.Second

type Status int

const (
	StatusPending Status = iota
	StatusRunning
	StatusStopped
	StatusDone
	StatusCrashed
)

func (s Status) String() string {
	switch s {
	case StatusPending:
		return "pending"
	case StatusRunning:
		return "running"
	case StatusStopped:
		return "stopped"
	case StatusDone:
		return "done"
	case StatusCrashed:
		return "crashed"
	default:
		return "unknown"
	}
}

// Process state change
type StatusMsg struct {
	Name   string
	Status Status
}

// New output line from process
type OutputMsg struct {
	Name      string
	Line      string
	LineIndex int  // index of this line in the buffer after the append
	Evicted   bool // true when the oldest buffered line was dropped to make room
}

// Metrics holds the most recent sampled resource usage for a process tree.
type Metrics struct {
	MemRSSMB   float64   `json:"mem_rss_mb"`
	PeakMemMB  float64   `json:"peak_mem_rss_mb"`
	CPUPercent float64   `json:"cpu_percent"`
	CPUTimeS   float64   `json:"cpu_time_s"`
	Threads    int32     `json:"thread_count"`
	Children   int       `json:"child_process_count"`
	FDs        int32     `json:"fd_count"`
	SampledAt  time.Time `json:"last_sampled_at"`
}

// Snapshot is a point-in-time view of a process suitable for serialization.
type Snapshot struct {
	Name     string `json:"process"`
	Status   string `json:"status"`
	PID      int    `json:"pid"`
	Ready    bool   `json:"ready"`
	ExitCode *int   `json:"exit_code"`

	StartedAt        time.Time  `json:"started_at"`
	ReadyAt          *time.Time `json:"ready_at,omitempty"`
	StartupDurationS *float64   `json:"startup_duration_s,omitempty"`

	// Nil until the first metrics sample arrives (~5s after start).
	MemRSSMB          *float64   `json:"mem_rss_mb"`
	PeakMemRSSMB      *float64   `json:"peak_mem_rss_mb"`
	CPUPercent        *float64   `json:"cpu_percent"`
	CPUTimeS          *float64   `json:"cpu_time_s"`
	ThreadCount       *int32     `json:"thread_count"`
	ChildProcessCount *int       `json:"child_process_count"`
	FDCount           *int32     `json:"fd_count"`
	LastSampledAt     *time.Time `json:"last_sampled_at"`
}

// Represents a single managed subprocess. Output is processed through a
// virtual terminal emulator (charmbracelet/x/vt) so ANSI escape sequences
// like cursor movement, line erasure, and progress bar animations render
// correctly instead of corrupting the line buffer.
type Process struct {
	Name string
	Cfg  config.ProcConfig

	mu            sync.Mutex
	maxLines      int
	status        Status
	lines         []string
	cmd           *exec.Cmd
	ptmx          *os.File // pty master; nil when using pipes
	readyPattern  *regexp.Regexp
	ready         bool // whether we've seen the ready pattern (or no pattern is set)
	stopRequested bool // set by Stop() to catch races with in-flight Start()

	vterm  *vt.Emulator
	vtermW int // last known width
	vtermH int // last known height

	startedAt time.Time
	readyAt   time.Time
	exitCode  *int
	metrics   *Metrics
}

func NewProcess(name string, cfg config.ProcConfig, scrollback int) *Process {
	em := vt.NewEmulator(80, 24)
	em.SetScrollbackSize(scrollback)

	p := &Process{
		Name:     name,
		Cfg:      cfg,
		maxLines: scrollback,
		status:   StatusStopped,
		vterm:    em,
		vtermW:   80,
		vtermH:   24,
		ready:    cfg.ReadyPattern == "",
	}
	if cfg.ReadyPattern != "" {
		if re, err := regexp.Compile(cfg.ReadyPattern); err == nil {
			p.readyPattern = re
		}
	}
	return p
}

func (p *Process) Status() Status {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.status
}

// Returns output lines extracted from the virtual terminal emulator.
// Scrollback lines (historical content) are plain text; current screen
// lines preserve ANSI styling for colors and formatting.
func (p *Process) Lines() []string {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.vterm == nil {
		return nil
	}

	var lines []string

	// Historical content that scrolled off the top of the screen
	sb := p.vterm.Scrollback()
	if sb != nil {
		for i := range sb.Len() {
			sbLine := sb.Line(i)
			var buf strings.Builder
			for _, cell := range sbLine {
				if cell.Content != "" {
					buf.WriteString(cell.Content)
				}
			}
			lines = append(lines, buf.String())
		}
	}

	// Current screen content with ANSI styling preserved
	render := p.vterm.Render()
	screenLines := strings.Split(render, "\n")
	for len(screenLines) > 0 {
		last := screenLines[len(screenLines)-1]
		if strings.TrimSpace(ansi.Strip(last)) == "" {
			screenLines = screenLines[:len(screenLines)-1]
		} else {
			break
		}
	}
	lines = append(lines, screenLines...)

	return lines
}

// AppendLine writes a line to the virtual terminal emulator. Intended for
// tests that inject output without running a real subprocess.
func (p *Process) AppendLine(line string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.vterm != nil {
		if _, err := p.vterm.WriteString(line + "\n"); err != nil {
			fmt.Fprintf(os.Stderr, "error writing to vterm: %v\n", err)
		}
	}
}

// Returns a consistent point-in-time view of the process
func (p *Process) Snapshot() Snapshot {
	p.mu.Lock()
	defer p.mu.Unlock()

	snap := Snapshot{
		Name:      p.Name,
		Status:    p.status.String(),
		Ready:     p.ready,
		ExitCode:  p.exitCode,
		StartedAt: p.startedAt,
	}
	if p.cmd != nil && p.cmd.Process != nil {
		snap.PID = p.cmd.Process.Pid
	}
	if !p.readyAt.IsZero() {
		t := p.readyAt
		snap.ReadyAt = &t
		d := p.readyAt.Sub(p.startedAt).Seconds()
		snap.StartupDurationS = &d
	}
	if m := p.metrics; m != nil {
		mem := m.MemRSSMB
		peak := m.PeakMemMB
		cpu := m.CPUPercent
		cpuT := m.CPUTimeS
		thr := m.Threads
		ch := m.Children
		fds := m.FDs
		sa := m.SampledAt
		snap.MemRSSMB = &mem
		snap.PeakMemRSSMB = &peak
		snap.CPUPercent = &cpu
		snap.CPUTimeS = &cpuT
		snap.ThreadCount = &thr
		snap.ChildProcessCount = &ch
		snap.FDCount = &fds
		snap.LastSampledAt = &sa
	}
	return snap
}

// It's safe to call Start concurrently as running process is a no-op
func (p *Process) Start(send func(tea.Msg)) error {
	p.mu.Lock()
	if p.status == StatusRunning {
		p.mu.Unlock()
		return nil
	}
	p.status = StatusPending
	// Reset vterm for fresh output
	if p.vterm != nil {
		_ = p.vterm.Close()
	}
	p.vterm = vt.NewEmulator(p.vtermW, p.vtermH)
	p.vterm.SetScrollbackSize(p.maxLines)

	p.metrics = nil
	p.exitCode = nil
	p.startedAt = time.Now()
	p.readyAt = time.Time{}
	p.stopRequested = false
	// Reset ready flag when restarting
	p.ready = p.readyPattern == nil
	p.mu.Unlock()

	env := os.Environ()
	for k, v := range p.Cfg.Env {
		env = append(env, fmt.Sprintf("%s=%s", k, v))
	}

	cmd := exec.Command("bash", "-c", p.Cfg.Shell)
	cmd.Env = env
	// Give child its own process group so Stop() can kill the entire tree,
	// preventing zombie tsx/node/vite processes when phrocs exits.
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

	ptmx, err := pty.Start(cmd)
	if err != nil {
		return err
	}

	p.mu.Lock()
	p.cmd = cmd
	p.ptmx = ptmx

	// Stop() was called while pty.Start was in progress — kill immediately
	if p.stopRequested {
		p.killProcessGroup()
		if p.ptmx != nil {
			_ = p.ptmx.Close()
			p.ptmx = nil
		}
		p.status = StatusStopped
		p.mu.Unlock()
		send(StatusMsg{Name: p.Name, Status: StatusStopped})
		return nil
	}

	// Only set to running if proc has no ready pattern
	if p.readyPattern == nil {
		p.status = StatusRunning
	}
	currentStatus := p.status
	p.mu.Unlock()
	// Send initial status message
	send(StatusMsg{Name: p.Name, Status: currentStatus})

	go p.startMetricsSampler(cmd.Process.Pid)

	readDone := make(chan struct{})
	go func() {
		p.readLoop(ptmx, send)
		close(readDone)
	}()

	go func() {
		exitErr := cmd.Wait()

		// Close the pty master to unblock readLoop if still reading
		p.mu.Lock()
		if p.ptmx != nil {
			_ = p.ptmx.Close()
			p.ptmx = nil
		}
		p.mu.Unlock()

		// Wait for readLoop to drain all buffered output before updating status
		<-readDone

		st := StatusDone
		if exitErr != nil {
			st = StatusCrashed
		}
		p.mu.Lock()

		// Don't update status if this cmd is no longer the active one
		// (process was restarted) or if an explicit Stop() was called
		if p.cmd == cmd && p.status != StatusStopped {
			p.status = st
			code := cmd.ProcessState.ExitCode()
			p.exitCode = &code
		}
		finalStatus := p.status
		shouldRestart := p.cmd == cmd && p.Cfg.Autorestart && st == StatusCrashed
		p.mu.Unlock()

		send(StatusMsg{Name: p.Name, Status: finalStatus})

		if shouldRestart {
			_ = p.Start(send)
		}
	}()

	return nil
}

// Reads raw bytes from the process output and feeds them into the virtual
// terminal emulator, which correctly handles ANSI escape sequences like
// cursor movement, line erasure, and progress bar animations.
func (p *Process) readLoop(r io.Reader, send func(tea.Msg)) {
	buf := make([]byte, 32*1024)
	// Keep a bounded trailing window so readyPattern can match across read()
	// chunk boundaries (e.g. "server sta" + "rted").
	const readyMatchWindow = 4 * 1024
	var tail []byte
	for {
		n, err := r.Read(buf)
		if n > 0 {
			chunk := buf[:n]

			p.mu.Lock()
			if p.vterm != nil {
				_, _ = p.vterm.Write(chunk)
			}

			shouldNotify := false
			if !p.ready && p.readyPattern != nil {
				matched := p.readyPattern.Match(chunk)
				if !matched && len(tail) > 0 {
					combined := append(append(make([]byte, 0, len(tail)+len(chunk)), tail...), chunk...)
					matched = p.readyPattern.Match(combined)
				}
				if matched {
					p.ready = true
					p.status = StatusRunning
					shouldNotify = true
					tail = nil
				} else {
					tail = append(tail, chunk...)
					if len(tail) > readyMatchWindow {
						tail = append([]byte(nil), tail[len(tail)-readyMatchWindow:]...)
					}
				}
			}
			p.mu.Unlock()

			send(OutputMsg{Name: p.Name})

			if shouldNotify {
				send(StatusMsg{Name: p.Name, Status: StatusRunning})
			}
		}
		if err != nil {
			break
		}
	}
}

// Sampling CPU/mem/threads every metricsSampleInterval for the process tree
func (p *Process) startMetricsSampler(pid int) {
	ps, err := gops.NewProcess(int32(pid))
	if err != nil {
		return
	}
	// First CPUPercent call initialises the measurement baseline; always 0
	_, _ = ps.CPUPercent()
	origPID := pid

	ticker := time.NewTicker(metricsSampleInterval)
	defer ticker.Stop()

	for range ticker.C {
		p.mu.Lock()
		st := p.status
		currentPID := 0
		if p.cmd != nil && p.cmd.Process != nil {
			currentPID = p.cmd.Process.Pid
		}

		p.mu.Unlock()
		if st != StatusRunning && st != StatusPending {
			return
		}
		if currentPID != 0 && currentPID != origPID {
			// Process has been restarted with a new PID
			return
		}

		all := collectProcessTree(ps)

		var rssBytes uint64
		var cpuPct, cpuTime float64
		var threads int32
		var fds int32
		for _, proc := range all {
			if mem, err := proc.MemoryInfo(); err == nil {
				rssBytes += mem.RSS
			}
			if c, err := proc.CPUPercent(); err == nil {
				cpuPct += c
			}
			if ct, err := proc.Times(); err == nil {
				cpuTime += ct.User + ct.System
			}
			if t, err := proc.NumThreads(); err == nil {
				threads += t
			}
			if f, err := proc.NumFDs(); err == nil {
				fds += f
			}
		}

		rssMB := float64(rssBytes) / 1024 / 1024

		p.mu.Lock()
		if p.metrics == nil {
			p.metrics = &Metrics{}
		}
		p.metrics.MemRSSMB = rssMB
		if rssMB > p.metrics.PeakMemMB {
			p.metrics.PeakMemMB = rssMB
		}
		p.metrics.CPUPercent = cpuPct
		p.metrics.CPUTimeS = cpuTime
		p.metrics.Threads = threads
		p.metrics.Children = len(all) - 1
		p.metrics.FDs = fds
		p.metrics.SampledAt = time.Now()
		p.mu.Unlock()
	}
}

// collectProcessTree returns ps and all its descendants via a depth-first walk.
func collectProcessTree(ps *gops.Process) []*gops.Process {
	all := []*gops.Process{ps}
	children, err := ps.Children()
	if err != nil {
		return all
	}
	for _, child := range children {
		all = append(all, collectProcessTree(child)...)
	}
	return all
}

// killProcessGroup sends SIGTERM to the process group. Must be called with
// p.mu held. Falls back to signaling the direct child if the group kill fails.
func (p *Process) killProcessGroup() {
	if p.cmd != nil && p.cmd.Process != nil {
		pgid := p.cmd.Process.Pid
		if err := syscall.Kill(-pgid, syscall.SIGTERM); err != nil {
			_ = p.cmd.Process.Signal(syscall.SIGTERM)
		}
	}
}

// Sends SIGTERM to the process group and marks it as stopped.
// Killing the process group (negative PID) ensures all descendants
// (bash → tsx watch → node, etc.) are terminated, not just the shell.
func (p *Process) Stop() {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.stopRequested = true
	p.killProcessGroup()
	if p.ptmx != nil {
		_ = p.ptmx.Close()
		p.ptmx = nil
	}
	p.status = StatusStopped
}

// Stops the process, clears its output buffer, and starts it again
func (p *Process) Restart(send func(tea.Msg)) {
	p.Stop()
	send(StatusMsg{Name: p.Name, Status: StatusStopped})
	_ = p.Start(send)
}

// PID returns the OS PID of the running process, or 0 if not started.
func (p *Process) PID() int {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.cmd != nil && p.cmd.Process != nil {
		return p.cmd.Process.Pid
	}
	return 0
}

// Updates the pty window size to keep output correctly reflowed
func (p *Process) Resize(cols, rows uint16) {
	p.mu.Lock()
	ptmx := p.ptmx
	p.vtermW = int(cols)
	p.vtermH = int(rows)
	if p.vterm != nil {
		p.vterm.Resize(int(cols), int(rows))
	}
	p.mu.Unlock()
	if ptmx != nil {
		_ = pty.Setsize(ptmx, &pty.Winsize{Rows: rows, Cols: cols})
	}
}
