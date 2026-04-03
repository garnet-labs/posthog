use anyhow::{Context, Result};
use async_trait::async_trait;
use bytes::Bytes;
use object_store::path::Path as ObjectPath;
use object_store::{ObjectStore, ObjectStoreExt, PutPayload, WriteMultipart};
use std::path::Path;
use std::sync::Arc;
use tokio::fs::File;
use tokio::io::AsyncReadExt;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

use super::config::CheckpointConfig;
use super::error::UploadCancelledError;
use super::s3_client::create_s3_client;
use super::uploader::CheckpointUploader;
use crate::metrics_const::CHECKPOINT_FILE_UPLOADS_COUNTER;

/// Part size for S3 multipart uploads. Each part is read from disk and uploaded
/// as an individual PUT request. S3 requires a minimum of 5MB per part.
const MULTIPART_PART_SIZE: usize = 10 * 1024 * 1024; // 10MB

fn is_cancelled(cancel_token: Option<&CancellationToken>) -> bool {
    cancel_token.is_some_and(CancellationToken::is_cancelled)
}

/// Hint the kernel to evict page cache pages for a file after it has been fully read.
/// This is a best-effort operation: failure is logged but does not abort the upload.
/// Only effective on Linux; a no-op on other platforms.
fn advise_dontneed(file: &File, path: &Path) {
    #[cfg(target_os = "linux")]
    {
        use std::os::unix::io::AsRawFd;
        let fd = file.as_raw_fd();
        // SAFETY: fd is valid for the lifetime of `file`, and posix_fadvise is safe to call
        // with any fd/offset/len combination — invalid values simply return an error code.
        let ret = unsafe { libc::posix_fadvise(fd, 0, 0, libc::POSIX_FADV_DONTNEED) };
        if ret != 0 {
            tracing::debug!("posix_fadvise(DONTNEED) returned {ret} for {path:?} (non-fatal)");
        }
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = (file, path);
    }
}

/// S3Uploader using `object_store` crate with `LimitStore` for bounded concurrency.
/// The LimitStore wraps the S3 client with a semaphore that limits concurrent requests.
///
/// Files are uploaded sequentially to minimize memory: only one file's buffers exist
/// at a time per partition. Part-level concurrency within each file (via `put_part`)
/// provides S3 throughput without the memory overhead of many open files.
#[derive(Debug)]
pub struct S3Uploader {
    store: Arc<dyn ObjectStore>,
    config: CheckpointConfig,
}

impl S3Uploader {
    pub async fn new(config: CheckpointConfig) -> Result<Self> {
        let store =
            create_s3_client(&config, config.max_concurrent_checkpoint_file_uploads).await?;

        info!(
            "S3 uploader initialized for bucket '{}' with max {} concurrent S3 requests",
            config.s3_bucket, config.max_concurrent_checkpoint_file_uploads,
        );

        let store: Arc<dyn ObjectStore> = store;
        Ok(Self { store, config })
    }

    /// Upload a single file using multipart upload.
    ///
    /// Uses `put_multipart` + `WriteMultipart` directly instead of `BufWriter` to avoid
    /// double-buffering: file data is read into a buffer, converted to `Bytes` (zero-copy),
    /// and submitted as a multipart part. The LimitStore semaphore on the underlying store
    /// governs how many S3 requests are in-flight across all uploads.
    async fn upload_file_cancellable(
        &self,
        local_path: &Path,
        s3_key: &str,
        cancel_token: Option<&CancellationToken>,
    ) -> Result<()> {
        if is_cancelled(cancel_token) {
            metrics::counter!(CHECKPOINT_FILE_UPLOADS_COUNTER, "status" => "cancelled")
                .increment(1);
            warn!("Upload cancelled before starting: {s3_key}");
            return Err(UploadCancelledError {
                reason: format!("before starting: {s3_key}"),
            }
            .into());
        }

        let path = ObjectPath::from(s3_key);

        let mut file = File::open(local_path)
            .await
            .with_context(|| format!("Failed to open file: {local_path:?}"))?;

        let file_size = file
            .metadata()
            .await
            .with_context(|| format!("Failed to get metadata for file: {local_path:?}"))?
            .len();

        let upload = self
            .store
            .put_multipart(&path)
            .await
            .with_context(|| format!("Failed to initiate multipart upload: {s3_key}"))?;

        let mut write = WriteMultipart::new_with_chunk_size(upload, MULTIPART_PART_SIZE);

        loop {
            if is_cancelled(cancel_token) {
                let _ = write.abort().await;
                metrics::counter!(CHECKPOINT_FILE_UPLOADS_COUNTER, "status" => "cancelled")
                    .increment(1);
                warn!("Upload of {s3_key} cancelled mid-stream");
                return Err(UploadCancelledError {
                    reason: format!("mid-stream: {s3_key}"),
                }
                .into());
            }

            // Read up to MULTIPART_PART_SIZE from file. Each read allocates a fresh buffer
            // that is moved (zero-copy) into the multipart part via Bytes::from(Vec).
            let mut buf = vec![0u8; MULTIPART_PART_SIZE];
            let n = match file.read(&mut buf).await {
                Ok(0) => break,
                Ok(n) => n,
                Err(e) => {
                    let _ = write.abort().await;
                    metrics::counter!(CHECKPOINT_FILE_UPLOADS_COUNTER, "status" => "error")
                        .increment(1);
                    return Err(anyhow::Error::new(e))
                        .with_context(|| format!("Failed to read file: {local_path:?}"));
                }
            };
            buf.truncate(n);

            // Bytes::from(Vec<u8>) takes ownership without copying.
            // WriteMultipart::put accumulates chunks and submits a part when chunk_size is reached.
            write.put(Bytes::from(buf));
        }

        advise_dontneed(&file, local_path);

        write
            .finish()
            .await
            .map_err(|e| anyhow::anyhow!(e))
            .with_context(|| format!("Failed to complete upload for: {s3_key}"))?;

        metrics::counter!(CHECKPOINT_FILE_UPLOADS_COUNTER, "status" => "success").increment(1);
        info!(
            "Uploaded file {local_path:?} ({file_size} bytes) to s3://{}/{}",
            self.config.s3_bucket, s3_key
        );
        Ok(())
    }

