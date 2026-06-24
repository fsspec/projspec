/// project.rs — Project struct and resolve logic.
/// Mirrors projspec.proj.base.Project.

use std::collections::HashMap;
use anyhow::Result;
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::Value as JsVal;

use crate::artifact::Artifact;
use crate::content::Content;
use crate::fs::{Vfs, vfs_from_url};
use crate::spec::{all_parsers, ParseCtx};

// ---------------------------------------------------------------------------
// Default exclusions when walking child directories
// ---------------------------------------------------------------------------

fn default_excludes() -> std::collections::HashSet<String> {
    ["bld", "build", "dist", "env", "envs", "htmlcov", "node_modules"]
        .iter().map(|s| s.to_string()).collect()
}

// ---------------------------------------------------------------------------
// ParsedSpec — a matched spec with its contents and artifacts
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParsedSpec {
    pub name: String,
    pub spec_doc: String,
    pub contents: HashMap<String, Content>,
    pub artifacts: HashMap<String, Artifact>,
}

// ---------------------------------------------------------------------------
// Project
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Project {
    /// Original path / URL as supplied by the caller.
    pub path: String,
    /// Canonical URL (absolute local path, or s3:// / http:// URL).
    pub url: String,
    /// Matched project specs (not extras).
    pub specs: HashMap<String, ParsedSpec>,
    /// Contents from ProjectExtra specs (merged into root).
    pub contents: HashMap<String, Content>,
    /// Artifacts from ProjectExtra specs (merged into root).
    pub artifacts: HashMap<String, Artifact>,
    /// Child projects found by walking subdirectories (local only).
    pub children: HashMap<String, Project>,
}

impl Project {
    // -----------------------------------------------------------------------
    // Constructors
    // -----------------------------------------------------------------------

    /// Parse a local path or URL, building a Vfs automatically.
    pub fn new(
        path: &str,
        walk: Option<bool>,
        types: Option<&[String]>,
        xtypes: Option<&[String]>,
        excludes: Option<&std::collections::HashSet<String>>,
    ) -> Result<Self> {
        let (vfs, url) = vfs_from_url(path)?;
        Self::new_with_vfs(path, &url, vfs, walk, types, xtypes, excludes)
    }

    /// Parse a project given an already-constructed Vfs.
    /// `display_path` is used as the `path` field (user-facing).
    /// `url` is the canonical location identifier.
    /// The Vfs root must be set to the project root already.
    pub fn new_with_vfs(
        display_path: &str,
        url: &str,
        vfs: Vfs,
        walk: Option<bool>,
        types: Option<&[String]>,
        xtypes: Option<&[String]>,
        excludes: Option<&std::collections::HashSet<String>>,
    ) -> Result<Self> {
        let default_exc = default_excludes();
        let excludes = excludes.unwrap_or(&default_exc);

        let mut proj = Project {
            path: display_path.to_string(),
            url: url.to_string(),
            specs: HashMap::new(),
            contents: HashMap::new(),
            artifacts: HashMap::new(),
            children: HashMap::new(),
        };

        proj.resolve(url, &vfs, walk, types, xtypes, excludes)?;
        Ok(proj)
    }

