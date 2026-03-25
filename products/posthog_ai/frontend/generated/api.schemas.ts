/**
 * Auto-generated from the Django backend OpenAPI schema.
 * To modify these types, update the Django serializers or views, then run:
 *   hogli build:openapi
 * Questions or issues? #team-devex on Slack
 *
 * PostHog API - generated
 * OpenAPI spec version: 1.0.0
 */
/**
 * * `engineering` - Engineering
 * `data` - Data
 * `product` - Product Management
 * `founder` - Founder
 * `leadership` - Leadership
 * `marketing` - Marketing
 * `sales` - Sales / Success
 * `other` - Other
 */
export type RoleAtOrganizationEnumApi = (typeof RoleAtOrganizationEnumApi)[keyof typeof RoleAtOrganizationEnumApi]

export const RoleAtOrganizationEnumApi = {
    Engineering: 'engineering',
    Data: 'data',
    Product: 'product',
    Founder: 'founder',
    Leadership: 'leadership',
    Marketing: 'marketing',
    Sales: 'sales',
    Other: 'other',
} as const

export type BlankEnumApi = (typeof BlankEnumApi)[keyof typeof BlankEnumApi]

export const BlankEnumApi = {
    '': '',
} as const

export type NullEnumApi = (typeof NullEnumApi)[keyof typeof NullEnumApi]

export const NullEnumApi = {} as const

/**
 * @nullable
 */
export type UserBasicApiHedgehogConfig = { [key: string]: unknown } | null | null

export interface UserBasicApi {
    readonly id: number
    readonly uuid: string
    /**
     * @maxLength 200
     * @nullable
     */
    distinct_id?: string | null
    /** @maxLength 150 */
    first_name?: string
    /** @maxLength 150 */
    last_name?: string
    /** @maxLength 254 */
    email: string
    /** @nullable */
    is_email_verified?: boolean | null
    /** @nullable */
    readonly hedgehog_config: UserBasicApiHedgehogConfig
    role_at_organization?: RoleAtOrganizationEnumApi | BlankEnumApi | NullEnumApi | null
}

export interface ActionPredictionModelRunApi {
    readonly id: string
    prediction_model: string
    /** Whether this run produced a winning prediction model. */
    is_winning?: boolean
    /**
     * S3 URL to the serialized model artifact.
     * @maxLength 2000
     */
    model_url: string
    /** Model evaluation metrics (e.g. accuracy, AUC, F1). */
    metrics?: unknown
    /** Feature importance scores from model training. */
    feature_importance?: unknown
    /** The Python script used to train and produce the model artifact. */
    artifact_script?: string
    /** User who created this run. */
    readonly created_by: UserBasicApi | null
    readonly created_at: string
    /** @nullable */
    readonly updated_at: string | null
}

export interface PaginatedActionPredictionModelRunListApi {
    count: number
    /** @nullable */
    next?: string | null
    /** @nullable */
    previous?: string | null
    results: ActionPredictionModelRunApi[]
}

export interface ActionPredictionModelApi {
    readonly id: string
    /**
     * Human-readable name for the prediction model.
     * @maxLength 400
     */
    name?: string
    /** Longer description of the prediction model's purpose. */
    description?: string
    /**
     * ID of the PostHog action to predict. Mutually exclusive with event_name.
     * @nullable
     */
    action?: number | null
    /**
     * Name of the raw event to predict. Mutually exclusive with action.
     * @maxLength 400
     * @nullable
     */
    event_name?: string | null
    /**
     * Number of days to look back for prediction data.
     * @minimum 1
     */
    lookback_days: number
    readonly created_by: UserBasicApi
    readonly created_at: string
    /** @nullable */
    readonly updated_at: string | null
}

export interface PaginatedActionPredictionModelListApi {
    count: number
    /** @nullable */
    next?: string | null
    /** @nullable */
    previous?: string | null
    results: ActionPredictionModelApi[]
}

export type ActionPredictionModelRunsListParams = {
    /**
     * Number of results to return per page.
     */
    limit?: number
    /**
     * The initial index from which to return the results.
     */
    offset?: number
}

export type ActionPredictionModelsListParams = {
    /**
     * Number of results to return per page.
     */
    limit?: number
    /**
     * The initial index from which to return the results.
     */
    offset?: number
}
