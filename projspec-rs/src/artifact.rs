/// Artifact types — executable actions or producible outputs.
/// Each variant maps to a Python BaseArtifact subclass.
///
/// Unlike the Python version which holds a live subprocess handle, the Rust
/// version models the *description* (cmd, fn_glob, etc.) separately from
/// the *execution result* (MakeResult).  Execution is done by `make()`.

use std::collections::HashMap;
use std::process::{Command as StdCommand, Stdio};
use anyhow::{Result, Context};
use serde::{Deserialize, Serialize};
use crate::types::Architecture;

// ---------------------------------------------------------------------------
// Make result — what make() returns to the caller
// ---------------------------------------------------------------------------

/// The outcome of executing an artifact.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum MakeResult {
    /// A long-running process was spawned; its PID is returned.
    /// The process is left running.
    ProcessSpawned { pid: u32, cmd: Vec<String> },
    /// A file artifact was produced; here are the paths.
    FilesProduced(Vec<String>),
    /// The artifact ran to completion (process exited 0) but produces no files.
    Completed { cmd: Vec<String>, stdout: String, stderr: String },
    /// Deployment-style action (e.g. helm upgrade).
    Deployed { release: String },
}

impl std::fmt::Display for MakeResult {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            MakeResult::ProcessSpawned { pid, cmd } => {
                write!(f, "Process spawned (pid={pid}): {}", cmd.join(" "))
            }
            MakeResult::FilesProduced(files) => {
                write!(f, "Files produced: {}", files.join(", "))
            }
            MakeResult::Completed { cmd, stdout, stderr } => {
                write!(f, "Completed: {}\n{}{}", cmd.join(" "), stdout, stderr)
            }
            MakeResult::Deployed { release } => {
                write!(f, "Deployed release: {release}")
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Artifact state
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ArtifactState {
    Clean,
    Done,
    Pending,
    Unknown,
}

impl std::fmt::Display for ArtifactState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ArtifactState::Clean => write!(f, "clean"),
            ArtifactState::Done => write!(f, "done"),
            ArtifactState::Pending => write!(f, "pending"),
            ArtifactState::Unknown => write!(f, ""),
        }
    }
}

// ---------------------------------------------------------------------------
// Individual artifact kinds
// ---------------------------------------------------------------------------

/// Common fields shared by all artifacts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArtifactBase {
    /// The command to run to produce/launch this artifact.
    pub cmd: Vec<String>,
}

/// A `FileArtifact` — output is one or more files matched by a glob.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileArtifact {
    #[serde(flatten)]
    pub base: ArtifactBase,
    /// Glob pattern for the expected output file(s).
    pub fn_glob: String,
}

impl FileArtifact {
    pub fn state(&self) -> ArtifactState {
        let matches = glob::glob(&self.fn_glob)
            .map(|paths| paths.filter_map(|p| p.ok()).count())
            .unwrap_or(0);
        if matches > 0 {
            ArtifactState::Done
        } else {
            ArtifactState::Clean
        }
    }

    pub fn make(&self, cwd: &str) -> Result<MakeResult> {
        run_to_completion(&self.base.cmd, cwd)?;
        // Re-glob to find what was produced
        let files: Vec<String> = glob::glob(&self.fn_glob)
            .context("glob error")?
            .filter_map(|p| p.ok())
            .map(|p| p.to_string_lossy().to_string())
            .collect();
        Ok(MakeResult::FilesProduced(files))
    }

    pub fn clean(&self) -> Result<()> {
        let files: Vec<_> = glob::glob(&self.fn_glob)
            .context("glob error")?
            .filter_map(|p| p.ok())
            .collect();
        for f in files {
            std::fs::remove_file(&f)
                .with_context(|| format!("removing {}", f.display()))?;
        }
        Ok(())
    }
}

/// A `Process` — a subprocess (batch or long-running).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Process {
    #[serde(flatten)]
    pub base: ArtifactBase,
    /// If true, this is a server that should stay running.
    #[serde(default)]
    pub server: bool,
    /// Optional port argument name (e.g. "--server.port")
    #[serde(default)]
    pub port_arg: Option<String>,
    /// Optional address argument name (e.g. "--server.address")
    #[serde(default)]
    pub address_arg: Option<String>,
}

impl Process {
    pub fn make(&self, cwd: &str, port: Option<u16>, address: Option<&str>, wait: bool) -> Result<MakeResult> {
        let mut cmd = self.base.cmd.clone();
        if let (Some(port), Some(arg)) = (port, &self.port_arg) {
            cmd.push(arg.clone());
            cmd.push(port.to_string());
        }
        if let (Some(addr), Some(arg)) = (address, &self.address_arg) {
            cmd.push(arg.clone());
            cmd.push(addr.to_string());
        }

        if self.server || !wait {
            // spawn and leave running
            let child = StdCommand::new(&cmd[0])
                .args(&cmd[1..])
                .current_dir(cwd)
                .spawn()
                .with_context(|| format!("spawning {}", cmd.join(" ")))?;
            let pid = child.id();
            // leak the child so process keeps running
            std::mem::forget(child);
            Ok(MakeResult::ProcessSpawned { pid, cmd })
        } else {
            run_to_completion(&cmd, cwd)
        }
    }
}

