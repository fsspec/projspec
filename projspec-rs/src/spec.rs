/// spec.rs — All ProjectSpec matchers and parsers.
///
/// Design decisions:
/// - Each spec is a function `parse_<name>(ctx: &ParseCtx) -> Option<SpecResult>`
///   returning None if match() fails, Some(SpecResult) if it succeeds.
/// - `ParseCtx` carries everything the parsers need: basenames, pyproject, url.
/// - ProjectExtra specs return a SpecResult with is_extra=true; their contents/
///   artifacts are merged into the root project.
/// - Parsers are intentionally lenient: if a file is missing or malformed,
///   they return a partial result rather than failing completely.
/// - YAML/TOML jinja stripping is done naively (skip lines with {%...%}).

use std::collections::HashMap;
use serde_json::Value as JsVal;

use crate::artifact::{
    Artifact, ArtifactBase, ArtifactGroup, CondaEnv, CondaPackage, DockerImage, DockerRuntime,
    FileArtifact, HelmDeployment, LockFile, PreCommit, Process, SystemInstallablePackage,
    VirtualEnv, Wheel,
};
use crate::content::{
    Citation, Command, Content, ContentGroup, DataResource, DescriptiveMetadata,
    Environment, IntakeSource, License, NodePackage, PythonPackage, TabularData,
};
use crate::types::{Architecture, Precision, Stack};

// ---------------------------------------------------------------------------
// ParseCtx — shared context for all parsers
// ---------------------------------------------------------------------------

pub struct ParseCtx<'a> {
    /// Absolute path to the project root.
    pub url: &'a str,
    /// {basename -> full_path} for every entry at the root.
    pub basenames: &'a HashMap<String, String>,
    /// Parsed pyproject.toml, or empty object.
    pub pyproject: &'a JsVal,
}

impl<'a> ParseCtx<'a> {
    pub fn has(&self, name: &str) -> bool {
        self.basenames.contains_key(name)
    }

    pub fn has_any(&self, names: &[&str]) -> bool {
        names.iter().any(|n| self.has(n))
    }

    /// Read a root-level text file; returns None on error.
    pub fn read_text(&self, name: &str) -> Option<String> {
        let path = self.basenames.get(name)?;
        std::fs::read_to_string(path).ok()
    }

    /// Parse a root-level TOML file; returns None on error.
    pub fn read_toml(&self, name: &str) -> Option<toml::Value> {
        let text = self.read_text(name)?;
        toml::from_str(&text).ok()
    }

    /// Parse a root-level YAML file (after stripping jinja); returns None on error.
    pub fn read_yaml(&self, name: &str) -> Option<JsVal> {
        let text = self.read_text(name)?;
        let stripped = strip_jinja(&text);
        serde_yaml::from_str(&stripped).ok()
    }

    /// Read a file at an arbitrary path (not necessarily at the root).
    pub fn read_text_path(&self, path: &str) -> Option<String> {
        std::fs::read_to_string(path).ok()
    }

    pub fn read_yaml_path(&self, path: &str) -> Option<JsVal> {
        let text = self.read_text_path(path)?;
        let stripped = strip_jinja(&text);
        serde_yaml::from_str(&stripped).ok()
    }

    /// tool.[name] table from pyproject.toml.
    pub fn pyproject_tool(&self, name: &str) -> Option<&JsVal> {
        self.pyproject.get("tool")?.get(name)
    }

    /// project.* table from pyproject.toml.
    pub fn pyproject_project(&self) -> Option<&JsVal> {
        self.pyproject.get("project")
    }
}

// ---------------------------------------------------------------------------
// SpecResult — what a successful parse() returns
// ---------------------------------------------------------------------------

#[derive(Debug, Default)]
pub struct SpecResult {
    pub spec_name: String,
    pub contents: HashMap<String, Content>,
    pub artifacts: HashMap<String, Artifact>,
    /// If true this is a ProjectExtra: contents/artifacts go to root, not specs.
    pub is_extra: bool,
    /// URL to upstream spec docs.
    pub spec_doc: String,
}

impl SpecResult {
    fn new(name: &str) -> Self {
        SpecResult {
            spec_name: name.to_string(),
            ..Default::default()
        }
    }
}

// ---------------------------------------------------------------------------
// Registry — list of all spec parsers
// ---------------------------------------------------------------------------

pub type SpecParser = fn(&ParseCtx) -> Option<SpecResult>;

/// Return all registered spec parsers in a stable order.
/// Order matters: more-specific specs (e.g. RattlerRecipe) come before general ones (CondaRecipe).
pub fn all_parsers() -> Vec<(&'static str, SpecParser)> {
    vec![
        // Python / packaging
        ("uv",              parse_uv),
        ("poetry",          parse_poetry),
        ("python_library",  parse_python_library),
        ("python_code",     parse_python_code),
        ("pyscript",        parse_pyscript),
        // Node
        ("j_lab_extension", parse_jlab_extension),
        ("yarn",            parse_yarn),
        ("node",            parse_node),
        // Conda
        ("pixi",            parse_pixi),
        ("conda_project",   parse_conda_project),
        ("rattler_recipe",  parse_rattler_recipe),
        ("conda_recipe",    parse_conda_recipe),
        // Rust
        ("rust_python",     parse_rust_python),
        ("rust",            parse_rust),
        // Go
        ("golang",          parse_golang),
        // Containers / infra
        ("helm_chart",      parse_helm_chart),
        // Documentation
        ("m_d_book",        parse_mdbook),
        ("r_t_d",           parse_rtd),
        // Web apps
        ("django",          parse_django),
        ("streamlit",       parse_streamlit),
        ("marimo",          parse_marimo),
        // Data
        ("data_package",    parse_datapackage),
        ("d_v_c_repo",      parse_dvc_repo),
        // Publishing / citation
        ("hugging_face_repo",     parse_hf_repo),
        ("hugging_face_dataset",  parse_hf_dataset),
        // Packaging (binary)
        ("briefcase",       parse_briefcase),
        // Meta / misc
        ("backstage_catalog", parse_backstage),
        ("m_l_flow",        parse_mlflow),
        ("git_repo",        parse_git_repo),
        ("a_i_enabled",     parse_ai_enabled),
        // IDE configs
        ("v_s_code",        parse_vscode),
        ("jetbrains_i_d_e", parse_jetbrains),
        ("nvidia_a_i_workbench", parse_nvidia_workbench),
        // ProjectExtra (merge into root)
        ("docker",          parse_docker),
        ("pre_committed",   parse_pre_committed),
        ("licensed",        parse_licensed),
        ("python_requirements", parse_python_requirements),
        ("conda_env_file",  parse_conda_env_file),
        ("intake_catalog",  parse_intake_catalog),
        ("cited",           parse_cited),
        ("zenodo",          parse_zenodo),
        ("data",            parse_data),
    ]
}

// ---------------------------------------------------------------------------
// Helper constructors
// ---------------------------------------------------------------------------

fn file_artifact(cmd: Vec<&str>, fn_glob: &str) -> Artifact {
    Artifact::FileArtifact(FileArtifact {
        base: ArtifactBase { cmd: cmd.into_iter().map(str::to_string).collect() },
        fn_glob: fn_glob.to_string(),
    })
}

