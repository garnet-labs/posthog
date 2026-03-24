package tui

import (
	"log"
	"strings"

	"charm.land/bubbles/v2/help"
	"charm.land/bubbles/v2/spinner"
	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/posthog/posthog/phtest/internal/discover"
	"github.com/posthog/posthog/phtest/internal/runner"
)

type focusPane int

const (
	focusSidebar focusPane = iota
	focusOutput
)

// sidebarEntry is either a category header or a selectable suite.
type sidebarEntry struct {
	isCategoryHeader bool
	category         discover.Category
	suite            *runner.TestSuite
}

type Model struct {
	mgr *runner.SuiteManager

	focusedPane focusPane

	viewport         viewport.Model
	viewportAtBottom bool

	// Search mode
	searchMode    bool
	searchQuery   string
	searchMatches []int
	searchCursor  int

	// Sidebar
	entries             []sidebarEntry
	entryCursor         int
	entryOffset         int
	collapsedCategories map[discover.Category]bool

	keys     keyMap
	help     help.Model
	spinner  spinner.Model
	showHelp bool

	width  int
	height int
	ready  bool

	log *log.Logger
}

func New(mgr *runner.SuiteManager, logger *log.Logger) Model {
	keys := defaultKeyMap()
	collapsed := make(map[discover.Category]bool)
	for _, s := range mgr.Suites() {
		collapsed[s.Suite.Category] = true
	}
	entries := buildSidebarEntries(mgr.Suites(), collapsed)

	return Model{
		mgr:                 mgr,
		entries:              entries,
		entryCursor:          0,
		collapsedCategories:  collapsed,
		focusedPane:          focusSidebar,
		viewportAtBottom:     true,
		keys:                 keys,
		help:                 help.New(),
		spinner:              spinner.New(spinner.WithSpinner(spinner.MiniDot)),
		log:                  logger,
	}
}

func buildSidebarEntries(suites []*runner.TestSuite, collapsed map[discover.Category]bool) []sidebarEntry {
	var entries []sidebarEntry
	var lastCat discover.Category
	for _, s := range suites {
		if s.Suite.Category != lastCat {
			entries = append(entries, sidebarEntry{isCategoryHeader: true, category: s.Suite.Category})
			lastCat = s.Suite.Category
		}
		if !collapsed[s.Suite.Category] {
			entries = append(entries, sidebarEntry{suite: s})
		}
	}
	return entries
}

func (m Model) dbg(format string, args ...any) {
	if m.log != nil {
		m.log.Printf(format, args...)
	}
}

func (m Model) Init() tea.Cmd {
	return tea.Batch(tea.RequestBackgroundColor, m.spinner.Tick)
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmds []tea.Cmd

	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.dbg("resize: %dx%d", msg.Width, msg.Height)
		m.width = msg.Width
		m.height = msg.Height
		m = m.applySize()

	case tea.BackgroundColorMsg:
		isDark := msg.IsDark()
		m.help.Styles = help.DefaultStyles(isDark)

	case spinner.TickMsg:
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		cmds = append(cmds, cmd)

	case runner.OutputMsg:
		if m.ready && m.activeSuite() != nil && m.activeSuite().Suite.Name == msg.Name {
			m.viewport.SetContent(m.buildContent())
			if m.viewportAtBottom && !m.searchMode {
				m.viewport.GotoBottom()
			}
			if m.searchQuery != "" {
				m.updateSearchForNewLine(msg)
			}
		}

	case runner.StatusMsg:
		m.dbg("status: suite=%s status=%s", msg.Name, msg.Status)
		m.rebuildEntries()

	case tea.KeyPressMsg:
		var handled bool
		if m.searchMode {
			m, cmds, handled = m.handleSearchKey(msg, cmds)
		}
		if !handled {
			return m.handleNormalKey(msg, cmds)
		}

	case tea.MouseClickMsg:
		return m.handleMouseClick(msg, cmds)

	case tea.MouseMsg:
		var vpCmd tea.Cmd
		m.viewport, vpCmd = m.viewport.Update(msg)
		cmds = append(cmds, vpCmd)
		m.viewportAtBottom = m.viewport.AtBottom()
	}

	return m, tea.Batch(cmds...)
}

