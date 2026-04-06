APPROVALS_CONTEXT_TEMPLATE = """Approval requests ({count} of {total_count}, showing {offset_start}-{offset_end}{state_filter}):

{entries}

{pagination_hint}"""

APPROVALS_NO_RESULTS = "No approval requests found matching the specified filters."

APPROVALS_PAGINATION_MORE = "There are more results. To see the next page, call with offset={next_offset}."

APPROVALS_PAGINATION_END = "All matching results have been shown."
