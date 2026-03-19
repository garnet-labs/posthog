package tui

import (
	"strings"

	"charm.land/bubbles/v2/key"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"

	"github.com/posthog/posthog/phtest/internal/runner"
)

func (m *Model) clearSearch() {
	m.searchQuery = ""
	m.searchMatches = nil
	m.searchCursor = 0
	m.viewport.StyleLineFunc = nil
}

func (m *Model) recomputeSearch() {
	m.searchMatches = nil
	m.searchCursor = 0
	if m.searchQuery == "" {
		m.viewport.StyleLineFunc = nil
		return
	}
	content := m.viewport.View()
	q := strings.ToLower(m.searchQuery)
	for i, line := range strings.Split(content, "\n") {
		if strings.Contains(strings.ToLower(line), q) {
			m.searchMatches = append(m.searchMatches, i)
		}
	}
	// Rebuild from actual lines for accuracy
	m.searchMatches = nil
	s := m.activeSuite()
	if s == nil {
		return
	}
	for i, line := range s.Lines() {
		if strings.Contains(strings.ToLower(line), q) {
			m.searchMatches = append(m.searchMatches, i)
		}
	}
	if len(m.searchMatches) > 0 {
		m.searchCursor = 0
	}
	m.applySearchStyle()
}

func (m *Model) applySearchStyle() {
	if m.searchQuery == "" || len(m.searchMatches) == 0 {
		m.viewport.StyleLineFunc = nil
		return
	}
	matches := m.searchMatches
	current := m.searchCursor
	m.viewport.StyleLineFunc = func(lineIdx int) lipgloss.Style {
		for i, matchIdx := range matches {
			if matchIdx == lineIdx {
				if i == current {
					return searchCurrentMatchStyle
				}
				return searchMatchStyle
			}
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
	q := strings.ToLower(m.searchQuery)

	if msg.Evicted && len(m.searchMatches) > 0 {
		// Shift all match indices down by 1; remove index 0 if it was a match
		var shifted []int
		for _, idx := range m.searchMatches {
			if idx > 0 {
				shifted = append(shifted, idx-1)
			}
		}
		m.searchMatches = shifted
		if m.searchCursor >= len(m.searchMatches) {
			m.searchCursor = max(0, len(m.searchMatches)-1)
		}
	}

	if strings.Contains(strings.ToLower(msg.Line), q) {
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
