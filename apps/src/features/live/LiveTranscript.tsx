import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { Badge, Card } from "../../components/ui";
import { apiUrl } from "../../lib/api";
import { readableState, stateTone } from "../../lib/job-state";
import { advanceInitialReplayState, buildTranscriptFeed, createInitialReplayState, shouldClearLiveDraft, shouldRenderTranscriptLine } from "../../lib/live-transcript";
import type { JobDetailResponse, LiveTranscriptSource, TranscriptBlock } from "../../lib/types";
import { formatRange, formatTimestamp, isNearBottom } from "./transcriptFormatting";

type SourceTranscriptState = {
  finalBlocks: TranscriptBlock[];
  interim: string;
  interimSpeaker: number | null | undefined;
  interimStart: number | undefined;
  speech: string;
};

const transcriptSources: Array<{ source: LiveTranscriptSource; label: string }> = [
  { source: "system", label: "System audio" },
  { source: "microphone", label: "Self" },
];

function emptySourceState(): SourceTranscriptState {
  return {
    finalBlocks: [],
    interim: "",
    interimSpeaker: null,
    interimStart: undefined,
    speech: "Awaiting speech",
  };
}

function sourceLabel(source: LiveTranscriptSource) {
  return source === "system" ? "System audio" : "Self";
}

function transcriptSource(event: TranscriptBlock): LiveTranscriptSource {
  return event.source === "microphone" ? "microphone" : "system";
}

function speakerLabel(source: LiveTranscriptSource, speaker: number | null | undefined) {
  if (source === "microphone") {
    return "Self";
  }
  return speaker !== null && speaker !== undefined ? `Speaker ${speaker}` : null;
}

function initialSourceState(job: JobDetailResponse | null, source: LiveTranscriptSource): SourceTranscriptState {
  if (!job) {
    return emptySourceState();
  }

  const sourceSnapshot = job.live_snapshot.sources?.[source];
  const legacySnapshot = source === "system" ? job.live_snapshot : null;
  const snapshot = sourceSnapshot ?? legacySnapshot;

  return {
    finalBlocks: snapshot?.final_blocks ?? [],
    interim: snapshot?.interim ?? "",
    interimSpeaker: null,
    interimStart: undefined,
    speech: "Awaiting speech",
  };
}

function initialSourceStates(job: JobDetailResponse | null): Record<LiveTranscriptSource, SourceTranscriptState> {
  return {
    system: initialSourceState(job, "system"),
    microphone: initialSourceState(job, "microphone"),
  };
}

