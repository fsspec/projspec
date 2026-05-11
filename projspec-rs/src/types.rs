/// Enums that mirror Python's projspec.content.environment.Stack/Precision
/// and projspec.artifact.installable.Architecture.

use serde::{Deserialize, Serialize};

/// Packaging technology for an Environment.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum Stack {
    Pip,
    Conda,
    Npm,
}

impl std::fmt::Display for Stack {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Stack::Pip => write!(f, "PIP"),
            Stack::Conda => write!(f, "CONDA"),
            Stack::Npm => write!(f, "NPM"),
        }
    }
}

/// How precisely an environment specification is pinned.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum Precision {
    Spec,
    Lock,
}

impl std::fmt::Display for Precision {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Precision::Spec => write!(f, "SPEC"),
            Precision::Lock => write!(f, "LOCK"),
        }
    }
}

/// Target platform / architecture for system-installable packages.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum Architecture {
    Android,
    Ios,
    Linux,
    Macos,
    Web,
    Windows,
}

impl std::fmt::Display for Architecture {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            Architecture::Android => "android",
            Architecture::Ios => "iOS",
            Architecture::Linux => "linux",
            Architecture::Macos => "macOS",
            Architecture::Web => "web",
            Architecture::Windows => "windows",
        };
        write!(f, "{s}")
    }
}
