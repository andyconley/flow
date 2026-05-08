# Accessibility and Internationalization Standard

This standard defines baseline expectations for inclusive and globally adaptable software.

## Accessibility baseline

User-facing surfaces should target a recognized accessibility standard such as WCAG 2.2 AA unless the project explicitly defines another target.

Common expectations:

- full keyboard access
- adequate contrast
- descriptive labels and errors
- non-color-only communication
- accessible focus and state handling

## Accessibility verification

Projects should combine:

- automated checks
- manual review
- assistive-technology testing for critical flows

Accessibility should be treated as a product requirement, not a final cosmetic pass.

## Internationalization baseline

Design for translation and locale handling early:

- externalize strings
- use locale-aware formatting
- avoid concatenated message fragments
- allow for string expansion and bidirectional layout where relevant

## Relevant standards and tools

Principles:

- WCAG 2.2 AA
- locale-aware formatting
- durable message catalogs

Common tools:

- axe-core
- Pa11y
- ICU Message Format