fn lock_artifact(cmd: Vec<&str>, fn_path: &str) -> Artifact {
    Artifact::LockFile(LockFile {
        file: FileArtifact {
            base: ArtifactBase { cmd: cmd.into_iter().map(str::to_string).collect() },
            fn_glob: fn_path.to_string(),
        },
    })
}

fn process_artifact(cmd: Vec<&str>) -> Artifact {
    Artifact::Process(Process {
        base: ArtifactBase { cmd: cmd.into_iter().map(str::to_string).collect() },
        server: false,
        port_arg: None,
        address_arg: None,
    })
}

fn server_artifact(cmd: Vec<&str>) -> Artifact {
    Artifact::Process(Process {
        base: ArtifactBase { cmd: cmd.into_iter().map(str::to_string).collect() },
        server: true,
        port_arg: None,
        address_arg: None,
    })
}

fn venv_artifact(cmd: Vec<&str>, fn_path: &str) -> Artifact {
    Artifact::VirtualEnv(VirtualEnv {
        file: FileArtifact {
            base: ArtifactBase { cmd: cmd.into_iter().map(str::to_string).collect() },
            fn_glob: fn_path.to_string(),
        },
    })
}

fn conda_env_artifact(cmd: Vec<&str>, fn_path: &str) -> Artifact {
    Artifact::CondaEnv(CondaEnv {
        file: FileArtifact {
            base: ArtifactBase { cmd: cmd.into_iter().map(str::to_string).collect() },
            fn_glob: fn_path.to_string(),
        },
    })
}

fn env(stack: Stack, precision: Precision, packages: Vec<String>) -> Content {
    Content::Environment(Environment {
        stack,
        precision,
        packages,
        channels: vec![],
    })
}

fn env_with_channels(stack: Stack, precision: Precision, packages: Vec<String>, channels: Vec<String>) -> Content {
    Content::Environment(Environment { stack, precision, packages, channels })
}

fn meta(pairs: Vec<(&str, &str)>) -> Content {
    Content::DescriptiveMetadata(DescriptiveMetadata {
        meta: pairs.into_iter().map(|(k, v)| (k.to_string(), JsVal::String(v.to_string()))).collect(),
    })
}

fn meta_from_map(map: HashMap<String, String>) -> Content {
    Content::DescriptiveMetadata(DescriptiveMetadata {
        meta: map.into_iter().map(|(k, v)| (k, JsVal::String(v))).collect(),
    })
}

// ---------------------------------------------------------------------------
// Jinja stripping helper (for conda recipes and conda-project yamls)
// ---------------------------------------------------------------------------

