package runner

import (
	"bufio"
	"os"
	"os/exec"
	"sync"
	"syscall"
	"time"

	tea "charm.land/bubbletea/v2"
	"github.com/posthog/posthog/phtest/internal/discover"
	"github.com/posthog/posthog/phtest/internal/parse"
)

const maxScrollback = 10_000

type Status int

const (
	StatusIdle Status = iota
	StatusRunning
	StatusPassed
	StatusFailed
	StatusStopped
)

func (s Status) String() string {
	switch s {
	case StatusIdle:
		return "idle"
	case StatusRunning:
		return "running"
	case StatusPassed:
		return "passed"
	case StatusFailed:
		return "failed"
	case StatusStopped:
		return "stopped"
	default:
		return "unknown"
	}
}

type StatusMsg struct {
	Name   string
	Status Status
}

type OutputMsg struct {
	Name      string
	Line      string
	LineIndex int
	Evicted   bool
}

type Snapshot struct {
	Name      string             `json:"name"`
	Category  discover.Category  `json:"category"`
	Status    string             `json:"status"`
	PID       int                `json:"pid"`
	ExitCode  *int               `json:"exit_code"`
	Result    *parse.TestResult  `json:"result,omitempty"`
	StartedAt time.Time          `json:"started_at"`
	Duration  float64            `json:"duration_s"`
}

type TestSuite struct {
	Suite discover.Suite

	mu            sync.Mutex
	status        Status
	lines         []string
	cmd           *exec.Cmd
	result        *parse.TestResult
	exitCode      *int
	startedAt     time.Time
	duration      time.Duration
	stopRequested bool
}

func NewTestSuite(suite discover.Suite) *TestSuite {
	return &TestSuite{
		Suite:  suite,
		status: StatusIdle,
	}
}

func (s *TestSuite) Status() Status {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.status
}

func (s *TestSuite) Lines() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	cp := make([]string, len(s.lines))
	copy(cp, s.lines)
	return cp
}

func (s *TestSuite) Result() *parse.TestResult {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.result
}

func (s *TestSuite) AppendLine(line string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.lines) >= maxScrollback {
		s.lines = s.lines[1:]
	}
	s.lines = append(s.lines, line)
}

func (s *TestSuite) Snapshot() Snapshot {
	s.mu.Lock()
	defer s.mu.Unlock()
	snap := Snapshot{
		Name:      s.Suite.Name,
		Category:  s.Suite.Category,
		Status:    s.status.String(),
		ExitCode:  s.exitCode,
		Result:    s.result,
		StartedAt: s.startedAt,
		Duration:  s.duration.Seconds(),
	}
	if s.cmd != nil && s.cmd.Process != nil {
		snap.PID = s.cmd.Process.Pid
	}
	return snap
}

func (s *TestSuite) Start(send func(tea.Msg)) error {
	s.mu.Lock()
	if s.status == StatusRunning {
		s.mu.Unlock()
		return nil
	}
	s.status = StatusRunning
	s.lines = nil
	s.result = nil
	s.exitCode = nil
	s.startedAt = time.Now()
	s.duration = 0
	s.stopRequested = false
	s.mu.Unlock()

	send(StatusMsg{Name: s.Suite.Name, Status: StatusRunning})

	cmd := exec.Command("bash", "-c", s.Suite.Cmd)
	cmd.Dir = s.Suite.Dir
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

	pr, pw, err := os.Pipe()
	if err != nil {
		s.mu.Lock()
		s.status = StatusFailed
		s.mu.Unlock()
		send(StatusMsg{Name: s.Suite.Name, Status: StatusFailed})
		return err
	}
	cmd.Stdout = pw
	cmd.Stderr = pw

	if err := cmd.Start(); err != nil {
		_ = pr.Close()
		_ = pw.Close()
		s.mu.Lock()
		s.status = StatusFailed
		s.mu.Unlock()
		send(StatusMsg{Name: s.Suite.Name, Status: StatusFailed})
		return err
	}

	s.mu.Lock()
	s.cmd = cmd

	if s.stopRequested {
		s.killProcessGroup()
		s.status = StatusStopped
		s.mu.Unlock()
		_ = pr.Close()
		_ = pw.Close()
		send(StatusMsg{Name: s.Suite.Name, Status: StatusStopped})
		return nil
	}
	s.mu.Unlock()

	readDone := make(chan struct{})
	go func() {
		s.readLoop(pr, send)
		close(readDone)
	}()

	go func() {
		exitErr := cmd.Wait()
		_ = pw.Close()
		<-readDone
		_ = pr.Close()

		s.mu.Lock()
		s.duration = time.Since(s.startedAt)

		if s.cmd == cmd && s.status != StatusStopped {
			code := cmd.ProcessState.ExitCode()
			s.exitCode = &code

			// Parse results from output
			s.result = parse.Parse(s.Suite.Category, s.lines)

			if exitErr != nil || (s.result != nil && !s.result.IsPass()) {
				s.status = StatusFailed
			} else {
				s.status = StatusPassed
			}
		}
		finalStatus := s.status
		s.mu.Unlock()

		send(StatusMsg{Name: s.Suite.Name, Status: finalStatus})
	}()

	return nil
}

func (s *TestSuite) Stop() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.stopRequested = true
	s.killProcessGroup()
	s.status = StatusStopped
}

func (s *TestSuite) readLoop(r *os.File, send func(tea.Msg)) {
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 256*1024), 256*1024)
	for scanner.Scan() {
		line := scanner.Text()
		s.mu.Lock()
		evicted := len(s.lines) >= maxScrollback
		if evicted {
			s.lines = s.lines[1:]
		}
		s.lines = append(s.lines, line)
		lineIndex := len(s.lines) - 1
		s.mu.Unlock()
		send(OutputMsg{Name: s.Suite.Name, Line: line, LineIndex: lineIndex, Evicted: evicted})
	}
}

func (s *TestSuite) killProcessGroup() {
	if s.cmd == nil || s.cmd.Process == nil {
		return
	}
	if s.cmd.ProcessState != nil && s.cmd.ProcessState.Exited() {
		return
	}
	pid := s.cmd.Process.Pid
	if err := syscall.Kill(-pid, syscall.SIGTERM); err != nil {
		_ = s.cmd.Process.Signal(syscall.SIGTERM)
	}
}

// PID returns the OS PID of the running process, or 0 if not started.
func (s *TestSuite) PID() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.cmd != nil && s.cmd.Process != nil {
		return s.cmd.Process.Pid
	}
	return 0
}