func (m Model) View() tea.View {
	if !m.ready {
		v := tea.NewView("\n  Initialising...\n")
		v.AltScreen = true
		return v
	}

	var middle string
	if m.searchMode {
		middle = m.renderOutput()
	} else {
		middle = lipgloss.JoinHorizontal(lipgloss.Top, m.renderSidebar(), m.renderOutput())
	}

	v := tea.NewView(lipgloss.JoinVertical(
		lipgloss.Left,
		m.renderHeader(),
		middle,
		m.renderFooter(),
	))
	v.AltScreen = true
	if m.searchMode {
		v.MouseMode = tea.MouseModeNone
	} else {
		v.MouseMode = tea.MouseModeCellMotion
	}
	return v
}

func (m Model) activeSuite() *runner.TestSuite {
	if m.entryCursor < 0 || m.entryCursor >= len(m.entries) {
		return nil
	}
	e := m.entries[m.entryCursor]
	if e.isCategoryHeader {
		return nil
	}
	return e.suite
}

func (m Model) applySize() Model {
	fh := footerHeightShort
	if m.showHelp {
		fh = footerHeightFull
	}
	contentH := max(m.height-headerHeight-fh, 1)

	vpW := m.width - sidebarWidth - horizontalBorderCount
	if m.searchMode {
		vpW = m.width - horizontalBorderCount
	}
	vpW = max(vpW, 1)

	if !m.ready {
		m.viewport = viewport.New(viewport.WithWidth(vpW), viewport.WithHeight(contentH))
		m.viewport.MouseWheelDelta = 3
		m.ready = true
		// Load initial content
		m.viewport.SetContent(m.buildContent())
	} else {
		m.viewport.SetWidth(vpW)
		m.viewport.SetHeight(contentH)
	}

	m.ensureSidebarCursorVisible()
	return m
}

func (m Model) loadActiveSuite() Model {
	if !m.ready {
		return m
	}
	m.searchMode = false
	m.clearSearch()
	m = m.applySize()
	m.viewport.SetContent(m.buildContent())
	if m.viewportAtBottom {
		m.viewport.GotoBottom()
	}
	return m
}

func (m Model) buildContent() string {
	s := m.activeSuite()
	if s == nil {
		return ""
	}
	return strings.Join(s.Lines(), "\n")
}

// Move cursor to the next entry in the given direction.
func (m *Model) moveCursor(dir int) bool {
	next := m.entryCursor + dir
	if next >= 0 && next < len(m.entries) {
		m.entryCursor = next
		return true
	}
	return false
}

// rebuildEntries reconstructs the sidebar entries preserving the cursor position.
func (m *Model) rebuildEntries() {
	var curSuite *runner.TestSuite
	var curCategory discover.Category
	var curIsHeader bool
	if m.entryCursor >= 0 && m.entryCursor < len(m.entries) {
		e := m.entries[m.entryCursor]
		curIsHeader = e.isCategoryHeader
		curCategory = e.category
		curSuite = e.suite
	}

	m.entries = buildSidebarEntries(m.mgr.Suites(), m.collapsedCategories)

	found := false
	if curIsHeader {
		for i, e := range m.entries {
			if e.isCategoryHeader && e.category == curCategory {
				m.entryCursor = i
				found = true
				break
			}
		}
	} else if curSuite != nil {
		for i, e := range m.entries {
			if !e.isCategoryHeader && e.suite == curSuite {
				m.entryCursor = i
				found = true
				break
			}
		}
	}
	if !found && len(m.entries) > 0 {
		m.entryCursor = min(m.entryCursor, len(m.entries)-1)
	}
	m.ensureSidebarCursorVisible()
}

// toggleCategory collapses or expands a category group.
func (m *Model) toggleCategory(cat discover.Category) {
	m.collapsedCategories[cat] = !m.collapsedCategories[cat]
	m.rebuildEntries()
}
