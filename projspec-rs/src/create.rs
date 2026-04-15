/// create.rs — Project scaffolding (ProjectSpec::create equivalent).
/// For each spec type that supports creation, writes the minimal files.

use std::fs;
use std::path::Path;
use anyhow::{Context, Result};

pub struct CreateSpec {
    pub name: &'static str,
    pub doc: &'static str,
    pub creator: fn(path: &str) -> Result<Vec<String>>,
}

pub fn all_creators() -> Vec<CreateSpec> {
    vec![
        CreateSpec { name: "python_library", doc: "pyproject.toml + src layout", creator: create_python_library },
        CreateSpec { name: "python_code",    doc: "__init__.py",                  creator: create_python_code },
        CreateSpec { name: "git_repo",       doc: "git init",                     creator: create_git_repo },
        CreateSpec { name: "pixi",           doc: "pixi.toml",                    creator: create_pixi },
        CreateSpec { name: "conda_recipe",   doc: "meta.yaml",                    creator: create_conda_recipe },
        CreateSpec { name: "rattler_recipe", doc: "recipe.yaml",                  creator: create_rattler_recipe },
        CreateSpec { name: "golang",         doc: "go.mod + hello.go",            creator: create_golang },
        CreateSpec { name: "rust",           doc: "cargo init",                   creator: create_rust },
        CreateSpec { name: "node",           doc: "package.json",                 creator: create_node },
        CreateSpec { name: "helm_chart",     doc: "Chart.yaml + templates/",      creator: create_helm_chart },
        CreateSpec { name: "m_d_book",       doc: "book.toml + src/",             creator: create_mdbook },
        CreateSpec { name: "r_t_d",          doc: ".readthedocs.yaml + docs/",    creator: create_rtd },
        CreateSpec { name: "django",         doc: "python -m django startproject", creator: create_django },
        CreateSpec { name: "streamlit",      doc: ".streamlit/ + streamlit_app.py", creator: create_streamlit },
        CreateSpec { name: "marimo",         doc: "marimo-app.py",                creator: create_marimo },
        CreateSpec { name: "data_package",   doc: "datapackage.json",             creator: create_datapackage },
        CreateSpec { name: "backstage_catalog", doc: "catalog-info.yaml",         creator: create_backstage },
        CreateSpec { name: "m_l_flow",       doc: "MLFlow + conda.yaml",          creator: create_mlflow },
        CreateSpec { name: "pyscript",       doc: "pyscript.toml + index.html",   creator: create_pyscript },
        CreateSpec { name: "intake_catalog", doc: "catalog.yaml",                 creator: create_intake_catalog },
        CreateSpec { name: "uv",             doc: "uv init --lib",                creator: create_uv },
        CreateSpec { name: "conda_project",  doc: "conda-project.yml + environment.yml", creator: create_conda_project },
    ]
}

// ---------------------------------------------------------------------------
// Individual creators
// ---------------------------------------------------------------------------

fn write(path: &str, content: &str) -> Result<()> {
    fs::write(path, content).with_context(|| format!("writing {path}"))
}

fn mkdir(path: &str) -> Result<()> {
    fs::create_dir_all(path).with_context(|| format!("creating directory {path}"))
}

fn created(paths: &[&str]) -> Vec<String> {
    paths.iter().map(|p| p.to_string()).collect()
}

