/// Config — mirrors projspec.config.
/// Reads/writes ~/.config/projspec/projspec.json.
/// Individual values can be overridden by PROJSPEC_<KEY> env vars.

use std::path::PathBuf;
use anyhow::Result;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    #[serde(default = "default_library_path_str")]
    pub library_path: String,
    #[serde(default = "default_scan_types")]
    pub scan_types: Vec<String>,
    #[serde(default = "default_scan_max_files")]
    pub scan_max_files: usize,
    #[serde(default = "default_scan_max_size")]
    pub scan_max_size: u64,
    #[serde(default = "default_false")]
    pub remote_artifact_status: bool,
    #[serde(default = "default_true")]
    pub capture_artifact_output: bool,
}

fn default_config_dir() -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("projspec")
}

fn default_library_path_str() -> String {
    default_config_dir()
        .join("library.json")
        .to_string_lossy()
        .to_string()
}

fn default_scan_types() -> Vec<String> {
    vec![
        ".py".into(), ".yaml".into(), ".yml".into(),
        ".toml".into(), ".json".into(), ".md".into(),
    ]
}
fn default_scan_max_files() -> usize { 100 }
fn default_scan_max_size() -> u64 { 5 * 1024 }
fn default_false() -> bool { false }
fn default_true() -> bool { true }

impl Default for Config {
    fn default() -> Self {
        Config {
            library_path: default_library_path_str(),
            scan_types: default_scan_types(),
            scan_max_files: default_scan_max_files(),
            scan_max_size: default_scan_max_size(),
            remote_artifact_status: false,
            capture_artifact_output: true,
        }
    }
}

impl Config {
    /// Load config from file, falling back to defaults for missing values.
    pub fn load() -> Self {
        let path = Self::config_file();
        let mut cfg = if path.exists() {
            let content = std::fs::read_to_string(&path).unwrap_or_default();
            serde_json::from_str(&content).unwrap_or_default()
        } else {
            Config::default()
        };

        // env-var overrides
        if let Ok(v) = std::env::var("PROJSPEC_LIBRARY_PATH") {
            cfg.library_path = v;
        }
        if let Ok(v) = std::env::var("PROJSPEC_SCAN_MAX_FILES") {
            if let Ok(n) = v.parse() { cfg.scan_max_files = n; }
        }
        if let Ok(v) = std::env::var("PROJSPEC_SCAN_MAX_SIZE") {
            if let Ok(n) = v.parse() { cfg.scan_max_size = n; }
        }
        if let Ok(v) = std::env::var("PROJSPEC_REMOTE_ARTIFACT_STATUS") {
            cfg.remote_artifact_status = matches!(v.as_str(), "true" | "True" | "1" | "T");
        }
        if let Ok(v) = std::env::var("PROJSPEC_CAPTURE_ARTIFACT_OUTPUT") {
            cfg.capture_artifact_output = matches!(v.as_str(), "true" | "True" | "1" | "T");
        }
        cfg
    }

    pub fn save(&self) -> Result<()> {
        let path = Self::config_file();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let json = serde_json::to_string_pretty(self)?;
        std::fs::write(&path, json)?;
        Ok(())
    }

    pub fn config_file() -> PathBuf {
        std::env::var("PROJSPEC_CONFIG_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|_| default_config_dir())
            .join("projspec.json")
    }

    pub fn get(&self, key: &str) -> Option<String> {
        match key {
            "library_path" => Some(self.library_path.clone()),
            "scan_max_files" => Some(self.scan_max_files.to_string()),
            "scan_max_size" => Some(self.scan_max_size.to_string()),
            "remote_artifact_status" => Some(self.remote_artifact_status.to_string()),
            "capture_artifact_output" => Some(self.capture_artifact_output.to_string()),
            _ => None,
        }
    }

    pub fn set(&mut self, key: &str, value: &str) -> Result<()> {
        match key {
            "library_path" => self.library_path = value.to_string(),
            "scan_max_files" => self.scan_max_files = value.parse()?,
            "scan_max_size" => self.scan_max_size = value.parse()?,
            "remote_artifact_status" => self.remote_artifact_status = value.parse()?,
            "capture_artifact_output" => self.capture_artifact_output = value.parse()?,
            _ => anyhow::bail!("unknown config key: {key}"),
        }
        Ok(())
    }

    pub fn unset(&mut self, key: &str) -> Result<()> {
        // reset to default
        let def = Config::default();
        match key {
            "library_path" => self.library_path = def.library_path,
            "scan_max_files" => self.scan_max_files = def.scan_max_files,
            "scan_max_size" => self.scan_max_size = def.scan_max_size,
            "remote_artifact_status" => self.remote_artifact_status = def.remote_artifact_status,
            "capture_artifact_output" => self.capture_artifact_output = def.capture_artifact_output,
            _ => anyhow::bail!("unknown config key: {key}"),
        }
        Ok(())
    }

    pub fn defaults_table() -> Vec<(&'static str, String, &'static str)> {
        let d = Config::default();
        vec![
            ("library_path", d.library_path, "location of persisted project objects"),
            ("scan_types", d.scan_types.join(", "), "file extensions automatically read for scanning"),
            ("scan_max_files", d.scan_max_files.to_string(), "don't scan files if more than this number in the project"),
            ("scan_max_size", d.scan_max_size.to_string(), "don't scan files bigger than this (bytes)"),
            ("remote_artifact_status", d.remote_artifact_status.to_string(), "whether to check status for remote artifacts"),
            ("capture_artifact_output", d.capture_artifact_output.to_string(), "capture subprocess output from Process artifacts"),
        ]
    }
}
