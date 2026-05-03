import type { ArtifactFile } from "./types";

const HIDDEN_ARTIFACT_NAMES = new Set([
  "controller-events.jsonl",
  "deepgram-events.jsonl",
  "metadata.json",
  "transcript.json",
  "transcript.txt",
]);

export function userVisibleArtifacts(artifacts: ArtifactFile[]) {
  return artifacts.filter((artifact) => !HIDDEN_ARTIFACT_NAMES.has(artifact.name));
}
