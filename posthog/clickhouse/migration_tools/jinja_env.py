from __future__ import annotations

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

# Sandbox: no attribute access or method calls in templates.
_ENV = SandboxedEnvironment(
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)


def render_sql(template_str: str, variables: dict[str, str]) -> str:
    # Migration SQL should only use {{ variable }} substitution.
    # Block tags allow loops/conditionals which bypass the schema graph safety model.
    if "{%" in template_str:
        raise ValueError(
            "Jinja2 block tags ({% ... %}) are not allowed in migration SQL. "
            "Use {{ variable }} substitution only, or use a template in manifest.yaml."
        )
    template = _ENV.from_string(template_str)
    return template.render(variables)