/// A `LockFile` — a file artifact where the output is a lock file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LockFile {
    #[serde(flatten)]
    pub file: FileArtifact,
}

/// A `VirtualEnv` — a Python virtual environment directory.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VirtualEnv {
    #[serde(flatten)]
    pub file: FileArtifact,
}

/// A `CondaEnv` — a conda environment directory.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CondaEnv {
    #[serde(flatten)]
    pub file: FileArtifact,
}

/// A `EnvPack` — a packed environment archive.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnvPack {
    #[serde(flatten)]
    pub file: FileArtifact,
}

/// A Python wheel.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Wheel {
    #[serde(flatten)]
    pub file: FileArtifact,
}

/// A conda package.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CondaPackage {
    #[serde(flatten)]
    pub file: FileArtifact,
    #[serde(default)]
    pub name: Option<String>,
}

/// A system-installable package (deb, rpm, msi, dmg, …).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemInstallablePackage {
    #[serde(flatten)]
    pub file: FileArtifact,
    pub arch: Architecture,
    pub filetype: String,
}

/// A Docker image.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DockerImage {
    pub cmd: Vec<String>,
    #[serde(default)]
    pub tag: Option<String>,
}

impl DockerImage {
    pub fn new(tag: Option<String>) -> Self {
        let cmd = if let Some(ref t) = tag {
            vec!["docker".into(), "build".into(), ".".into(), "-t".into(), t.clone()]
        } else {
            vec!["docker".into(), "build".into(), ".".into()]
        };
        DockerImage { cmd, tag }
    }

    pub fn make(&self, cwd: &str) -> Result<MakeResult> {
        run_to_completion(&self.cmd, cwd)
    }
}

/// A Docker runtime (container running from an image).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DockerRuntime {
    pub image: DockerImage,
}

/// A Helm deployment.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HelmDeployment {
    pub release: String,
    pub cmd: Vec<String>,
    pub clean_cmd: Vec<String>,
}

impl HelmDeployment {
    pub fn new(release: &str) -> Self {
        HelmDeployment {
            release: release.to_string(),
            cmd: vec!["helm".into(), "upgrade".into(), "--install".into(), release.into(), ".".into()],
            clean_cmd: vec!["helm".into(), "uninstall".into(), release.into()],
        }
    }

    pub fn state(&self) -> ArtifactState {
        let status = StdCommand::new("helm")
            .args(["status", &self.release])
            .output();
        match status {
            Ok(out) if out.status.success() => ArtifactState::Done,
            _ => ArtifactState::Clean,
        }
    }

    pub fn make(&self, cwd: &str) -> Result<MakeResult> {
        run_to_completion(&self.cmd, cwd)?;
        Ok(MakeResult::Deployed { release: self.release.clone() })
    }

    pub fn clean(&self, cwd: &str) -> Result<()> {
        run_to_completion(&self.clean_cmd, cwd)?;
        Ok(())
    }
}

/// A `PreCommit` artifact.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PreCommit {
    pub cmd: Vec<String>,
}

impl Default for PreCommit {
    fn default() -> Self {
        PreCommit { cmd: vec!["pre-commit".into(), "run".into(), "-a".into()] }
    }
}

// ---------------------------------------------------------------------------
// The main Artifact enum
// ---------------------------------------------------------------------------

/// Named group of artifacts of the same kind, keyed by label (e.g. "debug"/"release").
pub type ArtifactGroup = HashMap<String, Artifact>;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "klass_name", rename_all = "snake_case")]
pub enum Artifact {
    FileArtifact(FileArtifact),
    Process(Process),
    LockFile(LockFile),
    VirtualEnv(VirtualEnv),
    CondaEnv(CondaEnv),
    EnvPack(EnvPack),
    Wheel(Wheel),
    CondaPackage(CondaPackage),
    SystemInstallablePackage(SystemInstallablePackage),
    DockerImage(DockerImage),
    DockerRuntime(DockerRuntime),
    HelmDeployment(HelmDeployment),
    PreCommit(PreCommit),
    /// Multiple artifacts of the same kind, keyed by a label.
    Group(ArtifactGroup),
}

