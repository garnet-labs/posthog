use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::io::Cursor;
use std::path::Path;

use anyhow::Result;
use serde::{Deserialize, Serialize};
use symbolic::debuginfo::dwarf::{gimli, Dwarf as DwarfObject};
use symbolic::debuginfo::{Archive, Object};
use tracing::{info, warn};

/// Manifest format stored as `__source/manifest.json` inside the dSYM ZIP
#[derive(Serialize, Deserialize)]
pub struct SourceManifest {
    pub version: u32,
    /// Maps absolute DWARF source path → ZIP-relative path (e.g. "__source/Foo.swift")
    pub files: BTreeMap<String, String>,
}

/// Collected source files ready to be added to a ZIP
pub struct SourceFiles {
    pub manifest: SourceManifest,
    /// Maps ZIP-relative path → file content (BTreeMap for deterministic zip ordering)
    pub contents: BTreeMap<String, Vec<u8>>,
}

/// Extract source file paths from a DWARF binary using only compilation-unit
/// main files (`DW_AT_comp_dir` + `DW_AT_name` on each `DW_TAG_compile_unit`).
///
/// This intentionally excludes the full DWARF line-number file table, which also
/// contains files from *other* modules referenced via `DW_AT_decl_file` on type
/// declarations.  Including those would cause the source-bundle hash to change
/// whenever a dependency's source changes — even when this binary's UUID is
/// identical — triggering spurious `content_hash_mismatch` rejections.
pub fn extract_source_paths_from_dwarf(dwarf_path: &Path) -> Result<Vec<String>> {
    let dwarf_data = fs::read(dwarf_path)?;
    let archive = Archive::parse(&dwarf_data)?;

    let mut paths = Vec::new();

    for obj in archive.objects() {
        let obj = obj?;
        // collect_cu_source_paths requires the concrete Dwarf implementor; the
        // Object enum itself does not implement the trait.
        match &obj {
            Object::MachO(m) => collect_cu_source_paths(m, &mut paths),
            Object::Elf(e) => collect_cu_source_paths(e, &mut paths),
            _ => {} // Other formats not relevant for iOS / Android
        }
    }

    // Deduplicate
    paths.sort();
    paths.dedup();

    for p in &paths {
        tracing::debug!("DWARF source path (CU main file): {}", p);
    }

    Ok(paths)
}

/// Walk `debug_info` with gimli and collect the main source file of each
/// compilation unit (the `DW_AT_comp_dir + DW_AT_name` pair on the CU DIE).
/// This does NOT read the line-number program's file table, so cross-module
/// file references that appear there are never included.
fn collect_cu_source_paths<'d>(obj: &impl DwarfObject<'d>, out: &mut Vec<String>) {
    // Load the minimal DWARF sections we need: debug_info, debug_abbrev, debug_str,
    // and debug_line_str (DWARF v5 string section).
    let empty: &[u8] = &[];

    let info_data = obj
        .section("debug_info")
        .map(|s| s.data.into_owned())
        .unwrap_or_default();
    let abbrev_data = obj
        .section("debug_abbrev")
        .map(|s| s.data.into_owned())
        .unwrap_or_default();
    let str_data = obj
        .section("debug_str")
        .map(|s| s.data.into_owned())
        .unwrap_or_default();
    let line_str_data = obj
        .section("debug_line_str")
        .map(|s| s.data.into_owned())
        .unwrap_or_default();

    let endian = if matches!(obj.endianity(), symbolic::debuginfo::dwarf::Endian::Big) {
        gimli::RunTimeEndian::Big
    } else {
        gimli::RunTimeEndian::Little
    };

    let dwarf = gimli::Dwarf {
        debug_info: gimli::DebugInfo::new(&info_data, endian),
        debug_abbrev: gimli::DebugAbbrev::new(&abbrev_data, endian),
        debug_str: gimli::DebugStr::new(&str_data, endian),
        debug_line_str: gimli::DebugLineStr::new(&line_str_data, endian),
        // Sections not needed for CU-name extraction:
        debug_addr: gimli::DebugAddr::from(gimli::EndianSlice::new(empty, endian)),
        debug_aranges: gimli::DebugAranges::new(empty, endian),
        debug_line: gimli::DebugLine::new(empty, endian),
        debug_str_offsets: gimli::DebugStrOffsets::from(gimli::EndianSlice::new(empty, endian)),
        debug_types: Default::default(),
        debug_macinfo: gimli::DebugMacinfo::new(empty, endian),
        debug_macro: gimli::DebugMacro::new(empty, endian),
        locations: Default::default(),
        ranges: gimli::RangeLists::new(
            gimli::DebugRanges::new(empty, endian),
            gimli::DebugRngLists::new(empty, endian),
        ),
        file_type: gimli::DwarfFileType::Main,
        abbreviations_cache: Default::default(),
        sup: None,
    };

    let mut cu_count = 0u32;
    let mut iter = dwarf.units();
    loop {
        let header = match iter.next() {
            Ok(Some(h)) => h,
            Ok(None) => break,
            Err(e) => { tracing::debug!("units().next() error: {:?}", e); break; },
        };
        cu_count += 1;

        // Obtain abbreviation table for this CU.
        let abbrevs = match dwarf.abbreviations(&header) {
            Ok(a) => a,
            Err(e) => { tracing::debug!("CU {}: abbreviations() error: {:?}", cu_count, e); continue; }
        };

        // Parse the root DIE WITHOUT calling dwarf.unit() — that helper also
        // tries to load the line program, which would fail because we omitted
        // debug_line from our minimal Dwarf instance.
        let mut cursor = header.entries(&abbrevs);
        let (_, root) = match cursor.next_dfs() {
            Ok(Some(e)) => e,
            _ => continue,
        };
        if root.tag() != gimli::DW_TAG_compile_unit {
            continue;
        }

        // Resolve an attribute value to a UTF-8 string from debug_str / inline data.
        let resolve_str = |val: gimli::AttributeValue<gimli::EndianSlice<'_, gimli::RunTimeEndian>>| -> Option<String> {
            match val {
                gimli::AttributeValue::String(s) =>
                    std::str::from_utf8(s.slice()).ok().map(|s| s.to_string()),
                gimli::AttributeValue::DebugStrRef(offset) =>
                    dwarf.debug_str.get_str(offset).ok()
                        .and_then(|s| std::str::from_utf8(s.slice()).ok().map(|s| s.to_string())),
                gimli::AttributeValue::DebugLineStrRef(offset) =>
                    dwarf.debug_line_str.get_str(offset).ok()
                        .and_then(|s| std::str::from_utf8(s.slice()).ok().map(|s| s.to_string())),
                _ => None,
            }
        };

        let comp_dir: Option<String> = root.attr_value(gimli::DW_AT_comp_dir).ok().flatten()
            .and_then(&resolve_str);
        let name: Option<String> = root.attr_value(gimli::DW_AT_name).ok().flatten()
            .and_then(&resolve_str);

        let path = match (comp_dir, name) {
            (Some(dir), Some(name)) if !name.starts_with('/') =>
                format!("{}/{}", dir.trim_end_matches('/'), name),
            (_, Some(name)) if name.starts_with('/') => name,
            (Some(dir), None) => dir,
            _ => continue,
        };

        if !path.is_empty() {
            out.push(path);
        }
    }
}

