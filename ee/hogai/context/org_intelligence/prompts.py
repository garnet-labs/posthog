# Approvals

APPROVALS_CONTEXT_TEMPLATE = """Approval requests ({count} of {total_count}, showing {offset_start}-{offset_end}{state_filter}):

{entries}

{pagination_hint}"""

APPROVALS_NO_RESULTS = "No approval requests found matching the specified filters."

APPROVALS_PAGINATION_MORE = "There are more results. To see the next page, call with offset={next_offset}."

APPROVALS_PAGINATION_END = "All matching results have been shown."

# Discussions

DISCUSSIONS_CONTEXT_TEMPLATE = """Discussion threads ({count} of {total_count}, showing {offset_start}-{offset_end}{scope_filter}):

{entries}

{pagination_hint}"""

DISCUSSIONS_NO_RESULTS = "No discussion threads found matching the specified filters."

DISCUSSIONS_PAGINATION_MORE = "There are more results. To see the next page, call with offset={next_offset}."

DISCUSSIONS_PAGINATION_END = "All matching results have been shown."

# Access control

ACCESS_CONTROL_CONTEXT_TEMPLATE = """Access control summary for project "{team_name}":

## Default Access Levels
{defaults}

## Restricted Resources
{restricted_resources}

{roles_section}{members_section}"""

ACCESS_CONTROL_NO_CUSTOM = "No custom access controls configured. All resources use organization defaults."

# Metalytics

METALYTICS_CONTEXT_TEMPLATE = """Resource usage metrics ({count} resources{scope_filter}, {date_range_desc}):

{entries}

{pagination_hint}"""

METALYTICS_NO_RESULTS = "No resource usage data found matching the specified filters."

METALYTICS_PAGINATION_MORE = "There are more results. To see the next page, call with offset={next_offset}."

METALYTICS_PAGINATION_END = "All matching results have been shown."

# Org members

ORG_MEMBERS_CONTEXT_TEMPLATE = """Organization members ({count} total):

{entries}"""

ORG_MEMBERS_NO_RESULTS = "No organization members found."

MEMBERSHIP_LEVEL_NAMES = {1: "member", 8: "admin", 15: "owner"}
