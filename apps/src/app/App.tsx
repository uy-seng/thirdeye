import { listen } from "@tauri-apps/api/event";
import { Bell, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  captureMicrophoneLiveUrl,
  createDesktop,
  deleteJob,
  getArtifactsOverview,
  getDesktops,
  getJob,
  getJobs,
  setRecordMicrophoneEnabled,
  setTargetAudioMuted,
  stopCapture,
} from "../lib/api";
import { userVisibleArtifacts } from "../lib/artifacts";
import { chooseSelectedJobId } from "../lib/job-selection";
import { ACTIVE_STATES, canDeleteJob, canStopCapture, recordMicrophoneEnabled } from "../lib/job-state";
import { getServiceStatus, requestMicrophoneAccess, startLocalServices, stopLocalServices } from "../lib/services";
import type { ArtifactFile, DesktopSession, JobDetailResponse, JobResponse, ServiceStatus } from "../lib/types";
import { useSilenceNotification } from "../lib/use-silence-notification";
import {
  formatVoiceNoteRecordingError,
  requestAuthorizedMicrophoneStream,
  startMicrophonePcmStream,
  stopMediaStream,
  type MicrophonePcmStreamSession,
} from "../lib/voice-note-audio";
import { Navigation } from "../components/navigation/Navigation";
import { Button } from "../components/ui";
import { StartCapturePanel } from "../features/capture";
import { JobDetail, JobsTable } from "../features/jobs";
import { LiveCaptureControls, LiveJobSelector, LiveSummaryPanel, LiveTranscript } from "../features/live";
import { SettingsPanel } from "../features/settings/SettingsPanel";
import { VoiceNotesPanel } from "../features/voice-notes/VoiceNotesPanel";
import { hashForView, viewFromHash, type View } from "./view";

const deleteSuccessNotice = "Job deleted.";
const stopRefreshIntervalMs = 1_500;
const stopRefreshTimeoutMs = 180_000;

type SilenceAppAlertPayload = {
  jobId: string;
  title: string;
  body: string;
};

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function viewTitle(view: View) {
  const titles: Record<View, string> = {
    capture: "Capture",
    live: "Live",
    "voice-notes": "Voice notes",
    settings: "Settings",
  };
  return titles[view];
}

