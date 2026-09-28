/// library.rs — ProjectLibrary persistence.
/// Mirrors projspec.library.ProjectLibrary.
/// Format: JSON file at library_path, dict of {url: project_dict}.

use std::collections::HashMap;
use anyhow::Result;
use serde_json::Value as JsVal;

use crate::config::Config;
use crate::project::Project;

pub struct ProjectLibrary {
    pub path: String,
    pub entries: HashMap<String, Project>,
}

impl ProjectLibrary {
    pub fn load(config: &Config) -> Self {
        let path = config.library_path.clone();
        let entries = load_entries(&path);
        ProjectLibrary { path, entries }
    }

    pub fn load_at(path: &str) -> Self {
        ProjectLibrary {
            path: path.to_string(),
            entries: load_entries(path),
        }
    }

    pub fn save(&self) -> Result<()> {
        if let Some(parent) = std::path::Path::new(&self.path).parent() {
            std::fs::create_dir_all(parent)?;
        }
        let map: HashMap<String, JsVal> = self.entries.iter()
            .map(|(k, v)| (k.clone(), v.to_json()))
            .collect();
        let json = serde_json::to_string_pretty(&map)?;
        std::fs::write(&self.path, json)?;
        Ok(())
    }

    pub fn add_entry(&mut self, url: &str, proj: Project) -> Result<()> {
        self.entries.insert(url.to_string(), proj);
        self.save()
    }

    pub fn delete_entry(&mut self, url: &str) -> Result<()> {
        if self.entries.remove(url).is_none() {
            anyhow::bail!("URL not found in library: {url}");
        }
        self.save()
    }

    pub fn clear(&mut self) -> Result<()> {
        self.entries.clear();
        if std::path::Path::new(&self.path).exists() {
            std::fs::remove_file(&self.path)?;
        }
        Ok(())
    }

    /// Filter entries by spec/artifact/content names.
    /// Each filter is ("spec"|"artifact"|"content", name).
    pub fn filter(&self, filters: &[(&str, &str)]) -> Vec<(&str, &Project)> {
        self.entries.iter()
            .filter(|(_, proj)| {
                filters.iter().all(|(cat, val)| match *cat {
                    "spec" => proj.has_spec(val),
                    "artifact" => proj.all_artifacts().iter().any(|(k, _)| *k == *val),
                    "content" => proj.all_contents().iter().any(|(k, _)| *k == *val),
                    _ => true,
                })
            })
            .map(|(k, v)| (k.as_str(), v))
            .collect()
    }
}

fn load_entries(path: &str) -> HashMap<String, Project> {
    let text = match std::fs::read_to_string(path) {
        Ok(t) => t,
        Err(_) => return HashMap::new(),
    };
    let map: HashMap<String, JsVal> = match serde_json::from_str(&text) {
        Ok(m) => m,
        Err(_) => return HashMap::new(),
    };
    map.into_iter()
        .filter_map(|(k, v)| Project::from_json(&v).ok().map(|p| (k, p)))
        .collect()
}
