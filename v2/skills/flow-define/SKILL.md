---
name: flow-define
description: Ask Goose/LangGraph to coordinate define; retain human decisions and approvals.
---

<!-- Managed by Flow v2.0 -->

Flow uses Goose/LangGraph for every stage's coordination and specialist dispatch. The native host is the conversational interface and approval surface. Use `FLOW_V2 --project PROJECT --work ID` as the command prefix. Read context/status and discuss the user's goal, constraints and decisions. Do not research, synthesize the stage, delegate specialists, or write the plan in the native host.

Propose the stage assignment with `assign --stage define --question QUESTION`. The coordinator must research evidence, needs, constraints, uncertainties and testable outcomes. Show the exact assignment revision and bounded budget to the user. Only after the user authorizes that assignment, invoke `run-stage --stage define --revision REVISION --actor ACTOR`. This enters the persisted LangGraph stage node; Goose coordinates `business-analyst` and other configured roles and returns the controlled stage artifact. Assignment alone starts no inference. Do not call native delegation or substitute host-written analysis when Goose is blocked.

Inspect status and present the recorded stage result, evidence, uncertainties and questions conversationally. An actual human stage decision is recorded with `approve-stage --stage define --revision RESULT_REVISION --actor ACTOR --reason REASON`; it does not approve implementation. A Goose-proposed brief must still receive exact-revision human approval through `approve --revision REVISION --actor ACTOR`. Never manufacture approval actors or decisions. Permission, authentication, uncertain effects and scope pauses go back to the user without silent retries. Other stage transitions remain under the same Goose/LangGraph owner.
