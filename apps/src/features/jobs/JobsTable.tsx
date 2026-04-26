import { Badge, Card } from "../../components/ui";
import { formatStateLabel, stateTone } from "../../lib/job-state";
import type { JobResponse } from "../../lib/types";

export type JobsTableProps = {
  jobs: JobResponse[];
  selectedJobId: string | null;
  onSelect: (jobId: string) => void;
};

export function JobsTable({ jobs, selectedJobId, onSelect }: JobsTableProps) {
  return (
    <Card className="table-card">
      <div className="card-heading-row">
        <div>
          <p className="eyebrow">Jobs</p>
          <h2>Capture history</h2>
        </div>
        <Badge tone="neutral">{jobs.length} total</Badge>
      </div>
      <div className="job-list">
        {jobs.map((job) => (
          <button className={job.id === selectedJobId ? "job-row job-row-active" : "job-row"} key={job.id} onClick={() => onSelect(job.id)} type="button">
            <span>
              <strong>{job.title}</strong>
              <small>{new Date(job.created_at).toLocaleString()}</small>
            </span>
            <Badge tone={stateTone(job.state, job.metadata_json)}>{formatStateLabel(job.state, job.metadata_json)}</Badge>
          </button>
        ))}
      </div>
    </Card>
  );
}