fn strip_jinja(text: &str) -> String {
    text.lines()
        .filter(|line| !line.contains("{%"))
        .map(|line| {
            // strip selector comments like `# [linux]`
            if let Some(idx) = line.find(" # [") {
                &line[..idx]
            } else {
                line
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
}

// ---------------------------------------------------------------------------
// Parsers
// ---------------------------------------------------------------------------

// --- Python / packaging ---

fn parse_python_library(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has_any(&["pyproject.toml", "setup.py"]) {
        return None;
    }
    let mut r = SpecResult::new("python_library");
    r.spec_doc = "https://packaging.python.org/en/latest/specifications/pyproject-toml/".into();

    // build artifact
    if ctx.pyproject.get("build-system").is_some() {
        r.artifacts.insert("wheel".into(), Artifact::Wheel(Wheel {
            file: FileArtifact {
                base: ArtifactBase { cmd: vec!["python".into(), "-m".into(), "build".into()] },
                fn_glob: format!("{}/dist/*.whl", ctx.url),
            },
        }));
    } else if ctx.has("setup.py") {
        r.artifacts.insert("wheel".into(), Artifact::Wheel(Wheel {
            file: FileArtifact {
                base: ArtifactBase { cmd: vec!["python".into(), format!("{}/setup.py", ctx.url), "bdist_wheel".into()] },
                fn_glob: format!("{}/dist/*.whl", ctx.url),
            },
        }));
    }

    // project metadata
    if let Some(proj) = ctx.pyproject_project() {
        if let Some(name) = proj.get("name").and_then(|v| v.as_str()) {
            r.contents.insert("python_package".into(), Content::PythonPackage(PythonPackage { package_name: name.to_string() }));
        }
        // dependencies → environment
        let deps: Vec<String> = proj.get("dependencies")
            .and_then(|v| v.as_array())
            .map(|a| a.iter().filter_map(|v| v.as_str().map(str::to_string)).collect())
            .unwrap_or_default();
        if !deps.is_empty() {
            r.contents.insert("environment".into(), Content::Group({
                let mut g = ContentGroup::new();
                g.insert("default".into(), env(Stack::Pip, Precision::Spec, deps));
                g
            }));
        }
    }
    Some(r)
}

fn parse_python_code(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("__init__.py") { return None; }
    let mut r = SpecResult::new("python_code");
    r.spec_doc = "https://docs.python.org/3/reference/import.html#regular-packages".into();
    let pkg_name = ctx.url.rsplit('/').next().unwrap_or("").to_string();
    r.contents.insert("python_package".into(), Content::PythonPackage(PythonPackage { package_name: pkg_name }));
    if ctx.has("__main__.py") {
        let mut group = ArtifactGroup::new();
        group.insert("main".into(), process_artifact(vec!["python", "__main__.py"]));
        r.artifacts.insert("process".into(), Artifact::Group(group));
    }
    Some(r)
}

fn parse_pyscript(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has_any(&["pyscript.toml", "pyscript.json"]) { return None; }
    let mut r = SpecResult::new("pyscript");
    r.spec_doc = "https://docs.pyscript.net/2023.11.2/user-guide/configuration/".into();
    if let Some(meta) = ctx.read_toml("pyscript.toml") {
        if let Some(pkgs) = meta.get("packages").and_then(|v| v.as_array()) {
            let packages: Vec<String> = pkgs.iter().filter_map(|v| v.as_str().map(str::to_string)).collect();
            r.contents.insert("environment".into(), Content::Group({
                let mut g = ContentGroup::new();
                g.insert("default".into(), env(Stack::Pip, Precision::Spec, packages));
                g
            }));
        }
    }
    r.artifacts.insert("server".into(), server_artifact(vec!["pyscript", "run"]));
    Some(r)
}

fn parse_uv(ctx: &ParseCtx) -> Option<SpecResult> {
    let has_uv_files = ctx.has_any(&["uv.lock", "uv.toml", ".python-version"]);
    let has_uv_backend = ctx.pyproject.get("build-system")
        .and_then(|v| v.get("build-backend"))
        .and_then(|v| v.as_str())
        .map(|s| s == "uv_build")
        .unwrap_or(false);
    if !has_uv_files && !has_uv_backend { return None; }

    let mut r = SpecResult::new("uv");
    r.spec_doc = "https://docs.astral.sh/uv/concepts/configuration-files/".into();

    // inherit from python_library
    if let Some(base) = parse_python_library(ctx) {
        r.contents.extend(base.contents);
        r.artifacts.extend(base.artifacts);
    }

    r.artifacts.insert("lock_file".into(), lock_artifact(vec!["uv", "lock"], &format!("{}/uv.lock", ctx.url)));
    r.artifacts.insert("virtual_env".into(), venv_artifact(vec!["uv", "sync"], &format!("{}/.venv", ctx.url)));

    // parse lock file for locked environment
    if let Some(lock_text) = ctx.read_text("uv.lock") {
        if let Ok(lock) = toml::from_str::<toml::Value>(&lock_text) {
            let py_ver = lock.get("requires-python").and_then(|v| v.as_str()).unwrap_or("");
            let mut pkgs = vec![format!("python {py_ver}")];
            if let Some(packages) = lock.get("package").and_then(|v| v.as_array()) {
                for p in packages {
                    if let (Some(name), Some(ver)) = (p.get("name").and_then(|v| v.as_str()),
                                                       p.get("version").and_then(|v| v.as_str())) {
                        pkgs.push(format!("{name} =={ver}"));
                    }
                }
            }
            let envs = r.contents.entry("environment".into()).or_insert_with(|| Content::Group(ContentGroup::new()));
            if let Content::Group(g) = envs {
                g.insert("lockfile".into(), env(Stack::Pip, Precision::Lock, pkgs));
            }
        }
    }
    Some(r)
}

fn parse_poetry(ctx: &ParseCtx) -> Option<SpecResult> {
    let has_poetry = ctx.pyproject_tool("poetry").is_some()
        || ctx.pyproject.get("build-system")
            .and_then(|v| v.get("build-backend")).and_then(|v| v.as_str())
            .map(|s| s.starts_with("poetry.")).unwrap_or(false);
    if !has_poetry { return None; }

    let mut r = SpecResult::new("poetry");
    r.spec_doc = "https://python-poetry.org/docs/pyproject/".into();

    if let Some(base) = parse_python_library(ctx) {
        r.contents.extend(base.contents);
        r.artifacts.extend(base.artifacts);
    }

    r.artifacts.insert("lock_file".into(), lock_artifact(vec!["poetry", "lock"], &format!("{}/poetry.lock", ctx.url)));

    // override wheel cmd
    r.artifacts.insert("wheel".into(), Artifact::Wheel(Wheel {
        file: FileArtifact {
            base: ArtifactBase { cmd: vec!["poetry".into(), "build".into()] },
            fn_glob: format!("{}/dist/*.whl", ctx.url),
        },
    }));

    // parse poetry.lock for locked env
    if let Some(lock_text) = ctx.read_text("poetry.lock") {
        if let Ok(lock) = toml::from_str::<toml::Value>(&lock_text) {
            let pkgs: Vec<String> = lock.get("package").and_then(|v| v.as_array())
                .map(|a| a.iter().filter_map(|p| {
                    let name = p.get("name")?.as_str()?;
                    let ver = p.get("version")?.as_str()?;
                    Some(format!("{name} =={ver}"))
                }).collect())
                .unwrap_or_default();
            let envs = r.contents.entry("environment".into()).or_insert_with(|| Content::Group(ContentGroup::new()));
            if let Content::Group(g) = envs {
                g.insert("default.lock".into(), env(Stack::Pip, Precision::Lock, pkgs));
            }
        }
    }
    Some(r)
}

// --- Node ---

fn parse_node(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("package.json") { return None; }
    let mut r = SpecResult::new("node");
    r.spec_doc = "https://docs.npmjs.com/cli/v11/configuring-npm/package-json".into();

    let pkg_text = ctx.read_text("package.json")?;
    let pkg: JsVal = serde_json::from_str(&pkg_text).ok()?;

    if let Some(name) = pkg.get("name").and_then(|v| v.as_str()) {
        r.contents.insert("node_package".into(), Content::NodePackage(NodePackage { name: name.to_string() }));
        let mut m = HashMap::new();
        m.insert("name".to_string(), name.to_string());
        if let Some(ver) = pkg.get("version").and_then(|v| v.as_str()) {
            m.insert("version".to_string(), ver.to_string());
        }
        r.contents.insert("descriptive_metadata".into(), meta_from_map(m));
    }

    // dependencies
    let deps: Vec<String> = pkg.get("dependencies").and_then(|v| v.as_object())
        .map(|m| m.keys().cloned().collect()).unwrap_or_default();
    if !deps.is_empty() {
        r.contents.insert("environment".into(), Content::Group({
            let mut g = ContentGroup::new();
            g.insert("node".into(), env(Stack::Npm, Precision::Spec, deps));
            g
        }));
    }

    // lock file
    if ctx.has("package-lock.json") {
        r.artifacts.insert("lock_file".into(), lock_artifact(
            vec!["npm", "install"],
            ctx.basenames.get("package-lock.json").unwrap(),
        ));
    }

    // scripts → process artifacts for "build"
    if let Some(scripts) = pkg.get("scripts").and_then(|v| v.as_object()) {
        if scripts.contains_key("build") {
            r.artifacts.insert("build".into(), process_artifact(vec!["npm", "run", "build"]));
        }
    }
    Some(r)
}

fn parse_yarn(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has(".yarnrc.yml") { return None; }
    let mut r = parse_node(ctx)?;
    r.spec_name = "yarn".into();
    r.spec_doc = "https://yarnpkg.com/configuration/yarnrc".into();

    if ctx.has("yarn.lock") {
        let lock_path = ctx.basenames.get("yarn.lock").cloned().unwrap_or_default();
        r.artifacts.insert("lock_file".into(), lock_artifact(vec!["yarn", "install"], &lock_path));
    }
    Some(r)
}

fn parse_jlab_extension(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("package.json") || ctx.pyproject.as_object().map(|m| m.is_empty()).unwrap_or(true) {
        return None;
    }
    let pkg_text = ctx.read_text("package.json")?;
    let pkg: JsVal = serde_json::from_str(&pkg_text).ok()?;
    let build_script = pkg.get("scripts")?.get("build")?.as_str()?;
    if !build_script.starts_with("jlpm") { return None; }

    let mut r = parse_yarn(ctx).unwrap_or_else(|| parse_node(ctx).unwrap_or_else(|| SpecResult::new("j_lab_extension")));
    r.spec_name = "j_lab_extension".into();
    r.spec_doc = "https://jupyterlab.readthedocs.io/en/latest/developer/contributing.html".into();
    r.artifacts.insert("lock_file".into(), lock_artifact(
        vec!["jlpm", "install"],
        &format!("{}/yarn.lock", ctx.url),
    ));
    Some(r)
}

// --- Conda ---

fn parse_pixi(ctx: &ParseCtx) -> Option<SpecResult> {
    let has_pixi = ctx.has("pixi.toml") || ctx.pyproject_tool("pixi").is_some();
    if !has_pixi { return None; }

    let mut r = SpecResult::new("pixi");
    r.spec_doc = "https://pixi.sh/latest/reference/pixi_manifest".into();

    let meta: toml::Value = if let Some(t) = ctx.read_toml("pixi.toml") {
        t
    } else {
        return None;
    };

    // tasks → processes
    if let Some(tasks) = meta.get("tasks").and_then(|v| v.as_table()) {
        let mut procs = ArtifactGroup::new();
        for name in tasks.keys() {
            procs.insert(name.clone(), process_artifact(vec!["pixi", "run", name]));
        }
        if !procs.is_empty() {
            r.artifacts.insert("process".into(), Artifact::Group(procs));
        }
    }

    r.artifacts.insert("lock_file".into(), lock_artifact(vec!["pixi", "lock"], &format!("{}/pixi.lock", ctx.url)));

    // conda envs from lock file
    if ctx.has("pixi.lock") {
        // just note its existence; detailed lock parsing is expensive
        let mut conda_envs = ArtifactGroup::new();
        conda_envs.insert("default".into(), conda_env_artifact(
            vec!["pixi", "install"],
            &format!("{}/.pixi/envs/default", ctx.url),
        ));
        r.artifacts.insert("conda_env".into(), Artifact::Group(conda_envs));
    }

    // package build
    if let Some(pkg) = meta.get("package").and_then(|v| v.as_table()) {
        if let Some(name) = pkg.get("name").and_then(|v| v.as_str()) {
            let ver = pkg.get("version").and_then(|v| v.as_str()).unwrap_or("*");
            r.artifacts.insert("conda_package".into(), Artifact::CondaPackage(CondaPackage {
                file: FileArtifact {
                    base: ArtifactBase { cmd: vec!["pixi".into(), "build".into()] },
                    fn_glob: format!("{}/{}-{}*.conda", ctx.url, name, ver),
                },
                name: Some(name.to_string()),
            }));
        }
    }

    // dependencies → environment
    if let Some(deps) = meta.get("dependencies").and_then(|v| v.as_table()) {
        let packages: Vec<String> = deps.keys().cloned().collect();
        r.contents.insert("environment".into(), Content::Group({
            let mut g = ContentGroup::new();
            g.insert("default".into(), env(Stack::Conda, Precision::Spec, packages));
            g
        }));
    }
    Some(r)
}

fn parse_conda_project(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has_any(&["conda-project.yml", "conda-meta.yaml"]) { return None; }
    let mut r = SpecResult::new("conda_project");
    r.spec_doc = "https://conda-incubator.github.io/conda-project/tutorial.html".into();

    let meta = ctx.read_yaml("conda-project.yml").or_else(|| ctx.read_yaml("conda-project.yaml"))?;
    let mut envs = ContentGroup::new();
    let mut locks = ArtifactGroup::new();
    let mut conda_envs = ArtifactGroup::new();

    if let Some(environments) = meta.get("environments").and_then(|v| v.as_object()) {
        for (env_name, _) in environments {
            envs.insert(env_name.clone(), env(Stack::Conda, Precision::Spec, vec![]));
            locks.insert(env_name.clone(), lock_artifact(
                vec!["conda", "project", "lock", env_name],
                &format!("{}/conda-lock.{env_name}.yml", ctx.url),
            ));
            conda_envs.insert(env_name.clone(), conda_env_artifact(
                vec!["conda", "project", "prepare", env_name],
                &format!("{}/./envs/{env_name}/", ctx.url),
            ));
        }
    }

    if !envs.is_empty() {
        r.contents.insert("environment".into(), Content::Group(envs));
        r.artifacts.insert("lock_file".into(), Artifact::Group(locks));
        r.artifacts.insert("conda_env".into(), Artifact::Group(conda_envs));
    }

    // commands
    if let Some(commands) = meta.get("commands").and_then(|v| v.as_object()) {
        let mut procs = ArtifactGroup::new();
        let mut cmds = ContentGroup::new();
        for (name, cmd_val) in commands {
            procs.insert(name.clone(), process_artifact(vec!["conda", "project", "run", name]));
            let cmd_str = cmd_val.as_str().unwrap_or("").to_string();
            cmds.insert(name.clone(), Content::Command(Command {
                cmd: crate::content::CmdValue::Str(cmd_str),
            }));
        }
        r.artifacts.insert("process".into(), Artifact::Group(procs));
        r.contents.insert("command".into(), Content::Group(cmds));
    }
    Some(r)
}

fn parse_conda_recipe(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has_any(&["meta.yaml", "meta.yml", "conda.yaml"]) { return None; }
    let mut r = SpecResult::new("conda_recipe");
    r.spec_doc = "https://docs.conda.io/projects/conda-build/en/stable/resources/define-metadata.html".into();

    r.artifacts.insert("conda_package".into(), Artifact::CondaPackage(CondaPackage {
        file: FileArtifact {
            base: ArtifactBase { cmd: vec!["conda-build".into(), format!("{ctx_url}/*.conda", ctx_url = ctx.url)] },
            fn_glob: format!("{}/output/**/*.conda", ctx.url),
        },
        name: None,
    }));

    // parse requirements if available
    for fname in &["meta.yaml", "meta.yml", "conda.yaml"] {
        if let Some(meta) = ctx.read_yaml(fname) {
            if let Some(reqs) = meta.get("requirements").and_then(|v| v.as_object()) {
                let mut envs = ContentGroup::new();
                for (phase, dep_list) in reqs {
                    let pkgs: Vec<String> = dep_list.as_array()
                        .map(|a| a.iter().filter_map(|v| v.as_str().map(str::to_string)).collect())
                        .unwrap_or_default();
                    envs.insert(phase.clone(), env(Stack::Conda, Precision::Spec, pkgs));
                }
                r.contents.insert("environment".into(), Content::Group(envs));
            }
            break;
        }
    }
    Some(r)
}

fn parse_rattler_recipe(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("recipe.yaml") { return None; }
    let mut r = SpecResult::new("rattler_recipe");
    r.spec_doc = "https://rattler.build/latest/reference/recipe_file/".into();

    let meta = ctx.read_yaml("recipe.yaml")?;
    let name = meta.get("context").and_then(|v| v.get("name"))
        .or_else(|| meta.get("recipe").and_then(|v| v.get("name")))
        .or_else(|| meta.get("package").and_then(|v| v.get("name")))
        .and_then(|v| v.as_str()).unwrap_or("package");

    r.artifacts.insert("conda_package".into(), Artifact::CondaPackage(CondaPackage {
        file: FileArtifact {
            base: ArtifactBase { cmd: vec!["rattler-build".into(), "build".into(), "-r".into(), ctx.url.to_string(), "--output-dir".into(), format!("{}/output", ctx.url)] },
            fn_glob: format!("{}/output/{}/*.conda", ctx.url, name),
        },
        name: Some(name.to_string()),
    }));
    Some(r)
}

// --- Rust ---

fn parse_rust(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("Cargo.toml") { return None; }
    let mut r = SpecResult::new("rust");
    r.spec_doc = "https://doc.rust-lang.org/cargo/reference/manifest.html".into();

    if let Some(meta) = ctx.read_toml("Cargo.toml") {
        if let Some(pkg) = meta.get("package").and_then(|v| v.as_table()) {
            let name = pkg.get("name").and_then(|v| v.as_str()).unwrap_or("package");
            let mut m = HashMap::new();
            for key in &["name", "version", "description"] {
                if let Some(v) = pkg.get(*key).and_then(|v| v.as_str()) {
                    m.insert(key.to_string(), v.to_string());
                }
            }
            r.contents.insert("descriptive_metadata".into(), meta_from_map(m));

            let mut bin_group = ArtifactGroup::new();
            bin_group.insert("debug".into(), file_artifact(
                vec!["cargo", "build"],
                &format!("{}/target/debug/{}*", ctx.url, name),
            ));
            bin_group.insert("release".into(), file_artifact(
                vec!["cargo", "build", "--release"],
                &format!("{}/target/release/{}*", ctx.url, name),
            ));
            r.artifacts.insert("file".into(), Artifact::Group(bin_group));
        }
    }
    Some(r)
}

fn parse_rust_python(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("Cargo.toml") { return None; }
    let has_maturin = ctx.pyproject_tool("maturin").is_some()
        || ctx.pyproject.get("build-system").and_then(|v| v.get("build-backend"))
            .and_then(|v| v.as_str()).map(|s| s == "maturin").unwrap_or(false);
    if !has_maturin { return None; }

    let mut r = SpecResult::new("rust_python");
    r.spec_doc = "https://www.maturin.rs/config.html".into();

    // inherit from both rust and python_library
    if let Some(base) = parse_rust(ctx) { r.contents.extend(base.contents); r.artifacts.extend(base.artifacts); }
    if let Some(base) = parse_python_library(ctx) { r.contents.extend(base.contents); r.artifacts.extend(base.artifacts); }
    Some(r)
}

// --- Go ---

fn parse_golang(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("go.mod") { return None; }
    let mut r = SpecResult::new("golang");
    r.spec_doc = "https://go.dev/doc/modules/gomod-ref".into();

    if let Some(text) = ctx.read_text("go.mod") {
        let mut m = HashMap::new();
        for line in text.lines() {
            if let Some(path) = line.strip_prefix("module ") {
                m.insert("module".to_string(), path.trim().to_string());
            }
            if let Some(ver) = line.strip_prefix("go ") {
                m.insert("go".to_string(), ver.trim().to_string());
            }
        }
        if !m.is_empty() {
            r.contents.insert("descriptive_metadata".into(), meta_from_map(m));
        }
    }

    r.artifacts.insert("build".into(), process_artifact(vec!["go", "build", "./..."]));
    r.artifacts.insert("test".into(), process_artifact(vec!["go", "test", "./..."]));

    // binary output if cmd/ exists
    let cmd_dir = format!("{}/cmd", ctx.url);
    if std::path::Path::new(&cmd_dir).is_dir() {
        r.artifacts.insert("binary".into(), file_artifact(
            vec!["go", "build", "-o", "bin/", "./cmd/..."],
            &format!("{}/bin/*", ctx.url),
        ));
    }
    Some(r)
}

// --- Containers / infra ---

fn parse_helm_chart(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("Chart.yaml") { return None; }
    let mut r = SpecResult::new("helm_chart");
    r.spec_doc = "https://helm.sh/docs/topics/charts/#the-chartyaml-file".into();

    if let Some(chart) = ctx.read_yaml("Chart.yaml") {
        let mut m = HashMap::new();
        for key in &["name", "version", "appVersion", "description", "type"] {
            if let Some(v) = chart.get(*key).and_then(|v| v.as_str()) {
                m.insert(key.to_string(), v.to_string());
            }
        }
        let name = m.get("name").cloned().unwrap_or_else(|| "release".to_string());
        let version = m.get("version").cloned().unwrap_or_default();
        r.contents.insert("descriptive_metadata".into(), meta_from_map(m));

        if !name.is_empty() && !version.is_empty() {
            r.artifacts.insert("packaged_chart".into(), file_artifact(
                vec!["helm", "package", "."],
                &format!("{}/{name}-{version}.tgz", ctx.url),
            ));
        }
        r.artifacts.insert("chart_lock".into(), file_artifact(
            vec!["helm", "dependency", "update", "."],
            &format!("{}/Chart.lock", ctx.url),
        ));
        r.artifacts.insert("release".into(), Artifact::HelmDeployment(HelmDeployment::new(&name)));
        r.artifacts.insert("lint".into(), process_artifact(vec!["helm", "lint", "."]));
    }
    Some(r)
}

// --- Documentation ---

fn parse_mdbook(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("book.toml") { return None; }
    let mut r = SpecResult::new("m_d_book");
    r.spec_doc = "https://rust-lang.github.io/mdBook/format/configuration/index.html".into();

    let build_dir = ctx.read_toml("book.toml")
        .and_then(|t| t.get("build").and_then(|b| b.get("build-dir")).and_then(|v| v.as_str()).map(str::to_string))
        .unwrap_or_else(|| "book".to_string());

    r.artifacts.insert("book".into(), file_artifact(
        vec!["mdbook", "build"],
        &format!("{}/{build_dir}/index.html", ctx.url),
    ));
    r.artifacts.insert("server".into(), server_artifact(vec!["mdbook", "serve"]));
    Some(r)
}

fn parse_rtd(ctx: &ParseCtx) -> Option<SpecResult> {
    let rtd_file = ctx.basenames.keys()
        .find(|k| {
            let k = k.as_str();
            k == ".readthedocs.yaml" || k == "readthedocs.yaml" || k == ".readthedocs.yml" || k == "readthedocs.yml"
        })?.clone();
    let mut r = SpecResult::new("r_t_d");
    r.spec_doc = "https://docs.readthedocs.com/platform/stable/config-file/v2.html".into();

    if let Some(cfg) = ctx.read_yaml(&rtd_file) {
        if cfg.get("sphinx").is_some() {
            let conf_py = cfg.get("sphinx").and_then(|s| s.get("configuration")).and_then(|v| v.as_str()).unwrap_or("docs/conf.py");
            let docs_dir = conf_py.rsplit('/').skip(1).next().unwrap_or("docs");
            r.artifacts.insert("docs".into(), file_artifact(
                vec!["sphinx-build", "-b", "html", docs_dir, &format!("{docs_dir}/_build/html")],
                &format!("{}/{docs_dir}/_build/html/index.html", ctx.url),
            ));
        } else if cfg.get("mkdocs").is_some() {
            r.artifacts.insert("docs".into(), file_artifact(
                vec!["mkdocs", "build"],
                &format!("{}/site/index.html", ctx.url),
            ));
        }
    }
    Some(r)
}

// --- Web apps ---

fn parse_django(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("manage.py") { return None; }
    let mut r = SpecResult::new("django");
    r.spec_doc = "https://docs.djangoproject.com/en/6.0/ref/settings/".into();
    r.artifacts.insert("server".into(), server_artifact(vec!["python", "manage.py", "runserver"]));
    Some(r)
}

fn parse_streamlit(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has_any(&[".streamlit", "streamlit_app.py"]) { return None; }
    let mut r = SpecResult::new("streamlit");
    r.spec_doc = "https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization".into();
    // find .py files
    let py_files: Vec<&String> = ctx.basenames.keys().filter(|k| k.ends_with(".py")).collect();
    if py_files.len() == 1 {
        r.artifacts.insert("server".into(), server_artifact(vec!["streamlit", "run", py_files[0]]));
    } else {
        // use streamlit_app.py if it exists
        if ctx.has("streamlit_app.py") {
            r.artifacts.insert("server".into(), server_artifact(vec!["streamlit", "run", "streamlit_app.py"]));
        }
    }
    Some(r)
}

fn parse_marimo(ctx: &ParseCtx) -> Option<SpecResult> {
    // Only match if at least one .py file contains marimo patterns (via scanned_files).
    // Without file content scanning we check basenames for .py files.
    let py_files: Vec<&String> = ctx.basenames.keys().filter(|k| k.ends_with(".py")).collect();
    if py_files.is_empty() { return None; }
    // Try to read and check content
    let mut found = false;
    let mut servers = ArtifactGroup::new();
    for py in &py_files {
        if let Some(full_path) = ctx.basenames.get(*py) {
            if let Ok(content) = std::fs::read_to_string(full_path) {
                if (content.contains("import marimo") || content.contains("from marimo")) && content.contains("marimo.App(") {
                    let name = py.trim_end_matches(".py");
                    servers.insert(name.to_string(), server_artifact(vec!["marimo", "run", full_path]));
                    found = true;
                }
            }
        }
    }
    if !found { return None; }
    let mut r = SpecResult::new("marimo");
    r.spec_doc = "https://docs.marimo.io/".into();
    r.artifacts.insert("server".into(), Artifact::Group(servers));
    Some(r)
}

// --- Data ---

fn parse_datapackage(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("datapackage.json") { return None; }
    let mut r = SpecResult::new("data_package");
    r.spec_doc = "https://datapackage.org/standard/data-package/#structure".into();

    if let Some(text) = ctx.read_text("datapackage.json") {
        if let Ok(conf) = serde_json::from_str::<JsVal>(&text) {
            let mut m = HashMap::new();
            for key in &["name", "title", "description"] {
                if let Some(v) = conf.get(*key).and_then(|v| v.as_str()) {
                    m.insert(key.to_string(), v.to_string());
                }
            }
            r.contents.insert("descriptive_metadata".into(), meta_from_map(m));

            if let Some(licenses) = conf.get("licenses").and_then(|v| v.as_array()) {
                if let Some(lic) = licenses.first() {
                    r.contents.insert("license".into(), Content::License(License {
                        shortname: lic.get("name").and_then(|v| v.as_str()).unwrap_or("unknown").to_string(),
                        fullname: "unknown".to_string(),
                        url: lic.get("path").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                    }));
                }
            }

            if let Some(resources) = conf.get("resources").and_then(|v| v.as_array()) {
                let tables: Vec<Content> = resources.iter().filter_map(|res| {
                    let name = res.get("name")?.as_str()?.to_string();
                    Some(Content::TabularData(TabularData {
                        name,
                        schema: res.get("schema").cloned().unwrap_or(JsVal::Null),
                        metadata: HashMap::new(),
                    }))
                }).collect();
                if !tables.is_empty() {
                    r.contents.insert("frictionless_data".into(), Content::List(tables));
                }
            }
        }
    }
    Some(r)
}

fn parse_dvc_repo(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has(".dvc") { return None; }
    let mut r = SpecResult::new("d_v_c_repo");
    r.spec_doc = "https://doc.dvc.org/command-reference/config".into();
    Some(r)
}

// --- Publishing / citation ---

fn parse_hf_repo(ctx: &ParseCtx) -> Option<SpecResult> {
    let text = ctx.read_text("README.md")?;
    if text.matches("---\n").count() < 2 { return None; }
    let front_matter = text.split("---\n").nth(1)?;
    let meta: JsVal = serde_yaml::from_str(front_matter).ok()?;
    if !meta.is_object() { return None; }
    // dataset discriminators mean it's a dataset card, not a model card
    let dataset_keys = ["dataset_info", "source_datasets", "task_categories", "task_ids"];
    if dataset_keys.iter().any(|k| meta.get(k).is_some()) { return None; }

    let mut r = SpecResult::new("hugging_face_repo");
    r.spec_doc = "https://huggingface.co/docs/hub/en/model-cards".into();

    let mut m = HashMap::new();
    for key in &["language", "library_name", "base_model"] {
        if let Some(v) = meta.get(*key).and_then(|v| v.as_str()) {
            m.insert(key.to_string(), v.to_string());
        }
    }
    r.contents.insert("descriptive_metadata".into(), meta_from_map(m));

    if let Some(lic) = meta.get("licence").and_then(|v| v.as_str()) {
        r.contents.insert("license".into(), Content::License(License {
            shortname: lic.to_string(), fullname: "unknown".to_string(), url: String::new(),
        }));
    }
    Some(r)
}

fn parse_hf_dataset(ctx: &ParseCtx) -> Option<SpecResult> {
    let text = ctx.read_text("README.md")?;
    if text.matches("---\n").count() < 2 { return None; }
    let front_matter = text.split("---\n").nth(1)?;
    let meta: JsVal = serde_yaml::from_str(front_matter).ok()?;
    if !meta.is_object() { return None; }
    // must have at least one dataset key
    let dataset_keys = ["dataset_info", "source_datasets", "task_categories", "task_ids", "size_categories"];
    if !dataset_keys.iter().any(|k| meta.get(k).is_some()) { return None; }

    let mut r = SpecResult::new("hugging_face_dataset");
    r.spec_doc = "https://huggingface.co/docs/hub/datasets-cards".into();

    let mut m = HashMap::new();
    for key in &["pretty_name", "language", "task_categories", "size_categories"] {
        if let Some(v) = meta.get(*key) {
            m.insert(key.to_string(), v.to_string());
        }
    }
    r.contents.insert("descriptive_metadata".into(), Content::DescriptiveMetadata(DescriptiveMetadata {
        meta: m.into_iter().map(|(k, v)| (k, JsVal::String(v))).collect(),
    }));
    Some(r)
}

// --- Briefcase ---

fn parse_briefcase(ctx: &ParseCtx) -> Option<SpecResult> {
    ctx.pyproject_tool("briefcase")?;
    let mut r = SpecResult::new("briefcase");
    r.spec_doc = "https://briefcase.readthedocs.io/en/stable/reference/configuration.html".into();
    // Add cross-platform installers as best-effort
    r.artifacts.insert("linux-deb".into(), Artifact::SystemInstallablePackage(SystemInstallablePackage {
        file: FileArtifact {
            base: ArtifactBase { cmd: vec!["briefcase".into(), "package".into(), "-p".into(), "deb".into()] },
            fn_glob: format!("{}/dist/*.deb", ctx.url),
        },
        arch: Architecture::Linux,
        filetype: "deb".to_string(),
    }));
    Some(r)
}

// --- Backstage ---

fn parse_backstage(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("catalog-info.yaml") { return None; }
    let mut r = SpecResult::new("backstage_catalog");
    r.spec_doc = "https://backstage.io/docs/features/software-catalog/descriptor-format/".into();

    if let Some(yaml_text) = ctx.read_text("catalog-info.yaml") {
        let mut meta_entries = ContentGroup::new();
        // iterate yaml documents
        for doc_str in yaml_text.split("---\n").filter(|s| !s.trim().is_empty()) {
            if let Ok(doc) = serde_yaml::from_str::<JsVal>(doc_str) {
                if let Some(api) = doc.get("apiVersion").and_then(|v| v.as_str()) {
                    if api.starts_with("backstage.io/") {
                        let kind = doc.get("kind").and_then(|v| v.as_str()).unwrap_or("unknown");
                        let metadata = doc.get("metadata");
                        let name = metadata.and_then(|m| m.get("name")).and_then(|v| v.as_str()).unwrap_or("unnamed");
                        let key = format!("{}.{}", kind.to_lowercase(), name);
                        let mut m = HashMap::new();
                        m.insert("kind".to_string(), JsVal::String(kind.to_string()));
                        m.insert("name".to_string(), JsVal::String(name.to_string()));
                        if let Some(desc) = metadata.and_then(|m| m.get("description")).and_then(|v| v.as_str()) {
                            m.insert("description".to_string(), JsVal::String(desc.to_string()));
                        }
                        meta_entries.insert(key, Content::DescriptiveMetadata(DescriptiveMetadata { meta: m }));
                    }
                }
            }
        }
        if !meta_entries.is_empty() {
            r.contents.insert("descriptive_metadata".into(), Content::Group(meta_entries));
        }
    }
    Some(r)
}

// --- MLFlow ---

fn parse_mlflow(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("MLFlow") { return None; }
    let mut r = SpecResult::new("m_l_flow");
    r.spec_doc = "https://mlflow.org/docs/latest/ml/projects/#mlproject-file-configuration".into();

    if let Some(meta) = ctx.read_yaml("MLFlow") {
        let stack = if meta.get("python_env").is_some() { Stack::Pip } else { Stack::Conda };
        r.contents.insert("environment".into(), env(stack, Precision::Spec, vec![]));

        if let Some(eps) = meta.get("entry_points").and_then(|v| v.as_object()) {
            let mut procs = ArtifactGroup::new();
            let mut cmds = ContentGroup::new();
            for (name, ep) in eps {
                procs.insert(name.clone(), process_artifact(vec!["mlflow", "run", ".", "-e", name]));
                let cmd_str = ep.get("command").and_then(|v| v.as_str()).unwrap_or("").to_string();
                cmds.insert(name.clone(), Content::Command(Command {
                    cmd: crate::content::CmdValue::Str(cmd_str),
                }));
            }
            r.artifacts.insert("process".into(), Artifact::Group(procs));
            r.contents.insert("command".into(), Content::Group(cmds));
        }
    }
    Some(r)
}

// --- Git ---

fn parse_git_repo(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has(".git") { return None; }
    let mut r = SpecResult::new("git_repo");
    r.spec_doc = "https://git-scm.com/docs/git-config#_configuration_file".into();

    // read branches from .git/refs/heads
    let heads_dir = format!("{}/.git/refs/heads", ctx.url);
    let branches: Vec<String> = std::fs::read_dir(&heads_dir).ok()
        .map(|rd| rd.filter_map(|e| e.ok()).map(|e| e.file_name().to_string_lossy().to_string()).collect())
        .unwrap_or_default();
    r.contents.insert("branches".into(), Content::Raw(JsVal::Array(branches.into_iter().map(JsVal::String).collect())));

    let tags_dir = format!("{}/.git/refs/tags", ctx.url);
    let tags: Vec<String> = std::fs::read_dir(&tags_dir).ok()
        .map(|rd| rd.filter_map(|e| e.ok()).map(|e| e.file_name().to_string_lossy().to_string()).collect())
        .unwrap_or_default();
    r.contents.insert("tags".into(), Content::Raw(JsVal::Array(tags.into_iter().map(JsVal::String).collect())));
    Some(r)
}

// --- AI enabled ---

fn parse_ai_enabled(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has_any(&["AGENTS.md", "CLAUDE.md", ".specify"]) { return None; }
    let mut r = SpecResult::new("a_i_enabled");
    r.spec_doc = "https://agents.md/".into();
    Some(r)
}

// --- IDEs ---

fn parse_vscode(ctx: &ParseCtx) -> Option<SpecResult> {
    let settings = format!("{}/.vscode/settings.json", ctx.url);
    if !std::path::Path::new(&settings).exists() { return None; }
    let mut r = SpecResult::new("v_s_code");
    r.spec_doc = "https://code.visualstudio.com/docs/configure/settings#_settings-json-file".into();
    r.artifacts.insert("launch".into(), process_artifact(vec!["code", ctx.url]));
    Some(r)
}

fn parse_jetbrains(ctx: &ParseCtx) -> Option<SpecResult> {
    let idea = format!("{}/.idea", ctx.url);
    if !std::path::Path::new(&idea).exists() { return None; }
    let mut r = SpecResult::new("jetbrains_i_d_e");
    r.artifacts.insert("launch".into(), process_artifact(vec!["pycharm", ctx.url, "nosplash", "dontReopenProjects"]));
    Some(r)
}

fn parse_nvidia_workbench(ctx: &ParseCtx) -> Option<SpecResult> {
    let spec = format!("{}/.project/spec.yaml", ctx.url);
    if !std::path::Path::new(&spec).exists() { return None; }
    let mut r = SpecResult::new("nvidia_a_i_workbench");
    r.spec_doc = "https://docs.nvidia.com/ai-workbench/user-guide/latest/projects/spec.html".into();
    r.artifacts.insert("set_project".into(), process_artifact(vec!["nvwb", "open", ctx.url]));
    Some(r)
}

// --- ProjectExtra parsers (is_extra = true) ---

fn parse_docker(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("Dockerfile") { return None; }
    let mut r = SpecResult::new("docker");
    r.is_extra = true;
    r.artifacts.insert("docker_image".into(), Artifact::DockerImage(DockerImage::new(None)));
    r.artifacts.insert("docker_runtime".into(), Artifact::DockerRuntime(DockerRuntime { image: DockerImage::new(None) }));
    Some(r)
}

fn parse_pre_committed(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has(".pre-commit-config.yaml") { return None; }
    let mut r = SpecResult::new("pre_committed");
    r.is_extra = true;
    r.artifacts.insert("precommit".into(), Artifact::PreCommit(PreCommit::default()));
    Some(r)
}

fn parse_licensed(ctx: &ParseCtx) -> Option<SpecResult> {
    let lic_file = ctx.basenames.keys().find(|k| {
        let ku = k.to_uppercase();
        ku.starts_with("LICENSE") || ku.starts_with("LICENCE") || ku.starts_with("COPYING")
    })?.clone();

    let mut r = SpecResult::new("licensed");
    r.is_extra = true;

    let known: &[(&str, &str, &str)] = &[
        ("GNU GENERAL PUBLIC LICENSE", "GPL-3.0-or-later", "GNU General Public License v3.0 or later"),
        ("MIT License", "MIT", "MIT License"),
        ("Apache License", "Apache-2.0", "Apache License 2.0"),
        ("BSD 3-Clause", "BSD-3-Clause", "BSD 3-Clause License"),
    ];

    let lic = if let Some(text) = ctx.read_text(&lic_file) {
        let mut found = License { shortname: "unknown".into(), fullname: "unknown".into(), url: lic_file.clone() };
        for (pattern, short, full) in known {
            if text.contains(pattern) {
                found = License {
                    shortname: short.to_string(),
                    fullname: full.to_string(),
                    url: format!("https://spdx.org/licenses/{short}.html"),
                };
                break;
            }
        }
        found
    } else {
        License { shortname: "unknown".into(), fullname: "unknown".into(), url: lic_file }
    };

    r.contents.insert("license".into(), Content::License(lic));
    Some(r)
}

fn parse_python_requirements(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("requirements.txt") { return None; }
    let text = ctx.read_text("requirements.txt")?;
    let deps: Vec<String> = text.lines()
        .map(str::trim)
        .filter(|l| !l.is_empty() && !l.starts_with('#'))
        .map(str::to_string)
        .collect();
    let precision = if deps.iter().all(|d| d.contains("==")) { Precision::Lock } else { Precision::Spec };
    let mut r = SpecResult::new("python_requirements");
    r.is_extra = true;
    r.contents.insert("environment".into(), env(Stack::Pip, precision, deps));
    Some(r)
}

fn parse_conda_env_file(ctx: &ParseCtx) -> Option<SpecResult> {
    let fname = if ctx.has("environment.yaml") { "environment.yaml" }
                else if ctx.has("environment.yml") { "environment.yml" }
                else { return None; };
    let yaml = ctx.read_yaml(fname)?;
    let deps: Vec<String> = yaml.get("dependencies").and_then(|v| v.as_array())
        .map(|a| a.iter().filter_map(|v| v.as_str().map(str::to_string)).collect())
        .unwrap_or_default();
    let channels: Vec<String> = yaml.get("channels").and_then(|v| v.as_array())
        .map(|a| a.iter().filter_map(|v| v.as_str().map(str::to_string)).collect())
        .unwrap_or_default();
    let mut r = SpecResult::new("conda_env_file");
    r.is_extra = true;
    r.contents.insert("environment".into(), env_with_channels(Stack::Conda, Precision::Spec, deps, channels));
    r.artifacts.insert("conda_env".into(), conda_env_artifact(
        vec!["conda", "env", "create", "-f", fname],
        fname,
    ));
    Some(r)
}

fn parse_intake_catalog(ctx: &ParseCtx) -> Option<SpecResult> {
    let cat_file = ctx.basenames.keys().find(|k| {
        let k = k.as_str();
        k == "cat.yaml" || k == "cat.yml" || k == "catalog.yaml" || k == "catalog.yml"
    })?.clone();

    let yaml = ctx.read_yaml(&cat_file)?;
    let mut r = SpecResult::new("intake_catalog");
    r.is_extra = true;

    let entries: Vec<String> = if yaml.get("version").and_then(|v| v.as_i64()) == Some(2) {
        yaml.get("entries").and_then(|v| v.as_object()).map(|m| m.keys().cloned().collect()).unwrap_or_default()
    } else {
        yaml.get("sources").and_then(|v| v.as_object()).map(|m| m.keys().cloned().collect()).unwrap_or_default()
    };

    if entries.is_empty() { return None; }

    let sources: Vec<Content> = entries.into_iter().map(|name| Content::IntakeSource(IntakeSource { name })).collect();
    r.contents.insert("intake_source".into(), Content::List(sources));
    Some(r)
}

fn parse_cited(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has("CITATION.cff") { return None; }
    let mut r = SpecResult::new("cited");
    r.is_extra = true;
    r.spec_doc = "https://citation-file-format.github.io/".into();
    if let Some(meta_yaml) = ctx.read_yaml("CITATION.cff") {
        let meta: HashMap<String, JsVal> = meta_yaml.as_object()
            .map(|m| m.iter().map(|(k, v)| (k.clone(), v.clone())).collect())
            .unwrap_or_default();
        r.contents.insert("descriptive_metadata".into(), Content::Citation(Citation { meta }));
    }
    Some(r)
}

fn parse_zenodo(ctx: &ParseCtx) -> Option<SpecResult> {
    if !ctx.has(".zenodo.json") { return None; }
    let mut r = SpecResult::new("zenodo");
    r.is_extra = true;
    r.spec_doc = "https://help.zenodo.org/docs/github/describe-software/zenodo-json/".into();
    if let Some(text) = ctx.read_text(".zenodo.json") {
        if let Ok(meta) = serde_json::from_str::<HashMap<String, JsVal>>(&text) {
            r.contents.insert("descriptive_metadata".into(), Content::Citation(Citation { meta }));
        }
    }
    Some(r)
}

fn parse_data(ctx: &ParseCtx) -> Option<SpecResult> {
    // Only match if there are data files at the root and no non-data sentinels override.
    // This is a simplified version — we check for common data extensions.
    let data_exts = [".csv", ".parquet", ".parq", ".arrow", ".hdf5", ".h5", ".nc",
                     ".zarr", ".npy", ".npz", ".feather", ".orc", ".avro"];
    let has_data = ctx.basenames.keys().any(|k| data_exts.iter().any(|e| k.ends_with(e)));

    let layout_sentinels = [".zattrs", ".zgroup", "zarr.json", "_metadata"];
    let has_layout = ctx.basenames.keys().any(|k| layout_sentinels.contains(&k.as_str()));

    if !has_data && !has_layout { return None; }

    let non_data_sentinels = ["pyproject.toml", "setup.py", "Cargo.toml", "package.json",
                               "go.mod", "Dockerfile", "Chart.yaml", "pixi.toml"];
    let has_non_data = ctx.basenames.keys().any(|k| non_data_sentinels.contains(&k.as_str()));

    if has_non_data && !has_data { return None; }

    let mut r = SpecResult::new("data");
    r.is_extra = true;

    // Produce DataResource entries for each data file type found
    let mut resources: HashMap<String, Content> = HashMap::new();
    for (basename, full_path) in ctx.basenames {
        let ext = basename.rsplit('.').next().map(|e| format!(".{e}")).unwrap_or_default();
        if data_exts.contains(&ext.as_str()) {
            let fmt = ext.trim_start_matches('.');
            resources.insert(basename.clone(), Content::DataResource(DataResource {
                path: basename.clone(),
                format: fmt.to_string(),
                modality: "tabular".to_string(),
                layout: "flat".to_string(),
                file_count: 1,
                total_size: std::fs::metadata(full_path).map(|m| m.len()).unwrap_or(0),
                schema: JsVal::Object(Default::default()),
                sample_path: full_path.clone(),
                metadata: HashMap::new(),
            }));
        }
    }

    if resources.len() == 1 {
        let (_, content) = resources.into_iter().next().unwrap();
        r.contents.insert("data_resource".into(), content);
    } else if !resources.is_empty() {
        r.contents.insert("data_resource".into(), Content::Group(resources));
    }

    Some(r)
}
