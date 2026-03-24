# Team Scoping

Automatic team scoping for Django models to prevent IDOR vulnerabilities. Instead of relying on developers to always include `team_id` filters, models use scoped managers that auto-filter by the current team from request context.

Related: [#47065](https://github.com/PostHog/posthog/issues/47065)

## How it works

Middleware sets team_id in a ContextVar on every request. Managers read it and auto-filter.

```python
# request context — automatic
Repo.objects.all()                    # filtered to current team

# explicit cross-team
Repo.objects.unscoped().all()         # no filtering

# background jobs
with team_scope(team_id):
    Repo.objects.all()                # filtered to team_id

# celery tasks
@shared_task
@with_team_scope()
def my_task(team_id: int): ...        # context set from param
```

## Which manager to use

| Situation                  | Manager                                | Why                                                 |
| -------------------------- | -------------------------------------- | --------------------------------------------------- |
| New product on separate DB | `ProductTeamModel` (abstract base)     | No FK to Team, plain `team_id` field, no JOINs      |
| Migrating existing model   | `BackwardsCompatibleTeamScopedManager` | Keeps `filter(team_id=X)` working during transition |
| Fully migrated model       | `TeamScopedManager`                    | Strict — only context-based scoping                 |

## ProductTeamModel (for multi-DB products)

```python
from posthog.models.scoping.product_mixin import ProductTeamModel

class Repo(ProductTeamModel):
    repo_name = models.CharField(max_length=255)
    # team_id inherited — BigIntegerField, no FK
```

Auto-scoped queries, `.unscoped()` escape hatch, `.for_team(id)` for explicit scoping.
