from products.workflows.backend.models.hog_flow_schedule import HogFlowSchedule


def resolve_variables(hog_flow, schedule: HogFlowSchedule) -> dict:
    """Build default variables from HogFlow schema, then merge schedule overrides."""
    defaults = {}
    for var in hog_flow.variables or []:
        defaults[var.get("key")] = var.get("default")
    defaults.update(schedule.variables or {})
    return defaults
