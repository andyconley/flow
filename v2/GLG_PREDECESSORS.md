# Linking successor work

Create a separately approved successor from a closed native work item using its
exact current closure revision from `status`:

```sh
flow --project /path/to/project --work new-work create \
  --request 'Define the new scope' \
  --predecessor-work prior-work \
  --predecessor-revision EXACT_CLOSURE_REVISION
```

Both predecessor options are required together. The predecessor must have a closed,
quiescent native checkpoint and an intact closure matching both its checkpoint
and current artifact revision. Flow holds its existing operator lock while creating
the successor. Active execution, pending decisions, wrong revisions, tampering,
missing state, and self-links are rejected. This operation never creates or updates
the predecessor checkpoint, artifacts, or lock file contents.

The successor's context records a dedicated `predecessor_work` relationship with
`work_id`, `closure_ref`, and `approval_imported: false`. Artifact `supersedes`
continues to mean a revision of the same record within one work item. The new work
requires its own brief and explicit approval; prior approval grants no authority.

The link is historical evidence of the predecessor's closed state at creation.
It does not permanently disable later predecessor recovery or authorize overlapping
delivery. Inspect current status before authorizing any future work.
