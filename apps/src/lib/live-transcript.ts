import type { JobDetailResponse, TranscriptBlock } from "./types";

export type InitialReplayState = {
  pendingDraft: string | null;
  pendingFinalBlocks: number;
};

export type TranscriptFeedRow =
  | {
      kind: "final";
      text: string;
      speaker?: number | null;
      start?: number;
      current?: number;
    }
  | {
      kind: "draft";
      text: string;
      speaker?: number | null;
      start?: number;
    };

function isValidTimestamp(value?: number) {
  return typeof value === "number" && !Number.isNaN(value);
}

function currentTimestamp(block: TranscriptBlock) {
  if (isValidTimestamp(block.end)) {
    return block.end;
  }

  if (isValidTimestamp(block.start)) {
    return block.start;
  }

  return undefined;
}

function appendTranscriptText(current: string, incoming: string) {
  if (!current) {
    return incoming;
  }

  if (!incoming) {
    return current;
  }

  return `${current} ${incoming}`;
}

function shouldMergeFinalBlock(previousBlock: TranscriptBlock | undefined, previousSpeaker: number | null | undefined, currentBlock: TranscriptBlock, currentSpeaker: number | null) {
  if (!previousBlock) {
    return false;
  }

  if (previousSpeaker === currentSpeaker) {
    return true;
  }

  return previousBlock.speech_final === false;
}

export function shouldRenderTranscriptLine(event: TranscriptBlock) {
  return event.type === "final" || event.type === "interim";
}

export function shouldClearLiveDraft(event: TranscriptBlock) {
  return event.type === "utterance_end" || event.type === "metadata" || event.type === "complete";
}

export function createInitialReplayState(snapshot: JobDetailResponse["live_snapshot"]): InitialReplayState {
  return {
    pendingDraft: snapshot.interim || null,
    pendingFinalBlocks: snapshot.final_blocks.length,
  };
}

export function advanceInitialReplayState(state: InitialReplayState, block: TranscriptBlock) {
  if (block.type === "final" && state.pendingFinalBlocks > 0) {
    return {
      replay: {
        ...state,
        pendingFinalBlocks: state.pendingFinalBlocks - 1,
      },
      skip: true,
    };
  }

  if (block.type === "interim" && state.pendingDraft !== null) {
    return {
      replay: {
        ...state,
        pendingDraft: null,
      },
      skip: block.text === state.pendingDraft,
    };
  }

  return {
    replay: state,
    skip: false,
  };
}

export function buildTranscriptFeed(draft: string, blocks: TranscriptBlock[]): TranscriptFeedRow[] {
  const rows: TranscriptFeedRow[] = [];
  const speakerKeys: Array<number | null> = [];
  const tailBlocks: TranscriptBlock[] = [];

  for (const block of blocks) {
    const text = block.text?.trim();

    if (!text) {
      continue;
    }

    const speakerKey = block.speaker ?? null;
    const previous = rows[rows.length - 1];
    const previousBlock = tailBlocks[tailBlocks.length - 1];
    const previousSpeakerKey = speakerKeys[speakerKeys.length - 1];

    if (previous?.kind === "final" && shouldMergeFinalBlock(previousBlock, previousSpeakerKey, block, speakerKey)) {
      previous.text = appendTranscriptText(previous.text, text);

      const current = currentTimestamp(block);
      if (current !== undefined) {
        previous.current = current;
      }

      if (previous.start === undefined && isValidTimestamp(block.start)) {
        previous.start = block.start;
      }

      tailBlocks[tailBlocks.length - 1] = block;
      speakerKeys[speakerKeys.length - 1] = speakerKey;
      continue;
    }

    const row: TranscriptFeedRow = {
      kind: "final",
      text,
      speaker: block.speaker,
    };

    if (isValidTimestamp(block.start)) {
      row.start = block.start;
    }

    const current = currentTimestamp(block);
    if (current !== undefined) {
      row.current = current;
    }

    rows.push(row);
    speakerKeys.push(speakerKey);
    tailBlocks.push(block);
  }

  if (draft) {
    rows.push({ kind: "draft", text: draft });
  }

  return rows;
}