    fn resolve(
        &mut self,
        url: &str,
        vfs: &Vfs,
        walk: Option<bool>,
        types: Option<&[String]>,
        xtypes: Option<&[String]>,
        excludes: &std::collections::HashSet<String>,
    ) -> Result<()> {
        // Build basenames map via Vfs
        let basenames = vfs.basenames();

        // Parse pyproject.toml via Vfs (needed before prefetch so parsers can
        // filter on build-backend / tool table without re-reading the file).
        // pyproject.toml is intentionally read here rather than in the prefetch
        // because it drives which other files are worth reading.
        let pyproject: JsVal = basenames.get("pyproject.toml")
            .and_then(|rel| vfs.read_text(rel))
            .and_then(|text| toml::from_str::<toml::Value>(&text).ok())
            .map(toml_to_json)
            .unwrap_or(JsVal::Object(Default::default()));

        // --- Concurrent prefetch ---
        // Build the lists of files and sub-paths to check in parallel, then
        // fire all reads/stats concurrently via rayon.  This collapses N
        // sequential network round-trips into ~1 round-trip worth of latency
        // for HTTP and S3 backends.
        let file_names = files_to_prefetch(&basenames, &pyproject);
        let sub_paths  = subpaths_to_prefetch();

        // Parallel file reads: only fetch files that are present in basenames.
        let file_cache: HashMap<String, String> = file_names
            .par_iter()
            .filter_map(|name| {
                let rel = basenames.get(*name)?;
                let text = vfs.read_text(rel)?;
                Some((name.to_string(), text))
            })
            .collect();

        // Parallel existence checks for sub-paths below the root.
        let exists_cache: HashMap<String, bool> = sub_paths
            .par_iter()
            .map(|path| (path.to_string(), vfs.exists(path)))
            .collect();

        let ctx = ParseCtx {
            url,
            basenames: &basenames,
            pyproject: &pyproject,
            vfs,
            file_cache: &file_cache,
            exists_cache: &exists_cache,
        };

        // Run all parsers
        for (spec_name, parser_fn) in all_parsers() {
            if let Some(types) = types {
                if !types.is_empty() && !types.iter().any(|t| camel_or_snake_eq(t, spec_name)) {
                    continue;
                }
            }
            if let Some(xtypes) = xtypes {
                if xtypes.iter().any(|t| camel_or_snake_eq(t, spec_name)) {
                    continue;
                }
            }

            if let Some(result) = parser_fn(&ctx) {
                if result.is_extra {
                    self.contents.extend(result.contents);
                    self.artifacts.extend(result.artifacts);
                } else {
                    self.specs.insert(result.spec_name.clone(), ParsedSpec {
                        name: result.spec_name,
                        spec_doc: result.spec_doc,
                        contents: result.contents,
                        artifacts: result.artifacts,
                    });
                }
            }
        }

        // Walk child directories — only supported for local Fs backend
        // (opendal::Http and S3 list_dir would require recursive listing)
        let should_walk = match walk {
            Some(true) => true,
            Some(false) => false,
            None => self.specs.is_empty(),
        };

        if should_walk && vfs.scheme == "file" {
            for basename in vfs.list_dir("") {
                if excludes.contains(&basename) || basename.starts_with('.') || basename.starts_with('_') {
                    continue;
                }
                // Check it is a directory by trying to list it
                let sub_entries = vfs.list_dir(&basename);
                if sub_entries.is_empty() { continue; }

                let child_url = format!("{url}/{basename}");
                if let Ok(child_vfs) = Vfs::local(&child_url) {
                    let child_result = Project::new_with_vfs(
                        &child_url,
                        &child_url,
                        child_vfs,
                        walk.map(|_| false),
                        types,
                        xtypes,
                        Some(excludes),
                    );
                    if let Ok(child) = child_result {
                        if !child.specs.is_empty() {
                            self.children.insert(basename, child);
                        } else if !child.children.is_empty() {
                            for (s2, p) in child.children {
                                self.children.insert(format!("{basename}/{s2}"), p);
                            }
                        }
                    }
                }
            }
        }
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Query helpers
    // -----------------------------------------------------------------------

    pub fn has_spec(&self, name: &str) -> bool {
        self.specs.contains_key(name)
            || self.children.values().any(|c| c.has_spec(name))
    }

    pub fn all_artifacts(&self) -> Vec<(&str, &Artifact)> {
        let mut out: Vec<(&str, &Artifact)> = vec![];
        for spec in self.specs.values() {
            for (k, a) in &spec.artifacts { out.push((k, a)); }
        }
        for (k, a) in &self.artifacts { out.push((k, a)); }
        out
    }

    pub fn all_contents(&self) -> Vec<(&str, &Content)> {
        let mut out: Vec<(&str, &Content)> = vec![];
        for spec in self.specs.values() {
            for (k, c) in &spec.contents { out.push((k, c)); }
        }
        for (k, c) in &self.contents { out.push((k, c)); }
        out
    }

    /// Find an artifact by qualified name: `[spec.]type[.name]`
    pub fn find_artifact(&self, qname: &str) -> Option<(&Artifact, &str)> {
        let parts: Vec<&str> = qname.splitn(3, '.').collect();
        match parts.as_slice() {
            [artifact_type] => {
                for spec in self.specs.values() {
                    if let Some(a) = spec.artifacts.get(*artifact_type) {
                        return Some((a, &self.url));
                    }
                }
                self.artifacts.get(*artifact_type).map(|a| (a, self.url.as_str()))
            }
            [spec_name, artifact_type] => {
                let spec = self.specs.get(*spec_name)?;
                spec.artifacts.get(*artifact_type).map(|a| (a, self.url.as_str()))
            }
            [spec_name, artifact_type, item_name] => {
                let spec = self.specs.get(*spec_name)?;
                let art = spec.artifacts.get(*artifact_type)?;
                if let Artifact::Group(g) = art {
                    g.get(*item_name).map(|a| (a, self.url.as_str()))
                } else {
                    Some((art, self.url.as_str()))
                }
            }
            _ => None,
        }
    }

    // -----------------------------------------------------------------------
    // Text output
    // -----------------------------------------------------------------------

    pub fn text_summary(&self, bare: bool) -> String {
        let header = if bare {
            self.url.clone()
        } else {
            format!("<Project '{}'>", self.url)
        };
        let spec_names: Vec<String> = self.specs.keys().cloned().collect();
        let mut lines = vec![format!("  /: {}", spec_names.join(" "))];
        for (k, child) in &self.children {
            let cnames: Vec<String> = child.specs.keys().cloned().collect();
            lines.push(format!("  {k}: {}", cnames.join(" ")));
        }
        format!("{header}\n{}", lines.join("\n"))
    }

    pub fn text_full(&self) -> String {
        let mut lines = vec![format!("<Project '{}'>", self.url)];

        for (sname, spec) in &self.specs {
            lines.push(format!("\n<{sname}>"));
            if !spec.spec_doc.is_empty() {
                lines.push(format!("  spec_doc: {}", spec.spec_doc));
            }
            if !spec.contents.is_empty() {
                lines.push("  Contents:".to_string());
                for (k, v) in &spec.contents {
                    lines.push(format!("    {k}: {}", v.summary()));
                }
            }
            if !spec.artifacts.is_empty() {
                lines.push("  Artifacts:".to_string());
                for (k, v) in &spec.artifacts {
                    lines.push(format!("    {k}: {}", v.summary()));
                }
            }
        }

        if !self.contents.is_empty() {
            lines.push("\n<GLOBAL>".to_string());
            lines.push("  Contents:".to_string());
            for (k, v) in &self.contents {
                lines.push(format!("    {k}: {}", v.summary()));
            }
        }
        if !self.artifacts.is_empty() {
            if self.contents.is_empty() { lines.push("\n<GLOBAL>".to_string()); }
            lines.push("  Artifacts:".to_string());
            for (k, v) in &self.artifacts {
                lines.push(format!("    {k}: {}", v.summary()));
            }
        }

        if !self.children.is_empty() {
            lines.push("\nChildren:".to_string());
            for (k, child) in &self.children {
                let cnames: Vec<String> = child.specs.keys().cloned().collect();
                lines.push(format!("  {k}: {}", cnames.join(" ")));
            }
        }
        lines.join("\n")
    }

    // -----------------------------------------------------------------------
    // JSON serialisation
    // -----------------------------------------------------------------------

    pub fn to_json(&self) -> serde_json::Value {
        fn content_to_json(c: &Content) -> serde_json::Value {
            serde_json::to_value(c).unwrap_or(serde_json::Value::Null)
        }
        fn artifact_to_json(a: &Artifact) -> serde_json::Value {
            serde_json::to_value(a).unwrap_or(serde_json::Value::Null)
        }
        fn spec_to_json(s: &ParsedSpec) -> serde_json::Value {
            let contents: serde_json::Map<_, _> = s.contents.iter()
                .map(|(k, v)| (k.clone(), content_to_json(v))).collect();
            let artifacts: serde_json::Map<_, _> = s.artifacts.iter()
                .map(|(k, v)| (k.clone(), artifact_to_json(v))).collect();
            serde_json::json!({
                "name": s.name,
                "spec_doc": s.spec_doc,
                "contents": contents,
                "artifacts": artifacts,
            })
        }
        fn proj_to_json(proj: &Project) -> serde_json::Value {
            let specs: serde_json::Map<_, _> = proj.specs.iter()
                .map(|(k, v)| (k.clone(), spec_to_json(v))).collect();
            let contents: serde_json::Map<_, _> = proj.contents.iter()
                .map(|(k, v)| (k.clone(), content_to_json(v))).collect();
            let artifacts: serde_json::Map<_, _> = proj.artifacts.iter()
                .map(|(k, v)| (k.clone(), artifact_to_json(v))).collect();
            let children: serde_json::Map<_, _> = proj.children.iter()
                .map(|(k, v)| (k.clone(), proj_to_json(v))).collect();
            serde_json::json!({
                "path": proj.path,
                "url": proj.url,
                "specs": specs,
                "contents": contents,
                "artifacts": artifacts,
                "children": children,
            })
        }
        proj_to_json(self)
    }

    pub fn from_json(v: &serde_json::Value) -> Result<Self> {
        let path = v.get("path").and_then(|x| x.as_str()).unwrap_or("").to_string();
        let url  = v.get("url").and_then(|x| x.as_str()).unwrap_or(&path).to_string();

        let specs = v.get("specs").and_then(|x| x.as_object()).map(|obj| {
            obj.iter().map(|(k, spec_val)| {
                let name = spec_val.get("name").and_then(|x| x.as_str()).unwrap_or(k).to_string();
                let spec_doc = spec_val.get("spec_doc").and_then(|x| x.as_str()).unwrap_or("").to_string();
                (k.clone(), ParsedSpec {
                    name,
                    spec_doc,
                    contents: HashMap::new(),
                    artifacts: HashMap::new(),
                })
            }).collect()
        }).unwrap_or_default();

        let children = v.get("children").and_then(|x| x.as_object()).map(|obj| {
            obj.iter().filter_map(|(k, child_val)| {
                Project::from_json(child_val).ok().map(|p| (k.clone(), p))
            }).collect()
        }).unwrap_or_default();

        Ok(Project {
            path,
            url,
            specs,
            contents: HashMap::new(),
            artifacts: HashMap::new(),
            children,
        })
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Return the set of root-level files to pre-fetch concurrently before parsers run.
///
/// Strategy: fetch every file present in `basenames` whose extension (or full name)
/// is in the set of metadata types that parsers commonly read. This is purely
/// extension-driven — no per-filename maintenance is required when a new parser
/// is added, as long as it reads a recognised metadata format.
///
/// Recognised extensions / names:
///   .toml   — pixi.toml, Cargo.toml, book.toml, pyscript.toml, uv.toml, …
///   .yaml   — Chart.yaml, conda-project.yml, .readthedocs.yaml, …
///   .yml    — same (alternate extension)
///   .json   — package.json, datapackage.json, .zenodo.json, …
///   .txt    — requirements.txt, LICENSE.txt, …
///   .md     — README.md, CITATION.md, …
///   .lock   — uv.lock, poetry.lock, pixi.lock, …
///   .cff    — CITATION.cff
///   .py     — marimo content-scan (all root-level .py files)
///   .mod    — go.mod
///   .toml   — (already covered)
///
/// Extensionless special cases read by parsers:
///   MLFlow, Dockerfile, LICENSE, LICENCE, COPYING — matched by name prefix/exact.
///
/// pyproject.toml is intentionally excluded — it is read before prefetch so
/// its contents are available to seed any future dynamic candidate logic.
///
/// The file listing itself (basenames) is already a single cached VFS call made
/// at the start of resolve(); ctx.has() / ctx.has_any() are free HashMap lookups.
/// This function is only about pre-reading file *contents*, not listing.
pub fn files_to_prefetch<'a>(
    basenames: &'a HashMap<String, String>,
    _pyproject: &JsVal,
) -> Vec<&'a str> {
    /// Extensions whose files are always worth pre-fetching.
    const PREFETCH_EXTS: &[&str] = &[
        ".toml", ".yaml", ".yml", ".json",
        ".txt", ".md", ".lock", ".cff", ".py", ".mod",
    ];

    /// Extensionless basenames that parsers read by exact name.
    const PREFETCH_EXACT: &[&str] = &["MLFlow", "Dockerfile"];

    /// Prefixes for extensionless license/copying files.
    const LICENSE_PREFIXES: &[&str] = &["LICENSE", "LICENCE", "COPYING"];

    basenames
        .keys()
        // exclude pyproject.toml — read separately before prefetch
        .filter(|name| *name != "pyproject.toml")
        .filter(|name| {
            // matches a known extension?
            if PREFETCH_EXTS.iter().any(|ext| name.ends_with(ext)) {
                return true;
            }
            // exact match (MLFlow, Dockerfile)?
            if PREFETCH_EXACT.contains(&name.as_str()) {
                return true;
            }
            // license-family prefix (extensionless, e.g. "LICENSE", "COPYING")?
            LICENSE_PREFIXES.iter().any(|pfx| name.starts_with(pfx))
        })
        .map(|s| s.as_str())
        .collect()
}

/// Sub-paths below the root whose *existence* parsers check via ctx.vfs_exists().
/// These are not visible in basenames (they are inside sub-directories) so they
/// cannot be covered by the extension-based prefetch above.
///
/// Unlike files_to_prefetch, this list DOES require manual maintenance:
/// add an entry whenever a new `ctx.vfs_exists("some/sub/path")` call is added
/// to spec.rs.
pub fn subpaths_to_prefetch() -> Vec<&'static str> {
    vec![
        ".vscode/settings.json",  // parse_vscode
        ".idea",                  // parse_jetbrains
        ".project/spec.yaml",     // parse_nvidia_workbench
        "cmd",                    // parse_golang binary check
    ]
}

/// Convert toml::Value to serde_json::Value recursively.
pub fn toml_to_json(v: toml::Value) -> JsVal {
    match v {
        toml::Value::String(s) => JsVal::String(s),
        toml::Value::Integer(i) => JsVal::Number(i.into()),
        toml::Value::Float(f) => {
            serde_json::Number::from_f64(f).map(JsVal::Number).unwrap_or(JsVal::Null)
        }
        toml::Value::Boolean(b) => JsVal::Bool(b),
        toml::Value::Array(a) => JsVal::Array(a.into_iter().map(toml_to_json).collect()),
        toml::Value::Table(t) => {
            JsVal::Object(t.into_iter().map(|(k, v)| (k, toml_to_json(v))).collect())
        }
        toml::Value::Datetime(d) => JsVal::String(d.to_string()),
    }
}

fn camel_or_snake_eq(user: &str, snake: &str) -> bool {
    user == snake || camel_to_snake(user) == snake
}

fn camel_to_snake(s: &str) -> String {
    let mut out = String::new();
    for (i, ch) in s.char_indices() {
        if ch.is_ascii_uppercase() && i > 0 {
            out.push('_');
        }
        out.push(ch.to_ascii_lowercase());
    }
    out
}
