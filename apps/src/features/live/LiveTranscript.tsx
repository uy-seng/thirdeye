import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { Badge, Card } from "../../components/ui";
import { authenticatedApiUrl } from "../../lib/api";
import { readableState, stateTone } from "../../lib/job-state";
import { advanceInitialReplayState, buildTranscriptFeed, createInitialReplayState, shouldRenderTranscriptLine } from "../../lib/live-transcript";
import type { JobDetailResponse, TranscriptBlock } from "../../lib/types";
import { formatRange, formatTimestamp, isNearBottom } from "./transcriptFormatting";

export function LiveTranscript({ job }: { job: JobDetailResponse | null }) {
  const [finalBlocks, setFinalBlocks] = useState<TranscriptBlock[]>([]);
  const [interim, setInterim] = useState("");
  const [interimSpeaker, setInterimSpeaker] = useState<number | null | undefined>(null);
  const [interimStart, setInterimStart] = useState<number | undefined>(undefined);
  const [streamMessage, setStreamMessage] = useState("Choose a job to view its transcript.");
  const [state, setState] = useState("idle");
  const [speech, setSpeech] = useState("Awaiting speech");
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const shouldFollowRef = useRef(true);
  const transcriptRows = useMemo(() => buildTranscriptFeed(interim, finalBlocks), [finalBlocks, interim]);

  useLayoutEffect(() => {
    if (!shouldFollowRef.current || !transcriptRef.current) {
      return;
    }
    transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
  }, [transcriptRows]);

  useEffect(() => {
    shouldFollowRef.current = true;
    setFinalBlocks(job?.live_snapshot.final_blocks ?? []);
    setInterim(job?.live_snapshot.interim ?? "");
    setInterimSpeaker(null);
    setInterimStart(undefined);
    setState(job?.state ?? "idle");
    setSpeech("Awaiting speech");
    if (!job) return;
    setStreamMessage("Connecting to live transcript...");
    let replay = createInitialReplayState(job.live_snapshot);
    const stream = new EventSource(authenticatedApiUrl(`/api/jobs/${job.id}/live/stream`), { withCredentials: true });
    stream.onopen = () => {
      setStreamMessage("Live transcript connected.");
    };
    stream.onmessage = (message) => {
      const event = JSON.parse(message.data) as TranscriptBlock;
      shouldFollowRef.current = isNearBottom(transcriptRef.current);
      if (event.type === "interim") {
        const replayUpdate = advanceInitialReplayState(replay, event);
        replay = replayUpdate.replay;
        if (replayUpdate.skip) {
          return;
        }
        setInterim(event.text ?? "");
        setInterimSpeaker(event.speaker);
        setInterimStart(event.start);
        setSpeech("Speech detected");
        setStreamMessage("Live draft updating.");
      } else if (event.type === "final") {
        const replayUpdate = advanceInitialReplayState(replay, event);
        replay = replayUpdate.replay;
        if (replayUpdate.skip) {
          return;
        }
        setInterim("");
        setInterimSpeaker(null);
        setInterimStart(undefined);
        if (event.text) {
          setFinalBlocks((current) => [...current, event]);
        }
        setSpeech("Awaiting speech");
        setStreamMessage("Transcript updated.");
      } else if (event.type === "status" && event.state) {
        setState(event.state);
        setStreamMessage("Live transcript connected.");
      } else if (event.type === "speech_started") {
        setSpeech("Speech detected");
        setStreamMessage("Listening for the next words.");
      } else if (event.type === "utterance_end") {
        setSpeech("Pause detected");
        setStreamMessage("Waiting for the next speaker.");
      } else if (event.type === "metadata") {
        setStreamMessage(event.model ? `Connected to ${event.model}.` : "Connected to speech service.");
      } else if (event.type === "warning") {
        setStreamMessage(event.message ?? "Live transcript warning.");
      } else if (event.type === "complete") {
        setState(event.state ?? "completed");
        setSpeech("Capture complete");
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
        <Badge tone={interim ? "info" : "neutral"}>{speech}</Badge>
        <span>{streamMessage}</span>
      </div>
      <div className="transcript-feed" onScroll={() => {
        shouldFollowRef.current = isNearBottom(transcriptRef.current);
      }} ref={transcriptRef}>
        {transcriptRows.length === 0 ? <p className="transcript-empty">Waiting for speech</p> : null}
        {transcriptRows.map((row, index) => {
          const speaker = row.kind === "draft" ? interimSpeaker : row.speaker;
          const range = row.kind === "draft" ? formatTimestamp(interimStart) : formatRange(row.start, row.current);
          return (
            <article className={row.kind === "draft" ? "transcript-row transcript-row-draft" : "transcript-row"} key={`${row.kind}-${range}-${index}`}>
              <div className="transcript-meta">
                {speaker !== null && speaker !== undefined ? <span className="transcript-chip">Speaker {speaker}</span> : null}
                {range ? <span className="transcript-chip">{range}</span> : null}
                {row.kind === "draft" ? <span className="transcript-chip transcript-chip-live">Live draft</span> : null}
              </div>
              <p className={row.kind === "draft" ? "transcript-interim" : "transcript-line"}>{row.text}</p>
            </article>
          );
        })}
      </div>
    </Card>
  );
}
