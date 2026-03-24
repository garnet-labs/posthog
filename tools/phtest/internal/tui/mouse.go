package tui

import tea "charm.land/bubbletea/v2"

func (m Model) handleMouseClick(msg tea.MouseClickMsg, cmds []tea.Cmd) (tea.Model, tea.Cmd) {
	if msg.Button == tea.MouseLeft {
		if msg.X < sidebarWidth && msg.Y >= headerHeight {
			m.focusedPane = focusSidebar
			row := msg.Y - headerHeight - 1
			idx := m.entryOffset + row
			if idx >= 0 && idx < len(m.entries) {
				if m.entries[idx].isCategoryHeader {
					m.entryCursor = idx
					m.toggleCategory(m.entries[idx].category)
				} else if idx != m.entryCursor {
					m.entryCursor = idx
					m.ensureSidebarCursorVisible()
					m = m.loadActiveSuite()
				}
			}
		} else if msg.X >= sidebarWidth {
			m.focusedPane = focusOutput
		}
	}

	var vpCmd tea.Cmd
	m.viewport, vpCmd = m.viewport.Update(msg)
	cmds = append(cmds, vpCmd)

	return m, tea.Batch(cmds...)
}
