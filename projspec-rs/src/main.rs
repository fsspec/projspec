// projspec-rs — Rust port of the projspec library and CLI
//
// Allow dead_code and unused at crate level: many items are public library API
// that may not be called by the CLI binary itself.
#![allow(dead_code)]
#![allow(unused_imports)]
//
// Module layout mirrors the Python package:
//   types      — enums (Stack, Precision, Architecture)
//   content    — BaseContent variants
//   artifact   — BaseArtifact variants + execution
//   spec       — ProjectSpec implementations (match + parse)
//   project    — Project struct + resolve logic
//   fs         — Virtual filesystem abstraction (opendal-backed)
//   library    — ProjectLibrary (JSON persistence)
//   config     — Config file read/write
//   create     — Project scaffolding (ProjectSpec::create)
//   cli        — clap-based CLI (main entry point lives here)

mod artifact;
mod cli;
mod config;
mod content;
mod create;
mod fs;
mod library;
mod project;
mod spec;
mod types;

fn main() {
    cli::run();
}
