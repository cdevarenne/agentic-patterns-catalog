# The same role table as policy.py TOOLS_BY_ROLE. tests/test_policy.py asserts the two agree.
package catalog.authz

import rego.v1

local_subject := "stdio-local"

read_tools := {"list_categories", "search_patterns", "get_pattern", "get_example", "select"}

tools_by_role := {
	"reader": read_tools,
	"curator": (read_tools | {"put_pattern"}),
}

role := "curator" if input.subject == local_subject

role := data.catalog.access[input.subject] if input.subject != local_subject

default decision := {"allow": false, "reason": "subject is not in the allowlist", "role": null}

decision := {"allow": true, "reason": sprintf("role %q may call %q", [role, input.tool]), "role": role} if {
	input.tool in tools_by_role[role]
}

decision := {"allow": false, "reason": sprintf("role %q may not call %q", [role, input.tool]), "role": role} if {
	role
	not input.tool in tools_by_role[role]
}
