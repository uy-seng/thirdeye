import liveSummaryDefaultPrompt from "../../../prompts/live_summary_default.txt?raw";
import voiceNoteSummaryDefaultPrompt from "../../../prompts/voice_note_summary_default.txt?raw";

function promptText(content: string) {
  return content.trim();
}

export function getDefaultLiveSummaryPrompt() {
  return promptText(liveSummaryDefaultPrompt);
}

export function getDefaultVoiceNoteSummaryPrompt() {
  return promptText(voiceNoteSummaryDefaultPrompt);
}
