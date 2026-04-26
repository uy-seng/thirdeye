import type { JobResponse } from "./types";
import { ACTIVE_STATES } from "./job-state";

export function chooseSelectedJobId({
  currentJobId = null,
  jobs,
  preferredJobId = null,
}: {
  currentJobId?: string | null;
  jobs: JobResponse[];
  preferredJobId?: string | null;
}) {
  const jobIds = new Set(jobs.map((job) => job.id));
  if (preferredJobId && jobIds.has(preferredJobId)) {
    return preferredJobId;
  }
  if (currentJobId && jobIds.has(currentJobId)) {
    return currentJobId;
  }
  return jobs.find((job) => ACTIVE_STATES.has(job.state))?.id ?? jobs[0]?.id ?? null;
}
