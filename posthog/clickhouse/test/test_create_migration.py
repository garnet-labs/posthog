import yaml


class TestCreateMigrationDirectory:
    def test_creates_directory_structure(self, tmp_path):
        from posthog.management.commands.create_ch_migration import create_migration

        (tmp_path / "max_migration.txt").write_text("0220_existing")

        result_path = create_migration(
            name="add_foo_column",
            migration_type="add-column",
            table="events",
            migrations_dir=tmp_path,
        )

        assert result_path.is_dir()
        assert (result_path / "manifest.yaml").exists()
        assert (result_path / "up.sql").exists()
        assert (result_path / "down.sql").exists()
        assert (result_path / "__init__.py").exists()

    def test_creates_with_correct_number(self, tmp_path):
        from posthog.management.commands.create_ch_migration import create_migration

        (tmp_path / "max_migration.txt").write_text("0220_existing")

        result_path = create_migration(
            name="add_foo_column",
            migration_type="add-column",
            table="events",
            migrations_dir=tmp_path,
        )

        assert result_path.name == "0221_add_foo_column"

        # Verify max_migration.txt was updated
        max_mig = (tmp_path / "max_migration.txt").read_text().strip()
        assert max_mig == "0221_add_foo_column"

    def test_type_add_column_generates_manifest(self, tmp_path):
        from posthog.management.commands.create_ch_migration import create_migration

        (tmp_path / "max_migration.txt").write_text("0010_test")

        result_path = create_migration(
            name="add_bar",
            migration_type="add-column",
            table="events",
            migrations_dir=tmp_path,
        )

        manifest = yaml.safe_load((result_path / "manifest.yaml").read_text())
        assert "description" in manifest
        assert "steps" in manifest
        assert len(manifest["steps"]) > 0

        # Should have TODO placeholders
        manifest_text = (result_path / "manifest.yaml").read_text()
        assert "TODO" in manifest_text

        # add-column should reference the table
        assert "events" in manifest_text.lower() or "events" in str(manifest)

    def test_type_new_table_generates_manifest(self, tmp_path):
        from posthog.management.commands.create_ch_migration import create_migration

        (tmp_path / "max_migration.txt").write_text("0010_test")

        result_path = create_migration(
            name="create_widgets",
            migration_type="new-table",
            table="widgets",
            migrations_dir=tmp_path,
        )

        manifest = yaml.safe_load((result_path / "manifest.yaml").read_text())
        assert "steps" in manifest
        # new-table should have multiple steps (local, distributed, kafka, mv)
        assert len(manifest["steps"]) >= 2

        manifest_text = (result_path / "manifest.yaml").read_text()
        assert "TODO" in manifest_text

    def test_type_add_mv_generates_manifest(self, tmp_path):
        from posthog.management.commands.create_ch_migration import create_migration

        (tmp_path / "max_migration.txt").write_text("0010_test")

        result_path = create_migration(
            name="add_mv_for_widgets",
            migration_type="add-mv",
            table="widgets",
            migrations_dir=tmp_path,
        )

        manifest = yaml.safe_load((result_path / "manifest.yaml").read_text())
        assert "steps" in manifest
        manifest_text = (result_path / "manifest.yaml").read_text()
        assert "TODO" in manifest_text

    def test_init_py_has_empty_operations(self, tmp_path):
        from posthog.management.commands.create_ch_migration import create_migration

        (tmp_path / "max_migration.txt").write_text("0010_test")

        result_path = create_migration(
            name="test_init",
            migration_type="add-column",
            table="events",
            migrations_dir=tmp_path,
        )

        init_content = (result_path / "__init__.py").read_text()
        assert "operations = []" in init_content
        assert "infi.clickhouse_orm" in init_content

    def test_fixes_stale_path(self):
        from posthog.management.commands.create_ch_migration import MIGRATIONS_DIR

        assert "posthog/clickhouse/migrations" in str(MIGRATIONS_DIR)
        assert "ee/clickhouse" not in str(MIGRATIONS_DIR)