export function LiveTranscript({ job }: { job: JobDetailResponse | null }) {
  const [sourceStates, setSourceStates] = useState<Record<LiveTranscriptSource, SourceTranscriptState>>(() => initialSourceStates(null));
  const [streamMessage, setStreamMessage] = useState("Choose a job to view its transcript.");
  const [state, setState] = useState("idle");
  const transcriptRefs = useRef<Record<LiveTranscriptSource, HTMLDivElement | null>>({ system: null, microphone: null });
  const shouldFollowRef = useRef<Record<LiveTranscriptSource, boolean>>({ system: true, microphone: true });
  const transcriptRowsBySource = useMemo(
    () => ({
      system: buildTranscriptFeed(sourceStates.system.interim, sourceStates.system.finalBlocks),
      microphone: buildTranscriptFeed(sourceStates.microphone.interim, sourceStates.microphone.finalBlocks),
    }),
    [sourceStates],
  );

  useLayoutEffect(() => {
    for (const { source } of transcriptSources) {
      const feed = transcriptRefs.current[source];
      if (!shouldFollowRef.current[source] || !feed) {
        continue;
      }
      feed.scrollTop = feed.scrollHeight;
    }
  }, [transcriptRowsBySource]);

  useEffect(() => {
    shouldFollowRef.current = { system: true, microphone: true };
    setSourceStates(initialSourceStates(job));
    setState(job?.state ?? "idle");
    if (!job) return;
    setStreamMessage("Connecting to live transcript...");
    let replay = {
      system: createInitialReplayState(job.live_snapshot, "system"),
      microphone: createInitialReplayState(job.live_snapshot, "microphone"),
    };
    const stream = new EventSource(apiUrl(`/api/jobs/${job.id}/live/stream`));
    stream.onopen = () => {
      setStreamMessage("Live transcript connected.");
    };
    stream.onmessage = (message) => {
      const event = JSON.parse(message.data) as TranscriptBlock;
      const source = transcriptSource(event);
      shouldFollowRef.current[source] = isNearBottom(transcriptRefs.current[source]);

      const updateSourceState = (updater: (current: SourceTranscriptState) => SourceTranscriptState) => {
        setSourceStates((current) => ({
          ...current,
          [source]: updater(current[source]),
        }));
      };

      if (event.type === "interim") {
        const replayUpdate = advanceInitialReplayState(replay[source], event);
        replay = { ...replay, [source]: replayUpdate.replay };
        if (replayUpdate.skip) {
          return;
        }
        updateSourceState((current) => ({
          ...current,
          interim: event.text ?? "",
          interimSpeaker: event.speaker,
          interimStart: event.start,
          speech: "Speech detected",
        }));
        setStreamMessage(`${sourceLabel(source)} draft updating.`);
      } else if (event.type === "final") {
        const replayUpdate = advanceInitialReplayState(replay[source], event);
        replay = { ...replay, [source]: replayUpdate.replay };
        if (replayUpdate.skip) {
          return;
        }
        updateSourceState((current) => ({
          ...current,
          finalBlocks: event.text ? [...current.finalBlocks, event] : current.finalBlocks,
          interim: "",
          interimSpeaker: null,
          interimStart: undefined,
          speech: "Awaiting speech",
        }));
        setStreamMessage(`${sourceLabel(source)} transcript updated.`);
      } else if (event.type === "status" && event.state) {
        setState(event.state);
        setStreamMessage("Live transcript connected.");
      } else if (event.type === "speech_started") {
        updateSourceState((current) => ({ ...current, speech: "Speech detected" }));
        setStreamMessage(`${sourceLabel(source)} is listening.`);
      } else if (event.type === "utterance_end") {
        updateSourceState((current) => ({
          ...current,
          interim: "",
          interimSpeaker: null,
          interimStart: undefined,
          speech: "Pause detected",
        }));
        setStreamMessage(`${sourceLabel(source)} is waiting.`);
      } else if (event.type === "metadata") {
        if (shouldClearLiveDraft(event)) {
          updateSourceState((current) => ({
            ...current,
            interim: "",
            interimSpeaker: null,
            interimStart: undefined,
          }));
        }
        setStreamMessage(event.model ? `Connected to ${event.model}.` : "Connected to speech service.");
      } else if (event.type === "warning") {
        setStreamMessage(event.message ?? "Live transcript warning.");
      } else if (event.type === "complete") {
        setSourceStates((current) => ({
          system: { ...current.system, interim: "", interimSpeaker: null, interimStart: undefined, speech: "Capture complete" },
          microphone: { ...current.microphone, interim: "", interimSpeaker: null, interimStart: undefined, speech: "Capture complete" },
        }));
        setState(event.state ?? "completed");
        setStreamMessage("Capture completed.");
      } else if (!shouldRenderTranscriptLine(event)) {
        setStreamMessage("Live transcript connected.");
      }
    };
    stream.onerror = () => {
      setStreamMessage("Live transcript disconnected. Reconnecting...");
    };
    return () => stream.close();
  }, [job?.id]);

  return (
    <Card className="transcript-card">
      <div className="card-heading-row">
        <div>
          <p className="eyebrow">Live transcript</p>
          <h2>{job ? job.title : "No job selected"}</h2>
        </div>
        {job ? <Badge tone={stateTone(state)}>{readableState(state)}</Badge> : null}
      </div>
      <div className="transcript-status-row">
        <span>{streamMessage}</span>
      </div>
      <div className="transcript-sections">
        {transcriptSources.map(({ source, label }) => {
          const sourceState = sourceStates[source];
          const transcriptRows = transcriptRowsBySource[source];
          const isMicrophone = source === "microphone";
          const isSystem = source === "system";
          return (
            <section className={isMicrophone ? "transcript-source-section transcript-source-section-microphone" : "transcript-source-section"} key={source}>
              <div className="transcript-source-heading">
                <h3>{label}</h3>
                <Badge tone={sourceState.interim ? "info" : isSystem ? "neutral" : "warn"}>{sourceState.speech}</Badge>
              </div>
              <div
                className="transcript-feed"
                onScroll={() => {
                  shouldFollowRef.current[source] = isNearBottom(transcriptRefs.current[source]);
                }}
                ref={(element) => {
                  transcriptRefs.current[source] = element;
                }}
              >
                {transcriptRows.length === 0 ? <p className="transcript-empty">Waiting for speech</p> : null}
                {transcriptRows.map((row, index) => {
                  const speaker = row.kind === "draft" ? sourceState.interimSpeaker : row.speaker;
                  const speakerText = speakerLabel(source, speaker);
                  const range = row.kind === "draft" ? formatTimestamp(sourceState.interimStart) : formatRange(row.start, row.current);
                  return (
                    <article className={row.kind === "draft" ? "transcript-row transcript-row-draft" : "transcript-row"} key={`${source}-${row.kind}-${range}-${index}`}>
                      <div className="transcript-meta">
                        {speakerText ? <span className="transcript-chip">{speakerText}</span> : null}
                        {range ? <span className="transcript-chip">{range}</span> : null}
                        {row.kind === "draft" ? <span className="transcript-chip transcript-chip-live">Live draft</span> : null}
                      </div>
                      <p className={row.kind === "draft" ? "transcript-interim" : "transcript-line"}>{row.text}</p>
                    </article>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </Card>
  );
}