/// System/SDK path prefixes to exclude from source bundling
const EXCLUDED_PREFIXES: &[&str] = &[
    "/usr/",
    "/Library/Developer/",
    "/Applications/Xcode",
    "/System/",
];

/// Path substrings that indicate system/generated code
const EXCLUDED_SUBSTRINGS: &[&str] = &[
    "/Xcode.app/",
    "/SDKs/",
    "<compiler-generated>",
    "<built-in>",
    "/DerivedData/",
];

/// Short (root-level) names produced by Apple's Clang/Swift linker as synthetic
/// DWARF compile-unit names for system frameworks. These are not real file paths
/// and can never be read from disk.
const EXCLUDED_SYNTHETIC_NAMES: &[&str] = &[
    "/_AvailabilityInternal",
    "/_Builtin_",
    "/_DarwinFoundation",
    "/CFNetwork",
    "/CoreFoundation",
    "/Darwin",
    "/Dispatch",
    "/Foundation",
    "/MachO",
    "/ObjectiveC",
    "/Security",
    "/XPC",
    "/asl",
    "/os_",
    "/ptrcheck",
    "/ptrauth",
    "<stdin>",
    "<swift-imported-modules>",
];

/// Filter out system framework and SDK paths, keeping only user source files.
pub fn filter_source_paths(paths: &[String]) -> Vec<&str> {
    paths
        .iter()
        .filter(|path| {
            // Exclude system prefixes
            if EXCLUDED_PREFIXES
                .iter()
                .any(|prefix| path.starts_with(prefix))
            {
                tracing::debug!("Filtered out (prefix): {}", path);
                return false;
            }
            // Exclude paths containing system substrings
            if EXCLUDED_SUBSTRINGS.iter().any(|sub| path.contains(sub)) {
                tracing::debug!("Filtered out (substring): {}", path);
                return false;
            }
            // Exclude synthetic short names that Apple's linker emits as
            // placeholder compile-unit names for system frameworks.
            if EXCLUDED_SYNTHETIC_NAMES
                .iter()
                .any(|s| path.starts_with(s))
            {
                tracing::debug!("Filtered out (synthetic): {}", path);
                return false;
            }
            true
        })
        .map(|s| s.as_str())
        .collect()
}

