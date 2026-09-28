/// fs.rs — Virtual filesystem abstraction backed by opendal.
///
/// Design decisions:
///
/// D-FS1: We use `opendal::blocking::Operator` throughout.
///   The parsers are synchronous (they do string processing, not IO-heavy work),
///   and the blocking operator is the clearest fit. The tokio runtime is created
///   once in `operator_from_url()` and lives for the duration of the scan.
///
/// D-FS2: `Vfs` is a thin struct wrapping `opendal::blocking::Operator`, not a
///   trait. This avoids `dyn Vfs` boxing complexity and lets the compiler inline
///   all calls. If heterogeneous backends per-parse are ever needed, promote to
///   a trait at that point.
///
/// D-FS3: Paths inside the operator are always *relative* to the operator's root.
///   The operator is configured with root = the project directory. So listing
///   "/" gives the project root entries, and reading "pyproject.toml" reads the
///   file at root/pyproject.toml. The caller (project.rs) strips the url prefix
///   before calling Vfs methods.
///
/// D-FS4: opendal::Http service only supports `read` and `stat` — no `list`.
///   We work around this: the caller must supply the file listing when constructing
///   a project from an HTTP backend. In practice we use the HTTP service for
///   reading specific files whose names are already known from the listing.
///   For tests we provide the basenames directly.
///
/// D-FS5: `operator_from_url()` reads configuration from environment variables
///   only (no explicit config struct yet). Each backend reads its own standard
///   env vars (AWS_ACCESS_KEY_ID, etc.) because opendal's S3 builder loads them
///   automatically when `disable_config_load` is NOT called.

use std::collections::HashMap;
use std::sync::OnceLock;

use anyhow::{Context, Result};
use opendal::blocking::Operator as BlockingOp;
use opendal::{services, ErrorKind, Operator};

// ---------------------------------------------------------------------------
// Runtime singleton — opendal's blocking wrapper requires an active tokio Handle
// ---------------------------------------------------------------------------

static RUNTIME: OnceLock<tokio::runtime::Runtime> = OnceLock::new();

fn get_runtime() -> &'static tokio::runtime::Runtime {
    RUNTIME.get_or_init(|| {
        tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .expect("failed to build tokio runtime for opendal")
    })
}

fn make_blocking(op: Operator) -> Result<BlockingOp> {
    let _guard = get_runtime().enter();
    BlockingOp::new(op).map_err(|e| anyhow::anyhow!("opendal blocking: {e}"))
}

// ---------------------------------------------------------------------------
// Vfs — thin wrapper around blocking::Operator
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct Vfs {
    pub op: BlockingOp,
    /// Human-readable scheme label for error messages / display.
    pub scheme: String,
}

impl Vfs {
    // ------------------------------------------------------------------
    // Constructors
    // ------------------------------------------------------------------

    /// Local filesystem backend, rooted at `path`.
    pub fn local(path: &str) -> Result<Self> {
        let builder = services::Fs::default().root(path);
        let op = make_blocking(Operator::new(builder)?.finish())?;
        Ok(Vfs { op, scheme: "file".into() })
    }

    /// In-memory backend. Caller populates it via `write_bytes`.
    pub fn memory() -> Result<Self> {
        let op = make_blocking(Operator::new(services::Memory::default())?.finish())?;
        Ok(Vfs { op, scheme: "memory".into() })
    }

    /// HTTP read-only backend. `endpoint` is e.g. `http://127.0.0.1:8080`.
    /// `root` is the path prefix on the server (e.g. `""` or `"/projects/foo"`).
    pub fn http(endpoint: &str, root: &str) -> Result<Self> {
        let mut builder = services::Http::default().endpoint(endpoint);
        if !root.is_empty() {
            builder = builder.root(root);
        }
        let op = make_blocking(Operator::new(builder)?.finish())?;
        Ok(Vfs { op, scheme: "http".into() })
    }

    /// S3 backend.  All configuration comes from environment variables:
    ///   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION,
    ///   AWS_ENDPOINT_URL (for moto/minio), AWS_DEFAULT_REGION.
    /// `bucket` and `root` (key prefix) are required.
    pub fn s3(bucket: &str, root: &str, endpoint: Option<&str>, region: Option<&str>) -> Result<Self> {
        let mut builder = services::S3::default().bucket(bucket);
        if !root.is_empty() {
            builder = builder.root(root);
        }
        if let Some(ep) = endpoint {
            builder = builder.endpoint(ep);
        }
        if let Some(r) = region {
            builder = builder.region(r);
        }
        // Env-var credentials are loaded automatically; we do NOT call
        // disable_config_load() so that AWS_ACCESS_KEY_ID etc. are respected.
        let op = make_blocking(Operator::new(builder)?.finish())?;
        Ok(Vfs { op, scheme: "s3".into() })
    }

