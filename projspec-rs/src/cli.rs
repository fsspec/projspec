/// cli.rs — clap-based CLI mirroring projspec.__main__.
/// Commands: scan, make, create, info, version, library (list/clear/delete/add), config (get/set/unset/show/defaults)

use clap::{Parser, Subcommand, Args};
use anyhow::Result;

use crate::config::Config;
use crate::create::all_creators;
use crate::library::ProjectLibrary;
use crate::project::Project;
use crate::spec::all_parsers;

// ---------------------------------------------------------------------------
// Top-level CLI
// ---------------------------------------------------------------------------

#[derive(Parser)]
#[command(
    name = "projspec",
    about = "Project introspection and management tool",
    version = env!("CARGO_PKG_VERSION"),
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Scan a directory for project types and display results
    Scan(ScanArgs),
    /// Execute an artifact in a project
    Make(MakeArgs),
    /// Create a new project of the given type
    Create(CreateArgs),
    /// Display information about known spec/content/artifact types
    Info(InfoArgs),
    /// Print version
    Version,
    /// Interact with the project library
    #[command(subcommand)]
    Library(LibraryCommands),
    /// Interact with projspec configuration
    #[command(subcommand)]
    Config(ConfigCommands),
}

// ---------------------------------------------------------------------------
// Scan
// ---------------------------------------------------------------------------

#[derive(Args)]
struct ScanArgs {
    /// Path to scan (default: current directory)
    #[arg(default_value = ".")]
    path: String,

    /// Only scan for these spec types (comma-separated, camel or snake case)
    #[arg(long, default_value = "")]
    types: String,

    /// Exclude these spec types (comma-separated)
    #[arg(long, default_value = "")]
    xtypes: String,

    /// Descend into all child directories
    #[arg(long)]
    walk: bool,

    /// Output abbreviated summary
    #[arg(long)]
    summary: bool,

    /// Output JSON
    #[arg(long)]
    json: bool,

    /// Add to library after scanning
    #[arg(long)]
    library: bool,
}

fn parse_types(s: &str) -> Option<Vec<String>> {
    if s.is_empty() || s == "ALL" {
        None
    } else {
        Some(s.split(',').map(|t| t.trim().to_string()).collect())
    }
}

// ---------------------------------------------------------------------------
// Make
// ---------------------------------------------------------------------------

#[derive(Args)]
struct MakeArgs {
    /// Artifact name: [spec.]type[.name]
    artifact: String,

    /// Path to the project (default: current directory)
    #[arg(default_value = ".")]
    path: String,

    /// For Process artifacts: wait for completion (default true)
    #[arg(long, default_value_t = true)]
    wait: bool,

    /// Only scan for these spec types
    #[arg(long, default_value = "")]
    types: String,

    /// Exclude these spec types
    #[arg(long, default_value = "")]
    xtypes: String,
}

// ---------------------------------------------------------------------------
// Create
// ---------------------------------------------------------------------------

#[derive(Args)]
struct CreateArgs {
    /// Spec type to create (snake_case)
    #[arg(name = "type")]
    spec_type: String,

    /// Target directory (default: current directory)
    #[arg(default_value = ".")]
    path: String,
}

// ---------------------------------------------------------------------------
// Info
// ---------------------------------------------------------------------------

#[derive(Args)]
struct InfoArgs {
    /// Class name to show docs for; omit to list all
    #[arg(default_value = "ALL")]
    name: String,
}

// ---------------------------------------------------------------------------
// Library sub-commands
// ---------------------------------------------------------------------------

#[derive(Subcommand)]
enum LibraryCommands {
    /// List all entries in the library
    List {
        /// Output as JSON
        #[arg(long)]
        json: bool,
    },
    /// Clear all entries from the library
    Clear,
    /// Delete a specific entry from the library
    Delete {
        /// URL of the entry to delete (as shown in `library list`)
        url: String,
    },
    /// Scan a path and add it to the library
    Add {
        /// Path to add
        #[arg(default_value = ".")]
        path: String,
        #[arg(long, default_value = "")]
        types: String,
        #[arg(long)]
        walk: bool,
    },
}

// ---------------------------------------------------------------------------
// Config sub-commands
// ---------------------------------------------------------------------------

