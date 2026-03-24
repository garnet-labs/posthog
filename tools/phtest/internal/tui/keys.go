package tui

import (
	"charm.land/bubbles/v2/key"
	tea "charm.land/bubbletea/v2"
)

func (m *Model) forwardToViewport(msg tea.Msg) tea.Cmd {
	var cmd tea.Cmd
	m.viewport, cmd = m.viewport.Update(msg)
	m.viewportAtBottom = m.viewport.AtBottom()
	return cmd
}

func (m Model) handleNormalKey(msg tea.KeyPressMsg, cmds []tea.Cmd) (tea.Model, tea.Cmd) {
	switch {
	case msg.Code == tea.KeyEscape:
		if m.searchQuery != "" {
			m.clearSearch()
		}

	case key.Matches(msg, m.keys.Quit):
		m.mgr.StopAll()
		return m, tea.Quit

	case key.Matches(msg, m.keys.Help):
		m.showHelp = !m.showHelp
		m = m.applySize()

	case key.Matches(msg, m.keys.NextPane):
		if m.focusedPane == focusSidebar {
			m.focusedPane = focusOutput
		} else {
			m.focusedPane = focusSidebar
		}

	case key.Matches(msg, m.keys.PrevPane):
		if m.focusedPane == focusOutput {
			m.focusedPane = focusSidebar
		} else {
			m.focusedPane = focusOutput
		}

	case key.Matches(msg, m.keys.NextSuite):
		if m.focusedPane == focusSidebar {
			if m.moveCursor(+1) {
				m.ensureSidebarCursorVisible()
				m = m.loadActiveSuite()
			}
		} else {
			cmds = append(cmds, m.forwardToViewport(msg))
		}

	case key.Matches(msg, m.keys.PrevSuite):
		if m.focusedPane == focusSidebar {
			if m.moveCursor(-1) {
				m.ensureSidebarCursorVisible()
				m = m.loadActiveSuite()
			}
		} else {
			cmds = append(cmds, m.forwardToViewport(msg))
		}

	case key.Matches(msg, m.keys.GotoTop):
		m.viewport.GotoTop()
		m.viewportAtBottom = false

	case key.Matches(msg, m.keys.GotoBottom):
		m.viewport.GotoBottom()
		m.viewportAtBottom = true

	case key.Matches(msg, m.keys.RunSuite):
		if m.focusedPane == focusSidebar {
			if e := m.entries[m.entryCursor]; e.isCategoryHeader {
				m.toggleCategory(e.category)
			} else if s := m.activeSuite(); s != nil {
				send := m.mgr.Send()
				go func() { _ = s.Start(send) }()
			}
		}

	case key.Matches(msg, m.keys.RunAll):
		go m.mgr.RunAll()

	case key.Matches(msg, m.keys.RunFailed):
		go m.mgr.RunFailed()

	case key.Matches(msg, m.keys.StopSuite):
		if s := m.activeSuite(); s != nil {
			s.Stop()
		}

	case key.Matches(msg, m.keys.Search):
		m.searchMode = true
		m.clearSearch()
		m = m.applySize()

	default:
		if m.focusedPane == focusOutput {
			cmds = append(cmds, m.forwardToViewport(msg))
		}
	}

	return m, tea.Batch(cmds...)
}
