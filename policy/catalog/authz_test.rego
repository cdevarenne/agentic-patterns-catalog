package catalog.authz_test

import data.catalog.authz
import rego.v1

access := {"a@x.com": "curator", "b@y.com": "reader"}

test_local_is_curator if {
	authz.decision.allow with input as {"subject": "stdio-local", "tool": "put_pattern", "args": {}}
}

test_reader_reads if {
	authz.decision.allow with input as {"subject": "b@y.com", "tool": "select", "args": {}}
		with data.catalog.access as access
}

test_reader_cannot_put if {
	d := authz.decision with input as {"subject": "b@y.com", "tool": "put_pattern", "args": {}}
		with data.catalog.access as access
	not d.allow
	d.role == "reader"
}

test_unknown_subject_denied if {
	d := authz.decision with input as {"subject": "x@x.com", "tool": "select", "args": {}}
		with data.catalog.access as access
	not d.allow
	d.role == null
}

test_unknown_tool_denied if {
	d := authz.decision with input as {"subject": "a@x.com", "tool": "drop_everything", "args": {}}
		with data.catalog.access as access
	not d.allow
}
