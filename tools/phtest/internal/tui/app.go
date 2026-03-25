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

// sidebarEntry is either a tree node (collapsible category) or a leaf (test suite).
type sidebarEntry struct {
	isNode bool
	label  string            // display label for this level
	path   string            // full slash-joined path for collapse key (e.g. "Backend/products")
	depth  int               // nesting depth (0 = top-level)
	suite  *runner.TestSuite // non-nil for leaf entries
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
	entries   []sidebarEntry
	entryCursor int
	entryOffset int
	collapsed map[string]bool // keyed by slash-joined node path

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
	collapsed := make(map[string]bool)
	for _, s := range mgr.Suites() {
		parts := strings.Split(string(s.Suite.Category), " / ")
		for i := range parts {
			collapsed[strings.Join(parts[:i+1], "/")] = true
		}
	}
	entries := buildSidebarEntries(mgr.Suites(), collapsed)

	return Model{
		mgr:              mgr,
		entries:           entries,
		entryCursor:       0,
		collapsed:         collapsed,
		focusedPane:       focusSidebar,
		viewportAtBottom:  true,
		keys:              keys,
		help:              help.New(),
		spinner:           spinner.New(spinner.WithSpinner(spinner.MiniDot)),
		log:               logger,
	}
}

func buildSidebarEntries(suites []*runner.TestSuite, collapsed map[string]bool) []sidebarEntry {
	var entries []sidebarEntry
	emitted := make(map[string]bool)

	for _, s := range suites {
		parts := strings.Split(string(s.Suite.Category), " / ")

		// Emit tree nodes for each depth level, stopping if an ancestor is collapsed.
		visible := true
		for i, part := range parts {
			path := strings.Join(parts[:i+1], "/")
			if !visible {
				break
			}
			if !emitted[path] {
				emitted[path] = true
				entries = append(entries, sidebarEntry{
					isNode: true,
					label:  part,
					path:   path,
					depth:  i,
				})
			}
			if collapsed[path] {
				visible = false
			}
		}

		if visible {
			entries = append(entries, sidebarEntry{
				label: s.Suite.Name,
				depth: len(parts),
				suite: s,
			})
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
	return m.entries[m.entryCursor].suite
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
	var curPath string
	var curSuite *runner.TestSuite
	var curIsNode bool
	if m.entryCursor >= 0 && m.entryCursor < len(m.entries) {
		e := m.entries[m.entryCursor]
		curIsNode = e.isNode
		curPath = e.path
		curSuite = e.suite
	}

	m.entries = buildSidebarEntries(m.mgr.Suites(), m.collapsed)

	found := false
	if curIsNode {
		for i, e := range m.entries {
			if e.isNode && e.path == curPath {
				m.entryCursor = i
				found = true
				break
			}
		}
	} else if curSuite != nil {
		for i, e := range m.entries {
			if !e.isNode && e.suite == curSuite {
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

// toggleNode collapses or expands a tree node.
func (m *Model) toggleNode(path string) {
	m.collapsed[path] = !m.collapsed[path]
	m.rebuildEntries()
}

// categoryToPath converts a Category like "Backend / products" to "Backend/products".
func categoryToPath(cat discover.Category) string {
	return strings.Join(strings.Split(string(cat), " / "), "/")
}

// nodeStatus returns the aggregate status of all suites under a tree node path.
func (m Model) nodeStatus(path string) runner.Status {
	var hasRunning, hasFailed, hasPassed bool
	for _, s := range m.mgr.Suites() {
		catPath := categoryToPath(s.Suite.Category)
		if catPath != path && !strings.HasPrefix(catPath, path+"/") {
			continue
		}
		switch s.Status() {
		case runner.StatusRunning:
			hasRunning = true
		case runner.StatusFailed:
			hasFailed = true
		case runner.StatusPassed:
			hasPassed = true
		}
	}
	switch {
	case hasRunning:
		return runner.StatusRunning
	case hasFailed:
		return runner.StatusFailed
	case hasPassed:
		return runner.StatusPassed
	default:
		return runner.StatusIdle
	}
}
