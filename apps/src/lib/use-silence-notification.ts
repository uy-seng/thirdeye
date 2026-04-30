import { useEffect, useRef } from "react";

import { apiUrl } from "./api";
import {
  SILENCE_ALERT_START_FAILED_MESSAGE,
  isEmptyTranscriptResult,
  isTranscriptActivity,
  notifyOnInactivityEnabled,
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

export function useSilenceNotification(job: JobResponse | null, onPermissionUnavailable: (message: string) => void) {
  const onPermissionUnavailableRef = useRef(onPermissionUnavailable);

  useEffect(() => {
    onPermissionUnavailableRef.current = onPermissionUnavailable;
  }, [onPermissionUnavailable]);

  useEffect(() => {
    if (!job || !notifyOnInactivityEnabled(job)) {
      return;
    }

    const activeJob = job;
    let closed = false;
    const timeoutMs = silenceNotificationTimeoutMsForJob(activeJob);
    const stream = new EventSource(apiUrl(`/api/jobs/${activeJob.id}/live/stream`));

    void startSilenceNotificationMonitor({
      jobId: activeJob.id,
      title: activeJob.title,
      timeoutMs,
      elapsedMs: elapsedMsSince(activeJob.started_at ?? activeJob.created_at),
    }).catch(() => {
      if (!closed) {
        onPermissionUnavailableRef.current(SILENCE_ALERT_START_FAILED_MESSAGE);
      }
    });

    function close() {
      closed = true;
      void stopSilenceNotificationMonitor(activeJob.id);
      stream.close();
    }

    stream.onmessage = (message) => {
      const event = JSON.parse(message.data) as TranscriptBlock;
      if (isTranscriptActivity(event)) {
        void recordSilenceNotificationActivity(activeJob.id);
      } else if (isEmptyTranscriptResult(event)) {
        return;
      } else if (event.type === "complete") {
        close();
      }
    };

    return close;
  }, [job?.id, job?.silence_timeout_minutes, job?.title]);
}
