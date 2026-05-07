# AI and ML Standard

This standard defines how machine learning and LLM-based features should be engineered with reproducibility and evaluation in mind.

## Reproducibility

At minimum, projects should be able to trace:

- model or prompt version
- dataset or example set version
- evaluation results
- code version

## Evaluation-first principle

AI features are not done without evaluation.

Projects should define:

- what “good enough” means
- what eval dataset or rubric is used
- what regressions fail the change

Where possible, evaluation should be automated and versioned alongside the system.

## Model and prompt documentation

Production-facing models or prompts should have durable documentation of:

- intended use
- limitations
- major failure modes
- version history

## Observability

Track AI/ML runtime signals such as:

- latency
- error rate
- cost or token usage
- evaluation drift where applicable

## Relevant standards and tools

Principles:

- MLOps maturity
- model cards
- prompt versioning
- evaluation gating

Common tools:

- MLflow / Weights & Biases
- DVC
- Langfuse / Promptflow
- OpenLLMetry
- KServe / ONNX
