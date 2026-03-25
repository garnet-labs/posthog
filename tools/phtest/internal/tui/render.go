package tui

import (
	"fmt"
	"strings"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
	"github.com/posthog/posthog/phtest/internal/runner"
)

func (m Model) renderHeader() string {
	brand := headerBrandStyle.Render("phtest")

	// Aggregate stats across all suites (not just visible entries)
	var passed, failed, running, total int
	for _, s := range m.mgr.Suites() {
		total++
		switch s.Status() {
		case runner.StatusPassed:
			passed++
		case runner.StatusFailed:
			failed++
		case runner.StatusRunning:
			running++
		}
	}

	var parts []string
	parts = append(parts, lipgloss.NewStyle().Foreground(colorGreen).Render(fmt.Sprintf("%d/%d passed", passed, total)))
	if failed > 0 {
		parts = append(parts, lipgloss.NewStyle().Foreground(colorRed).Render(fmt.Sprintf("%d failed", failed)))
	}
	if running > 0 {
		parts = append(parts, lipgloss.NewStyle().Foreground(colorYellow).Render(fmt.Sprintf("%d running", running)))
	}
	meta := headerMetaStyle.Render(strings.Join(parts, "  "))

	spacerW := max(m.width-lipgloss.Width(stripesStyle)-lipgloss.Width(brand)-lipgloss.Width(meta), 0)
	spacer := lipgloss.NewStyle().Width(spacerW).Render("")
	return lipgloss.JoinHorizontal(lipgloss.Top, stripesStyle, brand, spacer, meta)
}

func (m Model) renderSidebar() string {
	h := m.sidebarHeight()
	innerW := sidebarWidth - 1

	start := min(max(m.entryOffset, 0), max(0, len(m.entries)-1))
	end := min(len(m.entries), start+h)

	var rows []string
	for i := start; i < end; i++ {
		e := m.entries[i]
		indent := strings.Repeat("  ", e.depth)
		selected := i == m.entryCursor
		availW := innerW - len(indent)

		if e.isNode {
			indicator := "▾"
			if m.collapsed[e.path] {
				indicator = "▸"
			}

			// Show aggregate status icon for the node
			ns := m.nodeStatus(e.path)
			iconChar := statusIconChar(ns)
			if ns == runner.StatusRunning {
				iconChar = ansi.Strip(m.spinner.View())
			}
			iconColor := statusIconColor(ns)

			label := truncate(e.label, max(availW-5, 1))
			rows = append(rows, renderTreeNodeRow(indent, indicator, iconChar, label, iconColor, selected, innerW))
			continue
		}

		s := e.suite
		iconChar := statusIconChar(s.Status())
		if s.Status() == runner.StatusRunning {
			iconChar = ansi.Strip(m.spinner.View())
		}
		iconColor := statusIconColor(s.Status())

		// Build name with optional result counts
		name := s.Suite.Name
		if r := s.Result(); r != nil {
			total := r.Passed + r.Failed + r.Skipped + r.Errors
			name = fmt.Sprintf("%s %d/%d", name, r.Passed, total)
		}
		name = truncate(name, max(availW-3, 1))

		rows = append(rows, renderSidebarRow(indent, iconChar, name, iconColor, selected, innerW))
	}

	// Pad remaining rows
	for i := end - start; i < h; i++ {
		rows = append(rows, procInactiveStyle.Width(innerW).Render(""))
	}

	style := borderStyle
	if m.focusedPane == focusSidebar {
		style = borderFocusedStyle
	}
	return style.Height(h).Render(strings.Join(rows, "\n"))
}

func (m Model) sidebarHeight() int {
	fh := footerHeightShort
	if m.showHelp {
		fh = footerHeightFull
	}
	return max(m.height-headerHeight-fh, 1)
}

func (m *Model) ensureSidebarCursorVisible() {
	h := m.sidebarHeight()
	if len(m.entries) <= h {
		m.entryOffset = 0
		return
	}
	maxOffset := len(m.entries) - h
	if m.entryOffset > maxOffset {
		m.entryOffset = max(maxOffset, 0)
	}
	if m.entryCursor < m.entryOffset {
		m.entryOffset = m.entryCursor
	}
	if m.entryCursor >= m.entryOffset+h {
		m.entryOffset = m.entryCursor - h + 1
	}
}

func (m Model) renderOutput() string {
	style := borderStyle
	if m.focusedPane == focusOutput {
		style = borderFocusedStyle
	}
	content := lipgloss.JoinHorizontal(lipgloss.Top, m.viewportWithIndicator())
	return style.Render(content)
}

func (m Model) viewportWithIndicator() string {
	view := m.viewport.View()
	total := m.viewport.TotalLineCount()
	if total <= m.viewport.Height() {
		return view
	}
	scrollLines := total - m.viewport.YOffset() - m.viewport.Height()
	if scrollLines <= 0 {
		return view
	}
	indicator := scrollIndicatorStyle.Render(fmt.Sprintf("-%d", scrollLines))
	indicatorW := lipgloss.Width(indicator)
	lines := strings.Split(view, "\n")
	if len(lines) == 0 {
		return view
	}
	firstLine := lines[0]
	firstLineW := lipgloss.Width(firstLine)
	if firstLineW >= indicatorW {
		lines[0] = ansi.Truncate(firstLine, firstLineW-indicatorW, "") + indicator
	}
	return strings.Join(lines, "\n")
}

func (m Model) renderFooter() string {
	if m.searchMode {
		var matchInfo string
		if m.searchQuery == "" {
			matchInfo = ""
		} else if len(m.searchMatches) == 0 {
			matchInfo = "  [no matches]"
		} else {
			matchInfo = fmt.Sprintf("  [%d/%d]", m.searchCursor+1, len(m.searchMatches))
		}
		prompt := lipgloss.NewStyle().Foreground(colorYellow).Render(fmt.Sprintf("/ %s▌%s", m.searchQuery, matchInfo))
		return footerStyle.Width(m.width - 2).Render(prompt)
	}

	if m.searchQuery != "" {
		var matchInfo string
		if len(m.searchMatches) == 0 {
			matchInfo = fmt.Sprintf("search: %q  [no matches]  esc: leave", m.searchQuery)
		} else {
			matchInfo = fmt.Sprintf("search: %q  [%d/%d]  ↵/⇧↵: navigate  esc: leave", m.searchQuery, m.searchCursor+1, len(m.searchMatches))
		}
		return footerStyle.Width(m.width - 2).Render(
			lipgloss.NewStyle().Foreground(colorYellow).Render(matchInfo),
		)
	}

	var content string
	if m.showHelp {
		content = m.help.FullHelpView(m.keys.FullHelp())
	} else {
		content = m.help.ShortHelpView(m.keys.ShortHelp())
	}
	return footerStyle.Width(m.width - 2).Render(content)
}
