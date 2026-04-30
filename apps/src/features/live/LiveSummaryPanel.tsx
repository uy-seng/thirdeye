import { RefreshCw, Save, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { Badge, Button, Card, TextArea } from "../../components/ui";
import { generateTranscriptSummary, saveTranscriptSummary } from "../../lib/api";
import { getDefaultLiveSummaryPrompt } from "../../lib/prompts";
import type { JobDetailResponse, TranscriptSummaryGenerateResponse } from "../../lib/types";

export function LiveSummaryPanel({ job, onSaved }: { job: JobDetailResponse | null; onSaved: () => void }) {
  const [prompt, setPrompt] = useState(() => getDefaultLiveSummaryPrompt());
  const [result, setResult] = useState<TranscriptSummaryGenerateResponse | null>(null);
  const [message, setMessage] = useState("");
  const [busyAction, setBusyAction] = useState<"" | "generate" | "save">("");

  useEffect(() => {
    setResult(null);
    setMessage("");
  }, [job?.id]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!job) {
      setMessage("Choose a job before asking for a summary.");
      return;
    }
    const request = prompt.trim();
    if (!request) {
      setMessage("Enter what you want summarized.");
      return;
    }
    setBusyAction("generate");
    setMessage("");
    try {
      setResult(await generateTranscriptSummary(job.id, request));
    } catch (error) {
      setResult(null);
      setMessage(error instanceof Error ? error.message : "Unable to generate a summary.");
    } finally {
      setBusyAction("");
    }
  }

  function resetSummary() {
    setPrompt(getDefaultLiveSummaryPrompt());
    setResult(null);
    setMessage("");
  }

  async function saveResult() {
    if (!job || !result) {
      return;
    }
    setBusyAction("save");
    setMessage("");
    try {
      const artifact = await saveTranscriptSummary(job.id, result.request_id);
      setMessage(`Saved as ${artifact.name}`);
      onSaved();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save this summary.");
    } finally {
      setBusyAction("");
    }
  }

  const summarySource = result
    ? `${result.source.final_block_count} finalized block${result.source.final_block_count === 1 ? "" : "s"}`
    : "";
  const canResetSummary = Boolean(result || message || prompt !== getDefaultLiveSummaryPrompt());

  return (
    <Card className="summary-panel">
      <div className="card-heading-row">
        <div>
          <p className="eyebrow">Live summary</p>
          <h2>Ask about this transcript</h2>
        </div>
        <Badge tone={job ? "info" : "neutral"}>{job ? "Ready" : "No job"}</Badge>
      </div>
      <form className="stack" onSubmit={submit}>
        <label>
          Ask about this transcript
          <TextArea
            disabled={!job || busyAction !== ""}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Summarize decisions and next steps"
            rows={5}
            value={prompt}
          />
        </label>
        <div className="toolbar">
          <Button disabled={!job || busyAction !== "" || !prompt.trim()} type="submit">
            <Sparkles aria-hidden="true" size={16} />
            {busyAction === "generate" ? "Generating..." : "Generate Summary"}
          </Button>
          <Button disabled={!result || busyAction !== ""} onClick={() => void saveResult()} type="button" variant="secondary">
            <Save aria-hidden="true" size={16} />
            {busyAction === "save" ? "Saving..." : "Save Result"}
          </Button>
          <Button disabled={busyAction !== "" || !canResetSummary} onClick={resetSummary} type="button" variant="quiet">
            <RefreshCw aria-hidden="true" size={16} />
            Reset
          </Button>
        </div>
      </form>
      {message ? <p className="form-message">{message}</p> : null}
      {result ? (
        <div className="summary-output">
          <div className="summary-meta">
            <Badge tone="info">{summarySource}</Badge>
            {result.source.interim_included ? <Badge tone="warn">Live draft included</Badge> : null}
          </div>
          <pre>{result.markdown}</pre>
        </div>
      ) : (
        <p className="muted">Generate a summary from the transcript as it stands now.</p>
      )}
    </Card>
  );
}