/// Collect source files from disk, reading each file referenced by DWARF debug info.
///
/// Since the CLI runs on the build machine, the absolute paths from DWARF are valid.
/// Files that don't exist are skipped with a warning.
pub fn collect_source_files(dwarf_paths: &[&str]) -> Result<SourceFiles> {
    let mut manifest_files = BTreeMap::new();
    let mut contents = BTreeMap::new();

    // Build a disambiguated relative path for each source file.
    // We use a simple approach: strip common prefix to get a short relative path,
    // and if there are collisions, use increasingly longer path components.
    let zip_paths = build_zip_relative_paths(dwarf_paths);

    for (dwarf_path, zip_rel_path) in dwarf_paths.iter().zip(zip_paths.iter()) {
        let path = Path::new(dwarf_path);
        match fs::read(path) {
            Ok(data) => {
                let zip_path = format!("__source/{}", zip_rel_path);
                manifest_files.insert(dwarf_path.to_string(), zip_path.clone());
                contents.insert(zip_path, data);
            }
            Err(e) => {
                warn!(
                    "Could not read source file {}: {} (skipping)",
                    dwarf_path, e
                );
            }
        }
    }

    for (dwarf_path, zip_path) in &manifest_files {
        tracing::debug!("Manifest entry: {} -> {}", dwarf_path, zip_path);
    }

    info!(
        "Collected {} source files ({} bytes total)",
        contents.len(),
        contents.values().map(|v| v.len()).sum::<usize>()
    );

    Ok(SourceFiles {
        manifest: SourceManifest {
            version: 1,
            files: manifest_files,
        },
        contents,
    })
}

/// Add source files to an existing ZIP writer.
///
/// Writes `__source/manifest.json` and all source file contents under `__source/`.
pub fn add_source_to_zip<W: std::io::Write + std::io::Seek>(
    zip: &mut zip::ZipWriter<W>,
    source_files: &SourceFiles,
) -> Result<()> {
    let options = zip::write::SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);

    // Write manifest
    let manifest_json = serde_json::to_vec_pretty(&source_files.manifest)?;
    zip.start_file("__source/manifest.json", options)?;
    std::io::Write::write_all(zip, &manifest_json)?;

    // Write source files
    for (zip_path, data) in &source_files.contents {
        zip.start_file(zip_path.clone(), options)?;
        std::io::Write::write_all(zip, data)?;
    }

    Ok(())
}

/// Build disambiguated relative paths for ZIP storage.
///
/// For a set of absolute paths, this creates short relative paths that are unique.
/// If two files have the same filename, it includes parent directory components
/// until they're disambiguated.
fn build_zip_relative_paths(paths: &[&str]) -> Vec<String> {
    // Start with just the filename
    let mut result: Vec<String> = paths
        .iter()
        .map(|p| {
            Path::new(p)
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("unknown")
                .to_string()
        })
        .collect();

    // Find and resolve duplicates by adding parent components
    let max_iterations = 10; // Safety limit
    for _ in 0..max_iterations {
        let mut seen: HashMap<String, Vec<usize>> = HashMap::new();
        for (i, name) in result.iter().enumerate() {
            seen.entry(name.clone()).or_default().push(i);
        }

        let mut has_duplicates = false;
        for indices in seen.values() {
            if indices.len() > 1 {
                has_duplicates = true;
                for &idx in indices {
                    // Add one more parent component
                    let components: Vec<&str> =
                        paths[idx].split('/').filter(|s| !s.is_empty()).collect();
                    let current_depth = result[idx].matches('/').count() + 1;
                    let new_depth = (current_depth + 1).min(components.len());
                    let start = components.len().saturating_sub(new_depth);
                    result[idx] = components[start..].join("/");
                }
            }
        }

        if !has_duplicates {
            break;
        }
    }

    result
}

/// Read source from a dSYM ZIP that was loaded into memory.
/// Used by Cymbal to extract source files from the uploaded bundle.
pub fn read_source_manifest_from_zip(
    archive: &mut zip::ZipArchive<Cursor<Vec<u8>>>,
) -> Option<SourceManifest> {
    let mut manifest_file = archive.by_name("__source/manifest.json").ok()?;
    let mut manifest_data = Vec::new();
    std::io::Read::read_to_end(&mut manifest_file, &mut manifest_data).ok()?;
    serde_json::from_slice(&manifest_data).ok()
}

/// Load all source file contents from a dSYM ZIP using the manifest.
pub fn load_sources_from_zip(
    archive: &mut zip::ZipArchive<Cursor<Vec<u8>>>,
    manifest: &SourceManifest,
) -> HashMap<String, String> {
    let mut sources = HashMap::new();

    for (dwarf_path, zip_path) in &manifest.files {
        if let Ok(mut file) = archive.by_name(zip_path) {
            let mut content = String::new();
            if std::io::Read::read_to_string(&mut file, &mut content).is_ok() {
                sources.insert(dwarf_path.clone(), content);
            }
        }
    }

    sources
}