fn create_python_library(path: &str) -> Result<Vec<String>> {
    let name = basename(path);
    let pyproject = format!(
r#"[build-system]
requires = ["setuptools >= 77.0.3"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "0.1.0"
dependencies = []
requires-python = ">=3.10"
description = "A Python library"
"#);
    write(&format!("{path}/pyproject.toml"), &pyproject)?;
    mkdir(&format!("{path}/src/{name}"))?;
    write(&format!("{path}/src/{name}/__init__.py"), "")?;
    Ok(created(&[&format!("{path}/pyproject.toml"), &format!("{path}/src/{name}/__init__.py")]))
}

fn create_python_code(path: &str) -> Result<Vec<String>> {
    write(&format!("{path}/__init__.py"), "")?;
    Ok(created(&[&format!("{path}/__init__.py")]))
}

fn create_git_repo(path: &str) -> Result<Vec<String>> {
    std::process::Command::new("git").args(["init"]).current_dir(path).status()
        .context("git init failed")?;
    Ok(vec![format!("{path}/.git")])
}

fn create_pixi(path: &str) -> Result<Vec<String>> {
    let name = basename(path);
    let content = format!(
r#"[workspace]
name = "{name}"
channels = ["conda-forge"]
platforms = ["osx-arm64", "linux-64", "win-64"]
version = "0.1.0"

[dependencies]
python = ">=3.10"

[tasks]
hello = "echo 'hello world'"
"#);
    write(&format!("{path}/pixi.toml"), &content)?;
    Ok(created(&[&format!("{path}/pixi.toml")]))
}

fn create_conda_recipe(path: &str) -> Result<Vec<String>> {
    let name = basename(path);
    let content = format!(
r#"package:
  name: {name}
  version: 0.1.0

source:
  path: .

requirements:
  build:
    - python >=3.10
  run:
    - python >=3.10
"#);
    write(&format!("{path}/meta.yaml"), &content)?;
    Ok(created(&[&format!("{path}/meta.yaml")]))
}

fn create_rattler_recipe(path: &str) -> Result<Vec<String>> {
    let name = basename(path);
    let content = format!(
r#"context:
  name: {name}
  version: "0.1.0"

package:
  name: ${{{{ name }}}}
  version: ${{{{ version }}}}

source:
  path: .

requirements:
  run:
    - python >=3.10
"#);
    write(&format!("{path}/recipe.yaml"), &content)?;
    Ok(created(&[&format!("{path}/recipe.yaml")]))
}

fn create_golang(path: &str) -> Result<Vec<String>> {
    let module = format!("example.com/{}", basename(path));
    write(&format!("{path}/go.mod"), &format!("module {module}\n\ngo 1.21\n"))?;
    write(&format!("{path}/hello.go"),
r#"package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}
"#)?;
    Ok(created(&[&format!("{path}/go.mod"), &format!("{path}/hello.go")]))
}

fn create_rust(path: &str) -> Result<Vec<String>> {
    std::process::Command::new("cargo").args(["init"]).current_dir(path).status()
        .context("cargo init failed")?;
    Ok(vec![format!("{path}/Cargo.toml"), format!("{path}/src/main.rs")])
}

fn create_node(path: &str) -> Result<Vec<String>> {
    let name = basename(path);
    let content = format!(
r#"{{
  "name": "{name}",
  "version": "0.1.0",
  "description": "",
  "main": "index.js",
  "scripts": {{
    "build": "echo 'build'"
  }},
  "dependencies": {{}}
}}
"#);
    write(&format!("{path}/package.json"), &content)?;
    Ok(created(&[&format!("{path}/package.json")]))
}

fn create_helm_chart(path: &str) -> Result<Vec<String>> {
    let name = basename(path);
    write(&format!("{path}/Chart.yaml"), &format!(
r#"apiVersion: v2
name: {name}
description: A Helm chart for {name}
type: application
version: 0.1.0
appVersion: "1.0.0"
"#))?;
    write(&format!("{path}/values.yaml"),
r#"replicaCount: 1
image:
  repository: nginx
  tag: latest
  pullPolicy: IfNotPresent
"#)?;
    mkdir(&format!("{path}/templates"))?;
    write(&format!("{path}/templates/deployment.yaml"),
r#"apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}
spec:
  replicas: {{ .Values.replicaCount }}
"#)?;
    Ok(created(&[&format!("{path}/Chart.yaml"), &format!("{path}/values.yaml")]))
}

fn create_mdbook(path: &str) -> Result<Vec<String>> {
    let name = basename(path);
    write(&format!("{path}/book.toml"), &format!(
r#"[book]
title = "{name}"
authors = []
description = ""

[build]
build-dir = "book"
"#))?;
    mkdir(&format!("{path}/src"))?;
    write(&format!("{path}/src/SUMMARY.md"), "# Summary\n\n- [Introduction](./introduction.md)\n")?;
    write(&format!("{path}/src/introduction.md"), &format!("# Introduction\n\nWelcome to {name}.\n"))?;
    Ok(created(&[&format!("{path}/book.toml"), &format!("{path}/src/SUMMARY.md")]))
}

fn create_rtd(path: &str) -> Result<Vec<String>> {
    let name = basename(path);
    write(&format!("{path}/.readthedocs.yaml"),
r#"version: 2

build:
  os: ubuntu-24.04
  tools:
    python: "3.12"

sphinx:
  configuration: docs/conf.py

python:
  install:
    - requirements: docs/requirements.txt
"#)?;
    mkdir(&format!("{path}/docs"))?;
    write(&format!("{path}/docs/conf.py"), &format!(
r#"project = "{name}"
extensions = []
html_theme = "alabaster"
"#))?;
    write(&format!("{path}/docs/index.rst"), &format!("{name}\n{}\n\n.. toctree::\n   :maxdepth: 2\n", "=".repeat(name.len())))?;
    write(&format!("{path}/docs/requirements.txt"), "sphinx\n")?;
    Ok(created(&[&format!("{path}/.readthedocs.yaml"), &format!("{path}/docs/conf.py")]))
}

fn create_django(path: &str) -> Result<Vec<String>> {
    std::process::Command::new("python")
        .args(["-m", "django", "startproject", "mysite", path])
        .status()
        .context("django startproject failed")?;
    Ok(vec![format!("{path}/manage.py"), format!("{path}/mysite/")])
}

fn create_streamlit(path: &str) -> Result<Vec<String>> {
    mkdir(&format!("{path}/.streamlit"))?;
    write(&format!("{path}/.streamlit/config.toml"),
r#"[global]

[logger]
level = "info"

[server]
headless = true
"#)?;
    write(&format!("{path}/streamlit_app.py"),
r#"import streamlit as st
st.title("My Streamlit App")
st.write("Hello, world!")
"#)?;
    write(&format!("{path}/requirements.txt"), "streamlit\n")?;
    Ok(created(&[&format!("{path}/streamlit_app.py"), &format!("{path}/.streamlit/config.toml")]))
}

fn create_marimo(path: &str) -> Result<Vec<String>> {
    write(&format!("{path}/marimo-app.py"),
r#"import marimo
__generated_with = "0.19.11"
app = marimo.App()

@app.cell
def _():
    import marimo as mo
    return "Hello, marimo!"

if __name__ == "__main__":
    app.run()
"#)?;
    Ok(created(&[&format!("{path}/marimo-app.py")]))
}

fn create_datapackage(path: &str) -> Result<Vec<String>> {
    write(&format!("{path}/datapackage.json"),
r#"{
  "name": "my-data-package",
  "title": "My Data Package",
  "description": "An example data package",
  "licenses": [{"name": "CC0-1.0", "path": "https://creativecommons.org/publicdomain/zero/1.0/"}],
  "resources": [{"name": "data", "path": "data.csv", "format": "csv"}]
}
"#)?;
    Ok(created(&[&format!("{path}/datapackage.json")]))
}

fn create_backstage(path: &str) -> Result<Vec<String>> {
    let name = basename(path);
    write(&format!("{path}/catalog-info.yaml"), &format!(
r#"apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: {name}
  description: A {name} component
spec:
  type: service
  lifecycle: experimental
  owner: team-default
"#))?;
    Ok(created(&[&format!("{path}/catalog-info.yaml")]))
}

fn create_mlflow(path: &str) -> Result<Vec<String>> {
    write(&format!("{path}/MLFlow"),
r#"name: tutorial

conda_env: conda.yaml

entry_points:
  main:
    parameters:
      alpha: {type: float, default: 0.5}
    command: "python train.py {alpha}"
"#)?;
    write(&format!("{path}/conda.yaml"),
r#"name: ml-project
channels:
  - conda-forge
dependencies:
  - python=3.10
"#)?;
    write(&format!("{path}/train.py"), "# MLFlow training code\n")?;
    Ok(created(&[&format!("{path}/MLFlow"), &format!("{path}/conda.yaml"), &format!("{path}/train.py")]))
}

fn create_pyscript(path: &str) -> Result<Vec<String>> {
    write(&format!("{path}/pyscript.toml"),
r#"name = "pyscript-app"
description = "A PyScript app"
packages = []
"#)?;
    write(&format!("{path}/main.py"), "# Replace with your code\nprint('Hello, world!')\n")?;
    write(&format!("{path}/index.html"),
r#"<!DOCTYPE html>
<html>
<head>
  <title>PyScript App</title>
  <link rel="stylesheet" href="https://pyscript.net/releases/2026.2.1/core.css">
  <script type="module" src="https://pyscript.net/releases/2026.2.1/core.js"></script>
</head>
<body>
  <script type="py" src="./main.py" config="./pyscript.toml" terminal></script>
</body>
</html>
"#)?;
    Ok(created(&[&format!("{path}/pyscript.toml"), &format!("{path}/main.py"), &format!("{path}/index.html")]))
}

fn create_intake_catalog(path: &str) -> Result<Vec<String>> {
    write(&format!("{path}/catalog.yaml"),
r#"aliases: {}
data: {}
entries: {}
metadata: {}
user_parameters: {}
version: 2
"#)?;
    Ok(created(&[&format!("{path}/catalog.yaml")]))
}

fn create_uv(path: &str) -> Result<Vec<String>> {
    std::process::Command::new("uv")
        .args(["init", "--lib", "--package", "--vcs", "none"])
        .current_dir(path)
        .status()
        .context("uv init failed")?;
    Ok(vec![
        format!("{path}/pyproject.toml"),
        format!("{path}/src/"),
    ])
}

fn create_conda_project(path: &str) -> Result<Vec<String>> {
    let name = basename(path);
    write(&format!("{path}/environment.yml"),
r#"channels:
  - conda-forge
dependencies:
  - python >=3.10
"#)?;
    write(&format!("{path}/conda-project.yml"), &format!(
r#"name: {name}
environments:
  default:
  - environment.yml
variables: {{}}
commands: {{}}
"#))?;
    Ok(created(&[&format!("{path}/environment.yml"), &format!("{path}/conda-project.yml")]))
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

fn basename(path: &str) -> String {
    Path::new(path)
        .file_name()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| "project".to_string())
}