impl Artifact {
    pub fn summary(&self) -> String {
        match self {
            Artifact::FileArtifact(fa) => {
                format!("FileArtifact({}, {})", fa.base.cmd.join(" "), fa.state())
            }
            Artifact::Process(p) => format!("Process({})", p.base.cmd.join(" ")),
            Artifact::LockFile(lf) => {
                format!("LockFile({}, {})", lf.file.base.cmd.join(" "), lf.file.state())
            }
            Artifact::VirtualEnv(ve) => {
                format!("VirtualEnv({}, {})", ve.file.base.cmd.join(" "), ve.file.state())
            }
            Artifact::CondaEnv(ce) => {
                format!("CondaEnv({}, {})", ce.file.base.cmd.join(" "), ce.file.state())
            }
            Artifact::EnvPack(ep) => {
                format!("EnvPack({}, {})", ep.file.base.cmd.join(" "), ep.file.state())
            }
            Artifact::Wheel(w) => {
                format!("Wheel({}, {})", w.file.base.cmd.join(" "), w.file.state())
            }
            Artifact::CondaPackage(cp) => {
                format!("CondaPackage({}, {})", cp.file.base.cmd.join(" "), cp.file.state())
            }
            Artifact::SystemInstallablePackage(sip) => {
                format!("SystemInstallablePackage({}, {})", sip.file.base.cmd.join(" "), sip.arch)
            }
            Artifact::DockerImage(di) => format!("DockerImage({})", di.cmd.join(" ")),
            Artifact::DockerRuntime(_) => "DockerRuntime".to_string(),
            Artifact::HelmDeployment(hd) => format!("HelmDeployment({})", hd.release),
            Artifact::PreCommit(pc) => format!("PreCommit({})", pc.cmd.join(" ")),
            Artifact::Group(g) => {
                let entries: Vec<_> = g.iter().map(|(k, v)| format!("{k}: {}", v.summary())).collect();
                format!("{{{}}}", entries.join(", "))
            }
        }
    }

    /// Execute this artifact.
    /// `wait`: for Process artifacts, whether to wait for completion.
    pub fn make(&self, cwd: &str, wait: bool) -> Result<MakeResult> {
        match self {
            Artifact::FileArtifact(fa) => fa.make(cwd),
            Artifact::Process(p) => p.make(cwd, None, None, wait),
            Artifact::LockFile(lf) => lf.file.make(cwd),
            Artifact::VirtualEnv(ve) => ve.file.make(cwd),
            Artifact::CondaEnv(ce) => ce.file.make(cwd),
            Artifact::EnvPack(ep) => ep.file.make(cwd),
            Artifact::Wheel(w) => w.file.make(cwd),
            Artifact::CondaPackage(cp) => cp.file.make(cwd),
            Artifact::SystemInstallablePackage(sip) => sip.file.make(cwd),
            Artifact::DockerImage(di) => di.make(cwd),
            Artifact::DockerRuntime(dr) => dr.image.make(cwd),
            Artifact::HelmDeployment(hd) => hd.make(cwd),
            Artifact::PreCommit(pc) => run_to_completion(&pc.cmd, cwd),
            Artifact::Group(g) => {
                // make the first entry in the group
                if let Some((_, first)) = g.iter().next() {
                    first.make(cwd, wait)
                } else {
                    anyhow::bail!("empty artifact group")
                }
            }
        }
    }

    /// Return the state of this artifact.
    pub fn state(&self) -> ArtifactState {
        match self {
            Artifact::FileArtifact(fa) => fa.state(),
            Artifact::LockFile(lf) => lf.file.state(),
            Artifact::VirtualEnv(ve) => ve.file.state(),
            Artifact::CondaEnv(ce) => ce.file.state(),
            Artifact::EnvPack(ep) => ep.file.state(),
            Artifact::Wheel(w) => w.file.state(),
            Artifact::CondaPackage(cp) => cp.file.state(),
            Artifact::SystemInstallablePackage(sip) => sip.file.state(),
            Artifact::HelmDeployment(hd) => hd.state(),
            _ => ArtifactState::Unknown,
        }
    }

    /// Remove / stop this artifact.
    pub fn clean(&self, cwd: &str) -> Result<()> {
        match self {
            Artifact::FileArtifact(fa) => fa.clean(),
            Artifact::LockFile(lf) => lf.file.clean(),
            Artifact::VirtualEnv(ve) => ve.file.clean(),
            Artifact::CondaEnv(ce) => ce.file.clean(),
            Artifact::EnvPack(ep) => ep.file.clean(),
            Artifact::Wheel(w) => w.file.clean(),
            Artifact::CondaPackage(cp) => cp.file.clean(),
            Artifact::SystemInstallablePackage(sip) => sip.file.clean(),
            Artifact::HelmDeployment(hd) => hd.clean(cwd),
            _ => Ok(()),
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Run a command synchronously, return stdout+stderr as MakeResult::Completed.
pub fn run_to_completion(cmd: &[String], cwd: &str) -> Result<MakeResult> {
    anyhow::ensure!(!cmd.is_empty(), "empty command");
    let output = StdCommand::new(&cmd[0])
        .args(&cmd[1..])
        .current_dir(cwd)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .with_context(|| format!("running {}", cmd.join(" ")))?;

    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();

    if !output.status.success() {
        anyhow::bail!(
            "command `{}` failed (exit {})\nstdout: {stdout}\nstderr: {stderr}",
            cmd.join(" "),
            output.status
        );
    }
    Ok(MakeResult::Completed { cmd: cmd.to_vec(), stdout, stderr })
}

/// Resolve glob and return existing paths (for FileArtifact state checks).
pub fn glob_paths(pattern: &str) -> Vec<String> {
    glob::glob(pattern)
        .map(|paths| {
            paths
                .filter_map(|p| p.ok())
                .map(|p| p.to_string_lossy().to_string())
                .collect()
        })
        .unwrap_or_default()
}
