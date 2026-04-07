package hints

import "testing"

func TestPickHint_emptyReturnsEmpty(t *testing.T) {
	p := NewProvider(nil)
	if got := p.PickHint(); got != "" {
		t.Errorf("expected empty, got %q", got)
	}
}

func TestPickHint_cyclesThroughHints(t *testing.T) {
	hints := []string{"a", "b", "c"}
	p := NewProvider(hints)

	for i := 0; i < 2; i++ {
		for _, want := range hints {
			got := p.PickHint()
			if got != want {
				t.Errorf("got %q, want %q", got, want)
			}
		}
	}
}

func TestPickHint_singleHintRepeats(t *testing.T) {
	p := NewProvider([]string{"only"})
	for range 3 {
		if got := p.PickHint(); got != "only" {
			t.Errorf("got %q, want %q", got, "only")
		}
	}
}
