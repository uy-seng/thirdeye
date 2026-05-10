import { Mic, Play, Save, Sparkles, Square, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Badge, Button, Card, TextArea, TextInput } from "../../components/ui";
import {
  deleteVoiceNote,
  generateVoiceNoteSummary,
  getVoiceNotes,
  importVoiceNotes,
  saveVoiceNote,
  updateVoiceNote,
  voiceNoteLiveUrl,
} from "../../lib/api";
import { getDefaultVoiceNoteSummaryPrompt } from "../../lib/prompts";
import { openMicrophoneSettings, requestMicrophoneAccess } from "../../lib/services";
import {
  encodeLinear16,
  formatVoiceNoteRecordingError,
  isAudibleMicrophoneInput,
  isVoiceNoteMicrophoneAccessBlocked,
  isVoiceNoteTranscriptTextEvent,
  mergedTranscriptText,
  mergeTranscriptEvent,
  requestAuthorizedMicrophoneStream,
} from "../../lib/voice-note-audio";
import {
  clearLegacyVoiceNotes,
  createVoiceNote,
  formatVoiceNoteDuration,
  loadLegacyVoiceNotes,
  type VoiceNote,
} from "../../lib/voice-notes";
import type { TranscriptBlock } from "../../lib/types";

type RecordingState = "idle" | "recording" | "saving";
type MicrophoneSignalState = "waiting" | "active" | "quiet";
type SummaryStatus = "idle" | "generating" | "ready" | "error";
type SummaryState = {
  noteId: string | null;
  status: SummaryStatus;
  message: string;
};

const recorderIntervalMs = 250;
const transcriptionTimeoutMs = 5_000;
const microphoneSignalQuietAfterMs = 3_000;
const microphoneSignalUpdateIntervalMs = 500;

function createId() {
  return globalThis.crypto?.randomUUID?.() ?? `voice-note-${Date.now()}`;
}

function blobToDataUrl(blob: Blob) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("Unable to save the recording."));
    reader.readAsDataURL(blob);
  });
}

