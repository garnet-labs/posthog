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
		m.focusedPane = m.nextPane(+1)

	case key.Matches(msg, m.keys.PrevPane):
		m.focusedPane = m.nextPane(-1)

	case key.Matches(msg, m.keys.NextSuite):
		switch m.focusedPane {
		case focusSidebar:
			if m.moveCursor(+1) {
				m.ensureSidebarCursorVisible()
				m = m.loadActiveSuite()
			}
		case focusDetail:
			if m.detailCursor < len(m.detailEntries)-1 {
				m.detailCursor++
				m.ensureDetailCursorVisible()
			}
		default:
			cmds = append(cmds, m.forwardToViewport(msg))
		}

	case key.Matches(msg, m.keys.PrevSuite):
		switch m.focusedPane {
		case focusSidebar:
			if m.moveCursor(-1) {
				m.ensureSidebarCursorVisible()
				m = m.loadActiveSuite()
			}
		case focusDetail:
			if m.detailCursor > 0 {
				m.detailCursor--
				m.ensureDetailCursorVisible()
			}
		default:
			cmds = append(cmds, m.forwardToViewport(msg))
		}

	case key.Matches(msg, m.keys.GotoTop):
		m.viewport.GotoTop()
		m.viewportAtBottom = false

	case key.Matches(msg, m.keys.GotoBottom):
		m.viewport.GotoBottom()
		m.viewportAtBottom = true

	case key.Matches(msg, m.keys.Toggle):
		if m.focusedPane == focusSidebar {
			if e := m.entries[m.entryCursor]; e.isNode {
				m.toggleNode(e.path)
			}
		}

	case key.Matches(msg, m.keys.RunSuite):
		switch m.focusedPane {
		case focusSidebar:
			if e := m.entries[m.entryCursor]; e.isNode {
				go m.mgr.RunPath(e.path)
			} else if s := m.activeSuite(); s != nil {
				send := m.mgr.Send()
				go func() { _ = s.Start(send) }()
			}
		case focusDetail:
			if s := m.activeSuite(); s != nil && m.detailCursor < len(m.detailEntries) {
				cmd := filteredCmd(s, m.detailEntries[m.detailCursor].Name)
				send := m.mgr.Send()
				go func() { _ = s.StartFiltered(cmd, send) }()
			}
		}

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

// nextPane cycles through available panes. Detail is only included when visible.
func (m Model) nextPane(dir int) focusPane {
	panes := []focusPane{focusSidebar, focusOutput}
	if m.hasDetail() {
		panes = []focusPane{focusSidebar, focusOutput, focusDetail}
	}
	for i, p := range panes {
		if p == m.focusedPane {
			return panes[(i+dir+len(panes))%len(panes)]
		}
	}
	return focusSidebar
}
