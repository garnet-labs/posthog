/**
 * Auto-generated from the Django backend OpenAPI schema.
 * MCP service uses these Zod schemas for generated tool handlers.
 * To regenerate: hogli build:openapi
 *
 * PostHog API - MCP 7 enabled ops
 * OpenAPI spec version: 1.0.0
 */
import * as zod from 'zod'

export const SurveysListParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const SurveysListQueryParams = /* @__PURE__ */ zod.object({
    limit: zod.number().optional().describe('Number of results to return per page.'),
    offset: zod.number().optional().describe('The initial index from which to return the results.'),
    search: zod.string().optional().describe('A search term.'),
})

export const SurveysCreateParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const surveysCreateBodyNameMax = 400

export const surveysCreateBodyResponsesLimitMin = 0
export const surveysCreateBodyResponsesLimitMax = 2147483647

export const surveysCreateBodyIterationCountMin = 0
export const surveysCreateBodyIterationCountMax = 500

export const surveysCreateBodyIterationFrequencyDaysMin = 0
export const surveysCreateBodyIterationFrequencyDaysMax = 2147483647

export const surveysCreateBodyCurrentIterationMin = 0
export const surveysCreateBodyCurrentIterationMax = 2147483647

export const surveysCreateBodyResponseSamplingIntervalMin = 0
export const surveysCreateBodyResponseSamplingIntervalMax = 2147483647

export const surveysCreateBodyResponseSamplingLimitMin = 0
export const surveysCreateBodyResponseSamplingLimitMax = 2147483647