    // ------------------------------------------------------------------
    // Write helper (used by test helpers and memory backend setup)
    // ------------------------------------------------------------------

    pub fn write_bytes(&self, path: &str, data: Vec<u8>) -> Result<()> {
        self.op.write(path, data)
            .with_context(|| format!("write {path}"))?;
        Ok(())
    }

    // ------------------------------------------------------------------
    // Read operations — used by ParseCtx
    // ------------------------------------------------------------------

    /// Read a file, returning its UTF-8 content. Returns None on any error.
    pub fn read_text(&self, path: &str) -> Option<String> {
        let buf = self.op.read(path).ok()?;
        String::from_utf8(buf.to_bytes().to_vec()).ok()
    }

    /// Check whether a path exists (file or dir).
    pub fn exists(&self, path: &str) -> bool {
        self.op.exists(path).unwrap_or(false)
    }

    /// List direct children of a directory path (e.g. `""` = root).
    /// Returns basenames only (no leading slash).
    pub fn list_dir(&self, path: &str) -> Vec<String> {
        // opendal requires dirs to end with "/"; root is "/"
        let listing_path = if path.is_empty() || path == "/" {
            "/".to_string()
        } else if path.ends_with('/') {
            path.to_string()
        } else {
            format!("{path}/")
        };

        match self.op.list(&listing_path) {
            Ok(entries) => entries
                .into_iter()
                .map(|e| {
                    // strip trailing "/" from directory names
                    e.path().trim_start_matches('/').trim_end_matches('/').to_string()
                })
                .filter(|s| !s.is_empty())
                .collect(),
            Err(_) => vec![],
        }
    }

    /// List direct children and return {basename: relative_path} map.
    /// For a local backend the relative_path equals the basename.
    /// For S3/HTTP we use the same relative path (object key within root).
    pub fn basenames(&self) -> HashMap<String, String> {
        self.list_dir("")
            .into_iter()
            .map(|name| (name.clone(), name))
            .collect()
    }
}

// ---------------------------------------------------------------------------
// operator_from_url — build a Vfs from a URL string
// ---------------------------------------------------------------------------
//
// Supported URL schemes:
//   /abs/path or ./rel/path  → local fs (services::Fs)
//   file:///abs/path         → local fs
//   s3://bucket/prefix       → S3 (env-var creds)
//   http://host/root         → HTTP read-only
//   https://host/root        → HTTP read-only
//   memory://               → in-memory (only useful for tests via Vfs::memory())
//
// For S3: the URL host is the bucket, the path is the root prefix.
// Region and endpoint are read from AWS_REGION / AWS_ENDPOINT_URL env vars.

pub fn vfs_from_url(url: &str) -> Result<(Vfs, String)> {
    if url.starts_with("s3://") {
        let without_scheme = &url[5..];
        let (bucket, root) = without_scheme.split_once('/').unwrap_or((without_scheme, ""));
        let endpoint = std::env::var("AWS_ENDPOINT_URL").ok();
        let region = std::env::var("AWS_REGION")
            .or_else(|_| std::env::var("AWS_DEFAULT_REGION"))
            .ok();
        let vfs = Vfs::s3(
            bucket,
            if root.is_empty() { "/" } else { root },
            endpoint.as_deref(),
            region.as_deref(),
        )?;
        // canonical URL is the s3:// URL itself (no local path)
        return Ok((vfs, url.to_string()));
    }

    if url.starts_with("http://") || url.starts_with("https://") {
        // Split endpoint from root path: http://host[:port]/root/path
        // We set endpoint = scheme://host[:port] and root = /root/path
        let without_scheme = if url.starts_with("https://") { &url[8..] } else { &url[7..] };
        let scheme_prefix = if url.starts_with("https://") { "https://" } else { "http://" };
        let (host_port, root_path) = without_scheme.split_once('/').unwrap_or((without_scheme, ""));
        let endpoint = format!("{scheme_prefix}{host_port}");
        let root = if root_path.is_empty() { "/".to_string() } else { format!("/{root_path}") };
        let vfs = Vfs::http(&endpoint, &root)?;
        return Ok((vfs, url.to_string()));
    }

    if url.starts_with("file://") {
        let path = &url[7..];
        let canonical = std::fs::canonicalize(path)
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|_| path.to_string());
        let vfs = Vfs::local(&canonical)?;
        return Ok((vfs, canonical));
    }

    // Default: treat as local path
    let canonical = std::fs::canonicalize(url)
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|_| url.to_string());
    let vfs = Vfs::local(&canonical)?;
    Ok((vfs, canonical))
}
