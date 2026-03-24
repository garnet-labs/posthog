package tui

import (
	"strings"

	"charm.land/bubbles/v2/key"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/posthog/posthog/phtest/internal/runner"
)

func (m *Model) clearSearch() {
	m.searchQuery = ""
	m.searchMatches = nil
	m.searchCursor = 0
	m.viewport.StyleLineFunc = nil
}

func (m *Model) recomputeSearch() {
	if m.searchQuery == "" {
		m.searchMatches = nil
		m.searchCursor = 0
		m.viewport.StyleLineFunc = nil
		return
	}
	s := m.activeSuite()
	if s == nil {
		m.searchMatches = nil
		return
	}
	q := strings.ToLower(m.searchQuery)
	m.searchMatches = nil
	for i, line := range s.Lines() {
		if strings.Contains(strings.ToLower(ansi.Strip(line)), q) {
			m.searchMatches = append(m.searchMatches, i)
		}
	}
	if m.searchCursor >= len(m.searchMatches) {
		m.searchCursor = max(len(m.searchMatches)-1, 0)
	}
	m.applySearchStyle()
}

func (m *Model) applySearchStyle() {
	if len(m.searchMatches) == 0 {
		m.viewport.StyleLineFunc = nil
		return
	}
	matchSet := make(map[int]bool, len(m.searchMatches))
	for _, idx := range m.searchMatches {
		matchSet[idx] = true
	}
	current := m.searchMatches[m.searchCursor]
	m.viewport.StyleLineFunc = func(idx int) lipgloss.Style {
		if idx == current {
			return searchCurrentMatchStyle
		}
		if matchSet[idx] {
			return searchMatchStyle
		}
		return lipgloss.NewStyle()
	}
}

func (m *Model) jumpToCurrentMatch() {
	if len(m.searchMatches) == 0 {
		return
	}
	lineIdx := m.searchMatches[m.searchCursor]
	m.viewport.SetYOffset(max(lineIdx-m.viewport.Height()/2, 0))
	m.viewportAtBottom = m.viewport.AtBottom()
}

func (m *Model) updateSearchForNewLine(msg runner.OutputMsg) {
	if m.searchQuery == "" {
		return
	}

	if msg.Evicted && len(m.searchMatches) > 0 {
		if m.searchMatches[0] == 0 {
			m.searchMatches = m.searchMatches[1:]
			if m.searchCursor > 0 {
				m.searchCursor--
			} else if len(m.searchMatches) == 0 {
				m.searchCursor = 0
			}
		}
		for i := range m.searchMatches {
			m.searchMatches[i]--
		}
	}

	if strings.Contains(strings.ToLower(ansi.Strip(msg.Line)), strings.ToLower(m.searchQuery)) {
		m.searchMatches = append(m.searchMatches, msg.LineIndex)
	}
	m.applySearchStyle()
}

func (m Model) handleSearchKey(msg tea.KeyPressMsg, cmds []tea.Cmd) (Model, []tea.Cmd, bool) {
	switch {
	case key.Matches(msg, m.keys.Quit), msg.Code == tea.KeyEscape:
		m.searchMode = false
		m.clearSearch()
		m = m.applySize()

	case key.Matches(msg, m.keys.SearchNext):
		if m.searchMode && m.searchQuery != "" {
			// Enter confirms search, exits typing mode
			m.searchMode = false
			m = m.applySize()
			if len(m.searchMatches) > 0 {
				m.searchCursor = (m.searchCursor + 1) % len(m.searchMatches)
				m.applySearchStyle()
				m.jumpToCurrentMatch()
			}
		} else if !m.searchMode && len(m.searchMatches) > 0 {
			m.searchCursor = (m.searchCursor + 1) % len(m.searchMatches)
			m.applySearchStyle()
			m.jumpToCurrentMatch()
		}

	case key.Matches(msg, m.keys.SearchPrev):
		if len(m.searchMatches) > 0 {
			m.searchCursor = (m.searchCursor - 1 + len(m.searchMatches)) % len(m.searchMatches)
			m.applySearchStyle()
			m.jumpToCurrentMatch()
		}

	case key.Matches(msg, m.keys.Backspace):
		if m.searchMode && len(m.searchQuery) > 0 {
			runes := []rune(m.searchQuery)
			m.searchQuery = string(runes[:len(runes)-1])
			m.recomputeSearch()
		}

	default:
		if !m.searchMode {
			return m, cmds, false
		}
		s := msg.String()
		var ch string
		if s == "space" {
			ch = " "
		} else if runes := []rune(s); len(runes) == 1 && runes[0] >= 32 {
			ch = s
		}
		if ch != "" {
			m.searchQuery += ch
			m.recomputeSearch()
		}
	}
	return m, cmds, true
}