export const SurveysCreateBody = /* @__PURE__ */ zod.object({
    name: zod.string().max(surveysCreateBodyNameMax),
    description: zod.string().optional(),
    type: zod
        .enum(['popover', 'widget', 'external_survey', 'api'])
        .describe('* `popover` - popover\n* `widget` - widget\n* `external_survey` - external survey\n* `api` - api'),
    schedule: zod.string().nullish(),
    linked_flag_id: zod.number().nullish(),
    linked_insight_id: zod.number().nullish(),
    targeting_flag_id: zod.number().optional(),
    targeting_flag_filters: zod.unknown().nullish(),
    remove_targeting_flag: zod.boolean().nullish(),
    questions: zod
        .unknown()
        .nullish()
        .describe(
            '\n        The `array` of questions included in the survey. Each question must conform to one of the defined question types: Basic, Link, Rating, or Multiple Choice.\n\n        Basic (open-ended question)\n        - `id`: The question ID\n        - `type`: `open`\n        - `question`: The text of the question.\n        - `description`: Optional description of the question.\n        - `descriptionContentType`: Content type of the description (`html` or `text`).\n        - `optional`: Whether the question is optional (`boolean`).\n        - `buttonText`: Text displayed on the submit button.\n        - `branching`: Branching logic for the question. See branching types below for details.\n\n        Link (a question with a link)\n        - `id`: The question ID\n        - `type`: `link`\n        - `question`: The text of the question.\n        - `description`: Optional description of the question.\n        - `descriptionContentType`: Content type of the description (`html` or `text`).\n        - `optional`: Whether the question is optional (`boolean`).\n        - `buttonText`: Text displayed on the submit button.\n        - `link`: The URL associated with the question.\n        - `branching`: Branching logic for the question. See branching types below for details.\n\n        Rating (a question with a rating scale)\n        - `id`: The question ID\n        - `type`: `rating`\n        - `question`: The text of the question.\n        - `description`: Optional description of the question.\n        - `descriptionContentType`: Content type of the description (`html` or `text`).\n        - `optional`: Whether the question is optional (`boolean`).\n        - `buttonText`: Text displayed on the submit button.\n        - `display`: Display style of the rating (`number` or `emoji`).\n        - `scale`: The scale of the rating (`number`).\n        - `lowerBoundLabel`: Label for the lower bound of the scale.\n        - `upperBoundLabel`: Label for the upper bound of the scale.\n        - `isNpsQuestion`: Whether the question is an NPS rating.\n        - `branching`: Branching logic for the question. See branching types below for details.\n\n        Multiple choice\n        - `id`: The question ID\n        - `type`: `single_choice` or `multiple_choice`\n        - `question`: The text of the question.\n        - `description`: Optional description of the question.\n        - `descriptionContentType`: Content type of the description (`html` or `text`).\n        - `optional`: Whether the question is optional (`boolean`).\n        - `buttonText`: Text displayed on the submit button.\n        - `choices`: An array of choices for the question.\n        - `shuffleOptions`: Whether to shuffle the order of the choices (`boolean`).\n        - `hasOpenChoice`: Whether the question allows an open-ended response (`boolean`).\n        - `branching`: Branching logic for the question. See branching types below for details.\n\n        Branching logic can be one of the following types:\n\n        Next question: Proceeds to the next question\n        ```json\n        {\n            "type": "next_question"\n        }\n        ```\n\n        End: Ends the survey, optionally displaying a confirmation message.\n        ```json\n        {\n            "type": "end"\n        }\n        ```\n\n        Response-based: Branches based on the response values. Available for the `rating` and `single_choice` question types.\n        ```json\n        {\n            "type": "response_based",\n            "responseValues": {\n                "responseKey": "value"\n            }\n        }\n        ```\n\n        Specific question: Proceeds to a specific question by index.\n        ```json\n        {\n            "type": "specific_question",\n            "index": 2\n        }\n        ```\n        '
        ),
    conditions: zod.unknown().nullish(),
    appearance: zod.unknown().nullish(),
    start_date: zod.iso.datetime({}).nullish(),
    end_date: zod.iso.datetime({}).nullish(),
    archived: zod.boolean().optional(),
    responses_limit: zod
        .number()
        .min(surveysCreateBodyResponsesLimitMin)
        .max(surveysCreateBodyResponsesLimitMax)
        .nullish(),
    iteration_count: zod
        .number()
        .min(surveysCreateBodyIterationCountMin)
        .max(surveysCreateBodyIterationCountMax)
        .nullish(),
    iteration_frequency_days: zod
        .number()
        .min(surveysCreateBodyIterationFrequencyDaysMin)
        .max(surveysCreateBodyIterationFrequencyDaysMax)
        .nullish(),
    iteration_start_dates: zod.array(zod.iso.datetime({}).nullable()).nullish(),
    current_iteration: zod
        .number()
        .min(surveysCreateBodyCurrentIterationMin)
        .max(surveysCreateBodyCurrentIterationMax)
        .nullish(),
    current_iteration_start_date: zod.iso.datetime({}).nullish(),
    response_sampling_start_date: zod.iso.datetime({}).nullish(),
    response_sampling_interval_type: zod
        .union([
            zod.enum(['day', 'week', 'month']).describe('* `day` - day\n* `week` - week\n* `month` - month'),
            zod.enum(['']),
            zod.literal(null),
        ])
        .nullish(),
    response_sampling_interval: zod
        .number()
        .min(surveysCreateBodyResponseSamplingIntervalMin)
        .max(surveysCreateBodyResponseSamplingIntervalMax)
        .nullish(),
    response_sampling_limit: zod
        .number()
        .min(surveysCreateBodyResponseSamplingLimitMin)
        .max(surveysCreateBodyResponseSamplingLimitMax)
        .nullish(),
    response_sampling_daily_limits: zod.unknown().nullish(),
    enable_partial_responses: zod.boolean().nullish(),
    enable_iframe_embedding: zod.boolean().nullish(),
    _create_in_folder: zod.string().optional(),
})

export const SurveysRetrieveParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this survey.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const SurveysPartialUpdateParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this survey.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

export const surveysPartialUpdateBodyNameMax = 400

export const surveysPartialUpdateBodyResponsesLimitMin = 0
export const surveysPartialUpdateBodyResponsesLimitMax = 2147483647

export const surveysPartialUpdateBodyIterationCountMin = 0
export const surveysPartialUpdateBodyIterationCountMax = 500

