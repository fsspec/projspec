// lib.rs — re-exports all internal modules for integration tests.
// This exists only to enable `#[cfg(test)]` integration tests to import
// internal modules without the `#[path]` hack (which causes duplicate imports).

pub mod artifact;
pub mod cli;
pub mod config;
pub mod content;
pub mod create;
pub mod fs;
pub mod library;
pub mod project;
pub mod spec;
pub mod types;
