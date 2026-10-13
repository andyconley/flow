# Delivery Lead planning coordination

After explicit solution approval, the active host assistant assumes Delivery
Lead coordination and initiates planning. Planning may also start directly
from an approved definition when the optional solution stage is skipped.
When both inputs are retained, the approved solution takes precedence.
The host coordinates technical specialists
and validation, reconciles evidence into the plan, handoff and validation plan,
and presents those outputs for explicit user approval before implementation.
The lead-developer remains the default technical specialist for planning.

This is an instruction contract in command templates and the shared stage
prompt used by OpenHands execution and native handoffs. The specialist prompt
asks for technical planning outputs returned to the host; ownership instructions
live in the host-facing command and native handoff guidance. The planning
handoff references the specialist role file for separate delegation rather
than embedding its persona directives into the host prompt. Approval records the
lifecycle transition; it does not launch a conversation. The active host starts
planning or explicitly hands it to another native session. OpenHands continues
to own execution, delegation, retries and conversation persistence. No MAF
contracts or additional execution controller are introduced.

Generated skills receive the command template through ordinary Flow sync.
Existing project or user overrides retain precedence and should be reviewed
when they intentionally override these instructions.