export const surveysPartialUpdateBodyIterationFrequencyDaysMin = 0
export const surveysPartialUpdateBodyIterationFrequencyDaysMax = 2147483647

export const surveysPartialUpdateBodyCurrentIterationMin = 0
export const surveysPartialUpdateBodyCurrentIterationMax = 2147483647

export const surveysPartialUpdateBodyResponseSamplingIntervalMin = 0
export const surveysPartialUpdateBodyResponseSamplingIntervalMax = 2147483647

export const surveysPartialUpdateBodyResponseSamplingLimitMin = 0
export const surveysPartialUpdateBodyResponseSamplingLimitMax = 2147483647

export const SurveysPartialUpdateBody = /* @__PURE__ */ zod.object({
    name: zod.string().max(surveysPartialUpdateBodyNameMax).optional(),
    description: zod.string().optional(),
    type: zod
        .enum(['popover', 'widget', 'external_survey', 'api'])
        .optional()
        .describe('* `popover` - popover\n* `widget` - widget\n* `external_survey` - external survey\n* `api` - api'),
    schedule: zod.string().nullish(),
    linked_flag_id: zod.number().nullish(),
    linked_insight_id: zod.number().nullish(),
    targeting_flag_id: zod.number().optional(),
    targeting_flag_filters: zod.unknown().nullish(),
    remove_targeting_flag: zod.boolean().nullish(),
    questions: zod
        .unknown()
        .nullish()
        .describe(
            '\n        The `array` of questions included in the survey. Each question must conform to one of the defined question types: Basic, Link, Rating, or Multiple Choice.\n\n        Basic (open-ended question)\n        - `id`: The question ID\n        - `type`: `open`\n        - `question`: The text of the question.\n        - `description`: Optional description of the question.\n        - `descriptionContentType`: Content type of the description (`html` or `text`).\n        - `optional`: Whether the question is optional (`boolean`).\n        - `buttonText`: Text displayed on the submit button.\n        - `branching`: Branching logic for the question. See branching types below for details.\n\n        Link (a question with a link)\n        - `id`: The question ID\n        - `type`: `link`\n        - `question`: The text of the question.\n        - `description`: Optional description of the question.\n        - `descriptionContentType`: Content type of the description (`html` or `text`).\n        - `optional`: Whether the question is optional (`boolean`).\n        - `buttonText`: Text displayed on the submit button.\n        - `link`: The URL associated with the question.\n        - `branching`: Branching logic for the question. See branching types below for details.\n\n        Rating (a question with a rating scale)\n        - `id`: The question ID\n        - `type`: `rating`\n        - `question`: The text of the question.\n        - `description`: Optional description of the question.\n        - `descriptionContentType`: Content type of the description (`html` or `text`).\n        - `optional`: Whether the question is optional (`boolean`).\n        - `buttonText`: Text displayed on the submit button.\n        - `display`: Display style of the rating (`number` or `emoji`).\n        - `scale`: The scale of the rating (`number`).\n        - `lowerBoundLabel`: Label for the lower bound of the scale.\n        - `upperBoundLabel`: Label for the upper bound of the scale.\n        - `isNpsQuestion`: Whether the question is an NPS rating.\n        - `branching`: Branching logic for the question. See branching types below for details.\n\n        Multiple choice\n        - `id`: The question ID\n        - `type`: `single_choice` or `multiple_choice`\n        - `question`: The text of the question.\n        - `description`: Optional description of the question.\n        - `descriptionContentType`: Content type of the description (`html` or `text`).\n        - `optional`: Whether the question is optional (`boolean`).\n        - `buttonText`: Text displayed on the submit button.\n        - `choices`: An array of choices for the question.\n        - `shuffleOptions`: Whether to shuffle the order of the choices (`boolean`).\n        - `hasOpenChoice`: Whether the question allows an open-ended response (`boolean`).\n        - `branching`: Branching logic for the question. See branching types below for details.\n\n        Branching logic can be one of the following types:\n\n        Next question: Proceeds to the next question\n        ```json\n        {\n            "type": "next_question"\n        }\n        ```\n\n        End: Ends the survey, optionally displaying a confirmation message.\n        ```json\n        {\n            "type": "end"\n        }\n        ```\n\n        Response-based: Branches based on the response values. Available for the `rating` and `single_choice` question types.\n        ```json\n        {\n            "type": "response_based",\n            "responseValues": {\n                "responseKey": "value"\n            }\n        }\n        ```\n\n        Specific question: Proceeds to a specific question by index.\n        ```json\n        {\n            "type": "specific_question",\n            "index": 2\n        }\n        ```\n        '
        ),
    conditions: zod.unknown().nullish(),
    appearance: zod.unknown().nullish(),
    start_date: zod.iso.datetime({}).nullish(),
    end_date: zod.iso.datetime({}).nullish(),
    archived: zod.boolean().optional(),
    responses_limit: zod
        .number()
        .min(surveysPartialUpdateBodyResponsesLimitMin)
        .max(surveysPartialUpdateBodyResponsesLimitMax)
        .nullish(),
    iteration_count: zod
        .number()
        .min(surveysPartialUpdateBodyIterationCountMin)
        .max(surveysPartialUpdateBodyIterationCountMax)
        .nullish(),
    iteration_frequency_days: zod
        .number()
        .min(surveysPartialUpdateBodyIterationFrequencyDaysMin)
        .max(surveysPartialUpdateBodyIterationFrequencyDaysMax)
        .nullish(),
    iteration_start_dates: zod.array(zod.iso.datetime({}).nullable()).nullish(),
    current_iteration: zod
        .number()
        .min(surveysPartialUpdateBodyCurrentIterationMin)
        .max(surveysPartialUpdateBodyCurrentIterationMax)
        .nullish(),
    current_iteration_start_date: zod.iso.datetime({}).nullish(),
    response_sampling_start_date: zod.iso.datetime({}).nullish(),
    response_sampling_interval_type: zod
        .union([
            zod.enum(['day', 'week', 'month']).describe('* `day` - day\n* `week` - week\n* `month` - month'),
            zod.enum(['']),
            zod.literal(null),
        ])
        .nullish(),
    response_sampling_interval: zod
        .number()
        .min(surveysPartialUpdateBodyResponseSamplingIntervalMin)
        .max(surveysPartialUpdateBodyResponseSamplingIntervalMax)
        .nullish(),
    response_sampling_limit: zod
        .number()
        .min(surveysPartialUpdateBodyResponseSamplingLimitMin)
        .max(surveysPartialUpdateBodyResponseSamplingLimitMax)
        .nullish(),
    response_sampling_daily_limits: zod.unknown().nullish(),
    enable_partial_responses: zod.boolean().nullish(),
    enable_iframe_embedding: zod.boolean().nullish(),
    _create_in_folder: zod.string().optional(),
})

export const SurveysDestroyParams = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this survey.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

/**
 * Get survey response statistics for a specific survey.

Args:
    date_from: Optional ISO timestamp for start date (e.g. 2024-01-01T00:00:00Z)
    date_to: Optional ISO timestamp for end date (e.g. 2024-01-31T23:59:59Z)
    exclude_archived: Optional boolean to exclude archived responses (default: false, includes archived)

Returns:
    Survey statistics including event counts, unique respondents, and conversion rates
 */
export const SurveysStatsRetrieve2Params = /* @__PURE__ */ zod.object({
    id: zod.string().describe('A UUID string identifying this survey.'),
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})

/**
 * Get aggregated response statistics across all surveys.

Args:
    date_from: Optional ISO timestamp for start date (e.g. 2024-01-01T00:00:00Z)
    date_to: Optional ISO timestamp for end date (e.g. 2024-01-31T23:59:59Z)

Returns:
    Aggregated statistics across all surveys including total counts and rates
 */
export const SurveysStatsRetrieveParams = /* @__PURE__ */ zod.object({
    project_id: zod
        .string()
        .describe(
            "Project ID of the project you're trying to access. To find the ID of the project, make a call to /api/projects/."
        ),
})
