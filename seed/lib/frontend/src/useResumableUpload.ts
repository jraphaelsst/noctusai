/** `useResumableUpload(api)` — React state around `uploadResumable`: status, honest progress, retry/resume, cancel. */
import { useCallback, useRef, useState } from 'react';
import { abortResumableUpload, uploadResumable } from './resumableUpload';
import type { ResumableUploadOptions, ResumableUploadResult, UploadApi, UploadProgress } from './resumableUpload';

export type ResumableUploadStatus = 'idle' | 'uploading' | 'done' | 'error';

const ZERO: UploadProgress = { confirmedBytes: 0, totalBytes: 0, confirmedParts: 0, totalParts: 0, percent: 0 };

export function useResumableUpload(api: UploadApi, defaults: ResumableUploadOptions = {}) {
  const [status, setStatus] = useState<ResumableUploadStatus>('idle');
  const [progress, setProgress] = useState<UploadProgress>(ZERO);
  const [error, setError] = useState<Error | null>(null);
  const controller = useRef<AbortController | null>(null);
  const lastId = useRef<string | null>(null);

  /** Calling it again with the same file RESUMES (the server reports the parts it already has). */
  const upload = useCallback(
    async (file: File, options: ResumableUploadOptions = {}): Promise<ResumableUploadResult> => {
      controller.current?.abort();
      const ctl = new AbortController();
      controller.current = ctl;
      setStatus('uploading');
      setError(null);
      try {
        const result = await uploadResumable(api, file, {
          ...defaults,
          ...options,
          signal: ctl.signal,
          onProgress: (p) => {
            setProgress(p);
            options.onProgress?.(p);
          },
        });
        lastId.current = result.uploadId;
        setStatus('done');
        return result;
      } catch (err) {
        setError(err as Error);
        setStatus('error');
        throw err;
      }
    },
    [api, defaults],
  );

  /** Stop sending. The server session stays open (resumable until it expires); use `discard` to drop it. */
  const cancel = useCallback(() => controller.current?.abort(), []);

  const discard = useCallback(
    async (uploadId?: string) => {
      const id = uploadId ?? lastId.current;
      controller.current?.abort();
      if (id) await abortResumableUpload(api, id, defaults.basePath);
      setStatus('idle');
      setProgress(ZERO);
    },
    [api, defaults.basePath],
  );

  const reset = useCallback(() => {
    setStatus('idle');
    setProgress(ZERO);
    setError(null);
  }, []);

  return { upload, cancel, discard, reset, status, progress, error, isUploading: status === 'uploading' };
}