#[derive(Subcommand)]
enum ConfigCommands {
    /// Get a config value
    Get { key: String },
    /// Set a config value
    Set { key: String, value: String },
    /// Unset a config value (reset to default)
    Unset { key: String },
    /// Show current config
    Show,
    /// Show all defaults and their descriptions
    Defaults,
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

pub fn run() {
    let cli = Cli::parse();
    if let Err(e) = dispatch(cli) {
        eprintln!("Error: {e:#}");
        std::process::exit(1);
    }
}

fn dispatch(cli: Cli) -> Result<()> {
    match cli.command {
        Commands::Version => {
            println!("projspec-rs {}", env!("CARGO_PKG_VERSION"));
        }

        Commands::Scan(args) => cmd_scan(args)?,
        Commands::Make(args) => cmd_make(args)?,
        Commands::Create(args) => cmd_create(args)?,
        Commands::Info(args) => cmd_info(args),

        Commands::Library(sub) => {
            let cfg = Config::load();
            let mut lib = ProjectLibrary::load(&cfg);
            match sub {
                LibraryCommands::List { json } => {
                    if json {
                        let map: serde_json::Map<String, serde_json::Value> = lib.entries.iter()
                            .map(|(k, v)| (k.clone(), v.to_json()))
                            .collect();
                        println!("{}", serde_json::to_string_pretty(&serde_json::Value::Object(map))?);
                    } else {
                        let mut urls: Vec<&str> = lib.entries.keys().map(|s| s.as_str()).collect();
                        urls.sort();
                        for url in urls {
                            let proj = &lib.entries[url];
                            println!("{}", proj.text_summary(true));
                        }
                    }
                }
                LibraryCommands::Clear => {
                    lib.clear()?;
                    eprintln!("Library cleared.");
                }
                LibraryCommands::Delete { url } => {
                    lib.delete_entry(&url)?;
                    eprintln!("Deleted {url}");
                }
                LibraryCommands::Add { path, types, walk } => {
                    let types_list = parse_types(&types);
                    let proj = Project::new(
                        &path,
                        Some(walk),
                        types_list.as_deref(),
                        None,
                        None,
                    )?;
                    let url = proj.url.clone();
                    lib.add_entry(&url, proj)?;
                    eprintln!("Added {url} to library.");
                }
            }
        }

        Commands::Config(sub) => {
            let mut cfg = Config::load();
            match sub {
                ConfigCommands::Get { key } => {
                    match cfg.get(&key) {
                        Some(v) => println!("{v}"),
                        None => {
                            eprintln!("Unknown key: {key}");
                            std::process::exit(1);
                        }
                    }
                }
                ConfigCommands::Set { key, value } => {
                    cfg.set(&key, &value)?;
                    cfg.save()?;
                    eprintln!("Set {key} = {value}");
                }
                ConfigCommands::Unset { key } => {
                    cfg.unset(&key)?;
                    cfg.save()?;
                    eprintln!("Unset {key} (reset to default)");
                }
                ConfigCommands::Show => {
                    println!("{}", serde_json::to_string_pretty(&cfg)?);
                }
                ConfigCommands::Defaults => {
                    let config_dir = std::env::var("PROJSPEC_CONFIG_DIR").unwrap_or_else(|_| "(unset)".to_string());
                    println!("PROJSPEC_CONFIG_DIR: {config_dir}");
                    println!();
                    for (key, default, doc) in Config::defaults_table() {
                        println!("{key}: {default} -- {doc}");
                    }
                }
            }
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Command implementations
// ---------------------------------------------------------------------------

fn cmd_scan(args: ScanArgs) -> Result<()> {
    let types_list = parse_types(&args.types);
    let xtypes_list = parse_types(&args.xtypes);

    let proj = Project::new(
        &args.path,
        if args.walk { Some(true) } else { None },
        types_list.as_deref(),
        xtypes_list.as_deref(),
        None,
    )?;

    if args.json {
        println!("{}", serde_json::to_string_pretty(&proj.to_json())?);
    } else if args.summary {
        println!("{}", proj.text_summary(false));
    } else {
        println!("{}", proj.text_full());
    }

    if args.library {
        let cfg = Config::load();
        let mut lib = ProjectLibrary::load(&cfg);
        let url = proj.url.clone();
        lib.add_entry(&url, proj)?;
        eprintln!("Added to library: {url}");
    }
    Ok(())
}

fn cmd_make(args: MakeArgs) -> Result<()> {
    let types_list = parse_types(&args.types);
    let xtypes_list = parse_types(&args.xtypes);

    let proj = Project::new(
        &args.path,
        None,
        types_list.as_deref(),
        xtypes_list.as_deref(),
        None,
    )?;

    let (artifact, cwd) = proj.find_artifact(&args.artifact)
        .ok_or_else(|| anyhow::anyhow!("Artifact '{}' not found in project at '{}'", args.artifact, args.path))?;

    let result = artifact.make(cwd, args.wait)?;
    println!("{result}");
    Ok(())
}

fn cmd_create(args: CreateArgs) -> Result<()> {
    std::fs::create_dir_all(&args.path)?;

    let creators = all_creators();
    let creator = creators.iter().find(|c| c.name == args.spec_type)
        .ok_or_else(|| {
            let names: Vec<&str> = creators.iter().map(|c| c.name).collect();
            anyhow::anyhow!("Unknown spec type '{}'. Supported: {}", args.spec_type, names.join(", "))
        })?;

    let files = (creator.creator)(&args.path)?;
    for f in &files {
        println!("{f}");
    }
    Ok(())
}

fn cmd_info(args: InfoArgs) {
    if args.name == "ALL" {
        // Print structured JSON of all known types
        let specs: Vec<serde_json::Value> = all_parsers().iter().map(|(name, _)| {
            serde_json::json!({"name": name, "category": "spec"})
        }).collect();
        let creators: Vec<serde_json::Value> = all_creators().iter().map(|c| {
            serde_json::json!({"name": c.name, "doc": c.doc, "category": "create"})
        }).collect();
        let info = serde_json::json!({
            "specs": specs,
            "creators": creators,
        });
        println!("{}", serde_json::to_string_pretty(&info).unwrap());
    } else {
        // look up by name
        if let Some((name, _)) = all_parsers().iter().find(|(n, _)| *n == args.name.as_str()) {
            println!("spec: {name}");
        } else if let Some(c) = all_creators().iter().find(|c| c.name == args.name.as_str()) {
            println!("create: {} — {}", c.name, c.doc);
        } else {
            eprintln!("Name not found: {}", args.name);
            std::process::exit(1);
        }
    }
}
