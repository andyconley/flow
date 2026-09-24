# Validation plan

- Reproduce Flow envelope denials and verify no denied action reaches a provider.
- Verify each worker response is linked to the actual Flow definition digest, charter digest, provider identity, and bounded input; mark unavailable providers failed.
- Verify MAF starts three authorized participants, records result/order and checkpoint, and resumes in a separate process without duplicate dispatch.
- Inspect a disposable Git baseline, changed paths, check results, and final commit independently of MAF output.
- Audit incremental cost evidence and CLI caps against the $10 limit; stop when accounting is unknown.
- Review the six architecture criteria and the avoided/added machinery estimate with unsupported claims labeled unverified.
