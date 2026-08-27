#
# Every injected line ends with this marker followed by the name of the
# payload that produced it:
#
#     ScopeTrace trace(__FILE__, __LINE__, __FUNCTION__);  // @tj:scope_trace
#
# Removal matches on the marker, never on the payload's own text, so it does
# not need to know what any payload looks like. That is what makes payloads
# configurable without a matching change to the remover.
#
MARKER_PREFIX = "// @tj:"

#
# Name of the built-in payload, defined in payloads.py. Configurable payloads
# keep their own names.
#
SCOPE_TRACE = "scope_trace"

#
# Traces injected before markers existed: a multi-line block with no marker
# on it. Removal still recognises these, so upgrading the tool does not
# orphan traces already sitting in a tree.
#
LEGACY_TRACE_PATTERN = "ScopeTrace trace("
