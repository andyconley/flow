"use strict";

const TRAILER_TOKEN = "Release-Note";
const MAX_BYTES = 240;
const TRAILER_LINE = /^([A-Za-z0-9-]+|BREAKING CHANGE):[ ]?(.*)$/;

function commitMessage(commit) {
  if (typeof commit.message === "string") {
    return commit.message;
  }
  return [commit.subject, commit.body, commit.footer]
    .filter((part) => typeof part === "string" && part.length > 0)
    .join("\n\n");
}

function finalParagraph(message) {
  const normalized = message.replace(/\r\n?/g, "\n").replace(/\n+$/u, "");
  if (!normalized) {
    return [];
  }
  const paragraphs = normalized.split(/\n[ \t]*\n/u);
  return paragraphs[paragraphs.length - 1].split("\n");
}

function releaseNoteFromCommit(commit, index) {
  const lines = finalParagraph(commitMessage(commit));
  if (!lines.length) {
    return null;
  }

  const identity = commit.hash ? `commit ${String(commit.hash).slice(0, 12)}` : `commit ${index + 1}`;
  const parsed = [];
  let currentToken = null;
  for (const line of lines) {
    const match = TRAILER_LINE.exec(line);
    if (match) {
      parsed.push(match);
      currentToken = match[1];
      continue;
    }
    if (/^[ \t]/u.test(line) && currentToken !== null) {
      if (currentToken === TRAILER_TOKEN) {
        throw new Error(`${identity} ${TRAILER_TOKEN} must be a single-line trailer`);
      }
      continue;
    }
    if (lines.some((candidate) => candidate.startsWith(`${TRAILER_TOKEN}:`))) {
      throw new Error(`${identity} ${TRAILER_TOKEN} must be a single-line trailer`);
    }
    return null;
  }

  const notes = parsed.filter((match) => match[1] === TRAILER_TOKEN);
  if (!notes.length) {
    return null;
  }

  if (notes.length > 1) {
    throw new Error(`${identity} has more than one ${TRAILER_TOKEN} trailer`);
  }

  const rawValue = notes[0][2];
  if (/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/u.test(rawValue)) {
    throw new Error(`${identity} ${TRAILER_TOKEN} contains a control character`);
  }
  const value = rawValue.trim();
  if (!value) {
    throw new Error(`${identity} has an empty ${TRAILER_TOKEN} trailer`);
  }
  if (value.startsWith("#")) {
    throw new Error(`${identity} ${TRAILER_TOKEN} must not start with a Markdown heading`);
  }
  if (value.includes("<!--") || value.includes("-->")) {
    throw new Error(`${identity} ${TRAILER_TOKEN} must not contain an HTML comment delimiter`);
  }
  if (/[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/u.test(value)) {
    throw new Error(`${identity} ${TRAILER_TOKEN} contains bidirectional formatting`);
  }
  const bytes = Buffer.byteLength(value, "utf8");
  if (bytes > MAX_BYTES) {
    throw new Error(`${identity} ${TRAILER_TOKEN} is ${bytes} UTF-8 bytes; maximum is ${MAX_BYTES}`);
  }
  return value;
}

function renderHighlights(commits = []) {
  const notes = commits
    .map((commit, index) => releaseNoteFromCommit(commit, index))
    .filter((note) => note !== null);
  if (!notes.length) {
    return "";
  }
  return `### Highlights\n\n${notes.map((note) => `- ${note}`).join("\n")}\n`;
}

async function generateNotes(_pluginConfig, context) {
  return renderHighlights(context.commits || []);
}

module.exports = {
  generateNotes,
  renderHighlights,
  releaseNoteFromCommit,
};
