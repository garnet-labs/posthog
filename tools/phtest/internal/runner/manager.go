package runner

import (
	"sync"

	tea "charm.land/bubbletea/v2"
	"github.com/posthog/posthog/phtest/internal/discover"
)

type SuiteManager struct {
	mu     sync.Mutex
	suites []*TestSuite
	byName map[string]*TestSuite
	send   func(tea.Msg)
}

func NewManager(discovered []discover.Suite) *SuiteManager {
	suites := make([]*TestSuite, 0, len(discovered))
	byName := make(map[string]*TestSuite, len(discovered))
	for _, d := range discovered {
		s := NewTestSuite(d)
		suites = append(suites, s)
		byName[d.Name] = s
	}
	return &SuiteManager{
		suites: suites,
		byName: byName,
	}
}

func (m *SuiteManager) SetSend(send func(tea.Msg)) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.send = send
}

func (m *SuiteManager) RunAll() {
	m.mu.Lock()
	send := m.send
	suites := m.suites
	m.mu.Unlock()

	for _, s := range suites {
		s := s
		go func() { _ = s.Start(send) }()
	}
}

func (m *SuiteManager) RunFailed() {
	m.mu.Lock()
	send := m.send
	suites := m.suites
	m.mu.Unlock()

	for _, s := range suites {
		if s.Status() == StatusFailed {
			s := s
			go func() { _ = s.Start(send) }()
		}
	}
}

func (m *SuiteManager) RunCategory(cat discover.Category) {
	m.mu.Lock()
	send := m.send
	suites := m.suites
	m.mu.Unlock()

	for _, s := range suites {
		if s.Suite.Category == cat {
			s := s
			go func() { _ = s.Start(send) }()
		}
	}
}

func (m *SuiteManager) StopAll() {
	m.mu.Lock()
	suites := m.suites
	m.mu.Unlock()
	for _, s := range suites {
		s.Stop()
	}
}

func (m *SuiteManager) Suites() []*TestSuite {
	m.mu.Lock()
	defer m.mu.Unlock()
	cp := make([]*TestSuite, len(m.suites))
	copy(cp, m.suites)
	return cp
}

func (m *SuiteManager) Get(name string) (*TestSuite, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	s, ok := m.byName[name]
	return s, ok
}

func (m *SuiteManager) Send() func(tea.Msg) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.send
}
