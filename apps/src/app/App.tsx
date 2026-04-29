import { listen } from "@tauri-apps/api/event";
import { Bell, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  deleteJob,
  getArtifactsOverview,
  getHealth,
  getJob,
  getJobs,
  getSession,
  logout,
  setTargetAudioMuted,
  stopCapture,
} from "../lib/api";
import { chooseSelectedJobId } from "../lib/job-selection";
import { ACTIVE_STATES, canDeleteJob, canStopCapture } from "../lib/job-state";
import { getServiceStatus, startLocalServices, stopLocalServices } from "../lib/services";
import type { ArtifactFile, HealthStatusResponse, JobDetailResponse, JobResponse, ServiceStatus, SessionResponse } from "../lib/types";
import { useSilenceNotification } from "../lib/use-silence-notification";
import { LoginPanel } from "../components/auth/LoginPanel";
import { Navigation } from "../components/navigation/Navigation";
import { ServiceStrip } from "../components/services/ServiceStrip";
import { Button } from "../components/ui";
import { StartCapturePanel } from "../features/capture";
import { HealthPanel } from "../features/health/HealthPanel";
import { JobDetail, JobsTable } from "../features/jobs";
import { LiveCaptureControls, LiveSummaryPanel, LiveTranscript } from "../features/live";
import { SettingsPanel } from "../features/settings/SettingsPanel";
import type { View } from "./view";

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

export function App() {
  const [view, setView] = useState<View>("dashboard");
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus | null>(null);
  const [health, setHealth] = useState<HealthStatusResponse | null>(null);
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<JobDetailResponse | null>(null);
  const [stoppingJobId, setStoppingJobId] = useState<string | null>(null);
  const [mutingJobId, setMutingJobId] = useState<string | null>(null);
  const [confirmingDeleteJobId, setConfirmingDeleteJobId] = useState<string | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactFile[]>([]);
  const [notice, setNotice] = useState("Starting local services...");
  const [silenceAlert, setSilenceAlert] = useState<SilenceAppAlertPayload | null>(null);
  const selectedJobIdRef = useRef<string | null>(null);

  const activeJob = useMemo(() => jobs.find((job) => ACTIVE_STATES.has(job.state)) ?? null, [jobs]);
  const visibleView = view === "live" && !activeJob ? "capture" : view;
  const liveJob = selectedJob?.id === activeJob?.id ? selectedJob : null;
  const handleSilenceNotificationUnavailable = useCallback((message: string) => {
    setNotice(message);
  }, []);

  useSilenceNotification(activeJob, handleSilenceNotificationUnavailable);

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
    setServiceStatus(await getServiceStatus());
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

  async function loadSelectedJob(jobId: string | null = selectedJobIdRef.current) {
    if (!jobId) {
      setSelectedJob(null);
      setArtifacts([]);
      return;
    }
    const [job, jobArtifacts] = await Promise.all([getJob(jobId), getArtifactsOverview()]);
    setSelectedJob(job);
    setArtifacts(jobArtifacts.jobs.find((entry) => entry.job.id === jobId)?.artifacts.files ?? []);
  }

  async function refreshStoppedJobUntilSettled(jobId: string) {
    const deadline = Date.now() + stopRefreshTimeoutMs;
    while (Date.now() < deadline) {
      await wait(stopRefreshIntervalMs);
      const job = await getJob(jobId);
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
    if (selectedJobIdRef.current === jobId) {
      await loadSelectedJob(jobId);
    }
  }

  async function refreshControllerData() {
    try {
      const current = await getSession();
      setSession(current);
      if (!current.authenticated) return;
      const [nextJobs, nextHealth] = await Promise.all([getJobs(), getHealth()]);
      setJobs(nextJobs);
      setHealth(nextHealth);
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
    if (visibleView !== "live" || !activeJob || selectedJob?.id === activeJob.id) {
      return;
    }
    selectJob(activeJob.id);
    void loadSelectedJob(activeJob.id);
  }, [activeJob?.id, selectedJob?.id, visibleView]);

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

  if (session && !session.authenticated) {
    return <LoginPanel onLogin={(nextSession) => {
      setSession(nextSession);
      void refreshControllerData();
    }} />;
  }

  async function handleStart() {
    setNotice((await startLocalServices()).detail);
    await refreshStatus();
  }

  async function handleStopServices() {
    setNotice((await stopLocalServices()).detail);
    await refreshStatus();
  }

  async function handleCaptureCreated(job: JobResponse) {
    selectJob(job.id);
    setSelectedJob(null);
    setArtifacts([]);
    await loadJobs(job.id);
    await loadSelectedJob(job.id);
    setView("live");
  }

  async function handleStopJob(jobId: string) {
    setStoppingJobId(jobId);
    try {
      await stopCapture(jobId);
      await loadJobs();
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
      <Navigation setView={setView} view={visibleView} liveAvailable={Boolean(activeJob)} />
      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Local first</p>
            <h2>{visibleView === "dashboard" ? "Operations overview" : visibleView[0].toUpperCase() + visibleView.slice(1)}</h2>
          </div>
          <div className="toolbar">
            <Button onClick={() => void refreshControllerData()} variant="quiet">
              <RefreshCw aria-hidden="true" size={16} />
              Refresh
            </Button>
            <Button onClick={() => void logout().then(setSession)} variant="secondary">
              Sign out
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

        {visibleView === "dashboard" ? (
          <div className="grid-two">
            <ServiceStrip onRefresh={() => void refreshStatus()} onStart={() => void handleStart()} onStop={() => void handleStopServices()} status={serviceStatus} />
            <HealthPanel health={health} />
            <StartCapturePanel activeCapture={activeJob} onCreated={(job) => void handleCaptureCreated(job)} />
            <JobsTable jobs={jobs.slice(0, 6)} onSelect={(jobId) => {
              selectJob(jobId);
              setView("jobs");
            }} selectedJobId={selectedJobId} />
          </div>
        ) : null}

        {visibleView === "capture" ? <StartCapturePanel activeCapture={activeJob} onCreated={(job) => void handleCaptureCreated(job)} /> : null}

        {visibleView === "jobs" ? (
          <div className="grid-two">
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

        {visibleView === "live" && activeJob ? (
          <>
            <LiveCaptureControls
              job={liveJob ?? activeJob}
              mutePending={mutingJobId === activeJob.id}
              onSetMuted={(jobId, muted) => void handleSetTargetAudioMuted(jobId, muted)}
            />
            <div className="grid-two live-workspace">
              <LiveTranscript job={liveJob} />
              <LiveSummaryPanel job={liveJob} onSaved={() => void loadSelectedJob(activeJob.id)} />
            </div>
          </>
        ) : null}

        {visibleView === "settings" ? (
          <SettingsPanel
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
