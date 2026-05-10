type ScrollableTranscriptSurface = {
  scrollHeight: number;
  scrollTop: number;
};

export function scrollVoiceNoteTranscriptToLatest(surface: ScrollableTranscriptSurface | null | undefined) {
  if (!surface) {
    return;
  }

  surface.scrollTop = surface.scrollHeight;
}
