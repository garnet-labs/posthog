package testnames

import (
	"testing"
)

func TestExtractPython(t *testing.T) {
	lines := []string{
		"from posthog.test.base import APIBaseTest",
		"",
		"class TestFeatureFlag(APIBaseTest):",
		"    def test_create(self):",
		"        pass",
		"    def test_delete(self):",
		"        pass",
		"    def helper_method(self):",
		"        pass",
		"",
		"class TestAnotherThing(APIBaseTest):",
		"    def test_foo(self):",
		"        pass",
	}
	entries := extractPython(lines)
	if len(entries) != 5 {
		t.Fatalf("expected 5 entries, got %d: %v", len(entries), entries)
	}
	if entries[0].Name != "TestFeatureFlag" || entries[0].Depth != 0 {
		t.Errorf("expected TestFeatureFlag at depth 0, got %+v", entries[0])
	}
	if entries[1].Name != "test_create" || entries[1].Depth != 1 {
		t.Errorf("expected test_create at depth 1, got %+v", entries[1])
	}
}

func TestExtractJest(t *testing.T) {
	lines := []string{
		"describe('myFunction', () => {",
		"    it('should return true', () => {",
		"        expect(true).toBe(true)",
		"    })",
		"    test('handles edge case', () => {",
		"        expect(false).toBe(false)",
		"    })",
		"})",
	}
	entries := extractJest(lines)
	if len(entries) != 3 {
		t.Fatalf("expected 3 entries, got %d: %v", len(entries), entries)
	}
	if entries[0].Name != "myFunction" || entries[0].Depth != 0 {
		t.Errorf("got %+v", entries[0])
	}
	if entries[1].Name != "should return true" || entries[1].Depth != 1 {
		t.Errorf("got %+v", entries[1])
	}
}

func TestExtractGo(t *testing.T) {
	lines := []string{
		"func TestFoo(t *testing.T) {",
		`    t.Run("sub case", func(t *testing.T) {`,
		"    })",
		"}",
		"func TestBar(t *testing.T) {",
		"}",
	}
	entries := extractGo(lines)
	if len(entries) != 3 {
		t.Fatalf("expected 3 entries, got %d: %v", len(entries), entries)
	}
	if entries[0].Name != "TestFoo" || entries[0].Depth != 0 {
		t.Errorf("got %+v", entries[0])
	}
	if entries[1].Name != "sub case" || entries[1].Depth != 1 {
		t.Errorf("got %+v", entries[1])
	}
}

func TestExtractRust(t *testing.T) {
	lines := []string{
		"#[cfg(test)]",
		"mod tests {",
		"    #[test]",
		"    fn it_works() {",
		"        assert!(true);",
		"    }",
		"    #[tokio::test]",
		"    async fn it_works_async() {",
		"        assert!(true);",
		"    }",
		"}",
	}
	entries := extractRust(lines)
	if len(entries) != 2 {
		t.Fatalf("expected 2 entries, got %d: %v", len(entries), entries)
	}
	if entries[0].Name != "it_works" {
		t.Errorf("got %+v", entries[0])
	}
	if entries[1].Name != "it_works_async" {
		t.Errorf("got %+v", entries[1])
	}
}

func TestExtractPlaywright(t *testing.T) {
	lines := []string{
		"test.describe('Auth', () => {",
		"    test('Login', async ({ page }) => {",
		"    })",
		"    test('Logout', async ({ page }) => {",
		"    })",
		"})",
	}
	entries := extractPlaywright(lines)
	if len(entries) != 3 {
		t.Fatalf("expected 3 entries, got %d: %v", len(entries), entries)
	}
	if entries[0].Name != "Auth" || entries[0].Depth != 0 {
		t.Errorf("got %+v", entries[0])
	}
	if entries[1].Name != "Login" || entries[1].Depth != 1 {
		t.Errorf("got %+v", entries[1])
	}
}
