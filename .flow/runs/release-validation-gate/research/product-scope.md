# Product Scope Analysis

The minimum useful slice is one release workflow that analyzes, gates, publishes, and verifies. It includes structured evidence and focused workflow tests. Public-tag installation and upgrade remain post-publication confirmations. Live client routing and capability verification are a separate follow-up.

The gate is intentionally bypass-free. Flaky checks block release until stabilized. Versioning-rule changes, unrelated PR checks, release deletion, and history rewriting are excluded.
