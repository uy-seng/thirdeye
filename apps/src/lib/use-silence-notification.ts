import { useEffect, useRef } from "react";

import { apiUrl } from "./api";
import {
  SILENCE_ALERT_START_FAILED_MESSAGE,
  isEmptyTranscriptResult,
  isTranscriptActivity,
  notifyOnInactivityEnabled,
  silenceNotificationRecordingLabel,
  silenceNotificationTimeoutMsForJob,
} from "./silence-notifications";
import {
  recordSilenceNotificationActivity,
  startSilenceNotificationMonitor,
  stopSilenceNotificationMonitor,
} from "./services";
import type { JobResponse, TranscriptBlock } from "./types";

function elapsedMsSince(timestamp: string | null) {
  if (!timestamp) {
    return 0;
  }
  const parsed = Date.parse(timestamp);
  return Number.isFinite(parsed) ? Math.max(0, Date.now() - parsed) : 0;
}

export function useSilenceNotification(jobs: JobResponse[] | JobResponse | null, onPermissionUnavailable: (message: string) => void) {
  const onPermissionUnavailableRef = useRef(onPermissionUnavailable);
  const activeJobs = Array.isArray(jobs) ? jobs : jobs ? [jobs] : [];
  const dependencyKey = activeJobs.map((job) => `${job.id}:${job.silence_timeout_minutes}:${job.title}:${job.capture_target.label}`).join("|");

  useEffect(() => {
    onPermissionUnavailableRef.current = onPermissionUnavailable;
  }, [onPermissionUnavailable]);

  useEffect(() => {
    if (activeJobs.length === 0) {
      return;
    }

    let closed = false;
    const streams: EventSource[] = [];
    const cleanupJobs: string[] = [];

    for (const activeJob of activeJobs) {
      if (!notifyOnInactivityEnabled(activeJob)) {
        continue;
      }
      const timeoutMs = silenceNotificationTimeoutMsForJob(activeJob);
      const stream = new EventSource(apiUrl(`/api/jobs/${activeJob.id}/live/stream`));
      streams.push(stream);
      cleanupJobs.push(activeJob.id);

      void startSilenceNotificationMonitor({
        jobId: activeJob.id,
        title: silenceNotificationRecordingLabel(activeJob),
        timeoutMs,
        elapsedMs: elapsedMsSince(activeJob.started_at ?? activeJob.created_at),
      }).catch(() => {
        if (!closed) {
          onPermissionUnavailableRef.current(SILENCE_ALERT_START_FAILED_MESSAGE);
        }
      });

      stream.onmessage = (message) => {
        const event = JSON.parse(message.data) as TranscriptBlock;
        if (isTranscriptActivity(event)) {
          void recordSilenceNotificationActivity(activeJob.id);
        } else if (isEmptyTranscriptResult(event)) {
          return;
        } else if (event.type === "complete") {
          void stopSilenceNotificationMonitor(activeJob.id);
          stream.close();
        }
      };
    }

    return () => {
      closed = true;
      for (const jobId of cleanupJobs) {
        void stopSilenceNotificationMonitor(jobId);
      }
      for (const stream of streams) {
        stream.close();
      }
    };
  }, [dependencyKey]);
}
