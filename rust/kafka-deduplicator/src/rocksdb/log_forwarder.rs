use std::collections::HashMap;
use std::path::{Path, PathBuf};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::task::JoinHandle;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Interval between scans for new/rotated LOG files in the shared log directory.
const SCAN_INTERVAL: std::time::Duration = std::time::Duration::from_secs(5);

/// Forwards RocksDB LOG file content to the application's tracing system.
///
/// When `rocksdb_log_dir` is set, all RocksDB instances write their LOG files
/// to a shared directory. This forwarder tails those files and emits each line
/// through `tracing::info!` so they appear in stdout and flow into Loki.
pub struct RocksDbLogForwarder {
    task: Option<JoinHandle<()>>,
    cancel: CancellationToken,
}

impl RocksDbLogForwarder {
    /// Start the log forwarder background task.
    /// Scans `log_dir` for RocksDB LOG files and tails them into tracing.
    pub fn start(log_dir: PathBuf) -> Self {
        let cancel = CancellationToken::new();
        let cancel_clone = cancel.clone();

        let task = tokio::spawn(async move {
            if let Err(e) = tokio::fs::create_dir_all(&log_dir).await {
                warn!("Failed to create RocksDB log directory {:?}: {e}", log_dir);
                return;
            }
            info!("RocksDB log forwarder started, watching {:?}", log_dir);
            run_forwarder(&log_dir, cancel_clone).await;
            info!("RocksDB log forwarder stopped");
        });

        Self {
            task: Some(task),
            cancel,
        }
    }

    /// Stop the forwarder and wait for it to finish.
    pub async fn stop(&mut self) {
        self.cancel.cancel();
        if let Some(task) = self.task.take() {
            let _ = task.await;
        }
    }
}

/// Track file position for each LOG file we're tailing.
struct FileState {
    /// Byte offset we've read up to.
    position: u64,
}

async fn run_forwarder(log_dir: &Path, cancel: CancellationToken) {
    let mut files: HashMap<PathBuf, FileState> = HashMap::new();

    loop {
        tokio::select! {
            biased;
            _ = cancel.cancelled() => break,
            _ = tokio::time::sleep(SCAN_INTERVAL) => {}
        }

        // Scan for LOG files (RocksDB names them LOG, LOG.old.*, etc.)
        let Ok(mut entries) = tokio::fs::read_dir(log_dir).await else {
            continue;
        };

        let mut current_files: Vec<PathBuf> = Vec::new();
        while let Ok(Some(entry)) = entries.next_entry().await {
            let name = entry.file_name();
            let name_str = name.to_string_lossy();
            // RocksDB LOG files are named like: LOG, LOG.old.1234567890
            // When using set_db_log_dir, they include the DB path in the name
            if name_str.contains("LOG") {
                current_files.push(entry.path());
            }
        }

        // Remove tracked files that no longer exist (rotated away)
        files.retain(|path, _| current_files.contains(path));

        // Tail each LOG file from where we left off
        for path in current_files {
            let state = files.entry(path.clone()).or_insert(FileState {
                position: match tokio::fs::metadata(&path).await {
                    // For new files we haven't seen, start from the current end
                    // to avoid dumping historical content on first discovery
                    Ok(meta) => meta.len(),
                    Err(_) => 0,
                },
            });

            if let Err(e) = tail_file(&path, state).await {
                debug!("Error tailing {:?}: {e}", path);
            }
        }
    }
}

async fn tail_file(path: &Path, state: &mut FileState) -> std::io::Result<()> {
    let file = tokio::fs::File::open(path).await?;
    let metadata = file.metadata().await?;

    // File was truncated or rotated (smaller than our position)
    if metadata.len() < state.position {
        state.position = 0;
    }

    // Nothing new to read
    if metadata.len() <= state.position {
        return Ok(());
    }

    // Seek to where we left off
    use tokio::io::AsyncSeekExt;
    let mut file = file;
    file.seek(std::io::SeekFrom::Start(state.position)).await?;

    let mut reader = BufReader::new(file);
    let mut line = String::new();
    let filename = path
        .file_name()
        .unwrap_or_default()
        .to_string_lossy()
        .to_string();

    loop {
        line.clear();
        let bytes_read = reader.read_line(&mut line).await?;
        if bytes_read == 0 {
            break;
        }
        state.position += bytes_read as u64;

        let trimmed = line.trim_end();
        if trimmed.is_empty() {
            continue;
        }

        // Emit through tracing — shows up in stdout and Loki
        info!(target: "rocksdb", file = filename, "{trimmed}");
    }

    Ok(())
}
