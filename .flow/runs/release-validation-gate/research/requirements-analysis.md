# Requirements Analysis

The release gate serves maintainers, release consumers, and support owners. The key hidden requirements are exact-SHA/version binding, absence of write credentials before publication, candidate installation through real release paths, durable failure evidence, and an honest distinction between pre-publication prevention and post-publication repair.

A release-producing commit must run the deterministic suite before any remote write. A non-release commit must be a cheap successful no-op. Post-publication and live-client checks must never be promoted into claims that publication was prevented.

