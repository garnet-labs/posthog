from posthog.models.action import Action
from posthog.models.team import Team


def get_action(action_id: int, team: Team) -> Action:
    """Look up an action by ID within a project, raising a clear ValidationError if not found.

    Uses team__project_id to find actions across all environments within the same project.
    """
    from rest_framework.exceptions import ValidationError

    try:
        return Action.objects.get(pk=action_id, team__project_id=team.project_id)
    except Action.DoesNotExist:
        raise ValidationError(f"Action ID {action_id} does not exist!")


def get_action_name(action_id: int, team: Team) -> str:
    """Look up an action's name by ID, returning a fallback name if not found."""
    try:
        action = Action.objects.get(pk=action_id, team__project_id=team.project_id)
        return action.name or "Unnamed action"
    except Action.DoesNotExist:
        return f"Unknown action ({action_id})"
