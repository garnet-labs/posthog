package tui

import "charm.land/bubbles/v2/key"

type keyMap struct {
	PrevSuite  key.Binding
	NextSuite  key.Binding
	ScrollUp   key.Binding
	ScrollDown key.Binding
	GotoTop    key.Binding
	GotoBottom key.Binding
	NextPane   key.Binding
	PrevPane   key.Binding
	Toggle     key.Binding
	RunSuite   key.Binding
	RunFailed  key.Binding
	StopSuite  key.Binding
	Search     key.Binding
	SearchNext key.Binding
	SearchPrev key.Binding
	Backspace  key.Binding
	Quit       key.Binding
	Help       key.Binding
}

func defaultKeyMap() keyMap {
	return keyMap{
		PrevSuite: key.NewBinding(
			key.WithKeys("k", "up"),
			key.WithHelp("↑:", "prev"),
		),
		NextSuite: key.NewBinding(
			key.WithKeys("j", "down"),
			key.WithHelp("↓:", "next"),
		),
		ScrollUp: key.NewBinding(
			key.WithKeys("pgup"),
			key.WithHelp("pgup:", "↥"),
		),
		ScrollDown: key.NewBinding(
			key.WithKeys("pgdn"),
			key.WithHelp("pgdn:", "↧"),
		),
		GotoTop: key.NewBinding(
			key.WithKeys("home"),
			key.WithHelp("home:", "⤒"),
		),
		GotoBottom: key.NewBinding(
			key.WithKeys("end"),
			key.WithHelp("end:", "⤓"),
		),
		NextPane: key.NewBinding(
			key.WithKeys("tab"),
			key.WithHelp("↹:", "next pane"),
		),
		PrevPane: key.NewBinding(
			key.WithKeys("shift+tab"),
			key.WithHelp("⇧↹:", "prev pane"),
		),
		Toggle: key.NewBinding(
			key.WithKeys("space", "l", "h"),
			key.WithHelp("␣:", "expand/collapse"),
		),
		RunSuite: key.NewBinding(
			key.WithKeys("enter"),
			key.WithHelp("↵:", "run"),
		),
		RunFailed: key.NewBinding(
			key.WithKeys("f"),
			key.WithHelp("f:", "run failed"),
		),
		StopSuite: key.NewBinding(
			key.WithKeys("s"),
			key.WithHelp("s:", "stop"),
		),
		Search: key.NewBinding(
			key.WithKeys("/"),
			key.WithHelp("/:", "search"),
		),
		SearchNext: key.NewBinding(
			key.WithKeys("enter"),
			key.WithHelp("↵:", "next match"),
		),
		SearchPrev: key.NewBinding(
			key.WithKeys("shift+enter"),
			key.WithHelp("⇧↵:", "prev match"),
		),
		Backspace: key.NewBinding(
			key.WithKeys("backspace"),
			key.WithHelp("⌫:", "del char"),
		),
		Quit: key.NewBinding(
			key.WithKeys("q", "ctrl+c"),
			key.WithHelp("q:", "quit"),
		),
		Help: key.NewBinding(
			key.WithKeys("?"),
			key.WithHelp("?:", "help"),
		),
	}
}

func (k keyMap) ShortHelp() []key.Binding {
	return []key.Binding{k.NextSuite, k.Toggle, k.RunSuite, k.RunFailed, k.StopSuite, k.Search, k.Quit, k.Help}
}

func (k keyMap) FullHelp() [][]key.Binding {
	return [][]key.Binding{
		{k.NextSuite, k.PrevSuite},
		{k.ScrollUp, k.ScrollDown},
		{k.GotoTop, k.GotoBottom, k.StopSuite},
		{k.Toggle, k.RunSuite, k.RunFailed},
		{k.Search, k.SearchNext, k.SearchPrev},
		{k.NextPane, k.PrevPane, k.Quit, k.Help},
	}
}
