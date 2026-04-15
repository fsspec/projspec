/// project.rs — Project struct and resolve logic.
/// Mirrors projspec.proj.base.Project.

use std::collections::HashMap;
use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value as JsVal;

use crate::artifact::Artifact;
use crate::content::Content;
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
    /// Original path as supplied by the caller.
    pub path: String,
    /// Canonical absolute path.
    pub url: String,
    /// Matched project specs (not extras).
    pub specs: HashMap<String, ParsedSpec>,
    /// Contents from ProjectExtra specs (merged into root).
    pub contents: HashMap<String, Content>,
    /// Artifacts from ProjectExtra specs (merged into root).
    pub artifacts: HashMap<String, Artifact>,
    /// Child projects found by walking subdirectories.
    pub children: HashMap<String, Project>,
}

impl Project {
    /// Parse a directory and return a Project.
    pub fn new(
        path: &str,
        walk: Option<bool>,
        types: Option<&[String]>,
        xtypes: Option<&[String]>,
        excludes: Option<&std::collections::HashSet<String>>,
    ) -> Result<Self> {
        let canonical = std::fs::canonicalize(path)
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|_| path.to_string());

        let default_exc = default_excludes();
        let excludes = excludes.unwrap_or(&default_exc);

        let mut proj = Project {
            path: path.to_string(),
            url: canonical.clone(),
            specs: HashMap::new(),
            contents: HashMap::new(),
            artifacts: HashMap::new(),
            children: HashMap::new(),
        };

        proj.resolve(&canonical, walk, types, xtypes, excludes)?;
        Ok(proj)
    }

    fn resolve(
        &mut self,
        url: &str,
        walk: Option<bool>,
        types: Option<&[String]>,
        xtypes: Option<&[String]>,
        excludes: &std::collections::HashSet<String>,
    ) -> Result<()> {
        // Build basenames map
        let basenames = build_basenames(url)?;

        // Parse pyproject.toml
        let pyproject: JsVal = basenames.get("pyproject.toml")
            .and_then(|p| std::fs::read_to_string(p).ok())
            .and_then(|text| toml::from_str::<toml::Value>(&text).ok())
            .map(|v| toml_to_json(v))
            .unwrap_or(JsVal::Object(Default::default()));

        let ctx = ParseCtx {
            url,
            basenames: &basenames,
            pyproject: &pyproject,
        };

        // Run all parsers
        for (spec_name, parser_fn) in all_parsers() {
            // filter by types/xtypes
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
                    // merge into root
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

        // Walk child directories
        let should_walk = match walk {
            Some(true) => true,
            Some(false) => false,
            None => self.specs.is_empty(), // default: walk only if root matched nothing
        };

        if should_walk {
            if let Ok(rd) = std::fs::read_dir(url) {
                for entry in rd.filter_map(|e| e.ok()) {
                    let meta = entry.metadata();
                    if meta.map(|m| !m.is_dir()).unwrap_or(true) { continue; }
                    let basename = entry.file_name().to_string_lossy().to_string();
                    if excludes.contains(&basename) || basename.starts_with('.') || basename.starts_with('_') {
                        continue;
                    }
                    let child_url = entry.path().to_string_lossy().to_string();
                    if let Ok(child) = Project::new(&child_url, walk.map(|_| false), types, xtypes, Some(excludes)) {
                        if !child.specs.is_empty() {
                            self.children.insert(basename, child);
                        } else if !child.children.is_empty() {
                            // flatten one level (matches Python behaviour)
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
            for (k, a) in &spec.artifacts {
                out.push((k, a));
            }
        }
        for (k, a) in &self.artifacts {
            out.push((k, a));
        }
        out
    }

    pub fn all_contents(&self) -> Vec<(&str, &Content)> {
        let mut out: Vec<(&str, &Content)> = vec![];
        for spec in self.specs.values() {
            for (k, c) in &spec.contents {
                out.push((k, c));
            }
        }
        for (k, c) in &self.contents {
            out.push((k, c));
        }
        out
    }

    /// Find an artifact by qualified name: `[spec.]type[.name]`
    pub fn find_artifact(&self, qname: &str) -> Option<(&Artifact, &str)> {
        let parts: Vec<&str> = qname.splitn(3, '.').collect();
        match parts.as_slice() {
            [artifact_type] => {
                // search all specs
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
    // JSON serialisation (compact=false for library)
    // -----------------------------------------------------------------------

    pub fn to_json(&self) -> serde_json::Value {
        // Build a clean JSON representation that avoids serde tag issues.
        fn content_to_json(c: &Content) -> serde_json::Value {
            // Delegate to serde but wrap with type tag manually
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
        // Our to_json() produces a custom shape; rebuild a Project from it.
        // We reconstruct only the fields needed for library listing and filtering.
        // Full round-trip of Content/Artifact detail is not guaranteed — shapes
        // are stored as Raw JSON for rich display, then deserialized on demand.
        let path = v.get("path").and_then(|x| x.as_str()).unwrap_or("").to_string();
        let url  = v.get("url").and_then(|x| x.as_str()).unwrap_or(&path).to_string();

        let specs = v.get("specs").and_then(|x| x.as_object()).map(|obj| {
            obj.iter().map(|(k, spec_val)| {
                let name = spec_val.get("name").and_then(|x| x.as_str()).unwrap_or(k).to_string();
                let spec_doc = spec_val.get("spec_doc").and_then(|x| x.as_str()).unwrap_or("").to_string();
                (k.clone(), ParsedSpec {
                    name,
                    spec_doc,
                    contents: HashMap::new(),  // not round-tripped for now
                    artifacts: HashMap::new(), // not round-tripped for now
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

/// Build {basename: full_path} for every entry in a directory.
pub fn build_basenames(url: &str) -> Result<HashMap<String, String>> {
    let mut map = HashMap::new();
    let rd = std::fs::read_dir(url)?;
    for entry in rd.filter_map(|e| e.ok()) {
        let basename = entry.file_name().to_string_lossy().to_string();
        let full = entry.path().to_string_lossy().to_string();
        map.insert(basename, full);
    }
    Ok(map)
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

/// Compare a user-supplied name (camelCase or snake_case) with a registry key (snake_case).
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
