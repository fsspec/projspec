/// Content types — read-only descriptive information extracted from a project.
/// Each variant maps 1-to-1 to a Python BaseContent subclass.
/// All variants carry `serde` attributes so they round-trip to/from the
/// Python `to_dict(compact=False)` JSON format (`{"klass": ["content", "<name>"], ...}`).

use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use crate::types::{Precision, Stack};

// ---------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Environment {
    pub stack: Stack,
    pub precision: Precision,
    pub packages: Vec<String>,
    #[serde(default)]
    pub channels: Vec<String>,
}

// ---------------------------------------------------------------------------
// Command
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum CmdValue {
    List(Vec<String>),
    Str(String),
}

impl CmdValue {
    pub fn display(&self) -> String {
        match self {
            CmdValue::List(v) => v.join(" "),
            CmdValue::Str(s) => s.clone(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Command {
    pub cmd: CmdValue,
}

// ---------------------------------------------------------------------------
// Metadata
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DescriptiveMetadata {
    pub meta: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Citation {
    pub meta: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct License {
    #[serde(default = "unknown_str")]
    pub shortname: String,
    #[serde(default = "unknown_str")]
    pub fullname: String,
    #[serde(default)]
    pub url: String,
}

fn unknown_str() -> String {
    "unknown".to_string()
}

// ---------------------------------------------------------------------------
// Package types
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PythonPackage {
    pub package_name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RustModule {
    pub name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodePackage {
    pub name: String,
}

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TabularData {
    pub name: String,
    #[serde(default)]
    pub schema: serde_json::Value,
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataResource {
    pub path: String,
    pub format: String,
    #[serde(default)]
    pub modality: String,
    #[serde(default)]
    pub layout: String,
    #[serde(default)]
    pub file_count: u64,
    #[serde(default)]
    pub total_size: u64,
    #[serde(default)]
    pub schema: serde_json::Value,
    #[serde(default)]
    pub sample_path: String,
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IntakeSource {
    pub name: String,
}

// ---------------------------------------------------------------------------
// Environment variables
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnvironmentVariables {
    pub variables: HashMap<String, Option<String>>,
}

// ---------------------------------------------------------------------------
// The main Content enum — one variant per concrete type
// ---------------------------------------------------------------------------

/// A named group of Content items of the same type, keyed by an identifying label.
/// This mirrors the Python AttrDict nesting: `{"environment": {"default": ..., "test": ...}}`.
pub type ContentGroup = HashMap<String, Content>;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "klass_name", rename_all = "snake_case")]
pub enum Content {
    // single items
    Environment(Environment),
    Command(Command),
    DescriptiveMetadata(DescriptiveMetadata),
    Citation(Citation),
    License(License),
    PythonPackage(PythonPackage),
    RustModule(RustModule),
    NodePackage(NodePackage),
    TabularData(TabularData),
    DataResource(DataResource),
    IntakeSource(IntakeSource),
    EnvironmentVariables(EnvironmentVariables),
    // grouped (multiple of same type, keyed by name)
    Group(ContentGroup),
    // list form (used by some specs that return plain lists)
    List(Vec<Content>),
    // raw JSON catch-all (DVCRepo remotes, Django apps, etc.)
    Raw(serde_json::Value),
}

impl Content {
    /// Human-readable one-line summary for text output.
    pub fn summary(&self) -> String {
        match self {
            Content::Environment(e) => {
                format!("Environment({}, {}, {} pkgs)", e.stack, e.precision, e.packages.len())
            }
            Content::Command(c) => format!("Command({})", c.cmd.display()),
            Content::DescriptiveMetadata(m) => {
                let keys: Vec<_> = m.meta.keys().cloned().collect();
                format!("DescriptiveMetadata({})", keys.join(", "))
            }
            Content::Citation(_) => "Citation".to_string(),
            Content::License(l) => format!("License({})", l.shortname),
            Content::PythonPackage(p) => format!("PythonPackage({})", p.package_name),
            Content::RustModule(r) => format!("RustModule({})", r.name),
            Content::NodePackage(n) => format!("NodePackage({})", n.name),
            Content::TabularData(t) => format!("TabularData({})", t.name),
            Content::DataResource(d) => format!("DataResource({}, {})", d.path, d.format),
            Content::IntakeSource(i) => format!("IntakeSource({})", i.name),
            Content::EnvironmentVariables(ev) => {
                format!("EnvironmentVariables({} vars)", ev.variables.len())
            }
            Content::Group(g) => {
                let entries: Vec<_> = g.iter().map(|(k, v)| format!("{k}: {}", v.summary())).collect();
                format!("{{{}}}", entries.join(", "))
            }
            Content::List(l) => format!("[{}]", l.iter().map(|c| c.summary()).collect::<Vec<_>>().join(", ")),
            Content::Raw(v) => format!("Raw({})", v),
        }
    }
}
