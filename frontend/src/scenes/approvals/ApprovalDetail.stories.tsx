import type { Meta, StoryObj } from '@storybook/react'

import { mswDecorator } from '~/mocks/browser'
import organizationCurrent from '~/mocks/fixtures/api/organizations/@current/@current.json'
import { ApprovalDecision, ChangeRequestState, ValidationStatus } from '~/types'

import { scene } from './ApprovalDetail'
import { ApprovalLogicProps } from './approvalLogic'

const ApprovalDetailComponent = scene.component

const mockUser = {
    id: 1,
    uuid: 'user-abc-123',
    first_name: 'Jane',
    last_name: 'Doe',
    email: 'jane@example.com',
}

const baseMockChangeRequest = {
    id: 'cr-001',
    action_key: 'feature_flag.update',
    action_version: 1,
    resource_type: 'FeatureFlag',
    resource_id: '42',
    intent: {
        full_request_data: { key: 'my-feature-flag', active: true },
    },
    intent_display: {
        description: 'Toggle feature flag active state',
        before: { active: false, rollout_percentage: 100 },
        after: { active: true, rollout_percentage: 100 },
    },
    policy_snapshot: {
        quorum: 1,
        users: [],
        roles: [],
        allow_self_approve: false,
    },
    validation_status: ValidationStatus.Valid,
    validation_errors: null,
    validated_at: '2024-01-15T10:00:00Z',
    created_by: mockUser,
    applied_by: null,
    created_at: '2024-01-15T10:00:00Z',
    updated_at: '2024-01-15T10:00:00Z',
    expires_at: '2024-01-22T10:00:00Z',
    applied_at: null,
    apply_error: '',
    result_data: null,
    approvals: [],
    can_approve: true,
    can_cancel: true,
    is_requester: false,
    user_decision: null,
}

const userWithApprovalsFeature = {
    email: 'test@posthog.com',
    first_name: 'Test',
    organization: {
        ...organizationCurrent,
        available_product_features: [{ key: 'approvals', name: 'Approvals' }],
    },
}

type Story = StoryObj<ApprovalLogicProps>
const meta: Meta<ApprovalLogicProps> = {
    title: 'Scenes/Approvals/ApprovalDetail',
    component: ApprovalDetailComponent,
    parameters: {
        layout: 'fullscreen',
        viewMode: 'story',
        mockDate: '2024-01-15',
    },
    decorators: [
        mswDecorator({
            get: {
                '/api/users/@me': () => [200, userWithApprovalsFeature],
                '/api/organizations/@current/members/': () => [200, { results: [], count: 0 }],
                '/api/organizations/@current/roles/': () => [200, { results: [], count: 0 }],
            },
        }),
    ],
}

export default meta

export const Pending: Story = {
    args: { id: 'cr-pending' },
    decorators: [
        mswDecorator({
            get: {
                '/api/environments/:team_id/change_requests/:id/': () => [
                    200,
                    { ...baseMockChangeRequest, id: 'cr-pending', state: ChangeRequestState.Pending },
                ],
            },
        }),
    ],
}

export const WithApprovals: Story = {
    args: { id: 'cr-approved' },
    decorators: [
        mswDecorator({
            get: {
                '/api/environments/:team_id/change_requests/:id/': () => [
                    200,
                    {
                        ...baseMockChangeRequest,
                        id: 'cr-approved',
                        state: ChangeRequestState.Approved,
                        can_approve: false,
                        approvals: [
                            {
                                id: 'approval-1',
                                created_by: { ...mockUser, first_name: 'Alice', email: 'alice@example.com' },
                                decision: ApprovalDecision.Approved,
                                reason: 'Looks good to me',
                                created_at: '2024-01-15T11:00:00Z',
                            },
                        ],
                    },
                ],
            },
        }),
    ],
}

export const Applied: Story = {
    args: { id: 'cr-applied' },
    decorators: [
        mswDecorator({
            get: {
                '/api/environments/:team_id/change_requests/:id/': () => [
                    200,
                    {
                        ...baseMockChangeRequest,
                        id: 'cr-applied',
                        state: ChangeRequestState.Applied,
                        can_approve: false,
                        can_cancel: false,
                        applied_by: mockUser,
                        applied_at: '2024-01-15T12:00:00Z',
                        result_data: { success: true, flag_id: 42 },
                    },
                ],
            },
        }),
    ],
}

export const Rejected: Story = {
    args: { id: 'cr-rejected' },
    decorators: [
        mswDecorator({
            get: {
                '/api/environments/:team_id/change_requests/:id/': () => [
                    200,
                    {
                        ...baseMockChangeRequest,
                        id: 'cr-rejected',
                        state: ChangeRequestState.Rejected,
                        can_approve: false,
                        can_cancel: false,
                        approvals: [
                            {
                                id: 'approval-2',
                                created_by: { ...mockUser, first_name: 'Bob', email: 'bob@example.com' },
                                decision: ApprovalDecision.Rejected,
                                reason: 'Not ready yet, needs more testing',
                                created_at: '2024-01-15T11:30:00Z',
                            },
                        ],
                    },
                ],
            },
        }),
    ],
}
