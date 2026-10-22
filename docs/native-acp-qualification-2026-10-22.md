# Native ACP candidate qualification — 2026-10-22

The real bounded fixture completed as `reviewed-and-ready` on tested code commit `4f273e97e1ed89f17c05c3e03a795af797a50c10`, based on released v0.53.0. Human acceptance was not fabricated. No merge, release or activation was performed; the installed Studio remains v0.53.0.

| Boundary | Observed result |
|---|---|
| Real coordinator | `codex-acp`, requested model `gpt-5.6-sol`, existing native login; no mock coordinator |
| Local implementation | Bound Qwen `qwen3.8:27b-q4_K_M`, digest `25b843619e944cd0ae6069f94ff4e5e26a16e109ccbc0a66a0f05979ed70098e`; real shell, file write and knowledge search; completed in 208.3 s |
| Independent deterministic check | Exact frozen Python unittest command: 7 tests passed |
| Fresh native review | `claude-acp`, requested model `opus`, canonical private Flow Claude configuration; independently re-ran the 7 tests and additional edge probes; `approve` in 42.4 s |
| Final candidate | `501dac6f74af2bdcd85dbbd534bb660563f1ac6e52b28b78190f9624187265e1`, matching implementation, independent review and final workspace |
| Regression suite | 350 tests run, 5 skipped, passed after final code changes |

The fixture changes `normalize_tags` from sorted-set behavior to whitespace stripping, Unicode casefolding, blank removal and stable deduplication, with a new result list and TypeError for non-string elements. Only tags.py changed. Frozen test SHA256 stayed `1bd8db3268fc6004b676243466d2ad6d136e5117e9ef0e1c0fa1fd7da81ee7c6`.

Actual knowledge evidence: the Qwen worker and private Claude reviewer each made one successful `search_cards` call. Returned cards included the concrete-test-oracle and reversible-delivery guidance, and their reports explained its use in concrete success/failure probes and proportionate verification. The coordinator consumed and cited the worker report; it did not itself call search in this final run. This proves tool invocation, returned guidance and stated use, not counterfactual causality. Graph traversal was not exercised.

Native sandbox rule literals remain unchanged from v0.53.0. Delegation is an explicit frozen capability hosted by the existing Flow operator, not an expansion of the native client's sandbox or a general command API. The role/transport design is documented in native-acp-bound-delegation.md. No credentials were copied, no new sign-in was completed, and no global settings or production authored notes were changed. All owned role processes were quiescent afterward; the local model was unloaded.

Earlier failures are preserved: source-cwd authentication access, Claude HOME/keychain discovery, separate default-provider OAuth acquisition, missing native delegation/knowledge startup, incompatible worker CLI flags, multiline recipe serialization, and absent developer tools on the standalone role. The final pass follows those fixes; it is not represented as a first-attempt pass.

Remaining limitations: the default Goose `chatgpt_codex` OAuth-cache route remains separately unqualified. This is one small fixture on the Qwen profile, not a broad reliability benchmark or qualification of the fast GPT-OSS profile. Bound-role evidence is separate from legacy Summon counters; aggregate token/cost totals should not be assumed complete.

Local evidence directory: `task-3/installed-flow-qualification-20261022/`. `QUALIFIED-RESULT.json` indexes commands, frozen brief/tests, independent check, role receipts, raw native/worker events, knowledge responses, and preserved prior attempts. Live artifacts reside in the isolated candidate's `v2/artifacts/29797fa1e50729ee-integrated-native-qualification-4/`. Raw account and model data are not committed.
