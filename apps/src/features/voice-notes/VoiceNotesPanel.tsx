import { Mic, Pencil, Play, RefreshCw, Save, Sparkles, Square, Trash2, X } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";

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
import { scrollVoiceNoteTranscriptToLatest } from "../../lib/voice-note-live-note";
import {
  clearLegacyVoiceNotes,
  createVoiceNote,
  createVoiceNoteSummary,
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
type AskAiAction = "" | "generate" | "save";
type NoteEditDraft = {
  noteId: string;
  title: string;
  summary: VoiceNote["summary"];
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
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [noteEditDraft, setNoteEditDraft] = useState<NoteEditDraft | null>(null);
  const [recordingState, setRecordingState] = useState<RecordingState>("idle");
  const [summaryState, setSummaryState] = useState<SummaryState>({ noteId: null, status: "idle", message: "" });
  const [askPrompt, setAskPrompt] = useState(() => getDefaultVoiceNoteSummaryPrompt());
  const [askResult, setAskResult] = useState<VoiceNote["summary"]>(null);
  const [askResultTargetId, setAskResultTargetId] = useState<string | null>(null);
  const [askMessage, setAskMessage] = useState("");
  const [askBusyAction, setAskBusyAction] = useState<AskAiAction>("");
  const [pendingSavedLiveSummary, setPendingSavedLiveSummaryState] = useState<VoiceNote["summary"]>(null);
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
  const liveTranscriptSurfaceRef = useRef<HTMLDivElement | null>(null);
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
  const pendingSavedLiveSummaryRef = useRef<VoiceNote["summary"]>(null);

  const previewText = useMemo(() => mergedTranscriptText({ transcript: liveTranscript, draft: liveDraft }), [liveDraft, liveTranscript]);
  const selectedNote = useMemo(() => {
    return expandedNoteId ? notes.find((note) => note.id === expandedNoteId) ?? null : null;
  }, [expandedNoteId, notes]);
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
  const askSourceTranscript = isRecording ? previewText : selectedNote?.transcript ?? "";
  const askSourceTitle = isRecording ? "Voice note" : selectedNote?.title ?? "Voice note";
  const askContextLabel = isRecording ? "Current recording" : selectedNote ? selectedNote.title : "Start recording or choose a saved note.";
  const askHasTranscript = Boolean(askSourceTranscript.trim());
  const askCanGenerate = askBusyAction === "" && askHasTranscript && Boolean(askPrompt.trim());
  const askCanSave = askBusyAction === "" && Boolean(askResult) && (isRecording || Boolean(selectedNote) || Boolean(askResultTargetId));
  const askCanReset =
    askBusyAction === "" &&
    Boolean(askResult || askMessage || pendingSavedLiveSummary || askPrompt !== getDefaultVoiceNoteSummaryPrompt());
  const askBadgeTone: "neutral" | "good" | "bad" | "info" =
    askBusyAction === "generate" || askBusyAction === "save"
      ? "info"
      : askMessage
        ? askMessage === "Saved for this recording." || askMessage === "Summary ready."
          ? "good"
          : "bad"
        : askResult
          ? "good"
          : askHasTranscript
            ? "info"
            : "neutral";
  const askBadgeLabel =
    askBusyAction === "generate"
      ? "Generating"
      : askBusyAction === "save"
        ? "Saving"
        : pendingSavedLiveSummary
          ? "Saved"
          : askResult
            ? "Ready"
            : askHasTranscript
              ? "Ready"
              : "Waiting";

  useEffect(() => {
    transcriptRef.current = liveTranscript;
  }, [liveTranscript]);

  useLayoutEffect(() => {
    scrollVoiceNoteTranscriptToLatest(liveTranscriptSurfaceRef.current);
  }, [previewText]);

  useEffect(() => {
    let disposed = false;

    async function loadSavedNotes() {
      try {
        const legacyNotes = loadLegacyVoiceNotes();
        const savedNotes = legacyNotes.length > 0 ? await importVoiceNotes(legacyNotes) : await getVoiceNotes();
        if (legacyNotes.length > 0) {
          clearLegacyVoiceNotes();
        }
        if (!disposed) {
          setNotes(savedNotes);
        }
      } catch {
        if (!disposed) {
          setStatus("Could not load saved notes.");
        }
      }
    }

    void loadSavedNotes();
    return () => {
      disposed = true;
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

  function setPendingSavedLiveSummary(summary: VoiceNote["summary"]) {
    pendingSavedLiveSummaryRef.current = summary;
    setPendingSavedLiveSummaryState(summary);
  }

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
      setPendingSavedLiveSummary(null);
      setAskResult(null);
      setAskResultTargetId(null);
      setAskMessage("");
      setAskBusyAction("");
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
    const savedLiveSummary = pendingSavedLiveSummaryRef.current;
    const noteToSave = savedLiveSummary ? { ...note, summary: savedLiveSummary } : note;

    let savedNote = noteToSave;
    let nextStatus = "Saved to notes";
    try {
      savedNote = await saveVoiceNote(noteToSave);
    } catch {
      nextStatus = "Saved for now. Restart the local app service to keep new notes.";
    }
    setNotes((current) => [savedNote, ...current.filter((currentNote) => currentNote.id !== savedNote.id)]);
    setExpandedNoteId(savedNote.id);
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
    setPendingSavedLiveSummary(null);
    setAskResultTargetId(savedNote.id);
    if (savedLiveSummary) {
      setAskMessage("Summary ready.");
      setSummaryState({ noteId: savedNote.id, status: "ready", message: "Summary ready." });
    } else if (savedNote.transcript) {
      void summarizeVoiceNote(savedNote, { persist: true });
    } else {
      setSummaryState({
        noteId: savedNote.id,
        status: "idle",
        message: "No words were captured, so there is nothing to summarize yet.",
      });
    }
  }

  async function summarizeVoiceNote(note: VoiceNote, options: { persist?: boolean } = {}) {
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
      const title = (noteEditDraft?.noteId === note.id ? noteEditDraft.title : note.title).trim() || "Voice note";
      const result = await generateVoiceNoteSummary({
        title,
        transcript,
        prompt: getDefaultVoiceNoteSummaryPrompt(),
      });
      const summary = createVoiceNoteSummary(result);
      if (options.persist) {
        const savedNote = await updateVoiceNote(note.id, { summary });
        setNotes((current) => current.map((currentNote) => (currentNote.id === note.id ? savedNote : currentNote)));
        setSummaryState({ noteId: note.id, status: "ready", message: "Summary ready." });
        return;
      }
      setNoteEditDraft((current) => {
        if (current?.noteId !== note.id) {
          return current;
        }
        return { ...current, summary };
      });
      setSummaryState((current) =>
        current.noteId === note.id && current.status === "generating"
          ? { noteId: note.id, status: "ready", message: "Summary ready. Click Save to keep it." }
          : current,
      );
    } catch (error) {
      setSummaryState((current) =>
        current.noteId === note.id && current.status === "generating"
          ? {
              noteId: note.id,
              status: "error",
              message: error instanceof Error ? error.message : "Unable to create a summary.",
            }
          : current,
      );
    }
  }

  async function generateAskAiSummary(event: FormEvent) {
    event.preventDefault();
    const prompt = askPrompt.trim();
    const transcript = askSourceTranscript.trim();
    if (!transcript) {
      setAskMessage("Record or choose a note before asking for a summary.");
      return;
    }
    if (!prompt) {
      setAskMessage("Enter what you want summarized.");
      return;
    }

    setAskBusyAction("generate");
    setAskMessage("");
    try {
      const result = await generateVoiceNoteSummary({
        title: askSourceTitle.trim() || "Voice note",
        transcript,
        prompt,
      });
      setAskResult(createVoiceNoteSummary(result));
      setAskResultTargetId(isRecording ? null : selectedNote?.id ?? null);
    } catch (error) {
      setAskResult(null);
      setAskResultTargetId(null);
      setAskMessage(error instanceof Error ? error.message : "Unable to create a summary.");
    } finally {
      setAskBusyAction("");
    }
  }

  async function saveAskAiResult() {
    if (!askResult) {
      return;
    }
    setAskBusyAction("save");
    setAskMessage("");
    try {
      if (isRecording) {
        setPendingSavedLiveSummary(askResult);
        setAskMessage("Saved for this recording.");
        return;
      }

      const noteId = askResultTargetId ?? selectedNote?.id;
      if (!noteId) {
        setAskMessage("Choose a saved note before saving this summary.");
        return;
      }
      const savedNote = await updateVoiceNote(noteId, { summary: askResult });
      setNotes((current) => current.map((currentNote) => (currentNote.id === noteId ? savedNote : currentNote)));
      setNoteEditDraft((current) => (current?.noteId === noteId ? { ...current, summary: askResult } : current));
      setSummaryState({ noteId, status: "ready", message: "Summary ready." });
      setAskResultTargetId(noteId);
      setAskMessage("Summary ready.");
    } catch (error) {
      setAskMessage(error instanceof Error ? error.message : "Unable to save this summary.");
    } finally {
      setAskBusyAction("");
    }
  }

  function resetAskAiSummary() {
    setAskPrompt(getDefaultVoiceNoteSummaryPrompt());
    setAskResult(null);
    setAskResultTargetId(null);
    setAskMessage("");
    setPendingSavedLiveSummary(null);
  }

  function beginEditNote(note: VoiceNote) {
    setExpandedNoteId(note.id);
    setEditingNoteId(note.id);
    setNoteEditDraft({
      noteId: note.id,
      title: note.title,
      summary: note.summary,
    });
    setSummaryState((current) => (current.noteId === note.id ? { noteId: null, status: "idle", message: "" } : current));
  }

  function cancelEditNote(noteId: string) {
    setEditingNoteId((current) => (current === noteId ? null : current));
    setNoteEditDraft((current) => (current?.noteId === noteId ? null : current));
    setSummaryState((current) => (current.noteId === noteId ? { noteId: null, status: "idle", message: "" } : current));
  }

  function updateNoteDraft(updates: Partial<NoteEditDraft>) {
    setNoteEditDraft((current) => (current ? { ...current, ...updates } : current));
  }

  function deleteNote(noteId: string) {
    setNotes((current) => {
      return current.filter((note) => note.id !== noteId);
    });
    setExpandedNoteId((current) => (current === noteId ? null : current));
    setEditingNoteId((current) => (current === noteId ? null : current));
    setNoteEditDraft((current) => (current?.noteId === noteId ? null : current));
    setSummaryState((current) => (current.noteId === noteId ? { noteId: null, status: "idle", message: "" } : current));
    void deleteVoiceNote(noteId).catch(() => {
      setStatus("Could not delete the saved note.");
    });
  }

  async function saveNote(noteId: string) {
    const note = notes.find((candidate) => candidate.id === noteId);
    if (!note || editingNoteId !== noteId || noteEditDraft?.noteId !== noteId) {
      return;
    }
    const title = noteEditDraft.title.trim() || "Voice note";
    try {
      const savedNote = await updateVoiceNote(noteId, {
        title,
        summary: noteEditDraft.summary,
      });
      setNotes((current) => current.map((currentNote) => (currentNote.id === noteId ? savedNote : currentNote)));
    } catch {
      setStatus("Could not save the note.");
      return;
    }
    setEditingNoteId(null);
    setNoteEditDraft(null);
    setStatus("Saved to notes");
  }

  function selectNote(note: VoiceNote) {
    const nextExpandedNoteId = expandedNoteId === note.id ? null : note.id;
    setExpandedNoteId(nextExpandedNoteId);
    if (editingNoteId && editingNoteId !== nextExpandedNoteId) {
      setEditingNoteId(null);
      setNoteEditDraft(null);
    }
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
          <div className="voice-live-note-body" ref={liveTranscriptSurfaceRef}>
            <p>{previewText || liveNotePlaceholder}</p>
          </div>
        </div>
      </Card>

      <Card className="summary-panel voice-ask-ai-card">
        <div className="card-heading-row">
          <div>
            <p className="eyebrow">Ask AI</p>
            <h2>Ask about this note</h2>
          </div>
          <Badge tone={askBadgeTone}>{askBadgeLabel}</Badge>
        </div>
        <p className="muted">{askContextLabel}</p>
        <form className="stack" onSubmit={(event) => void generateAskAiSummary(event)}>
          <label>
            Ask about this note
            <TextArea
              disabled={askBusyAction !== ""}
              onChange={(event) => setAskPrompt(event.target.value)}
              placeholder="Summarize key points and follow-up actions"
              rows={5}
              value={askPrompt}
            />
          </label>
          <div className="toolbar">
            <Button disabled={!askCanGenerate} type="submit">
              <Sparkles aria-hidden="true" size={16} />
              {askBusyAction === "generate" ? "Generating..." : "Generate Summary"}
            </Button>
            <Button disabled={!askCanSave} onClick={() => void saveAskAiResult()} type="button" variant="secondary">
              <Save aria-hidden="true" size={16} />
              {askBusyAction === "save" ? "Saving..." : "Save Result"}
            </Button>
            <Button disabled={!askCanReset} onClick={resetAskAiSummary} type="button" variant="quiet">
              <RefreshCw aria-hidden="true" size={16} />
              Reset
            </Button>
          </div>
        </form>
        {askMessage ? (
          <p aria-live="polite" className="form-message">
            {askMessage}
          </p>
        ) : null}
        {askResult ? (
          <div className="summary-output">
            <div className="summary-meta">
              <Badge tone="info">{askResult.provider}</Badge>
              <Badge tone="neutral">{new Date(askResult.generatedAt).toLocaleString()}</Badge>
              {pendingSavedLiveSummary === askResult ? <Badge tone="good">Saved for this recording</Badge> : null}
            </div>
            <pre>{askResult.markdown}</pre>
          </div>
        ) : (
          <p className="muted">Generate a summary from the words available right now.</p>
        )}
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
            const isEditing = editingNoteId === note.id;
            const draft = isEditing && noteEditDraft?.noteId === note.id ? noteEditDraft : null;
            const displayedSummary = draft ? draft.summary : note.summary;
            const noteSummaryState = summaryState.noteId === note.id ? summaryState : null;
            const summaryIsGenerating = noteSummaryState?.status === "generating";
            const summaryMessage = noteSummaryState?.message ?? "";
            return (
              <article className={expanded ? "voice-note-item voice-note-item-open" : "voice-note-item"} key={note.id}>
                <div className="voice-note-card-row">
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
                  {!isEditing ? (
                    <Button
                      aria-label={`Edit ${note.title}`}
                      className="voice-note-edit-button"
                      onClick={() => beginEditNote(note)}
                      type="button"
                      variant="quiet"
                    >
                      <Pencil aria-hidden="true" size={16} />
                      Edit
                    </Button>
                  ) : null}
                </div>
                {expanded ? (
                  <div className="voice-note-details">
                    {isEditing && draft ? (
                      <TextInput
                        aria-label="Note title"
                        onChange={(event) => updateNoteDraft({ title: event.target.value })}
                        value={draft.title}
                      />
                    ) : null}
                    <div aria-label={`Transcript for ${note.title}`} className="voice-note-transcript" role="region">
                      <p>{note.transcript || "No transcript captured."}</p>
                    </div>
                    {displayedSummary ? (
                      <div className="summary-output voice-note-summary-output">
                        <div className="summary-meta">
                          <Badge tone="info">{displayedSummary.provider}</Badge>
                          <Badge tone="neutral">{new Date(displayedSummary.generatedAt).toLocaleString()}</Badge>
                          {isEditing && displayedSummary !== note.summary ? <Badge tone="warn">Unsaved</Badge> : null}
                        </div>
                        <pre>{displayedSummary.markdown}</pre>
                      </div>
                    ) : null}
                    {summaryMessage ? (
                      <p aria-live="polite" className="form-message">
                        {summaryMessage}
                      </p>
                    ) : null}
                    {note.audioDataUrl ? <audio controls src={note.audioDataUrl} /> : null}
                    {isEditing ? (
                      <div className="toolbar">
                        <Button onClick={() => void saveNote(note.id)} type="button" variant="secondary">
                          <Save aria-hidden="true" size={16} />
                          Save
                        </Button>
                        <Button onClick={() => cancelEditNote(note.id)} type="button" variant="quiet">
                          <X aria-hidden="true" size={16} />
                          Cancel
                        </Button>
                        <Button
                          disabled={!note.transcript.trim() || summaryIsGenerating}
                          onClick={() => void summarizeVoiceNote(note)}
                          type="button"
                          variant="secondary"
                        >
                          <Sparkles aria-hidden="true" size={16} />
                          {summaryIsGenerating ? "Generating..." : note.summary ? "Regenerate summary" : "Generate summary"}
                        </Button>
                        <Button onClick={() => deleteNote(note.id)} type="button" variant="danger">
                          <Trash2 aria-hidden="true" size={16} />
                          Delete
                        </Button>
                      </div>
                    ) : null}
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
