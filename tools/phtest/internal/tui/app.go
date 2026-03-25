package tui

import (
	"log"
	"path/filepath"
	"strings"

	"charm.land/bubbles/v2/help"
	"charm.land/bubbles/v2/spinner"
	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/posthog/posthog/phtest/internal/discover"
	"github.com/posthog/posthog/phtest/internal/runner"
	"github.com/posthog/posthog/phtest/internal/testnames"
)

type focusPane int

const (
	focusSidebar focusPane = iota
	focusOutput
	focusDetail
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
	mgr      *runner.SuiteManager
	repoRoot string

	focusedPane focusPane

	viewport         viewport.Model
	viewportAtBottom bool

	// Search mode
	searchMode    bool
	searchQuery   string
	searchMatches []int
	searchCursor  int

	// Sidebar (left)
	entries     []sidebarEntry
	entryCursor int
	entryOffset int
	collapsed   map[string]bool // keyed by slash-joined node path

	// Detail sidebar (right) — shows individual tests in the selected file
	detailEntries []testnames.TestEntry
	detailCursor  int
	detailOffset  int

	keys     keyMap
	help     help.Model
	spinner  spinner.Model
	showHelp bool

	width  int
	height int
	ready  bool

	log *log.Logger
}

func New(mgr *runner.SuiteManager, repoRoot string, logger *log.Logger) Model {
	keys := defaultKeyMap()
	// Build the tree, compact it, then collect node paths for initial collapse state.
	root := buildTree(mgr.Suites())
	compactTree(root)
	collapsed := make(map[string]bool)
	collectNodePaths(root, collapsed)
	entries := flattenTree(root, collapsed)

	return Model{
		mgr:              mgr,
		repoRoot:         repoRoot,
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

func (m *Model) ensureDetailCursorVisible() {
	h := m.sidebarHeight()
	if len(m.detailEntries) <= h {
		m.detailOffset = 0
		return
	}
	maxOffset := len(m.detailEntries) - h
	if m.detailOffset > maxOffset {
		m.detailOffset = max(maxOffset, 0)
	}
	if m.detailCursor < m.detailOffset {
		m.detailOffset = m.detailCursor
	}
	if m.detailCursor >= m.detailOffset+h {
		m.detailOffset = m.detailCursor - h + 1
	}
}

// filteredCmd builds a command that runs a single test within a suite.
func filteredCmd(s *runner.TestSuite, testName string) string {
	q := "'" + strings.ReplaceAll(testName, "'", "'\\''") + "'"
	switch s.Suite.Category {
	case discover.CategoryBackend:
		return s.Suite.Cmd + " -k " + q
	case discover.CategoryFrontend:
		return s.Suite.Cmd + " -t " + q
	case discover.CategoryPlaywright:
		return s.Suite.Cmd + " -g " + q
	case discover.CategoryGo:
		return s.Suite.Cmd + " -run " + q
	case discover.CategoryRust:
		return s.Suite.Cmd + " " + testName
	default:
		return s.Suite.Cmd
	}
}

// ── sidebar tree construction ───────────────────────────────────────────────────

// dirNode is an intermediate tree node used to build and compact the sidebar.
type dirNode struct {
	name     string
	path     string // full slash-joined path (used as collapse key)
	children []*dirNode
	suites   []*runner.TestSuite
}

func buildSidebarEntries(suites []*runner.TestSuite, collapsed map[string]bool) []sidebarEntry {
	root := buildTree(suites)
	compactTree(root)
	return flattenTree(root, collapsed)
}

// buildTree inserts all suites into a tree keyed by path segments.
func buildTree(suites []*runner.TestSuite) *dirNode {
	root := &dirNode{}
	idx := make(map[string]*dirNode) // path → node

	for _, s := range suites {
		parts := strings.Split(s.Suite.RelPath, string(filepath.Separator))
		dirParts := parts[:len(parts)-1]

		// Ensure all intermediate nodes exist.
		parent := root
		for i, part := range dirParts {
			path := strings.Join(parts[:i+1], "/")
			if n, ok := idx[path]; ok {
				parent = n
				continue
			}
			n := &dirNode{name: part, path: path}
			idx[path] = n
			parent.children = append(parent.children, n)
			parent = n
		}
		parent.suites = append(parent.suites, s)
	}
	return root
}

// compactTree merges single-child chains: when a node has exactly one child
// and no direct suites, fold the child's label into the parent.
func compactTree(node *dirNode) {
	for _, child := range node.children {
		compactTree(child)
	}
	for len(node.children) == 1 && len(node.suites) == 0 {
		child := node.children[0]
		node.name = node.name + "/" + child.name
		node.path = child.path
		node.children = child.children
		node.suites = child.suites
	}
}

// collectNodePaths sets all node paths as collapsed.
func collectNodePaths(node *dirNode, collapsed map[string]bool) {
	for _, child := range node.children {
		collapsed[child.path] = true
		collectNodePaths(child, collapsed)
	}
}

// flattenTree walks the compacted tree and emits sidebar entries,
// respecting collapsed state.
func flattenTree(root *dirNode, collapsed map[string]bool) []sidebarEntry {
	var entries []sidebarEntry
	for _, child := range root.children {
		flattenNode(child, 0, collapsed, &entries)
	}
	return entries
}

func flattenNode(node *dirNode, depth int, collapsed map[string]bool, entries *[]sidebarEntry) {
	*entries = append(*entries, sidebarEntry{
		isNode: true,
		label:  node.name,
		path:   node.path,
		depth:  depth,
	})
	if collapsed[node.path] {
		return
	}
	for _, child := range node.children {
		flattenNode(child, depth+1, collapsed, entries)
	}
	for _, s := range node.suites {
		parts := strings.Split(s.Suite.RelPath, string(filepath.Separator))
		*entries = append(*entries, sidebarEntry{
			label: parts[len(parts)-1],
			depth: depth + 1,
			suite: s,
		})
	}
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
	} else if m.hasDetail() {
		middle = lipgloss.JoinHorizontal(lipgloss.Top, m.renderSidebar(), m.renderOutput(), m.renderDetail())
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

func (m Model) hasDetail() bool {
	return len(m.detailEntries) > 0 && !m.searchMode
}

// sidebarWidth returns the effective sidebar width, growing with the deepest visible entry.
func (m Model) sidebarWidth() int {
	maxDepth := 0
	for _, e := range m.entries {
		if e.depth > maxDepth {
			maxDepth = e.depth
		}
	}
	return sidebarBaseWidth + sidebarDepthUnit*maxDepth
}

func (m Model) applySize() Model {
	fh := footerHeightShort
	if m.showHelp {
		fh = footerHeightFull
	}
	contentH := max(m.height-headerHeight-fh, 1)

	sw := m.sidebarWidth()
	vpW := m.width - sw - horizontalBorderCount
	if m.searchMode {
		vpW = m.width - horizontalBorderCount
	}
	if m.hasDetail() {
		vpW -= detailSidebarWidth + 2 // +2 for border
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
	m.loadDetailEntries()
	m = m.applySize()
	m.viewport.SetContent(m.buildContent())
	if m.viewportAtBottom {
		m.viewport.GotoBottom()
	}
	return m
}

func (m *Model) loadDetailEntries() {
	m.detailEntries = nil
	m.detailCursor = 0
	m.detailOffset = 0
	s := m.activeSuite()
	if s == nil {
		return
	}
	m.detailEntries = testnames.Extract(filepath.Join(m.repoRoot, s.Suite.RelPath))
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

// nodeStatus returns the aggregate status of all suites under a tree node path.
func (m Model) nodeStatus(path string) runner.Status {
	prefix := path + "/"
	var hasRunning, hasFailed, hasPassed bool
	for _, s := range m.mgr.Suites() {
		rp := strings.ReplaceAll(s.Suite.RelPath, string(filepath.Separator), "/")
		if rp != path && !strings.HasPrefix(rp, prefix) {
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