export function App() {
  const [view, setViewState] = useState<View>(() => viewFromHash(window.location.hash));
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus | null>(null);
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [desktops, setDesktops] = useState<DesktopSession[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<JobDetailResponse | null>(null);
  const [stoppingJobId, setStoppingJobId] = useState<string | null>(null);
  const [mutingJobId, setMutingJobId] = useState<string | null>(null);
  const [microphoneJobId, setMicrophoneJobId] = useState<string | null>(null);
  const [confirmingDeleteJobId, setConfirmingDeleteJobId] = useState<string | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactFile[]>([]);
  const [notice, setNotice] = useState("Starting local services...");
  const [silenceAlert, setSilenceAlert] = useState<SilenceAppAlertPayload | null>(null);
  const selectedJobIdRef = useRef<string | null>(null);
  const microphoneSessionsRef = useRef<Record<string, MicrophonePcmStreamSession>>({});

  const activeJobs = useMemo(() => jobs.filter((job) => ACTIVE_STATES.has(job.state)), [jobs]);
  const visibleView = view === "live" && activeJobs.length === 0 ? "capture" : view;
  const selectedActiveListJob = selectedJobId ? activeJobs.find((job) => job.id === selectedJobId) ?? null : null;
  const selectedActiveJob = selectedJob && selectedJob.id === selectedJobId && ACTIVE_STATES.has(selectedJob.state) ? selectedJob : null;
  const liveJobListItem = selectedActiveListJob ?? activeJobs[0] ?? null;
  const liveJob = selectedActiveJob?.id === liveJobListItem?.id ? selectedActiveJob : null;
  const handleSilenceNotificationUnavailable = useCallback((message: string) => {
    setNotice(message);
  }, []);
  const setView = useCallback((nextView: View) => {
    setViewState(nextView);
    const nextHash = hashForView(nextView);
    if (window.location.hash !== nextHash) {
      window.history.pushState(null, "", nextHash);
    }
  }, []);

  useSilenceNotification(activeJobs, handleSilenceNotificationUnavailable);

  useEffect(() => {
    function handleRouteChange() {
      setViewState(viewFromHash(window.location.hash));
    }

    window.addEventListener("hashchange", handleRouteChange);
    handleRouteChange();
    return () => window.removeEventListener("hashchange", handleRouteChange);
  }, []);

  useEffect(() => {
    let active = true;
    let cleanup: (() => void) | null = null;

    void listen<SilenceAppAlertPayload>("silence-alert", (event) => {
      setSilenceAlert(event.payload);
    }).then((unlisten) => {
      if (active) {
        cleanup = unlisten;
      } else {
        unlisten();
      }
    }).catch((error) => {
      setNotice(error instanceof Error ? error.message : "Unable to listen for silence alerts.");
    });

    return () => {
      active = false;
      cleanup?.();
    };
  }, []);

  useEffect(() => {
    selectedJobIdRef.current = selectedJobId;
  }, [selectedJobId]);

  function selectJob(jobId: string | null) {
    selectedJobIdRef.current = jobId;
    setSelectedJobId(jobId);
  }

  async function refreshStatus() {
    try {
      setServiceStatus(await getServiceStatus());
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to refresh local service status.");
    }
  }

  async function loadJobs(preferredJobId: string | null = null) {
    const nextJobs = await getJobs();
    setJobs(nextJobs);
    const nextSelected = chooseSelectedJobId({
      currentJobId: selectedJobIdRef.current,
      jobs: nextJobs,
      preferredJobId,
    });
    selectJob(nextSelected);
  }

  async function loadDesktops() {
    const payload = await getDesktops();
    setDesktops(payload.desktops);
  }

  async function loadSelectedJob(jobId: string | null = selectedJobIdRef.current) {
    if (!jobId) {
      setSelectedJob(null);
      setArtifacts([]);
      return;
    }
    const [job, jobArtifacts] = await Promise.all([getJob(jobId), getArtifactsOverview()]);
    setSelectedJob(job);
    setArtifacts(userVisibleArtifacts(jobArtifacts.jobs.find((entry) => entry.job.id === jobId)?.artifacts.files ?? []));
  }

  async function refreshStoppedJobUntilSettled(jobId: string) {
    const deadline = Date.now() + stopRefreshTimeoutMs;
    while (Date.now() < deadline) {
      await wait(stopRefreshIntervalMs);
      const job = await getJob(jobId);
      await loadDesktops();
      if (selectedJobIdRef.current === jobId) {
        setSelectedJob(job);
      }
      if (!ACTIVE_STATES.has(job.state)) {
        await loadJobs();
        if (selectedJobIdRef.current === jobId) {
          await loadSelectedJob(jobId);
        }
        return;
      }
    }
    await loadJobs();
    await loadDesktops();
    if (selectedJobIdRef.current === jobId) {
      await loadSelectedJob(jobId);
    }
  }

  async function refreshControllerData() {
    try {
      const nextJobs = await getJobs();
      setJobs(nextJobs);
      const nextSelected = chooseSelectedJobId({
        currentJobId: selectedJobIdRef.current,
        jobs: nextJobs,
      });
      selectJob(nextSelected);
      if (nextSelected) {
        await loadSelectedJob(nextSelected);
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to reach the controller.");
    }

    try {
      const nextDesktops = await getDesktops();
      setDesktops(nextDesktops.desktops);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to load desktop workspaces.");
    }
  }

  useEffect(() => {
    async function boot() {
      try {
        const result = await startLocalServices();
        setNotice(result.detail);
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "Unable to start local services.");
      }
      await refreshStatus();
      await refreshControllerData();
    }
    void boot();
  }, []);

  useEffect(() => {
    void loadSelectedJob(selectedJobId);
  }, [selectedJobId]);

  useEffect(() => {
    if (visibleView !== "live" || !liveJobListItem || selectedJobId === liveJobListItem.id) {
      return;
    }
    selectJob(liveJobListItem.id);
    void loadSelectedJob(liveJobListItem.id);
  }, [liveJobListItem?.id, selectedJobId, visibleView]);

  useEffect(() => {
    if (stoppingJobId && selectedJob?.id === stoppingJobId && !canStopCapture(selectedJob.state)) {
      setStoppingJobId(null);
    }
  }, [selectedJob?.id, selectedJob?.state, stoppingJobId]);

  useEffect(() => {
    setConfirmingDeleteJobId(null);
  }, [selectedJobId]);

  useEffect(() => {
    setNotice((currentNotice) => (currentNotice === deleteSuccessNotice ? "" : currentNotice));
  }, [view]);

  useEffect(() => () => {
    Object.values(microphoneSessionsRef.current).forEach((session) => {
      void session.stop({ finalize: false });
    });
    microphoneSessionsRef.current = {};
  }, []);

  async function handleStart() {
    setNotice((await startLocalServices()).detail);
    await refreshStatus();
  }

  async function handleStopServices() {
    setNotice((await stopLocalServices()).detail);
    await refreshStatus();
  }

  async function startCaptureMicrophone(jobId: string, microphoneStream: MediaStream | null = null) {
    if (microphoneSessionsRef.current[jobId]) {
      stopMediaStream(microphoneStream);
      return;
    }
    const stream = microphoneStream ?? (await requestAuthorizedMicrophoneStream({ requestAccess: requestMicrophoneAccess }));
    try {
      const session = await startMicrophonePcmStream({
        stream,
        url: captureMicrophoneLiveUrl(jobId),
        requireReady: true,
        onMessage: (event) => {
          if (typeof event === "object" && event && "type" in event && event.type === "warning" && "message" in event) {
            setNotice(String(event.message || "Microphone recording stopped."));
          }
        },
        onClose: () => {
          delete microphoneSessionsRef.current[jobId];
          setNotice("Microphone recording stopped. Stopping the capture.");
          void stopCapture(jobId).then(() => loadJobs(jobId)).catch((error) => {
            setNotice(error instanceof Error ? error.message : "Unable to stop capture after microphone stopped.");
          });
        },
      });
      microphoneSessionsRef.current[jobId] = session;
    } catch (error) {
      stopMediaStream(stream);
      throw error;
    }
  }

  async function stopCaptureMicrophone(jobId: string, finalize = true) {
    const session = microphoneSessionsRef.current[jobId];
    if (!session) {
      return;
    }
    delete microphoneSessionsRef.current[jobId];
    await session.stop({ finalize });
  }

  async function handleCaptureCreated(job: JobResponse, microphoneStream: MediaStream | null = null) {
    try {
      if (recordMicrophoneEnabled(job)) {
        await startCaptureMicrophone(job.id, microphoneStream);
        microphoneStream = null;
      }
    } catch (error) {
      await setRecordMicrophoneEnabled(job.id, false).catch(() => undefined);
      await stopCapture(job.id).catch(() => undefined);
      throw error;
    } finally {
      stopMediaStream(microphoneStream);
    }
    selectJob(job.id);
    setSelectedJob(null);
    setArtifacts([]);
    await loadJobs(job.id);
    await loadDesktops();
    await loadSelectedJob(job.id);
    setView("live");
  }

  async function handleCreateDesktop(label: string) {
    await createDesktop(label);
    await loadDesktops();
  }

  function handleSelectLiveJob(jobId: string) {
    selectJob(jobId);
    setSelectedJob(null);
    setArtifacts([]);
  }

  async function handleStopJob(jobId: string) {
    setStoppingJobId(jobId);
    try {
      await stopCaptureMicrophone(jobId);
      await stopCapture(jobId);
      await loadJobs();
      await loadDesktops();
      await loadSelectedJob(jobId);
      await refreshStoppedJobUntilSettled(jobId);
    } catch (error) {
      setStoppingJobId(null);
      setNotice(error instanceof Error ? error.message : "Unable to stop capture.");
    }
  }

  async function handleSetTargetAudioMuted(jobId: string, muted: boolean) {
    setMutingJobId(jobId);
    try {
      await setTargetAudioMuted(jobId, muted);
      await loadJobs(jobId);
      await loadSelectedJob(jobId);
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to change app audio.");
    } finally {
      setMutingJobId(null);
    }
  }

  async function handleSetRecordMicrophone(jobId: string, enabled: boolean) {
    setMicrophoneJobId(jobId);
    let microphoneStream: MediaStream | null = null;
    try {
      if (enabled) {
        microphoneStream = await requestAuthorizedMicrophoneStream({ requestAccess: requestMicrophoneAccess });
        await setRecordMicrophoneEnabled(jobId, true);
        await startCaptureMicrophone(jobId, microphoneStream);
        microphoneStream = null;
      } else {
        await stopCaptureMicrophone(jobId);
        await setRecordMicrophoneEnabled(jobId, false);
      }
      await loadJobs(jobId);
      await loadSelectedJob(jobId);
      setNotice("");
    } catch (error) {
      stopMediaStream(microphoneStream);
      if (enabled) {
        await setRecordMicrophoneEnabled(jobId, false).catch(() => undefined);
        await stopCapture(jobId).catch(() => undefined);
      }
      setNotice(formatVoiceNoteRecordingError(error));
    } finally {
      setMicrophoneJobId(null);
    }
  }

  function requestDeleteJob(jobId: string) {
    const job = selectedJob?.id === jobId ? selectedJob : jobs.find((candidate) => candidate.id === jobId);
    if (job && !canDeleteJob(job.state)) {
      setNotice("Stop the capture before deleting this job.");
      return;
    }
    setConfirmingDeleteJobId(jobId);
  }

  async function handleDeleteJob(jobId: string) {
    const job = selectedJob?.id === jobId ? selectedJob : jobs.find((candidate) => candidate.id === jobId);
    if (job && !canDeleteJob(job.state)) {
      setConfirmingDeleteJobId(null);
      setNotice("Stop the capture before deleting this job.");
      return;
    }
    setConfirmingDeleteJobId(null);
    setDeletingJobId(jobId);
    try {
      await deleteJob(jobId);
      const nextJobs = await getJobs();
      setJobs(nextJobs);
      const nextSelected = nextJobs.find((candidate) => ACTIVE_STATES.has(candidate.state))?.id ?? nextJobs[0]?.id ?? null;
      selectJob(nextSelected);
      if (nextSelected) {
        await loadSelectedJob(nextSelected);
      } else {
        setSelectedJob(null);
        setArtifacts([]);
      }
      setNotice(deleteSuccessNotice);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to delete job.");
    } finally {
      setDeletingJobId(null);
    }
  }

  return (
    <div className="app-shell">
      <Navigation setView={setView} view={visibleView} liveAvailable={activeJobs.length > 0} />
      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Local first</p>
            <h2>{viewTitle(visibleView)}</h2>
          </div>
          <div className="toolbar">
            <Button onClick={() => void refreshControllerData()} variant="quiet">
              <RefreshCw aria-hidden="true" size={16} />
              Refresh
            </Button>
          </div>
        </header>
        {silenceAlert ? (
          <div className="silence-alert-region" aria-live="assertive">
            <div className="silence-alert" role="alert">
              <Bell aria-hidden="true" size={18} />
              <div className="silence-alert-copy">
                <strong>{silenceAlert.title}</strong>
                <p>{silenceAlert.body}</p>
              </div>
              <Button aria-label="Dismiss silence alert" onClick={() => setSilenceAlert(null)} title="Dismiss silence alert" type="button" variant="secondary">
                <X aria-hidden="true" size={16} />
              </Button>
            </div>
          </div>
        ) : null}
        {notice ? <p className="notice">{notice}</p> : null}

        {visibleView === "capture" ? (
          <div className="grid-two">
            <StartCapturePanel activeCaptures={activeJobs} onCreated={handleCaptureCreated} targetRefreshSignal={desktops} />
            <JobsTable jobs={jobs} onSelect={selectJob} selectedJobId={selectedJobId} />
            <JobDetail
              artifacts={artifacts}
              deleteConfirming={Boolean(selectedJob && confirmingDeleteJobId === selectedJob.id)}
              deletePending={Boolean(selectedJob && deletingJobId === selectedJob.id)}
              job={selectedJob}
              onCancelDelete={() => setConfirmingDeleteJobId(null)}
              onConfirmDelete={(jobId) => void handleDeleteJob(jobId)}
              onDelete={requestDeleteJob}
              onStop={(jobId) => void handleStopJob(jobId)}
              stopPending={Boolean(selectedJob && stoppingJobId === selectedJob.id)}
            />
          </div>
        ) : null}

        {visibleView === "live" && liveJobListItem ? (
          <>
            <LiveJobSelector jobs={activeJobs} selectedJobId={liveJobListItem.id} onSelect={handleSelectLiveJob} />
            <LiveCaptureControls
              job={liveJobListItem}
              microphonePending={microphoneJobId === liveJobListItem.id}
              mutePending={mutingJobId === liveJobListItem.id}
              onSetRecordMicrophone={(jobId, enabled) => void handleSetRecordMicrophone(jobId, enabled)}
              onSetMuted={(jobId, muted) => void handleSetTargetAudioMuted(jobId, muted)}
            />
            <div className="grid-two live-workspace">
              <LiveTranscript job={liveJob} />
              <LiveSummaryPanel job={liveJob} onSaved={() => liveJob ? void loadSelectedJob(liveJob.id) : undefined} />
            </div>
          </>
        ) : null}

        {visibleView === "voice-notes" ? <VoiceNotesPanel /> : null}

        {visibleView === "settings" ? (
          <SettingsPanel
            desktops={desktops}
            onCreateDesktop={handleCreateDesktop}
            onDesktopDestroyed={loadDesktops}
            onDesktopsRefresh={loadDesktops}
            onRefresh={() => void refreshStatus()}
            onStart={() => void handleStart()}
            onStop={() => void handleStopServices()}
            serviceStatus={serviceStatus}
          />
        ) : null}
      </main>
    </div>
  );
}