export function VoiceNotesPanel() {
  const [notes, setNotes] = useState<VoiceNote[]>([]);
  const [expandedNoteId, setExpandedNoteId] = useState<string | null>(null);
  const [unsavedNoteIds, setUnsavedNoteIds] = useState<Set<string>>(() => new Set());
  const [recordingState, setRecordingState] = useState<RecordingState>("idle");
  const [summaryState, setSummaryState] = useState<SummaryState>({ noteId: null, status: "idle", message: "" });
  const [status, setStatus] = useState("Ready");
  const [recordingIssue, setRecordingIssue] = useState("");
  const [microphoneAccessBlocked, setMicrophoneAccessBlocked] = useState(false);
  const [microphoneSignal, setMicrophoneSignal] = useState<MicrophoneSignalState>("waiting");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [liveTranscript, setLiveTranscript] = useState("");
  const [liveDraft, setLiveDraft] = useState("");
  const chunksRef = useRef<Blob[]>([]);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const websocketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const audioProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const startedAtRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const recordingRef = useRef(false);
  const finishingRef = useRef(false);
  const transcriptRef = useRef("");
  const draftRef = useRef("");
  const lastSignalUpdateAtRef = useRef(0);
  const transcriptionDoneRef = useRef<Promise<void>>(Promise.resolve());
  const resolveTranscriptionDoneRef = useRef<(() => void) | null>(null);

  const previewText = useMemo(() => mergedTranscriptText({ transcript: liveTranscript, draft: liveDraft }), [liveDraft, liveTranscript]);
  const activeSummaryNote = useMemo(() => {
    const selectedNote = summaryState.noteId ? notes.find((note) => note.id === summaryState.noteId) : null;
    return selectedNote ?? notes.find((note) => note.summary) ?? notes[0] ?? null;
  }, [notes, summaryState.noteId]);
  const activeSummary = activeSummaryNote?.summary ?? null;
  const canRecord = recordingState === "idle";
  const isRecording = recordingState === "recording";
  const recorderBadgeTone: "neutral" | "good" | "bad" | "info" = isRecording
    ? "info"
    : recordingIssue
      ? "bad"
      : status === "Saved to notes"
        ? "good"
        : "neutral";
  const recorderBadgeLabel = recordingIssue ? "Needs microphone" : status;
  const microphoneBadgeTone: "neutral" | "good" | "warn" | "info" =
    microphoneSignal === "active" ? "good" : microphoneSignal === "quiet" ? "warn" : "info";
  const microphoneBadgeLabel =
    microphoneSignal === "active" ? "Hearing mic" : microphoneSignal === "quiet" ? "No microphone sound yet" : "Ready for voice";
  const liveNotePlaceholder =
    isRecording && microphoneSignal === "active" ? "Listening for words..." : "Your words will appear here while you talk.";
  const summaryBadgeTone: "neutral" | "good" | "bad" | "info" =
    summaryState.status === "generating" ? "info" : summaryState.status === "error" ? "bad" : activeSummary ? "good" : "neutral";
  const summaryBadgeLabel =
    summaryState.status === "generating" ? "Generating" : summaryState.status === "error" ? "Needs retry" : activeSummary ? "Ready" : "Waiting";
  const summaryPanelMessage =
    summaryState.message ||
    (activeSummary
      ? ""
      : activeSummaryNote?.transcript
        ? "A summary will appear here after recording stops."
        : "Record a note with words to create a summary.");

  useEffect(() => {
    transcriptRef.current = liveTranscript;
  }, [liveTranscript]);

  useEffect(() => {
    let cancelled = false;

    async function loadSavedNotes() {
      try {
        const legacyNotes = loadLegacyVoiceNotes();
        const savedNotes = legacyNotes.length > 0 ? await importVoiceNotes(legacyNotes) : await getVoiceNotes();
        if (legacyNotes.length > 0) {
          clearLegacyVoiceNotes();
        }
        if (!cancelled) {
          setNotes(savedNotes);
        }
      } catch {
        if (!cancelled) {
          setStatus("Could not load saved notes.");
        }
      }
    }

    void loadSavedNotes();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    draftRef.current = liveDraft;
  }, [liveDraft]);

  useEffect(() => () => {
    clearTimer();
    recordingRef.current = false;
    resolveTranscriptionDoneRef.current?.();
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    closeLiveTranscription();
    stopStream();
  }, []);

  function clearTimer() {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  function stopStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  function closeLiveTranscription() {
    stopLiveAudioGraph();
    if (websocketRef.current && websocketRef.current.readyState < WebSocket.CLOSING) {
      websocketRef.current.close();
    }
    websocketRef.current = null;
  }

  function stopLiveAudioGraph() {
    audioProcessorRef.current?.disconnect();
    audioSourceRef.current?.disconnect();
    void audioContextRef.current?.close().catch(() => undefined);
    audioProcessorRef.current = null;
    audioSourceRef.current = null;
    audioContextRef.current = null;
  }

  function resetTranscriptionDone() {
    transcriptionDoneRef.current = new Promise((resolve) => {
      resolveTranscriptionDoneRef.current = resolve;
    });
  }

  function handleTranscriptEvent(event: TranscriptBlock) {
    if (event.type === "interim" || event.type === "final") {
      setMicrophoneSignal("active");
      if (!isVoiceNoteTranscriptTextEvent(event)) {
        if (!transcriptRef.current && !draftRef.current) {
          setStatus("Waiting for words");
        }
        return;
      }
      const next = mergeTranscriptEvent(
        {
          transcript: transcriptRef.current,
          draft: draftRef.current,
        },
        event,
      );
      transcriptRef.current = next.transcript;
      draftRef.current = next.draft;
      setLiveTranscript(next.transcript);
      setLiveDraft(next.draft);
      setStatus("Listening now");
      return;
    }

    if (event.type === "warning") {
      setStatus(event.message || "Live note paused.");
      return;
    }

    if (event.type === "complete") {
      resolveTranscriptionDoneRef.current?.();
      resolveTranscriptionDoneRef.current = null;
    }
  }

  async function startLiveTranscription(stream: MediaStream) {
    resetTranscriptionDone();
    const websocket = new WebSocket(voiceNoteLiveUrl());
    websocket.binaryType = "arraybuffer";
    websocketRef.current = websocket;
    websocket.onopen = () => setStatus("Ready for your voice");
    websocket.onerror = () => {
      setStatus("Live note connection stopped.");
      resolveTranscriptionDoneRef.current?.();
    };
    websocket.onclose = () => {
      resolveTranscriptionDoneRef.current?.();
    };
    websocket.onmessage = (message) => {
      if (typeof message.data !== "string") {
        return;
      }
      try {
        handleTranscriptEvent(JSON.parse(message.data) as TranscriptBlock);
      } catch {
        setStatus("Live note paused.");
      }
    };

    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (event) => {
      event.outputBuffer.getChannelData(0).fill(0);
      const samples = event.inputBuffer.getChannelData(0);
      updateMicrophoneSignal(samples);
      if (!recordingRef.current || websocket.readyState !== WebSocket.OPEN) {
        return;
      }
      websocket.send(encodeLinear16(samples, audioContext.sampleRate));
    };
    source.connect(processor);
    processor.connect(audioContext.destination);
    await audioContext.resume();
    audioContextRef.current = audioContext;
    audioSourceRef.current = source;
    audioProcessorRef.current = processor;
  }

  function updateMicrophoneSignal(samples: Float32Array) {
    const now = Date.now();
    if (now - lastSignalUpdateAtRef.current < microphoneSignalUpdateIntervalMs) {
      return;
    }
    lastSignalUpdateAtRef.current = now;

    const hasTranscriptText = Boolean(transcriptRef.current || draftRef.current);
    if (isAudibleMicrophoneInput(samples)) {
      setMicrophoneSignal("active");
      if (!hasTranscriptText) {
        setStatus("Waiting for words");
      }
      return;
    }

    if (!hasTranscriptText && now - startedAtRef.current >= microphoneSignalQuietAfterMs) {
      setMicrophoneSignal("quiet");
      setStatus("No microphone sound yet");
    }
  }

  async function startRecording() {
    if (!canRecord) {
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setRecordingIssue("Voice recording is not available in this window.");
      setMicrophoneAccessBlocked(false);
      return;
    }

    try {
      setRecordingIssue("");
      setMicrophoneAccessBlocked(false);
      setStatus("Asking for microphone access");
      const stream = await requestAuthorizedMicrophoneStream({ requestAccess: requestMicrophoneAccess });
      const recorder = new MediaRecorder(stream);

      chunksRef.current = [];
      streamRef.current = stream;
      mediaRecorderRef.current = recorder;
      startedAtRef.current = Date.now();
      lastSignalUpdateAtRef.current = 0;
      recordingRef.current = true;
      finishingRef.current = false;
      transcriptRef.current = "";
      draftRef.current = "";
      setElapsedMs(0);
      setLiveTranscript("");
      setLiveDraft("");
      setMicrophoneSignal("waiting");
      setStatus("Connecting live note...");
      setRecordingState("recording");

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        void finishRecording();
      };

      recorder.start(recorderIntervalMs);
      await startLiveTranscription(stream);
      clearTimer();
      timerRef.current = window.setInterval(() => {
        setElapsedMs(Date.now() - startedAtRef.current);
      }, 250);
    } catch (error) {
      setRecordingIssue(formatVoiceNoteRecordingError(error));
      setMicrophoneAccessBlocked(isVoiceNoteMicrophoneAccessBlocked(error));
      setStatus("Ready");
      setRecordingState("idle");
      recordingRef.current = false;
      closeLiveTranscription();
      stopStream();
    }
  }

  function stopRecording() {
    if (!isRecording) {
      return;
    }
    setRecordingState("saving");
    setStatus("Saving note");
    recordingRef.current = false;
    clearTimer();
    stopLiveAudioGraph();
    if (websocketRef.current?.readyState === WebSocket.OPEN) {
      websocketRef.current.send(JSON.stringify({ type: "Finalize" }));
    } else {
      resolveTranscriptionDoneRef.current?.();
    }
    if (mediaRecorderRef.current?.state !== "inactive") {
      mediaRecorderRef.current?.stop();
    } else {
      void finishRecording();
    }
    stopStream();
  }

  async function finishRecording() {
    if (finishingRef.current) {
      return;
    }
    finishingRef.current = true;
    await Promise.race([
      transcriptionDoneRef.current,
      new Promise((resolve) => window.setTimeout(resolve, transcriptionTimeoutMs)),
    ]);
    const durationMs = Math.max(Date.now() - startedAtRef.current, elapsedMs);
    const transcript = mergedTranscriptText({ transcript: transcriptRef.current, draft: draftRef.current });
    const blobType = chunksRef.current[0]?.type || "audio/webm";
    const blob = new Blob(chunksRef.current, { type: blobType });
    let audioDataUrl: string | undefined;
    try {
      audioDataUrl = blob.size > 0 ? await blobToDataUrl(blob) : undefined;
    } catch {
      audioDataUrl = undefined;
    }
    const note = createVoiceNote({
      id: createId(),
      createdAt: new Date().toISOString(),
      transcript,
      durationMs,
      audioDataUrl,
    });

    let savedNote = note;
    let nextStatus = "Saved to notes";
    try {
      savedNote = await saveVoiceNote(note);
    } catch {
      nextStatus = "Saved for now. Restart the local app service to keep new notes.";
    }
    setNotes((current) => [savedNote, ...current.filter((currentNote) => currentNote.id !== savedNote.id)]);
    setUnsavedNoteIds((current) => new Set(current).add(note.id));
    setExpandedNoteId(note.id);
    setLiveTranscript("");
    setLiveDraft("");
    setRecordingIssue("");
    setMicrophoneAccessBlocked(false);
    setMicrophoneSignal("waiting");
    setElapsedMs(0);
    setStatus(nextStatus);
    setRecordingState("idle");
    chunksRef.current = [];
    mediaRecorderRef.current = null;
    closeLiveTranscription();
    finishingRef.current = false;
    if (savedNote.transcript) {
      void summarizeVoiceNote(savedNote);
    } else {
      setSummaryState({
        noteId: savedNote.id,
        status: "idle",
        message: "No words were captured, so there is nothing to summarize yet.",
      });
    }
  }

  async function summarizeVoiceNote(note: VoiceNote) {
    const transcript = note.transcript.trim();
    setSummaryState({
      noteId: note.id,
      status: transcript ? "generating" : "idle",
      message: transcript ? "Creating summary..." : "No transcript to summarize.",
    });
    if (!transcript) {
      return;
    }

    try {
      const result = await generateVoiceNoteSummary({
        title: note.title,
        transcript,
        prompt: getDefaultVoiceNoteSummaryPrompt(),
      });
      const summary: NonNullable<VoiceNote["summary"]> = {
        markdown: result.markdown,
        provider: result.provider,
        generatedAt: new Date().toISOString(),
      };
      const savedNote = await updateVoiceNote(note.id, { summary });
      setNotes((current) => current.map((currentNote) => (currentNote.id === note.id ? savedNote : currentNote)));
      setSummaryState({ noteId: note.id, status: "ready", message: "Summary ready." });
    } catch (error) {
      setSummaryState({
        noteId: note.id,
        status: "error",
        message: error instanceof Error ? error.message : "Unable to create a summary.",
      });
    }
  }

  function updateNote(noteId: string, updates: Partial<Pick<VoiceNote, "title" | "transcript">>) {
    setNotes((current) => {
      return current.map((note) => (note.id === noteId ? { ...note, ...updates } : note));
    });
    setUnsavedNoteIds((current) => new Set(current).add(noteId));
  }

  function deleteNote(noteId: string) {
    setNotes((current) => {
      return current.filter((note) => note.id !== noteId);
    });
    setUnsavedNoteIds((current) => {
      const next = new Set(current);
      next.delete(noteId);
      return next;
    });
    setExpandedNoteId((current) => (current === noteId ? null : current));
    setSummaryState((current) => (current.noteId === noteId ? { noteId: null, status: "idle", message: "" } : current));
    void deleteVoiceNote(noteId).catch(() => {
      setStatus("Could not delete the saved note.");
    });
  }

  async function saveNote(noteId: string) {
    if (!unsavedNoteIds.has(noteId)) {
      return;
    }
    const note = notes.find((candidate) => candidate.id === noteId);
    if (!note) {
      return;
    }
    try {
      const savedNote = await updateVoiceNote(noteId, {
        title: note.title,
        transcript: note.transcript,
        durationMs: note.durationMs,
        audioDataUrl: note.audioDataUrl,
        summary: note.summary,
      });
      setNotes((current) => current.map((currentNote) => (currentNote.id === noteId ? savedNote : currentNote)));
    } catch {
      setStatus("Could not save the note.");
      return;
    }
    setUnsavedNoteIds((current) => {
      const next = new Set(current);
      next.delete(noteId);
      return next;
    });
    setExpandedNoteId(null);
    setStatus("Saved to notes");
  }

  function selectNote(note: VoiceNote) {
    setExpandedNoteId((current) => (current === note.id ? null : note.id));
    setSummaryState((current) => {
      if (current.noteId === note.id && current.status === "generating") {
        return current;
      }
      if (note.summary) {
        return { noteId: note.id, status: "ready", message: "Summary ready." };
      }
      return {
        noteId: note.id,
        status: "idle",
        message: note.transcript ? "No summary yet." : "No transcript to summarize.",
      };
    });
  }

  return (
    <div className="grid-two voice-notes-workspace">
      <Card className="voice-recorder-card">
        <div className="card-heading-row">
          <div>
            <p className="eyebrow">Voice notes</p>
            <h2>Record a note</h2>
          </div>
          <Badge tone={recorderBadgeTone}>{recorderBadgeLabel}</Badge>
        </div>
        <div className={isRecording ? "voice-recorder-surface voice-recorder-surface-active" : "voice-recorder-surface"}>
          <div className="voice-recorder-meter" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </div>
          <div className="voice-recorder-copy">
            <strong>{formatVoiceNoteDuration(elapsedMs)}</strong>
            <span>{isRecording ? status : "Ready when you are"}</span>
          </div>
          <div className="toolbar">
            <Button disabled={!canRecord} onClick={() => void startRecording()} type="button">
              <Mic aria-hidden="true" size={16} />
              Start recording
            </Button>
            <Button disabled={!isRecording} onClick={stopRecording} type="button" variant="secondary">
              <Square aria-hidden="true" size={16} />
              Stop
            </Button>
          </div>
        </div>
        {recordingIssue ? (
          <div className="permission-notice voice-recorder-permission" role="alert">
            <p className="permission-title">Recording could not start</p>
            <p className="permission-copy">{recordingIssue}</p>
            {microphoneAccessBlocked ? (
              <Button onClick={() => void openMicrophoneSettings()} type="button" variant="secondary">
                <Mic aria-hidden="true" size={16} />
                Open microphone settings
              </Button>
            ) : null}
          </div>
        ) : null}
        <div className="voice-live-note">
          <div className="card-heading-row">
            <p className="eyebrow">Live note</p>
            {isRecording && !previewText ? <Badge tone={microphoneBadgeTone}>{microphoneBadgeLabel}</Badge> : null}
            {liveDraft ? <Badge tone="warn">Still listening</Badge> : null}
          </div>
          <p>{previewText || liveNotePlaceholder}</p>
        </div>
      </Card>

      <Card className="summary-panel voice-summary-card">
        <div className="card-heading-row">
          <div>
            <p className="eyebrow">Voice summary</p>
            <h2>Summary</h2>
          </div>
          <Badge tone={summaryBadgeTone}>{summaryBadgeLabel}</Badge>
        </div>
        {activeSummaryNote ? <p className="muted">For {activeSummaryNote.title}</p> : <p className="muted">Stop a recording to create a summary.</p>}
        {summaryPanelMessage ? (
          <p aria-live="polite" className="form-message">
            {summaryPanelMessage}
          </p>
        ) : null}
        {activeSummary ? (
          <div className="summary-output">
            <div className="summary-meta">
              <Badge tone="info">{activeSummary.provider}</Badge>
              <Badge tone="neutral">{new Date(activeSummary.generatedAt).toLocaleString()}</Badge>
            </div>
            <pre>{activeSummary.markdown}</pre>
          </div>
        ) : null}
        <div className="toolbar">
          <Button
            disabled={!activeSummaryNote?.transcript || summaryState.status === "generating"}
            onClick={() => (activeSummaryNote ? void summarizeVoiceNote(activeSummaryNote) : undefined)}
            type="button"
            variant="secondary"
          >
            <Sparkles aria-hidden="true" size={16} />
            {summaryState.status === "generating" ? "Generating..." : activeSummary ? "Regenerate" : "Generate summary"}
          </Button>
        </div>
      </Card>

      <Card className="voice-notes-list-card">
        <div className="card-heading-row">
          <div>
            <p className="eyebrow">Notes</p>
            <h2>Saved notes</h2>
          </div>
          <Badge tone={notes.length > 0 ? "info" : "neutral"}>{notes.length}</Badge>
        </div>
        <div className="voice-notes-list">
          {notes.length === 0 ? <p className="muted">No voice notes yet.</p> : null}
          {notes.map((note) => {
            const expanded = expandedNoteId === note.id;
            const canSave = unsavedNoteIds.has(note.id);
            return (
              <article className={expanded ? "voice-note-item voice-note-item-open" : "voice-note-item"} key={note.id}>
                <button
                  aria-expanded={expanded}
                  className="voice-note-card"
                  onClick={() => selectNote(note)}
                  type="button"
                >
                  <span className="voice-note-card-copy">
                    <strong>{note.title}</strong>
                    <small>{note.transcript || "No transcript captured."}</small>
                  </span>
                  <span className="summary-meta">
                    <Badge tone="good">
                      <Play aria-hidden="true" size={12} />
                      {formatVoiceNoteDuration(note.durationMs)}
                    </Badge>
                    {note.summary ? (
                      <Badge tone="info">
                        <Sparkles aria-hidden="true" size={12} />
                        Summary
                      </Badge>
                    ) : null}
                    <Badge tone="neutral">{new Date(note.createdAt).toLocaleString()}</Badge>
                  </span>
                </button>
                {expanded ? (
                  <div className="voice-note-details">
                    <TextInput
                      aria-label="Note title"
                      onChange={(event) => updateNote(note.id, { title: event.target.value })}
                      value={note.title}
                    />
                    <TextArea
                      aria-label={`Transcript for ${note.title}`}
                      onChange={(event) => updateNote(note.id, { transcript: event.target.value })}
                      value={note.transcript}
                    />
                    {note.audioDataUrl ? <audio controls src={note.audioDataUrl} /> : null}
                    <div className="toolbar">
                      {canSave ? (
                        <Button onClick={() => void saveNote(note.id)} type="button" variant="secondary">
                          <Save aria-hidden="true" size={16} />
                          Save
                        </Button>
                      ) : null}
                      <Button onClick={() => deleteNote(note.id)} type="button" variant="danger">
                        <Trash2 aria-hidden="true" size={16} />
                        Delete
                      </Button>
                    </div>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