    /// Upload bytes directly to S3
    async fn upload_bytes(&self, s3_key: &str, data: Vec<u8>) -> Result<()> {
        let path = ObjectPath::from(s3_key);

        self.store
            .put(&path, PutPayload::from(data))
            .await
            .with_context(|| format!("Failed to upload to S3 key: {s3_key}"))?;

        Ok(())
    }
}

#[async_trait]
impl CheckpointUploader for S3Uploader {
    async fn upload_checkpoint_with_plan_cancellable(
        &self,
        plan: &super::CheckpointPlan,
        cancel_token: Option<&CancellationToken>,
    ) -> Result<Vec<String>> {
        if is_cancelled(cancel_token) {
            warn!("Upload cancelled before starting batch");
            return Err(UploadCancelledError {
                reason: "before starting batch".to_string(),
            }
            .into());
        }

        info!(
            "Starting upload: {} files to upload, {} reused from parents",
            plan.files_to_upload.len(),
            plan.info.metadata.files.len() - plan.files_to_upload.len()
        );

        let mut uploaded_keys = Vec::with_capacity(plan.files_to_upload.len());

        // Upload files sequentially to minimize memory. Only one file's read buffers
        // and in-flight multipart parts exist at a time. The LimitStore semaphore on the
        // underlying store governs S3 concurrency across all concurrent partition uploads.
        for file_info in &plan.files_to_upload {
            if is_cancelled(cancel_token) {
                warn!("Upload cancelled between files");
                return Err(UploadCancelledError {
                    reason: "between files".to_string(),
                }
                .into());
            }

            let dest = plan.info.get_file_key(&file_info.filename);
            self.upload_file_cancellable(&file_info.local_path, &dest, cancel_token)
                .await?;
            uploaded_keys.push(dest);
        }

        if is_cancelled(cancel_token) {
            warn!("Upload cancelled before metadata upload");
            return Err(UploadCancelledError {
                reason: "before metadata upload".to_string(),
            }
            .into());
        }

        // ALL files succeeded - now safe to upload metadata
        let metadata_json = plan.info.metadata.to_json()?;
        let metadata_key = plan.info.get_metadata_key();
        self.upload_bytes(&metadata_key, metadata_json.into_bytes())
            .await
            .with_context(|| format!("Failed to upload metadata to S3 key: {metadata_key}"))?;

        info!(
            "Uploaded {} files and metadata to s3://{}/{}",
            plan.files_to_upload.len(),
            self.config.s3_bucket,
            plan.info.get_remote_attempt_path(),
        );

        let mut all_keys = uploaded_keys;
        all_keys.push(metadata_key);
        Ok(all_keys)
    }

    async fn is_available(&self) -> bool {
        !self.config.s3_bucket.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_cancelled_none_token() {
        assert!(!is_cancelled(None));
    }

    #[test]
    fn test_is_cancelled_active_token() {
        let token = CancellationToken::new();
        assert!(!is_cancelled(Some(&token)));
    }

    #[test]
    fn test_is_cancelled_cancelled_token() {
        let token = CancellationToken::new();
        token.cancel();
        assert!(is_cancelled(Some(&token)));
    }

}
