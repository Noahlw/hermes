"""hermes-agent plugin entry point for the persona contract gate.

This package is a thin adapter that connects hermes-agent's
``pre_gateway_dispatch`` hook to this repo's persona policy layer. It
is shipped as a separate module so its hermes-agent-specific code
lives next to the policy it wraps, but stays out of the policy module
itself (which must remain hermes-agent-agnostic).

External (SSH-gated) deployment steps to wire this plugin to a live
hermes-agent are tracked in the parent issue; the source in this
package is fully testable in this repo with no hermes-agent
dependency.
"""
