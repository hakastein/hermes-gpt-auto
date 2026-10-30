# GPT Auto Context for Hermes

Select a normal model such as `gpt-6.1-sol` under **OpenAI Codex**. Hermes uses
its account-specific `max_context_window` instead of the smaller advertised
`context_window`. There is no hardcoded token ceiling or list of future GPTs.

- Refreshes its profile-scoped catalog cache on demand after one hour. New
  sessions, model switches and context lookups follow increases and decreases.
- Leaves Hermes's native model list and UI untouched. Select the ordinary model
  ID; the legacy `-900k` choices may still appear, but are no longer needed.
- On a catalog outage, remembers the last successful window in this profile.
  A first-use outage keeps Hermes's normal fallback.
- When a successful catalog omits `max_context_window`, uses its advertised
  `context_window` rather than inventing a larger number.
- Explicit user context pins still take precedence. Do not add a fixed
  `model.context_length` if you want automatic updates.

## Scope

Designed for one active account on the official ChatGPT/Codex OAuth route per
profile. Proxies and account switching are explicitly outside this plugin's
scope; clear its plugin-data cache if the account changes. Other providers are
unchanged. Authentication and expired-token refresh go through Hermes's own
credentialed request broker, not a separate login implementation.

No model requests, quota probes, image settings, direct auth-file access,
dependencies, background services, or changes
to compression configuration. The reported limit comes from OpenAI's catalog;
it is not an experimentally measured hard server limit.

Already running chats keep the window assigned at creation/model switch; the
plugin does not mutate live compressor state or conversation history. Normal
compression and auxiliary-model feasibility checks remain Hermes's job.

## Installation

Copy this directory to `$HERMES_HOME/plugins/gpt-auto`. This is a native
`kind: model-provider` plugin: Hermes discovers it automatically and uses the
supported `ProviderProfile.get_model_context_length()` extension for the existing
`openai-codex` provider. It keeps the bundled profile's auth and transport fields.
There is no additional provider to choose or model list to maintain.

Validate before installation with `hermes plugins validate <path>` and
`hermes plugins doctor <path> --ci`. Only authenticated catalog GETs are made.

`hermes plugins disable gpt-auto` makes context discovery return to the native
policy. No model overrides or fixed windows are written to config.
Plugin-owned last-known window values live in Hermes's `plugin-data` directory;
only catalog model IDs, integer window sizes and cache timestamps are stored, never credentials.

## Compatibility and testing

Uses documented provider registration and context discovery, not monkey-patches.
A few Hermes helpers supply catalog compatibility URLs and atomic plugin state; their compatibility should be rechecked after updates.
Profile-scoped provider discovery and cache storage keep installations separate.

Run the dependency-free behavioral suite with the Hermes runtime interpreter
and the Hermes source on `PYTHONPATH`:

```sh
python -m unittest discover -s tests -v
```

Tests isolate Hermes home and network; live catalog checks are separate.
