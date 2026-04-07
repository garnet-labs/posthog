package hints

// Provider cycles through config-supplied hint strings.
type Provider struct {
	hints []string
	index int
}

// NewProvider creates a provider that cycles through the given hints.
// If hints is empty, PickHint always returns "".
func NewProvider(hints []string) *Provider {
	return &Provider{hints: hints}
}

// PickHint returns the next hint, cycling through the list.
func (p *Provider) PickHint() string {
	if len(p.hints) == 0 {
		return ""
	}
	hint := p.hints[p.index]
	p.index = (p.index + 1) % len(p.hints)
	return hint
}
