from typing import Literal, Union

from pydantic import BaseModel, Field

from posthog.models import Team

from ee.hogai.chat_agent.query_planner.toolkit import TaxonomyAgentToolkit
from ee.hogai.utils.helpers import format_events_yaml


class ReadEvents(BaseModel):
    """Returns the list of available events. Events are sorted by their popularity where the most popular events are at the top."""

    kind: Literal["events"] = "events"
    limit: int = Field(default=500, ge=1, le=500, description="Number of events to return per page.")
    offset: int = Field(default=0, ge=0, description="Number of events to skip for pagination.")


class ReadEventProperties(BaseModel):
    """Returns the properties list for a provided event. Before calling this tool, ensure the event exists by reading events."""

    kind: Literal["event_properties"] = "event_properties"
    event_name: str = Field(description="The name of the event that you want to retrieve properties for.")


class ReadEntityProperties(BaseModel):
    """Returns the properties list for a provided entity."""

    kind: Literal["entity_properties"] = "entity_properties"
    entity: str = Field(description="The type of the entity that you want to retrieve properties for.")
    # Keep entity as string to allow for dynamic entity types.


class ReadActionProperties(BaseModel):
    """Returns the properties list for a provided action. Before calling this tool, ensure the action exists by searching actions or if it was provided in the context."""

    kind: Literal["action_properties"] = "action_properties"
    action_id: int


class ReadEntitySamplePropertyValues(BaseModel):
    """For a provided entity and a property, returns a list of maximum 25 sample values that the combination has."""

    kind: Literal["entity_property_values"] = "entity_property_values"
    entity: str = Field(description="The type of the entity that you want to retrieve properties for.")
    # Keep entity as string to allow for dynamic entity types.
    property_name: str = Field(description="Verified property name of an entity.")


class ReadEventSamplePropertyValues(BaseModel):
    """For a provided event and a property, returns a list of maximum 25 sample values that the combination has."""

    kind: Literal["event_property_values"] = "event_property_values"
    event_name: str = Field(description="Verified event name")
    property_name: str = Field(description="Verified property name of an event.")


class ReadActionSamplePropertyValues(BaseModel):
    """For a provided event and a property, returns a list of maximum 25 sample values that the combination has."""

    kind: Literal["action_property_values"] = "action_property_values"
    action_id: int = Field(description="Verified action ID")
    property_name: str = Field(description="Verified property name of an action.")


ReadTaxonomyQuery = Union[
    ReadEvents,
    ReadEventProperties,
    ReadEventSamplePropertyValues,
    ReadEntityProperties,
    ReadEntitySamplePropertyValues,
    ReadActionProperties,
    ReadActionSamplePropertyValues,
]


class ReadTaxonomyToolArgs(BaseModel):
    query: ReadTaxonomyQuery = Field(..., discriminator="kind")


def _is_excluded_ai_property(event_name: str, property_name: str) -> bool:
    """Check if a property is excluded from scanning for the given AI event."""
    from posthog.hogql_queries.ai.event_taxonomy_query_runner import AI_LARGE_PROPERTIES_BY_EVENT

    return property_name in AI_LARGE_PROPERTIES_BY_EVENT.get(event_name, ())


def execute_taxonomy_query(query: ReadTaxonomyQuery, toolkit: TaxonomyAgentToolkit, team: Team) -> str:
    """
    Execute a taxonomy query and return the result.

    This is the shared execution logic used by both internal and external tools.
    """
    match query:
        case ReadEvents():
            return format_events_yaml([], team, limit=query.limit, offset=query.offset)
        case ReadEventProperties():
            return toolkit.retrieve_event_or_action_properties(query.event_name)
        case ReadEventSamplePropertyValues():
            if _is_excluded_ai_property(query.event_name, query.property_name):
                return (
                    f"Sample values for {query.property_name} are not available because values are typically too large "
                    f"to display. This property contains raw AI model input/output data."
                )
            return toolkit.retrieve_event_or_action_property_values(query.event_name, query.property_name)
        case ReadActionProperties():
            return toolkit.retrieve_event_or_action_properties(query.action_id)
        case ReadActionSamplePropertyValues():
            return toolkit.retrieve_event_or_action_property_values(query.action_id, query.property_name)
        case ReadEntityProperties():
            return toolkit.retrieve_entity_properties(query.entity)
        case ReadEntitySamplePropertyValues():
            return toolkit.retrieve_entity_property_values(query.entity, query.property_name)
        case _:
            raise ValueError(f"Invalid query type: The query structure '{type(query).__name__}' is not recognized.")
