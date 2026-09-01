/* Preview and publication share this release policy. Preview stays read-only. */
const mode = process.env.FLOW_RELEASE_MODE;
const repositoryUrl = process.env.FLOW_RELEASE_REPOSITORY_URL;

if (mode !== "preview" && mode !== "publish") {
  throw new Error("FLOW_RELEASE_MODE must be set explicitly to 'preview' or 'publish'");
}

if (repositoryUrl && !/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\.git$/.test(repositoryUrl)) {
  throw new Error("FLOW_RELEASE_REPOSITORY_URL must be a canonical GitHub HTTPS clone URL");
}

const analyzer = [
  "@semantic-release/commit-analyzer",
  {
    preset: "conventionalcommits",
    releaseRules: [
      // Pre-1.0: a breaking change bumps the minor, not the major.
      // Remove this rule when 1.0 is deliberately released.
      { breaking: true, release: "minor" },
      { type: "docs", scope: "framework", release: "minor" },
      { type: "docs", scope: "commands", release: "minor" },
      { type: "docs", scope: "agents", release: "minor" },
      { type: "docs", scope: "standards", release: "minor" },
      { type: "docs", release: "patch" },
      { type: "chore", scope: "release", release: false }
    ]
  }
];

const notes = [
  "@semantic-release/release-notes-generator",
  {
    preset: "conventionalcommits",
    presetConfig: {
      types: [
        { type: "feat", section: "Features", hidden: false },
        { type: "fix", section: "Bug Fixes", hidden: false },
        { type: "docs", section: "Documentation", hidden: false },
        { type: "perf", section: "Performance", hidden: false },
        { type: "refactor", section: "Code Refactoring", hidden: false },
        { type: "test", section: "Tests", hidden: false },
        { type: "build", section: "Build System", hidden: false },
        { type: "ci", section: "Continuous Integration", hidden: false },
        { type: "chore", section: "Maintenance", hidden: false }
      ]
    }
  }
];

const mutatingPlugins = [
  [
    "@semantic-release/changelog",
    {
      changelogFile: "CHANGELOG.md",
      changelogTitle: "# Changelog\n\nAll notable changes to flow are generated from Conventional Commits. Longer design context belongs in the documentation changed by the release."
    }
  ],
  [
    "@semantic-release/git",
    {
      assets: ["CHANGELOG.md"],
      message: "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}"
    }
  ],
  "@semantic-release/github"
];

module.exports = {
  branches: ["main"],
  tagFormat: "v${version}",
  ...(repositoryUrl ? { repositoryUrl } : {}),
  plugins: [analyzer, notes, ...(mode === "publish" ? mutatingPlugins : [])]
};
