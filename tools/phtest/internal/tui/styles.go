package tui

import (
	"image/color"

	"charm.land/lipgloss/v2"
	"github.com/posthog/posthog/phtest/internal/palette"
	"github.com/posthog/posthog/phtest/internal/runner"
)

var (
	colorYellow   = palette.ColorYellow
	colorBlue     = palette.ColorBlue
	colorGrey     = palette.ColorGrey
	colorDarkGrey = palette.ColorDarkGrey
	colorGreen    = palette.ColorGreen
	colorRed      = palette.ColorRed
	colorWhite    = palette.ColorWhite
	colorBlack    = palette.ColorBlack
)

const sidebarWidth = 24
const headerHeight = 1
const footerHeightShort = 3
const footerHeightFull = 5
const horizontalBorderCount = 4

var (
	headerBrandStyle = lipgloss.NewStyle().
				Foreground(colorWhite).
				Bold(true).
				Padding(0, 1)

	headerMetaStyle = lipgloss.NewStyle().
			Foreground(colorGrey).
			Padding(0, 1)

	stripesStyle = lipgloss.NewStyle().
			PaddingLeft(1).
			Render(
			lipgloss.NewStyle().Background(colorBlue).Render(" ") +
				lipgloss.NewStyle().Background(colorYellow).Render(" ") +
				lipgloss.NewStyle().Background(colorRed).Render(" ") +
				lipgloss.NewStyle().Background(colorBlack).Render(" "),
		)

	borderStyle = lipgloss.NewStyle().
			BorderRight(true).
			BorderTop(true).
			BorderBottom(true).
			BorderLeft(true).
			BorderStyle(lipgloss.NormalBorder()).
			BorderForeground(colorDarkGrey)

	borderFocusedStyle = borderStyle.
				BorderStyle(lipgloss.ThickBorder())

	procInactiveStyle = lipgloss.NewStyle().
				PaddingLeft(1).
				Foreground(colorGrey)

	footerStyle = lipgloss.NewStyle().
			Foreground(colorGrey).
			PaddingLeft(1)

	scrollIndicatorStyle = lipgloss.NewStyle().
				Foreground(colorBlack).
				Background(colorYellow).
				Padding(0, 1)

	searchMatchStyle = lipgloss.NewStyle().
				Background(colorDarkGrey)

	searchCurrentMatchStyle = lipgloss.NewStyle().
				Background(colorYellow).
				Foreground(colorBlack)

	categoryHeaderStyle = lipgloss.NewStyle().
				Foreground(colorYellow).
				Bold(true).
				PaddingLeft(1)
)

func statusIconChar(s runner.Status) string {
	switch s {
	case runner.StatusRunning:
		return palette.IconRunning
	case runner.StatusPassed:
		return palette.IconDone
	case runner.StatusFailed:
		return palette.IconCrashed
	case runner.StatusStopped, runner.StatusIdle:
		return palette.IconStopped
	default:
		return palette.IconStopped
	}
}

func statusIconColor(s runner.Status) color.Color {
	switch s {
	case runner.StatusRunning:
		return colorYellow
	case runner.StatusPassed:
		return colorGreen
	case runner.StatusFailed:
		return colorRed
	case runner.StatusStopped, runner.StatusIdle:
		return colorGrey
	default:
		return colorGrey
	}
}

func renderSidebarRow(icon, name string, iconColor color.Color, selected bool, innerW int) string {
	if selected {
		base := lipgloss.NewStyle().Background(colorDarkGrey).Bold(true)
		iconSeg := base.PaddingLeft(1).Foreground(iconColor).Render(icon)
		nameSeg := base.Foreground(colorWhite).Width(innerW - 2).Render(" " + name)
		return iconSeg + nameSeg
	}
	iconSeg := lipgloss.NewStyle().PaddingLeft(1).Foreground(iconColor).Render(icon)
	nameSeg := lipgloss.NewStyle().Foreground(colorGrey).Width(innerW - 2).Render(" " + name)
	return iconSeg + nameSeg
}

func truncate(s string, maxLen int) string {
	if maxLen <= 0 {
		return ""
	}
	runes := []rune(s)
	if len(runes) <= maxLen {
		return s
	}
	return string(runes[:maxLen-1]) + "…"
}
