import { Badge, Select } from "../../components/ui";
import type { JobResponse } from "../../lib/types";

function jobOptionLabel(job: JobResponse) {
  const title = job.title.trim() || "Untitled capture";
  const target = job.capture_target.label.trim();
  return target && target !== title ? `${title} - ${target}` : title;
}

export function LiveJobSelector({
  jobs,
  selectedJobId,
  onSelect,
}: {
  jobs: JobResponse[];
  selectedJobId: string | null;
  onSelect: (jobId: string) => void;
}) {
  if (jobs.length <= 1) {
    return null;
  }

  return (
    <div className="live-job-switcher">
      <label className="live-job-field">
        <span>Live capture</span>
        <Select aria-label="Choose live capture" onChange={(event) => onSelect(event.target.value)} value={selectedJobId ?? ""}>
          {jobs.map((job) => (
            <option key={job.id} value={job.id}>
              {jobOptionLabel(job)}
            </option>
          ))}
        </Select>
      </label>
      <Badge tone="info">{jobs.length} live captures</Badge>
    </div>
  );
}
